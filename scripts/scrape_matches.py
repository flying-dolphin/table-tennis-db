#!/usr/bin/env python3
"""
ITTF players-matches-per-event scraper (safer v2)

Design goals:
- Manual login + persisted storage state (no hardcoded credentials)
- Slow, single-threaded, human-paced navigation
- Circuit-breaker when risk-control pages appear (captcha/403/429/access denied)
- Resume from checkpoint
- Fetch years 2024-2026 by default
- Prefer structured extraction from detail tables and keep raw JSON responses for audit
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import platform
import random
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from lib.anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep, move_mouse_to_locator, type_like_human
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.browser_session import ensure_logged_in
from lib.capture import sanitize_filename, save_json
from lib.checkpoint import CheckpointStore, utc_now_iso
from lib.navigation_runtime import verify_cdp_session_or_prompt
from lib.page_ops import click_next_page_if_any, guarded_goto


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_scraper_v2")


BASE_URL = "https://results.ittf.link"
SEARCH_URL = f"{BASE_URL}/index.php/matches/players-matches-per-event"
DEFAULT_FROM_DATE = "2024-01-01"

SCORE_RE = re.compile(r"(\d+)\s*-\s*(\d+)")
GAME_RE = re.compile(r"(\d+):(\d+)")
# 球员名字格式: "Name (COUNTRY)", "Name Surname (COUNTRY)", 或 "UPPER Surname (COUNTRY)"
PLAYER_NAME_RE = re.compile(r"([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)+)\s*\(([A-Z]{3})\)")


def _ck_player_base(checkpoint: CheckpointStore, player_id: Any, player_name: str, from_date_str: str) -> str:
    # Prefix to avoid collisions with other uses of CheckpointStore.
    return "matches|" + checkpoint.key(player_id, player_name, from_date_str)


def _ck_event(ck_player: str, event_year: Any, event_name: str) -> str:
    raw = f"{event_year}|{event_name}"
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{ck_player}|event:{h}"

# UA 与 sec-ch-ua 版本绑定为配对结构，避免版本不一致被检测
# 按 OS 分组，运行时按实际系统选取，确保 UA / platform / DPR 三者自洽
BROWSER_PROFILES_WINDOWS = [
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"Windows"',
        "viewport_choices": [
            {"width": 1280, "height": 768},
            {"width": 1366, "height": 900},
            {"width": 1440, "height": 900},
            {"width": 1920, "height": 1080},
        ],
        "dpr_choices": [1.0, 1.25, 1.5],
    },
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"Windows"',
        "viewport_choices": [
            {"width": 1280, "height": 768},
            {"width": 1366, "height": 900},
            {"width": 1440, "height": 900},
            {"width": 1920, "height": 1080},
        ],
        "dpr_choices": [1.0, 1.25, 1.5],
    },
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="122", "Google Chrome";v="122", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"Windows"',
        "viewport_choices": [
            {"width": 1280, "height": 768},
            {"width": 1366, "height": 900},
            {"width": 1440, "height": 900},
            {"width": 1920, "height": 1080},
        ],
        "dpr_choices": [1.0, 1.25, 1.5],
    },
]

# macOS：Retina DPR=2.0，viewport 使用逻辑像素（非物理像素）
BROWSER_PROFILES_MACOS = [
    {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"macOS"',
        "viewport_choices": [
            {"width": 1280, "height": 800},
            {"width": 1440, "height": 900},
            {"width": 1512, "height": 982},
        ],
        "dpr_choices": [2.0],
    },
    {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"macOS"',
        "viewport_choices": [
            {"width": 1280, "height": 800},
            {"width": 1440, "height": 900},
            {"width": 1512, "height": 982},
        ],
        "dpr_choices": [2.0],
    },
    {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="122", "Google Chrome";v="122", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"macOS"',
        "viewport_choices": [
            {"width": 1280, "height": 800},
            {"width": 1440, "height": 900},
            {"width": 1512, "height": 982},
        ],
        "dpr_choices": [2.0],
    },
]


def select_browser_profiles() -> list[dict[str, Any]]:
    """根据当前运行 OS 返回对应的浏览器配置列表"""
    system = platform.system()
    if system == "Darwin":
        logger.info("OS detected: macOS — using macOS browser profiles")
        return BROWSER_PROFILES_MACOS
    logger.info("OS detected: %s — using Windows browser profiles", system)
    return BROWSER_PROFILES_WINDOWS




def latest_rankings_file(rankings_dir: Path) -> Path:
    candidates = sorted(
        rankings_dir.glob("women_singles_top100_*.json"),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No ranking files found in {rankings_dir} matching women_singles_top100_*.json"
        )
    return candidates[0]


def parse_top_spec(raw: str) -> slice:
    raw = str(raw).strip()
    if not raw:
        raise ValueError("top spec cannot be empty")

    if "-" in raw:
        parts = raw.split("-", 1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            raise ValueError(f"Invalid --top-n value '{raw}', expected N or START-END")
        start = int(parts[0].strip())
        end = int(parts[1].strip())
        if start < 1 or end < 1:
            raise ValueError(f"Invalid --top-n value '{raw}', ranks must be >= 1")
        if end < start:
            raise ValueError(f"Invalid --top-n value '{raw}', END must be >= START")
        return slice(start - 1, end)

    top_n = int(raw)
    if top_n < 1:
        raise ValueError(f"Invalid --top-n value '{raw}', must be >= 1")
    return slice(0, top_n)


def load_players(players_file: Path, top_spec: str) -> list[dict[str, Any]]:
    if players_file.is_dir():
        players_file = latest_rankings_file(players_file)

    if not players_file.exists():
        raise FileNotFoundError(f"players file not found: {players_file}")

    data = json.loads(players_file.read_text(encoding="utf-8"))
    rankings = data.get("rankings", [])
    player_slice = parse_top_spec(top_spec)
    return rankings[player_slice]


def _player_name_from_entry(player: dict[str, Any]) -> str:
    for key in ("english_name", "player_name", "name"):
        value = (player.get(key) or "").strip()
        if value:
            return value
    return ""


def parse_from_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise ValueError(f"Invalid --from-date format '{raw}', expected YYYY-MM-DD")


def _query_selector_all_with_retry(root: Any, selector: str, retries: int = 3, delay_sec: float = 0.4) -> list[Any]:
    """Query selector with a small retry window for transient DOM churn."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            nodes = root.query_selector_all(selector)
            return nodes or []
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(delay_sec * (attempt + 1))
    if last_exc:
        raise last_exc
    return []


