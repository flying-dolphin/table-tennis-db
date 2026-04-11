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
from lib.browser_session import ensure_logged_in
from lib.capture import capture_json_responses_for_page, sanitize_filename, save_json
from lib.checkpoint import CheckpointStore, utc_now_iso
from lib.page_ops import click_next_page_if_any, guarded_goto
from lib.translator import Translator


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




def load_players(players_file: Path, top_n: int) -> list[dict[str, Any]]:
    if not players_file.exists():
        raise FileNotFoundError(f"players file not found: {players_file}")

    data = json.loads(players_file.read_text(encoding="utf-8"))
    rankings = data.get("rankings", [])
    return rankings[:top_n]


def parse_from_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise ValueError(f"Invalid --from-date format '{raw}', expected YYYY-MM-DD")




def parse_event_rows(page: Any) -> list[dict[str, Any]]:
    tables = page.query_selector_all("table")
    events: list[dict[str, Any]] = []

    for table in tables:
        rows = table.query_selector_all("tbody tr") or table.query_selector_all("tr")
        for row in rows:
            cells = row.query_selector_all("td")
            if len(cells) < 2:
                continue

            first_text = (cells[0].inner_text() or "").strip()
            if not first_text.isdigit():
                continue

            link = cells[0].query_selector("a")
            href = link.get_attribute("href") if link else None
            if not href:
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
    """遍历 event 分页，遇到早于 from_date 的赛事即停止，避免翻到空页。"""
    all_events: list[dict[str, Any]] = []
    visited_snapshots: set[str] = set()

    for page_num in range(max_pages):
        events = parse_event_rows(page)
        if not events:
            break

        reached_cutoff = False
        for event in events:
            event_date = _event_sort_date(event)
            if event_date and event_date < from_date:
                reached_cutoff = True
                logger.info(
                    "Reached event date=%s < from_date=%s on page %s, stopping pagination",
                    event_date.isoformat(), from_date.isoformat(), page_num + 1,
                )
                break
            all_events.append(event)

        if reached_cutoff:
            break

        snapshot = "|".join(sorted(e.get("href", "") for e in events)[:50])
        if snapshot in visited_snapshots:
            break
        visited_snapshots.add(snapshot)

        if not click_next_page_if_any(page):
            break

    return dedupe_events(all_events)