def _wait_for_result_area(page: Any, timeout_sec: float = 20.0) -> bool:
    """Wait until the result page is stable enough to parse."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            body_lower = (page.inner_text("body") or "").lower()
        except Exception:
            body_lower = ""

        if "total: 0" in body_lower or "no records" in body_lower:
            return True

        try:
            if _query_selector_all_with_retry(page, "table", retries=1):
                return True
        except Exception:
            pass

        time.sleep(0.5)
    return False




def parse_event_rows(page: Any) -> list[dict[str, Any]]:
    tables = _query_selector_all_with_retry(page, "table", retries=4)
    events: list[dict[str, Any]] = []
    rows_total = 0
    rows_no_href = 0

    for table in tables:
        rows = _query_selector_all_with_retry(table, "tbody tr", retries=2)
        if not rows:
            rows = _query_selector_all_with_retry(table, "tr", retries=2)
        for row in rows:
            cells = _query_selector_all_with_retry(row, "td", retries=2)
            if len(cells) < 2:
                continue

            first_text = (cells[0].inner_text() or "").strip()
            if not first_text.isdigit():
                continue

            rows_total += 1
            link = cells[0].query_selector("a")
            href = link.get_attribute("href") if link else None
            if not href:
                rows_no_href += 1
                cell_texts = [((c.inner_text() or "").strip()) for c in cells]
                logger.debug(
                    "Row skipped (no href): match_count=%s event=%s",
                    first_text, cell_texts[1] if len(cell_texts) > 1 else "",
                )
                continue

            cell_texts = [((c.inner_text() or "").strip()) for c in cells]
            event_name = cell_texts[1] if len(cell_texts) > 1 else ""
            event_type = cell_texts[2] if len(cell_texts) > 2 else ""
            event_year = cell_texts[3] if len(cell_texts) > 3 else ""
            start_date = cell_texts[4].strip() if len(cell_texts) > 4 else ""
            end_date = cell_texts[5].strip() if len(cell_texts) > 5 else ""

            events.append(
                {
                    "match_count": int(first_text),
                    "event_name": event_name,
                    "event_type": event_type,
                    "year": event_year,
                    "start_date": start_date,
                    "end_date": end_date,
                    "href": href,
                }
            )

    if rows_no_href > 0:
        logger.info(
            "parse_event_rows: %s data rows found, %s skipped (no href), %s kept",
            rows_total, rows_no_href, rows_total - rows_no_href,
        )
    return dedupe_events(events)


def dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, int]] = set()
    out: list[dict[str, Any]] = []
    for e in events:
        key = (e.get("event_name", ""), e.get("href", ""), int(e.get("match_count", 0)))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out




def _event_sort_date(event: dict[str, Any]) -> date | None:
    """尽量从 event 字段解析日期，失败时回退到 year=YYYY-12-31。"""
    # 优先使用页面抓取的 start_date 字段（格式 YYYY-MM-DD）
    start = str(event.get("start_date", "") or "").strip()
    if start:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                from datetime import datetime
                return datetime.strptime(start, fmt).date()
            except Exception:
                pass

    texts = [
        str(event.get("event_name", "") or ""),
        str(event.get("event_type", "") or ""),
        str(event.get("year", "") or ""),
    ]
    joined = " ".join(texts)

    # YYYY-MM-DD / YYYY/MM/DD
    m = re.search(r"\b(20\d{2}|19\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", joined)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass

    # DD-MM-YYYY / DD/MM/YYYY
    m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2}|19\d{2})\b", joined)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except Exception:
            pass

    try:
        y = int(str(event.get("year", "") or "0"))
        if y > 0:
            return date(y, 12, 31)
    except Exception:
        pass
    return None


def collect_events_with_pagination(
    page: Any, from_date: date, max_pages: int = 50
) -> list[dict[str, Any]]:
    """遍历 event 分页，收集所有 >= from_date 的赛事。

    注意：网站事件列表并非严格按日期降序排列，同一页内可能混有旧事件。
    因此不能在遇到单个旧事件时立即停止分页——只过滤该条事件，继续翻页。
    仅当整页事件全部早于 from_date 时才停止（此时后续页面也不太可能有新事件）。
    """
    all_events: list[dict[str, Any]] = []
    visited_snapshots: set[str] = set()

    for page_num in range(max_pages):
        events = parse_event_rows(page)
        logger.info(
            "Page %s: parse_event_rows returned %s events (href-bearing rows only)",
            page_num + 1, len(events),
        )
        if not events:
            break

        events_on_page = 0
        old_events_on_page = 0
        for event in events:
            event_date = _event_sort_date(event)
            events_on_page += 1
            if event_date and event_date < from_date:
                old_events_on_page += 1
                logger.debug(
                    "Skip old event date=%s < from_date=%s on page %s: %s",
                    event_date.isoformat(), from_date.isoformat(), page_num + 1,
                    event.get("event_name", ""),
                )
                continue
            all_events.append(event)

        # 整页都是旧事件，后续页面也不会有新事件，安全停止
        if events_on_page > 0 and old_events_on_page == events_on_page:
            logger.info(
                "All %s events on page %s are before from_date=%s, stopping pagination",
                events_on_page, page_num + 1, from_date.isoformat(),
            )
            break

        snapshot = "|".join(sorted(e.get("href", "") for e in events)[:50])
        if snapshot in visited_snapshots:
            break
        visited_snapshots.add(snapshot)

        if not click_next_page_if_any(page):
            break

    return dedupe_events(all_events)


def _normalize_column_name(text: str) -> str:
    text = " ".join((text or "").split()).strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _build_column_map(table: Any) -> dict[str, int]:
    header_rows = _query_selector_all_with_retry(table, "thead tr", retries=2)
    if not header_rows:
        header_rows = _query_selector_all_with_retry(table, "tr", retries=2)

    for row in header_rows:
        header_cells = _query_selector_all_with_retry(row, "th", retries=2)
        if not header_cells:
            continue
        column_map: dict[str, int] = {}
        for idx, cell in enumerate(header_cells):
            header_text = " ".join((cell.inner_text() or "").split())
            normalized = _normalize_column_name(header_text)
            if normalized and normalized not in column_map:
                column_map[normalized] = idx
        if column_map:
            return column_map
    return {}


def parse_match_from_row(
    cells: list[Any],
    player_name: str,
    column_map: dict[str, int] | None = None,
) -> dict[str, Any] | None:
    cell_texts = [" ".join((c.inner_text() or "").split()) for c in cells]
    # Keep empty cells so gaps in the source table remain visible in debug output.
    row_text = " | ".join(cell_texts)

    def cell_text(index: int) -> str:
        if 0 <= index < len(cells):
            return " ".join((cells[index].inner_text() or "").split())
        return ""

    def column_text(*aliases: str, fallback_index: int | None = None) -> str:
        if column_map:
            for alias in aliases:
                idx = column_map.get(_normalize_column_name(alias))
                if idx is not None:
                    text = cell_text(idx)
                    if text:
                        return text
        if fallback_index is not None:
            return cell_text(fallback_index)
        return ""

    def normalize_score(text: str) -> str:
        m = SCORE_RE.search(text or "")
        if not m:
            return ""
        return f"{m.group(1)}-{m.group(2)}"

    player_a_text = column_text("Player A", fallback_index=2)
    player_b_text = column_text("Player B", fallback_index=3)
    player_x_text = column_text("Player X", fallback_index=4)
    player_y_text = column_text("Player Y", fallback_index=5)
    sub_event_text = column_text("Sub-event", "Sub event", fallback_index=6)
    stage_text = column_text("Stage", fallback_index=7)
    round_text = column_text("Round", fallback_index=8)
    result_text = column_text("Result", fallback_index=9)
    games_text = column_text("Games", fallback_index=10)
    winner_text = column_text("Winner", fallback_index=11)

    score_idx = -1
    match_score = ""
    score_a = score_b = None
    normalized_result = normalize_score(result_text)
    if normalized_result:
        match_score = normalized_result
        score_idx = column_map.get(_normalize_column_name("Result"), 9) if column_map else 9
        score_a = int(normalized_result.split("-", 1)[0])
        score_b = int(normalized_result.split("-", 1)[1])

    raw_games = GAME_RE.findall(games_text or row_text)
    game_scores = [f"{a}:{b}" for a, b in raw_games]
    game_objects = [{"player": int(a), "opponent": int(b)} for a, b in raw_games]

    if not match_score:
        for idx, text in enumerate(cell_texts):
            m = SCORE_RE.search(text)
            if m:
                score_idx = idx
                match_score = f"{m.group(1)}-{m.group(2)}"
                score_a = int(m.group(1))
                score_b = int(m.group(2))
                break

    if score_idx == -1 and not game_scores:
        return None

    # 从所有 cell 文本中提取球员名字（格式: "Name (COUNTRY)"）
    all_players_found: list[tuple[str, str]] = []  # (full_match, country_code)
    for text in cell_texts:
        for m in PLAYER_NAME_RE.finditer(text):
            all_players_found.append((m.group(0), m.group(2)))

    # 去重并保持顺序
    seen_names: set[str] = set()
    unique_players: list[str] = []
    for full_name, _ in all_players_found:
        if full_name not in seen_names:
            seen_names.add(full_name)
            unique_players.append(full_name)

    # 优先使用表头列中的球员名来构建 side_a / side_b
    explicit_players = [p for p in [player_a_text, player_x_text] if p]
    explicit_opponents = [p for p in [player_b_text, player_y_text] if p]

    side_a: list[str] = []
    side_b: list[str] = []
    if explicit_players or explicit_opponents:
        side_a = explicit_players
        side_b = explicit_opponents
    elif score_idx >= 0 and unique_players:
        # 简单策略：前一半是 side_a，后一半是 side_b
        mid = len(unique_players) // 2
        side_a = unique_players[:mid] if mid > 0 else unique_players[:1]
        side_b = unique_players[mid:] if mid > 0 else unique_players[1:]
    elif unique_players:
        side_a = unique_players[:1]
        side_b = unique_players[1:] if len(unique_players) > 1 else []

    # 同时保留 anchor 提取的名字作为备用（如果上面的方法失败）
    anchor_names_by_cell: list[list[str]] = []
    for c in cells:
        names = [" ".join((a.inner_text() or "").split()) for a in _query_selector_all_with_retry(c, "a", retries=2)]
        names = [n for n in names if n]
        anchor_names_by_cell.append(names)

    all_names: list[str] = []
    for names in anchor_names_by_cell:
        for n in names:
            if n not in all_names:
                all_names.append(n)

    if not side_a and not side_b and all_names:
        mid = len(all_names) // 2
        side_a = all_names[:mid] if mid > 0 else all_names[:1]
        side_b = all_names[mid:] if mid > 0 else all_names[1:]

    winner = winner_text
    if not winner:
        winner_m = re.search(r"Winner:\s*([^|]+)", row_text, flags=re.IGNORECASE)
        if winner_m:
            winner = winner_m.group(1).strip()

    sub_event = sub_event_text
    if not sub_event:
        for token in ["WS", "MS", "WD", "MD", "XD", "U19", "U17", "U15"]:
            if re.search(rf"\b{re.escape(token)}\b", row_text):
                sub_event = token
                break

    stage = stage_text
    if not stage:
        for s in ["Main Draw", "Qualification", "Qualifying", "Group", "Final"]:
            if s.lower() in row_text.lower():
                stage = s
                break

    if not round_text:
        round_m = re.search(
            r"\b(R\d{1,2}|QF|SF|F|QuarterFinal|SemiFinal|Final|R32|R64|R128|Round of \d+)\b",
            row_text,
            flags=re.IGNORECASE,
        )
        if round_m:
            round_text = round_m.group(1)

    perspective = "unknown"
    opponents: list[str] = []
    teammates: list[str] = []
    result_for_player = "unknown"

    if side_a or side_b:
        in_a = any(player_name.lower() == n.lower() for n in side_a)
        in_b = any(player_name.lower() == n.lower() for n in side_b)

        if in_a:
            perspective = "side_a"
            opponents = side_b
            teammates = [n for n in side_a if n.lower() != player_name.lower()]
            if score_a is not None and score_b is not None:
                result_for_player = "win" if score_a > score_b else "loss"
        elif in_b:
            perspective = "side_b"
            opponents = side_a
            teammates = [n for n in side_b if n.lower() != player_name.lower()]
            if score_a is not None and score_b is not None:
                result_for_player = "win" if score_b > score_a else "loss"

    return {
        "sub_event": sub_event,
        "stage": stage,
        "round": round_text,
        "match_score": match_score,
        "games": game_objects,
        "games_display": game_scores,
        "winner": winner,
        "all_players_in_row": unique_players if unique_players else all_names,
        "side_a": side_a,
        "side_b": side_b,
        "teammates": teammates,
        "opponents": opponents,
        "result_for_player": result_for_player,
        "result": result_for_player,
        "perspective": perspective,
        "raw_row_text": row_text,
    }


def parse_detail_matches_from_dom(page: Any, player_name: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()

    tables = _query_selector_all_with_retry(page, "table", retries=4)
    for table in tables:
        column_map = _build_column_map(table)
        rows = _query_selector_all_with_retry(table, "tbody tr", retries=2)
        if not rows:
            rows = _query_selector_all_with_retry(table, "tr", retries=2)
        for row in rows:
            cells = _query_selector_all_with_retry(row, "td", retries=2)
            if len(cells) < 2:
                continue
            parsed = parse_match_from_row(cells, player_name, column_map=column_map)
            if not parsed:
                continue
            key = "||".join(
                [
                    parsed.get("match_score", ""),
                    ",".join(parsed.get("side_a", [])),
                    ",".join(parsed.get("side_b", [])),
                    parsed.get("round", ""),
                    parsed.get("raw_row_text", "")[:160],
                ]
            )
            if key in seen:
                continue
            seen.add(key)
            matches.append(parsed)

    return matches


def absolute_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return f"{BASE_URL}/{href.lstrip('/')}"


def open_or_select_autocomplete(page: Any, player_name: str, country_code: str) -> bool:
    search_key = f"{player_name} ({country_code})" if country_code else player_name

    logger.info("[autocomplete] start player=%s country=%s search_key=%s", player_name, country_code or "", search_key)

    search_input = page.locator("input[type='text']").first
    input_count = search_input.count()
    logger.info("[autocomplete] text inputs found, using first locator count=%s", input_count)
    if input_count == 0:
        logger.warning("[autocomplete] no text input found")
        return False

    def wait_and_click_option(target_text: str, fallback_text: str) -> bool:
        target_lower = target_text.lower()
        fallback_lower = fallback_text.lower()
        name_lower = player_name.lower()
        country_lower = country_code.lower().strip()

        def _normalize_words(text: str) -> list[str]:
            return [part for part in re.split(r"[^a-z0-9]+", (text or "").lower()) if part]

        player_words = sorted(_normalize_words(player_name))

        def selection_matches_value(value: str) -> bool:
            normalized = " ".join((value or "").split()).lower()
            if not normalized:
                return False
            if target_lower and target_lower in normalized:
                return True
            if fallback_lower and fallback_lower in normalized:
                return True
            if name_lower and name_lower in normalized:
                return True

            candidate_name = normalized
            if "(" in candidate_name:
                candidate_name = candidate_name.split("(", 1)[0].strip()
            candidate_words = sorted(_normalize_words(candidate_name))
            if player_words and candidate_words and player_words == candidate_words:
                if not country_lower:
                    return True
                country_match = re.search(r"\(([a-z]{3})\)", normalized)
                return bool(country_match and country_match.group(1) == country_lower)
            return False

        def candidate_score(text: str) -> int:
            normalized = " ".join(text.split()).lower()
            if not normalized:
                return -1

            score = 0
            if selection_matches_value(text):
                score += 100

            candidate_name = normalized
            if "(" in candidate_name:
                candidate_name = candidate_name.split("(", 1)[0].strip()
            candidate_words = sorted(_normalize_words(candidate_name))

            if player_words and candidate_words:
                if player_words == candidate_words:
                    score += 80
                else:
                    overlap = len(set(player_words) & set(candidate_words))
                    score += overlap * 10

            country_match = re.search(r"\(([a-z]{3})\)", normalized)
            if country_lower and country_match:
                if country_match.group(1) == country_lower:
                    score += 30
                else:
                    score -= 20

            if target_lower and target_lower == normalized:
                score += 50
            if fallback_lower and fallback_lower == candidate_name:
                score += 40

            return score

        def click_best_effort(loc: Any) -> None:
            try:
                loc.click(timeout=1500)
                return
            except Exception as exc:
                logger.warning("[autocomplete] click failed: %s", exc)
            try:
                loc.click(force=True, timeout=1500)
                logger.info("[autocomplete] force click ok")
                return
            except Exception as exc:
                logger.warning("[autocomplete] force click failed: %s", exc)
            try:
                loc.evaluate(
                    """(el) => {
                        const options = { bubbles: true, cancelable: true, view: window };
                        el.dispatchEvent(new MouseEvent('mousedown', options));
                        el.dispatchEvent(new MouseEvent('mouseup', options));
                        el.dispatchEvent(new MouseEvent('click', options));
                    }"""
                )
                logger.info("[autocomplete] dom click dispatched")
                return
            except Exception as exc:
                logger.warning("[autocomplete] dom click failed: %s", exc)
            move_mouse_to_locator(page, loc)
            logger.info("[autocomplete] mouse click ok")

        for attempt in range(12):
            exact = page.get_by_text(target_text, exact=True).first
            try:
                exact_count = exact.count()
            except Exception:
                exact_count = 0
            logger.info("[autocomplete] attempt=%s exact_count=%s target=%s", attempt + 1, exact_count, target_text)
            try:
                if exact_count > 0 and exact.is_visible():
                    logger.info("[autocomplete] exact option visible, trying click: %s", target_text)
                    click_best_effort(exact)
                    return True
            except Exception as exc:
                logger.info("[autocomplete] exact option probe failed: %s", exc)

            autocomplete_root = page.locator(
                "ul.dropdown-menu[role='menu']:visible, ul.ui-autocomplete:visible, ul[id*='ui-id']:visible, .ui-autocomplete:visible, [role='listbox']:visible"
            ).first
            root_count = 0
            try:
                root_count = autocomplete_root.count()
            except Exception:
                root_count = 0

            if root_count > 0:
                candidates = autocomplete_root.locator("li > a[data-value]")
                logger.info("[autocomplete] using scoped autocomplete container")
            else:
                candidates = page.locator("ul.dropdown-menu[role='menu'] li > a[data-value]")
                logger.info("[autocomplete] autocomplete container not found, using a[data-value] fallback selectors")

            try:
                count = min(candidates.count(), 20)
            except Exception:
                count = 0
            logger.info("[autocomplete] attempt=%s candidate_count=%s", attempt + 1, count)

            best_candidate: tuple[int, int, Any, str] | None = None
            for i in range(count):
                item = candidates.nth(i)
                try:
                    if not item.is_visible():
                        continue
                    txt = " ".join((item.inner_text() or "").split())
                    data_value = item.get_attribute("data-value") if item.count() > 0 else None
                    if not txt:
                        continue
                    score = candidate_score(txt)
                    logger.info("[autocomplete] candidate[%s]=%s data-value=%s score=%s", i, txt[:120], data_value, score)
                    if score > 0 and (best_candidate is None or score > best_candidate[0]):
                        best_candidate = (score, i, item, txt)
                except Exception as exc:
                    logger.info("[autocomplete] candidate[%s] probe failed: %s", i, exc)
                    continue

            if best_candidate is not None:
                score, best_idx, best_item, best_text = best_candidate
                logger.info("[autocomplete] best candidate[%s]=%s score=%s, trying click", best_idx, best_text[:120], score)
                before_value = None
                try:
                    before_value = search_input.input_value()
                except Exception:
                    pass
                click_best_effort(best_item)

                time.sleep(0.4)
                try:
                    after_value = search_input.input_value()
                except Exception:
                    after_value = None
                logger.info("[autocomplete] input before click=%s after click=%s", before_value, after_value)
                if selection_matches_value(after_value or ""):
                    return True
                time.sleep(0.4)
                try:
                    settled_value = search_input.input_value()
                except Exception:
                    settled_value = None
                if selection_matches_value(settled_value or ""):
                    return True
                logger.info("[autocomplete] selection did not settle, retrying")

            time.sleep(0.25)
        logger.warning("[autocomplete] no option matched after retries for target=%s fallback=%s", target_text, fallback_text)
        return False

    short_query = player_name[:20]
    logger.info("[autocomplete] typing short query=%s", short_query)
    type_like_human(page, search_input, short_query)
    try:
        logger.info("[autocomplete] input value after short query=%s", search_input.input_value())
    except Exception as exc:
        logger.info("[autocomplete] could not read input after short query: %s", exc)
    time.sleep(random.uniform(0.8, 1.6))
    if wait_and_click_option(search_key, player_name):
        logger.info("[autocomplete] selected by short query: %s", search_key)
        return True

    logger.info("[autocomplete] typing full query=%s", search_key)
    type_like_human(page, search_input, search_key)
    try:
        logger.info("[autocomplete] input value after full query=%s", search_input.input_value())
    except Exception as exc:
        logger.info("[autocomplete] could not read input after full query: %s", exc)
    time.sleep(random.uniform(0.8, 1.8))
    if wait_and_click_option(search_key, player_name):
        logger.info("[autocomplete] selected by full query: %s", search_key)
        return True

    logger.warning("[autocomplete] option not selected: %s", search_key)
    return False


def try_select_year(page: Any, year: int) -> bool:
    selects = _query_selector_all_with_retry(page, "select", retries=2)
    for sel in selects:
        try:
            options = _query_selector_all_with_retry(sel, "option", retries=2)
            vals = [((o.get_attribute("value") or "").strip(), (o.inner_text() or "").strip()) for o in options]
            if any(str(year) == v or str(year) == t for v, t in vals):
                sel.select_option(str(year))
                return True
        except Exception:
            continue
    return False


def click_go(page: Any) -> bool:
    candidates = [
        "button:has-text('Go')",
        "input[type='button'][value='Go'][name='filter']",
        "input[type='button'][value='Go']",
        "input[type='submit'][value='Go']",
        "button[type='submit']",
    ]
    for sel in candidates:
        loc = page.locator(sel).first
        try:
            if loc.count() > 0 and loc.is_visible():
                # P1: 用鼠标轨迹点击，而非直接 loc.click()
                move_mouse_to_locator(page, loc)
                return True
        except Exception:
            continue
    try:
        btn_values = []
        for el in _query_selector_all_with_retry(page, "input[type='button'], input[type='submit'], button", retries=2):
            val = (el.get_attribute("value") or el.inner_text() or "").strip()
            cls = (el.get_attribute("class") or "").strip()
            name = (el.get_attribute("name") or "").strip()
            if val:
                btn_values.append({"value": val, "name": name, "class": cls[:80]})
        logger.warning("Go button candidates on page: %s", btn_values[:20])
    except Exception:
        pass
    return False


def scrape_player(
    page: Any,
    player_name: str,
    country_code: str,
    from_date: date,
    delay_cfg: DelayConfig,
    raw_dir: Path,
    checkpoint: CheckpointStore | None = None,
    ck_player: str | None = None,
    force: bool = False,
    out_file: Path | None = None,
    player_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """获取该球员从 from_date 至今的全部赛事，不依赖年份下拉过滤。"""
    result: dict[str, Any] = {
        "player_name": player_name,
        "country_code": country_code,
        "from_date": from_date.isoformat(),
        "captured_at": utc_now_iso(),
        "events": [],
    }
    guarded_goto(page, SEARCH_URL, delay_cfg, f"open query page for {player_name}")

    if not open_or_select_autocomplete(page, player_name, country_code):
        raise RuntimeError(f"autocomplete not found for {player_name} ({country_code})")

    # 不选年份过滤，直接提交，获取按时间倒序的全量赛事列表
    human_sleep(5.0, 10.0, "before click Go")
    if not click_go(page):
        raise RuntimeError("Go button not found")

    page.wait_for_load_state("domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    if not _wait_for_result_area(page, timeout_sec=20.0):
        raise RuntimeError("Result page did not stabilize after clicking Go")

    risk = detect_risk(page)
    if risk:
        raise RiskControlTriggered(risk)

    body = (page.inner_text("body") or "").lower()
    if "total: 0" in body or "no records" in body:
        return result

    events = collect_events_with_pagination(page, from_date=from_date)
    logger.info("Found %s events on web for %s since %s", len(events), player_name, from_date)

    # 翻页结束后记录事件列表 URL，作为 detail 页面的 Referer
    events_list_url = page.url

    # 直接从 JSON 文件重新加载，计算已有的 events 数量（不依赖传入的 player_output）
    existing_event_count = 0
    existing_event_keys: set[tuple[str, str]] = set()
    if (not force) and out_file is not None and out_file.exists():
        try:
            fresh_data = json.loads(out_file.read_text(encoding="utf-8"))
            logger.debug("Loaded JSON from %s, keys: %s", out_file, list(fresh_data.keys()))
            years_data = fresh_data.get("years", {})
            logger.debug("Years in JSON: %s", list(years_data.keys()))
            for year_str, year_data in years_data.items():
                try:
                    year_int = int(year_str)
                    if year_int > 0 and year_int < from_date.year:
                        logger.debug("Skipping year %s (before %s)", year_str, from_date.year)
                        continue  # 跳过不符合时间要求的年份
                except (ValueError, TypeError):
                    pass
                year_events = year_data.get("events", [])
                logger.debug("Year %s has %s events", year_str, len(year_events))
                for event in year_events:
                    event_year = str(event.get("event_year", ""))
                    try:
                        event_year_int = int(event_year) if event_year else 0
                        if event_year_int > 0 and event_year_int < from_date.year:
                            continue  # 跳过不符合时间要求的 event
                    except (ValueError, TypeError):
                        pass
                    existing_event_count += 1
                    existing_event_keys.add((event_year, event.get("event_name", "")))
        except Exception as exc:
            logger.warning("Failed to load existing data from %s: %s", out_file, exc)
    else:
        logger.debug("No existing JSON file: %s", out_file)

    # Best-effort: keep checkpoint consistent with existing output file (per-event done marks).
    if (not force) and checkpoint is not None and ck_player and existing_event_keys:
        try:
            with checkpoint.bulk():
                for (ey, en) in existing_event_keys:
                    if not en:
                        continue
                    ck = _ck_event(ck_player, ey, en)
                    if not checkpoint.is_done(ck):
                        checkpoint.mark_done(ck, meta={"bootstrapped_from": str(out_file) if out_file else None})
        except Exception:
            pass

    # 判断逻辑：用 key 集合对比（不用数量），避免分页不完整或日期/年份过滤差异导致的误判
    web_event_keys = {(str(e.get("year", "unknown")), e.get("event_name", "")) for e in events}
    missing_keys = web_event_keys - existing_event_keys

    if not missing_keys:
        # 网页上的所有 events 都已在 JSON 中，数据完整
        logger.info(
            "Data complete for %s (%s): all %s web events found in JSON (JSON has %s events)",
            player_name, country_code, len(web_event_keys), existing_event_count,
        )
        # 更新元数据并返回完整的 player_output（不返回 events=[] 的 result）
        if player_output is not None:
            player_output["captured_at"] = utc_now_iso()
            player_output["updated_at"] = utc_now_iso()
            if out_file is not None:
                save_json(out_file, player_output)
        return player_output if player_output is not None else result
    else:
        # 有新增 events 需要抓取
        logger.info(
            "Found %s new events for %s (%s), will capture (web=%s, json=%s)",
            len(missing_keys), player_name, country_code, len(web_event_keys), existing_event_count,
        )

    # 使用从 JSON 文件加载的 keys 作为 already_scraped
    already_scraped = existing_event_keys

    # 计算期望抓取的 events 数量（有 href 且未抓取过的）
    events_with_href = [e for e in events if e.get("href")]
    events_without_href = [e for e in events if not e.get("href")]
    
    # 记录没有 href 的 events 作为 error
    if events_without_href:
        error_msg = f"Events without href for {player_name} ({country_code}):\n"
        for e in events_without_href:
            error_msg += f"  - {e.get('event_name', 'unknown')} ({e.get('year', 'unknown')})\n"
        logger.error(error_msg)
    
    expected_to_capture = sum(1 for e in events_with_href 
                              if (str(e.get("year", "unknown")), e.get("event_name", "")) not in already_scraped)
    logger.info("Expected to capture: %s events (with href, not already scraped)", expected_to_capture)

    for idx, event in enumerate(events, start=1):
        href = event.get("href")
        if not href:
            # 已在上面记录 error，这里跳过
            continue

        event_year = event.get("year", "unknown")
        event_key = (str(event_year), event.get("event_name", ""))
        if (not force) and event_key in already_scraped:
            logger.info("Skip [%s/%s] already scraped: [%s] %s",
                        idx, len(events), event_year, event.get("event_name", ""))
            continue

        # If checkpoint says done but output JSON doesn't include it, we must rescrape.
        ck_event = _ck_event(ck_player, event_year, event.get("event_name", "")) if (checkpoint is not None and ck_player) else None
        if (not force) and ck_event and checkpoint is not None and checkpoint.is_done(ck_event):
            logger.info("Checkpoint done but event missing in output JSON, will rescrape: [%s] %s", event_year, event.get("event_name", ""))

        detail_url = absolute_url(href)
        logger.info("Event %s/%s [%s]: %s", idx, len(events), event_year, detail_url)

        def visit_detail(url: str = detail_url, pos: int = idx) -> None:
            guarded_goto(page, url, delay_cfg, f"visit event detail {pos}/{len(events)}",
                         referer=events_list_url)

        visit_detail()
        matches = parse_detail_matches_from_dom(page, player_name)

        safe_event = sanitize_filename(f"{event_year}_{idx}_{event.get('event_name', 'event')}")
        raw_file = raw_dir / sanitize_filename(player_name) / f"{safe_event}.json"
        save_json(
            raw_file,
            {
                "event_meta": event,
                "detail_url": detail_url,
                "captured_at": utc_now_iso(),
                "parsed_matches": matches,
            },
        )

        result["events"].append({
            "event_name": event.get("event_name", ""),
            "event_type": event.get("event_type", ""),
            "event_year": event_year,
            "match_count": event.get("match_count", 0),
            "detail_url": detail_url,
            "raw_capture_file": str(raw_file),
            "matches": matches,
        })

        # 每获取一个 event 立即写入，防止中断丢失进度
        if out_file is not None and player_output is not None:
            merge_player_data(player_output, result)
            save_json(out_file, player_output)
            logger.debug("Incremental save: %s event(s) written to %s", idx, out_file.name)

        if checkpoint is not None and ck_event:
            checkpoint.mark_done(
                ck_event,
                meta={
                    "event_year": event_year,
                    "event_name": event.get("event_name", ""),
                    "detail_url": detail_url,
                    "raw_capture_file": str(raw_file),
                },
            )

    # 校验：确认 missing_keys 中的 events 都已被抓取
    newly_captured = len(result.get("events", []))
    newly_captured_keys = {
        (str(e.get("event_year", "unknown")), e.get("event_name", ""))
        for e in result.get("events", [])
    }

    still_missing = missing_keys - newly_captured_keys
    if still_missing:
        raise RuntimeError(
            f"Event capture incomplete for {player_name} ({country_code}): "
            f"{len(still_missing)} events still missing after scrape: {still_missing}. "
            f"Expected {len(missing_keys)} new events, captured {newly_captured}."
        )

    if player_output is not None:
        return player_output
    return result


def _scraped_event_keys(player_output: dict[str, Any] | None, from_year: int | None = None) -> set[tuple[str, str]]:
    """提取已抓取的 (event_year, event_name) 组合，用于跳过重复抓取。
    
    Args:
        player_output: 已抓取的数据
        from_year: 如果指定，只返回年份 >= from_year 的 events
    """
    if not player_output:
        return set()
    keys: set[tuple[str, str]] = set()
    for year_str, year_data in player_output.get("years", {}).items():
        # 如果指定了 from_year，跳过不符合年份要求的
        if from_year is not None:
            try:
                event_year = int(year_str)
                if event_year > 0 and event_year < from_year:
                    continue
            except (ValueError, TypeError):
                pass
        for event in year_data.get("events", []):
            event_year = event.get("event_year", "")
            # 再次检查单个 event 的年份
            if from_year is not None:
                try:
                    event_year_int = int(event_year) if event_year else 0
                    if event_year_int > 0 and event_year_int < from_year:
                        continue
                except (ValueError, TypeError):
                    pass
            keys.add((str(event_year), event.get("event_name", "")))
    return keys


def merge_player_data(existing: dict[str, Any], player_data: dict[str, Any]) -> dict[str, Any]:
    """将 scrape_player 的结果增量合并到 existing，不覆盖已存在的 events。"""
    if "years" not in existing:
        existing["years"] = {}

    captured_at = player_data.get("captured_at", utc_now_iso())

    for field in [
        "schema_version",
        "player_id",
        "player_name",
        "english_name",
        "country",
        "country_code",
        "continent",
        "rank",
        "from_date",
    ]:
        value = player_data.get(field)
        if value not in (None, ""):
            existing[field] = value

    # 构建已有 events 的去重 key，避免重复写入
    existing_keys = _scraped_event_keys(existing)

    for event in player_data.get("events", []):
        year_key = str(event.get("event_year", "unknown"))
        key = (year_key, event.get("event_name", ""))
        if key in existing_keys:
            continue
        existing["years"].setdefault(
            year_key, {"captured_at": captured_at, "events": []}
        )["events"].append(event)
        existing_keys.add(key)

    existing["captured_at"] = captured_at
    existing["updated_at"] = utc_now_iso()
    return existing


def count_events_in_player_output(player_data: dict[str, Any], from_year: int) -> int:
    """统计 from_year 及之后的事件数，兼容 `years` 和扁平 `events` 两种结构。"""
    years = player_data.get("years")
    if isinstance(years, dict) and years:
        total = 0
        for year_str, year_data in years.items():
            try:
                year_int = int(year_str)
            except (ValueError, TypeError):
                year_int = 0
            if year_int > 0 and year_int < from_year:
                continue
            events = (year_data or {}).get("events", [])
            if isinstance(events, list):
                total += len(events)
        return total

    events = player_data.get("events", [])
    if not isinstance(events, list):
        return 0

    total = 0
    for event in events:
        event_year = event.get("event_year", "")
        try:
            event_year_int = int(event_year) if event_year else 0
        except (ValueError, TypeError):
            event_year_int = 0
        if event_year_int > 0 and event_year_int < from_year:
            continue
        total += 1
    return total


def run(args: argparse.Namespace) -> int:
    # 解析指定 player 参数（如果有的话）
    target_player_name = getattr(args, 'player_name', None)
    target_country_code = getattr(args, 'player_country', None)
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        logger.error("patchright is required. Install with: pip install patchright && python -m patchright install chromium")
        return 2

    players_file = Path(args.players_file)
    output_dir = Path(args.output_dir)
    
    # 创建 orig 和 cn 子目录
    output_orig_dir = output_dir / "orig"
    output_orig_dir.mkdir(parents=True, exist_ok=True)
    
    raw_dir = Path(args.raw_dir)
    storage_state = Path(args.storage_state)
    checkpoint_file = Path(args.checkpoint)
    
    from_date = parse_from_date(args.from_date)
    delay_cfg = DelayConfig(
        min_request_sec=args.min_delay,
        max_request_sec=args.max_delay,
        min_player_gap_sec=args.min_player_gap,
        max_player_gap_sec=args.max_player_gap,
    )

    players = load_players(players_file, args.top_n)
    if not players:
        logger.error("No players loaded from %s", players_file)
        return 2

    logger.info("Loaded %s players, from_date=%s", len(players), from_date)

    checkpoint = CheckpointStore(checkpoint_file)
    if getattr(args, "rebuild_checkpoint", False):
        checkpoint.reset()

    with sync_playwright() as p:
        profile = random.choice(select_browser_profiles())
        chosen_viewport = random.choice(profile["viewport_choices"])
        chosen_dpr = random.choice(profile["dpr_choices"])
        context_kwargs: dict[str, Any] = {
            "viewport": chosen_viewport,
            "locale": "en-US",
            "timezone_id": "Asia/Shanghai",
            "user_agent": profile["user_agent"],
            "device_scale_factor": chosen_dpr,
            "color_scheme": "light",
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "sec-ch-ua": profile["sec_ch_ua"],
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": profile["sec_ch_ua_platform"],
            },
        }
        if storage_state.exists():
            context_kwargs["storage_state"] = str(storage_state)

        via_cdp, browser, context, page = open_browser_page(
            p,
            use_cdp=True,
            cdp_port=args.cdp_port,
            cdp_only=False,
            launch_kwargs={"headless": args.headless, "slow_mo": args.slow_mo},
            context_kwargs=context_kwargs,
            log_prefix="matches",
        )
        if not via_cdp:
            logger.info(
                "New browser context: ua=...%s viewport=%sx%s dpr=%.2f",
                profile["user_agent"][-30:],
                chosen_viewport["width"],
                chosen_viewport["height"],
                chosen_dpr,
            )

        if via_cdp:
            # CDP 模式：session 已在真实 Chrome 中，只做一次轻量验证
            verify_cdp_session_or_prompt(page, SEARCH_URL, delay_cfg)
        else:
            try:
                ensure_logged_in(page, SEARCH_URL, delay_cfg, storage_state, args.init_session)
            except Exception:
                close_browser_page(via_cdp, browser, page)
                raise

            if args.init_session:
                logger.info("Session initialized. Exiting due to --init-session.")
                close_browser_page(via_cdp, browser, page)
                return 0

        # 如果指定了 player_name，只抓取该 player
        if target_player_name:
            filtered_players = []
            for p in players:
                name = _player_name_from_entry(p)
                country = (p.get("country_code") or "").strip()
                if target_country_code:
                    if name.lower() == target_player_name.lower() and country.lower() == target_country_code.lower():
                        filtered_players.append(p)
                        break
                else:
                    if name.lower() == target_player_name.lower():
                        filtered_players.append(p)
                        break

            if filtered_players:
                players = filtered_players
                logger.info("Filtered to target player from players file: %s (%s)", target_player_name, target_country_code or "any")
            else:
                logger.warning(
                    "Target player not found in players file, falling back to direct page search: %s (%s)",
                    target_player_name,
                    target_country_code or "any",
                )
                players = [{
                    "english_name": target_player_name,
                    "country_code": target_country_code or "",
                    "player_id": None,
                    "rank": 0,
                    "country": "",
                    "continent": "",
                }]

        for i, player in enumerate(players, start=1):
            player_name = _player_name_from_entry(player)
            country_code = (player.get("country_code") or "").strip()
            player_id = player.get("player_id")
            rank = player.get("rank", i)

            if not player_name:
                continue

            logger.info("[%s/%s] Player: %s (%s)", i, len(players), player_name, country_code)

            orig_file = output_orig_dir / f"{sanitize_filename(player_name)}.json"
            # 从 orig 目录读取现有数据
            if orig_file.exists():
                try:
                    player_output = json.loads(orig_file.read_text(encoding="utf-8"))
                except Exception:
                    player_output = {}
            else:
                player_output = {}

            if not player_output:
                player_output = {
                    "schema_version": "match.v2",
                    "player_id": player_id,
                    "player_name": player_name,
                    "english_name": player_name,
                    "country": player.get("country", ""),
                    "country_code": country_code,
                    "continent": player.get("continent", ""),
                    "rank": rank,
                    "from_date": from_date.isoformat(),
                    "years": {},
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                }
            else:
                player_output.setdefault("schema_version", "match.v2")
                player_output.setdefault("player_id", player_id)
                player_output.setdefault("player_name", player_name)
                player_output.setdefault("english_name", player_name)
                player_output.setdefault("country", player.get("country", ""))
                player_output.setdefault("country_code", country_code)
                player_output.setdefault("continent", player.get("continent", ""))
                player_output.setdefault("rank", rank)
                player_output.setdefault("from_date", from_date.isoformat())

            ck_player = _ck_player_base(checkpoint, player_id, player_name, from_date.isoformat())

            # Bootstrap per-event checkpoints from existing orig output (when checkpoint is missing/empty or rebuild requested).
            if (not args.force) and (getattr(args, "rebuild_checkpoint", False) or (not checkpoint.has_any_completed())) and orig_file.exists():
                try:
                    fresh = json.loads(orig_file.read_text(encoding="utf-8"))
                    years = fresh.get("years", {}) if isinstance(fresh, dict) else {}
                    with checkpoint.bulk():
                        for year_str, year_data in (years or {}).items():
                            try:
                                y = int(year_str)
                                if y > 0 and y < from_date.year:
                                    continue
                            except Exception:
                                pass
                            for ev in (year_data or {}).get("events", []) or []:
                                ey = ev.get("event_year", year_str)
                                en = ev.get("event_name", "")
                                if not en:
                                    continue
                                ck_event = _ck_event(ck_player, ey, en)
                                if not checkpoint.is_done(ck_event):
                                    checkpoint.mark_done(ck_event, meta={"bootstrapped_from": str(orig_file)})
                except Exception:
                    pass

            # --force: clear existing events (from from_date.year onwards) so rescrape can overwrite.
            if args.force and isinstance(player_output, dict) and player_output.get("years"):
                years = player_output.get("years", {})
                if isinstance(years, dict):
                    for yk in list(years.keys()):
                        try:
                            yi = int(yk)
                            if yi >= from_date.year:
                                years.pop(yk, None)
                        except Exception:
                            continue

            logger.info("Scraping/verifying %s since %s (force=%s)", player_name, from_date, bool(args.force))
            try:
                player_data = scrape_player(
                    page=page,
                    player_name=player_name,
                    country_code=country_code,
                    from_date=from_date,
                    delay_cfg=delay_cfg,
                    raw_dir=raw_dir,
                    checkpoint=checkpoint,
                    ck_player=ck_player,
                    force=bool(args.force),
                    out_file=orig_file,
                    player_output=player_output,
                )
                player_data["schema_version"] = "match.v2"
                player_data["player_id"] = player_id
                player_data["player_name"] = player_name
                player_data["english_name"] = player_name
                player_data["country"] = player.get("country", player_data.get("country", ""))
                player_data["country_code"] = country_code
                player_data["continent"] = player.get("continent", player_data.get("continent", ""))
                player_data["rank"] = rank
                player_data["from_date"] = from_date.isoformat()
                # 统计总 event 数（网页 events 数量 = 我们的 JSON 总 event 数）
                total_events_in_json = count_events_in_player_output(player_data, from_date.year)
                if total_events_in_json == 0:
                    raise RuntimeError(
                        f"No events found for {player_name} ({country_code}) since {from_date}. "
                        f"This should never happen for a real player — possible parsing or network issue."
                    )
                # 保存原始数据到 orig 目录
                save_json(orig_file, player_data)
                logger.info("Saved original: %s", orig_file)
                
                checkpoint.mark_done(ck_player, meta={"orig_path": str(orig_file)})
                logger.info("Completed %s (%s events in JSON)", player_name, total_events_in_json)
            except RiskControlTriggered as exc:
                checkpoint.mark_failed(ck_player, f"risk_control: {exc}")
                # 风险触发时也保存已获取的数据
                if orig_file:
                    save_json(orig_file, player_output)
                logger.error("Risk control triggered: %s", exc)
                logger.error("Stop immediately to protect account/session.")
                close_browser_page(via_cdp, browser, page)
                return 3
            except Exception as exc:
                checkpoint.mark_failed(ck_player, str(exc))
                logger.error("Failed %s: %s", player_name, exc)
                close_browser_page(via_cdp, browser, page)
                return 4

            human_sleep(delay_cfg.min_player_gap_sec, delay_cfg.max_player_gap_sec, "gap between players")

        close_browser_page(via_cdp, browser, page)

    logger.info("Completed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF safer scraper v2 (manual login + resume)")
    parser.add_argument(
        "--players-file",
        default="data/rankings/orig",
        help="Ranking JSON file or directory. Defaults to the latest women_singles_top100_*.json under data/rankings/orig/",
    )
    parser.add_argument("--output-dir", default="data/matches_complete")
    parser.add_argument("--raw-dir", default="data/raw_event_payloads")
    parser.add_argument("--storage-state", default="data/session/ittf_storage_state.json")
    parser.add_argument("--checkpoint", default="data/checkpoints/ittf_checkpoint.json")
    parser.add_argument("--from-date", default=DEFAULT_FROM_DATE, help="Scrape events from this date onwards (YYYY-MM-DD)")
    parser.add_argument(
        "--top-n",
        default="30",
        help="Top ranking slice to load. Use N for top N players, or START-END for an inclusive range like 51-100.",
    )

    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP port of an existing Chrome to reuse (avoids re-login)")
    parser.add_argument("--init-session", action="store_true", help="Open browser for manual login and save storage-state")
    parser.add_argument("--headless", action="store_true", help="Run headless (not recommended for login flow)")
    parser.add_argument("--slow-mo", type=int, default=100)

    parser.add_argument("--min-delay", type=float, default=5.0)
    parser.add_argument("--max-delay", type=float, default=18.0)
    parser.add_argument("--min-player-gap", type=float, default=20.0)
    parser.add_argument("--max-player-gap", type=float, default=45.0)

    parser.add_argument("--force", action="store_true", help="Ignore checkpoint completed marks")
    parser.add_argument("--rebuild-checkpoint", action="store_true", help="Rebuild checkpoint from existing orig outputs")
    parser.add_argument("--player-name", type=str, default=None, help="Scrape only a specific player by English name (case-insensitive)")
    parser.add_argument("--player-country", type=str, default=None, help="Country code for the specific player (optional, used with --player-name)")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        rc = run(args)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        rc = 130
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        rc = 1

    sys.exit(rc)


if __name__ == "__main__":
    main()