def parse_match_from_row(cells: list[Any], player_name: str) -> dict[str, Any] | None:
    cell_texts = [" ".join((c.inner_text() or "").split()) for c in cells]
    row_text = " | ".join(t for t in cell_texts if t)

    score_idx = -1
    match_score = ""
    score_a = score_b = None
    for idx, text in enumerate(cell_texts):
        m = SCORE_RE.search(text)
        if m:
            score_idx = idx
            match_score = f"{m.group(1)}-{m.group(2)}"
            score_a = int(m.group(1))
            score_b = int(m.group(2))
            break

    raw_games = GAME_RE.findall(row_text)
    game_scores = [f"{a}:{b}" for a, b in raw_games]
    game_objects = [{"player": int(a), "opponent": int(b)} for a, b in raw_games]
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

    # 根据比分位置分割 side_a 和 side_b
    side_a: list[str] = []
    side_b: list[str] = []
    if score_idx >= 0 and unique_players:
        # 简单策略：前一半是 side_a，后一半是 side_b
        # 对于单打：1个球员 vs 1个球员
        # 对于双打：2个球员 vs 2个球员
        mid = len(unique_players) // 2
        side_a = unique_players[:mid] if mid > 0 else unique_players[:1]
        side_b = unique_players[mid:] if mid > 0 else unique_players[1:]
    elif unique_players:
        # 没有比分列时，尝试用 "vs" 或 "-" 分割
        side_a = unique_players[:1]
        side_b = unique_players[1:] if len(unique_players) > 1 else []

    # 同时保留 anchor 提取的名字作为备用（如果上面的方法失败）
    anchor_names_by_cell: list[list[str]] = []
    for c in cells:
        names = [" ".join((a.inner_text() or "").split()) for a in c.query_selector_all("a")]
        names = [n for n in names if n]
        anchor_names_by_cell.append(names)

    all_names: list[str] = []
    for names in anchor_names_by_cell:
        for n in names:
            if n not in all_names:
                all_names.append(n)

    # 如果正则提取失败，回退到 anchor 方法
    if not side_a and not side_b and all_names:
        mid = len(all_names) // 2
        side_a = all_names[:mid] if mid > 0 else all_names[:1]
        side_b = all_names[mid:] if mid > 0 else all_names[1:]

    winner = ""
    winner_m = re.search(r"Winner:\s*([^|]+)", row_text, flags=re.IGNORECASE)
    if winner_m:
        winner = winner_m.group(1).strip()

    sub_event = ""
    for token in ["WS", "MS", "WD", "MD", "XD", "U19", "U17", "U15"]:
        if re.search(rf"\b{re.escape(token)}\b", row_text):
            sub_event = token
            break

    stage = ""
    for s in ["Main Draw", "Qualification", "Qualifying", "Group", "Final"]:
        if s.lower() in row_text.lower():
            stage = s
            break

    round_text = ""
    round_m = re.search(r"\b(R\d{1,2}|QF|SF|F|R32|R64|R128|Round of \d+)\b", row_text, flags=re.IGNORECASE)
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

    tables = page.query_selector_all("table")
    for table in tables:
        rows = table.query_selector_all("tbody tr") or table.query_selector_all("tr")
        for row in rows:
            cells = row.query_selector_all("td")
            if len(cells) < 2:
                continue
            parsed = parse_match_from_row(cells, player_name)
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
                    try:
                        exact.scroll_into_view_if_needed()
                    except Exception as exc:
                        logger.info("[autocomplete] exact scroll skipped: %s", exc)
                    try:
                        exact.click(timeout=2000)
                        logger.info("[autocomplete] exact click ok")
                    except Exception as exc:
                        logger.warning("[autocomplete] exact click failed: %s", exc)
                        try:
                            exact.click(force=True, timeout=2000)
                            logger.info("[autocomplete] exact force click ok")
                        except Exception as exc2:
                            logger.warning("[autocomplete] exact force click failed, fallback mouse: %s", exc2)
                            move_mouse_to_locator(page, exact)
                            logger.info("[autocomplete] exact mouse click ok")
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

            for i in range(count):
                item = candidates.nth(i)
                try:
                    if not item.is_visible():
                        continue
                    txt = " ".join((item.inner_text() or "").split())
                    data_value = item.get_attribute("data-value") if item.count() > 0 else None
                    if not txt:
                        continue
                    logger.info("[autocomplete] candidate[%s]=%s data-value=%s", i, txt[:120], data_value)
                    if (target_text in txt or fallback_text in txt) and data_value:
                        logger.info("[autocomplete] matched candidate[%s], trying click", i)
                        before_value = None
                        try:
                            before_value = search_input.input_value()
                        except Exception:
                            pass
                        try:
                            item.scroll_into_view_if_needed()
                        except Exception as exc:
                            logger.info("[autocomplete] candidate scroll skipped: %s", exc)
                        try:
                            item.click(timeout=2000)
                            logger.info("[autocomplete] candidate click ok")
                        except Exception as exc:
                            logger.warning("[autocomplete] candidate click failed: %s", exc)
                            try:
                                item.click(force=True, timeout=2000)
                                logger.info("[autocomplete] candidate force click ok")
                            except Exception as exc2:
                                logger.warning("[autocomplete] candidate force click failed, fallback mouse: %s", exc2)
                                move_mouse_to_locator(page, item)
                                logger.info("[autocomplete] candidate mouse click ok")

                        time.sleep(0.4)
                        try:
                            after_value = search_input.input_value()
                        except Exception:
                            after_value = None
                        logger.info("[autocomplete] input before click=%s after click=%s", before_value, after_value)
                        return True
                except Exception as exc:
                    logger.info("[autocomplete] candidate[%s] probe failed: %s", i, exc)
                    continue

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
    selects = page.query_selector_all("select")
    for sel in selects:
        try:
            options = sel.query_selector_all("option")
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
        for el in page.query_selector_all("input[type='button'], input[type='submit'], button"):
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
    human_sleep(delay_cfg.min_request_sec, delay_cfg.max_request_sec, "before click Go")
    if not click_go(page):
        raise RuntimeError("Go button not found")

    page.wait_for_load_state("domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

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
    if out_file is not None and out_file.exists():
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

    # 判断逻辑：数据只会增加，只需判断是否有新增
    new_event_count = len(events) - existing_event_count
    
    if new_event_count <= 0:
        # 网页 events <= JSON events，说明数据已完整（或一致）
        logger.info("Data complete for %s (%s): JSON has %s events, web has %s events", 
                    player_name, country_code, existing_event_count, len(events))
        # 更新元数据并返回完整的 player_output（不返回 events=[] 的 result）
        if player_output is not None:
            player_output["captured_at"] = utc_now_iso()
            player_output["updated_at"] = utc_now_iso()
            if out_file is not None:
                save_json(out_file, player_output)
        return player_output if player_output is not None else result
    else:
        # 网页 events > JSON events，有新增需要抓取
        logger.info("Found %s new events for %s (%s), will capture", 
                    new_event_count, player_name, country_code)

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
        if event_key in already_scraped:
            logger.info("Skip [%s/%s] already scraped: [%s] %s",
                        idx, len(events), event_year, event.get("event_name", ""))
            continue

        detail_url = absolute_url(href)
        logger.info("Event %s/%s [%s]: %s", idx, len(events), event_year, detail_url)

        def visit_detail(url: str = detail_url, pos: int = idx) -> None:
            guarded_goto(page, url, delay_cfg, f"visit event detail {pos}/{len(events)}",
                         referer=events_list_url)

        captures = capture_json_responses_for_page(page, visit_detail)
        matches = parse_detail_matches_from_dom(page, player_name)

        safe_event = sanitize_filename(f"{event_year}_{idx}_{event.get('event_name', 'event')}")
        raw_file = raw_dir / sanitize_filename(player_name) / f"{safe_event}.json"
        save_json(
            raw_file,
            {
                "event_meta": event,
                "detail_url": detail_url,
                "captured_at": utc_now_iso(),
                "captured_json_responses": captures,
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

    # 校验：对比实际抓取的 event 数量和期望数量
    newly_captured = len(result.get("events", []))
    
    if newly_captured != expected_to_capture:
        raise RuntimeError(
            f"Event count mismatch for {player_name} ({country_code}): "
            f"expected to capture {expected_to_capture} new events, "
            f"but only {newly_captured} were captured. "
            f"Some events may have been skipped due to duplicate keys or other issues."
        )
    
    # 最终校验：总数量应该匹配
    total_captured = newly_captured + len(already_scraped)
    if total_captured != len(events):
        raise RuntimeError(
            f"Final count mismatch for {player_name} ({country_code}): "
            f"web has {len(events)} events, "
            f"but total captured is {total_captured} (new: {newly_captured}, previous: {len(already_scraped)})."
        )

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


def translate_matches_data(data: dict[str, Any], translator: Translator) -> dict[str, Any]:
    """翻译比赛数据为中文"""
    result = data.copy()
    
    # 翻译运动员姓名
    if 'player_name' in result and result['player_name']:
        result['player_name_zh'] = translator.translate(result['player_name'], category='players', use_api=True)
    
    # 翻译国家代码
    if 'country_code' in result and result['country_code']:
        result['country_code_zh'] = translator.translate(result['country_code'], category='countries', use_api=True)
    
    # 翻译每年的赛事数据
    if 'years' in result:
        for year, year_data in result['years'].items():
            if 'events' in year_data:
                for event in year_data['events']:
                    # 翻译赛事名称
                    if 'event_name' in event and event['event_name']:
                        event['event_name_zh'] = translator.translate(event['event_name'], category='events', use_api=True)
                    
                    # 翻译赛事类型
                    if 'event_type' in event and event['event_type']:
                        event['event_type_zh'] = translator.translate(event['event_type'], category='events', use_api=True)
                    
                    # 翻译比赛数据
                    if 'matches' in event:
                        for match in event['matches']:
                            # 翻译阶段
                            if 'stage' in match and match['stage']:
                                match['stage_zh'] = translator.translate(match['stage'], category='terms', use_api=True)
                            
                            # 翻译轮次
                            if 'round' in match and match['round']:
                                original = match['round']
                                if original.startswith('R') and original[1:].isdigit():
                                    match['round_zh'] = f"第{original[1:]}轮"
                                else:
                                    match['round_zh'] = translator.translate(original, category='terms', use_api=True)
                            
                            # 翻译子赛事类型
                            if 'sub_event' in match and match['sub_event']:
                                sub_event_map = {
                                    'WS': '女子单打',
                                    'MS': '男子单打',
                                    'WD': '女子双打',
                                    'MD': '男子双打',
                                    'XD': '混合双打',
                                    'XT': '混合团体',
                                    'WT': '女子团体',
                                    'MT': '男子团体',
                                }
                                match['sub_event_zh'] = sub_event_map.get(match['sub_event'], match['sub_event'])
    
    return result


def _try_connect_cdp(p: Any, cdp_port: int) -> tuple[bool, Any, Any]:
    """尝试连接已有 Chrome（CDP 模式），复用其登录 session。
    返回 (via_cdp, browser, context)；连接失败时返回 (False, None, None)。
    """
    import urllib.request as _urllib_req

    cdp_url = f"http://localhost:{cdp_port}"
    try:
        _urllib_req.urlopen(f"{cdp_url}/json/version", timeout=2)
    except Exception as exc:
        logger.info(
            "No Chrome with remote debugging found at %s (%s) — will launch new browser.\n"
            "  To reuse an existing session (avoids re-login), start a dedicated Chrome instance first:\n"
            "    macOS:\n"
            "      /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\\n"
            "        --remote-debugging-port=%s \\\n"
            "        --user-data-dir=\"$HOME/.chrome-ittf-profile\" \\\n"
            "        --no-first-run --no-default-browser-check\n"
            "    Windows:\n"
            "      \"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\"\n"
            "        --remote-debugging-port=%s\n"
            "        --user-data-dir=\"%%USERPROFILE%%\\.chrome-ittf-profile\"\n"
            "  Log in to ITTF in that window once; the session persists across runs.",
            cdp_url, exc, cdp_port, cdp_port,
        )
        return False, None, None

    try:
        browser = p.chromium.connect_over_cdp(cdp_url)
        contexts = browser.contexts
        context = contexts[0] if contexts else browser.new_context()
        logger.info("Connected to existing Chrome via CDP at %s (context has %s page(s))",
                    cdp_url, len(context.pages))
        return True, browser, context
    except Exception as exc:
        logger.warning("CDP handshake failed: %s — falling back to new browser", exc)
        return False, None, None


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
    output_cn_dir = output_dir / "cn"
    output_orig_dir.mkdir(parents=True, exist_ok=True)
    output_cn_dir.mkdir(parents=True, exist_ok=True)
    
    raw_dir = Path(args.raw_dir)
    storage_state = Path(args.storage_state)
    checkpoint_file = Path(args.checkpoint)
    
    # 初始化翻译器
    translator = Translator()
    translator_stats = translator.get_stats()
    logger.info("Translator loaded: %s", translator_stats)

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

    with sync_playwright() as p:
        # 优先 CDP 连接已有 Chrome（保留登录 session），连不上才新启动
        via_cdp, browser, context = _try_connect_cdp(p, args.cdp_port)

        if not via_cdp:
            # patchright 新启动：在编译层已消除自动化标识
            browser = p.chromium.launch(
                headless=args.headless,
                slow_mo=args.slow_mo,
            )

            # 按当前 OS 选取配置，UA / sec-ch-ua / platform / DPR / viewport 全部自洽
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

            logger.info(
                "New browser context: ua=...%s viewport=%sx%s dpr=%.2f",
                profile["user_agent"][-30:],
                chosen_viewport["width"],
                chosen_viewport["height"],
                chosen_dpr,
            )
            context = browser.new_context(**context_kwargs)

        page = context.new_page()

        if via_cdp:
            # CDP 模式：session 已在真实 Chrome 中，只做一次轻量验证
            guarded_goto(page, SEARCH_URL, delay_cfg, "verify CDP session", sleep_first=False)
            if page.locator("input[name='username']").count() > 0:
                print("\n=== CDP session requires login ===")
                print("1) Complete login in the opened browser window")
                print("2) Return here and press ENTER")
                input("Press ENTER after login is completed...")
                if page.locator("input[name='username']").count() > 0:
                    raise RuntimeError("Login not completed. Aborting.")
        else:
            try:
                ensure_logged_in(page, delay_cfg, storage_state, args.init_session)
            except Exception:
                browser.close()
                raise

            if args.init_session:
                logger.info("Session initialized. Exiting due to --init-session.")
                browser.close()
                return 0

        # 如果指定了 player_name，只抓取该 player
        if target_player_name:
            filtered_players = []
            for p in players:
                name = (p.get("english_name") or "").strip()
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
            player_name = (player.get("english_name") or "").strip()
            country_code = (player.get("country_code") or "").strip()
            player_id = player.get("player_id")
            rank = player.get("rank", i)

            if not player_name:
                continue

            logger.info("[%s/%s] Player: %s (%s)", i, len(players), player_name, country_code)

            orig_file = output_orig_dir / f"{sanitize_filename(player_name)}.json"
            cn_file = output_cn_dir / f"{sanitize_filename(player_name)}.json"
            
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

            ck = checkpoint.key(player_id, player_name, from_date.isoformat())

            # 始终调用 scrape_player：它会访问网页对比实际 event 数量，
            # 只有网页 events > JSON events 时才会真正抓取 detail 页面
            if args.force and checkpoint.is_done(ck):
                logger.info("Force rescraping %s since %s (checkpoint cleared)", player_name, from_date)
            else:
                logger.info("Scraping/verifying %s since %s", player_name, from_date)
            try:
                player_data = scrape_player(
                    page=page,
                    player_name=player_name,
                    country_code=country_code,
                    from_date=from_date,
                    delay_cfg=delay_cfg,
                    raw_dir=raw_dir,
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
                total_events_in_json = sum(
                    len(year_data.get("events", []))
                    for year_str, year_data in player_data.get("years", {}).items()
                    if int(year_str) >= from_date.year
                )
                if total_events_in_json == 0:
                    raise RuntimeError(
                        f"No events found for {player_name} ({country_code}) since {from_date}. "
                        f"This should never happen for a real player — possible parsing or network issue."
                    )
                # 保存原始数据到 orig 目录
                save_json(orig_file, player_data)
                logger.info("Saved original: %s", orig_file)
                
                # 翻译并保存中文版本到 cn 目录 (unless disabled)
                if not args.no_translate:
                    player_data_cn = translate_matches_data(player_data, translator)
                    save_json(cn_file, player_data_cn)
                    logger.info("Saved Chinese: %s", cn_file)
                else:
                    logger.debug("Translation skipped (--no-translate)")
                
                checkpoint.mark_done(ck)
                logger.info("Completed %s (%s events in JSON)", player_name, total_events_in_json)
            except RiskControlTriggered as exc:
                checkpoint.mark_failed(ck, f"risk_control: {exc}")
                # 风险触发时也保存已获取的数据
                if orig_file:
                    save_json(orig_file, player_output)
                logger.error("Risk control triggered: %s", exc)
                logger.error("Stop immediately to protect account/session.")
                if not via_cdp:
                    browser.close()
                return 3
            except Exception as exc:
                checkpoint.mark_failed(ck, str(exc))
                logger.error("Failed %s: %s", player_name, exc)
                if args.stop_on_error:
                    if not via_cdp:
                        browser.close()
                    return 4

            human_sleep(delay_cfg.min_player_gap_sec, delay_cfg.max_player_gap_sec, "gap between players")

        if via_cdp:
            page.close()  # 只关闭新开的标签页，保留用户原有 Chrome 窗口
        else:
            browser.close()

    logger.info("Completed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF safer scraper v2 (manual login + resume)")
    parser.add_argument("--players-file", default="data/women_singles_top50.json")
    parser.add_argument("--output-dir", default="data/matches_complete")
    parser.add_argument("--raw-dir", default="data/raw_event_payloads")
    parser.add_argument("--storage-state", default="data/session/ittf_storage_state.json")
    parser.add_argument("--checkpoint", default="data/checkpoints/ittf_checkpoint.json")
    parser.add_argument("--from-date", default=DEFAULT_FROM_DATE, help="Scrape events from this date onwards (YYYY-MM-DD)")
    parser.add_argument("--top-n", type=int, default=30)

    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP port of an existing Chrome to reuse (avoids re-login)")
    parser.add_argument("--init-session", action="store_true", help="Open browser for manual login and save storage-state")
    parser.add_argument("--headless", action="store_true", help="Run headless (not recommended for login flow)")
    parser.add_argument("--slow-mo", type=int, default=100)

    parser.add_argument("--min-delay", type=float, default=5.0)
    parser.add_argument("--max-delay", type=float, default=18.0)
    parser.add_argument("--min-player-gap", type=float, default=20.0)
    parser.add_argument("--max-player-gap", type=float, default=45.0)

    parser.add_argument("--force", action="store_true", help="Ignore checkpoint completed marks")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--player-name", type=str, default=None, help="Scrape only a specific player by English name (case-insensitive)")
    parser.add_argument("--player-country", type=str, default=None, help="Country code for the specific player (optional, used with --player-name)")
    parser.add_argument("--no-translate", action="store_true", help="Skip translation, save only original data")
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
