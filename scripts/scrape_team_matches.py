#!/usr/bin/env python3
"""
Scrape team-event finals matches from ITTF event matches pages.

Workflow:
1. Load seed events from data/matches_complete/orig/*.json where sub_event=WT and round=Final.
2. Resolve event_id in DB and filter out events whose category has filtering_only=1.
3. Search each event on https://results.ittf.link/index.php/events, open matches link,
   jump to End page, and collect matches with round=Final while paging backwards.
4. Save one JSON per event into data/team_matches/orig/.
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import random
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from lib.anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep, move_mouse_to_locator
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.browser_session import ensure_logged_in
from lib.checkpoint import CheckpointStore, utc_now_iso
from lib.navigation_runtime import verify_cdp_session_or_prompt
from lib.page_ops import guarded_goto
from scrape_matches import parse_detail_matches_from_dom

try:
    from db import config as db_config

    DEFAULT_DB_PATH = Path(db_config.DB_PATH)
except Exception:
    DEFAULT_DB_PATH = Path("data/db/ittf.db")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("team_matches_scraper")


BASE_URL = "https://results.ittf.link"
EVENTS_URL = f"{BASE_URL}/index.php/events"
SEARCH_INPUT = "#searchall_27_com_fabrik_27"

PLAYER_TOKEN_RE = re.compile(r"^(.+?)\s*\((\w+)\)$")


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
    }
]

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
    }
]


@dataclass(frozen=True)
class TargetEvent:
    event_id: int
    event_name: str
    event_year: int | None
    source_count: int

    @property
    def checkpoint_key(self) -> str:
        return f"team_event|{self.event_id}|{self.event_year or 0}|{self.event_name}"


def select_browser_profiles() -> list[dict[str, Any]]:
    if platform.system() == "Darwin":
        return BROWSER_PROFILES_MACOS
    return BROWSER_PROFILES_WINDOWS


def normalize_event_name(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"\s+presented\s+by\s+.*$", "", s)
    s = re.sub(r"[,.]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_player_str(player_str: str) -> tuple[str, str | None]:
    m = PLAYER_TOKEN_RE.match((player_str or "").strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return (player_str or "").strip(), None


def make_side_key(side: list[str]) -> str:
    keys: list[str] = []
    for item in side:
        name, country = parse_player_str(item)
        keys.append(f"{name.strip().lower()}|{(country or '').strip().lower()}")
    keys.sort()
    return "||".join(keys)


def infer_winner_side(winner_name: str, side_a: list[str], side_b: list[str]) -> str | None:
    winner = (winner_name or "").strip().lower()
    if not winner:
        return None

    def _hit(side: list[str]) -> bool:
        for player in side:
            name, _ = parse_player_str(player)
            if name and name.strip().lower() in winner:
                return True
        return False

    hit_a = _hit(side_a)
    hit_b = _hit(side_b)
    if hit_a and not hit_b:
        return "A"
    if hit_b and not hit_a:
        return "B"
    return None


def resolve_event_id(event_index: dict[str, Any], event_name: str, event_year: int | None) -> int | None:
    norm = normalize_event_name(event_name)
    if not norm:
        return None
    if event_year is not None:
        event_id = event_index["by_name_year"].get((norm, event_year))
        if event_id is not None:
            return event_id
    candidates = sorted(event_index["by_name"].get(norm, set()))
    if len(candidates) == 1:
        return candidates[0]
    return None


def build_event_index(cursor: sqlite3.Cursor) -> dict[str, Any]:
    cursor.execute("SELECT event_id, name, year FROM events")
    by_name_year: dict[tuple[str, int], int] = {}
    by_name: dict[str, set[int]] = {}
    for event_id, name, year in cursor.fetchall():
        norm = normalize_event_name(name or "")
        if not norm:
            continue
        if year is not None:
            by_name_year[(norm, int(year))] = int(event_id)
        by_name.setdefault(norm, set()).add(int(event_id))
    return {"by_name_year": by_name_year, "by_name": by_name}


def load_filtering_only_event_ids(cursor: sqlite3.Cursor) -> set[int]:
    cursor.execute(
        """
        SELECT e.event_id
        FROM events e
        JOIN event_categories c ON c.id = e.event_category_id
        WHERE c.filtering_only = 1
        """
    )
    return {int(row[0]) for row in cursor.fetchall() if row and row[0] is not None}


def collect_target_events(source_dir: Path, db_path: Path) -> list[TargetEvent]:
    if not source_dir.exists():
        raise FileNotFoundError(f"source dir not found: {source_dir}")
    if not db_path.exists():
        raise FileNotFoundError(f"db not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    event_index = build_event_index(cursor)
    filtering_only_event_ids = load_filtering_only_event_ids(cursor)
    conn.close()

    targets: dict[int, TargetEvent] = {}
    unresolved_events: set[str] = set()
    skipped_filtering_only = 0
    scanned_files = 0

    for path in sorted(source_dir.glob("*.json")):
        scanned_files += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skip unreadable file %s: %s", path.name, exc)
            continue

        years = payload.get("years") or {}
        if not isinstance(years, dict):
            continue

        for year_data in years.values():
            events = (year_data or {}).get("events", [])
            for event in events:
                matches = event.get("matches", [])
                has_ws_final = any(
                    isinstance(m, dict)
                    and (m.get("sub_event") or "").strip().upper() == "WT"
                    and (m.get("round") or "").strip().lower() == "final"
                    for m in matches
                )
                if not has_ws_final:
                    continue

                event_name = (event.get("event_name") or "").strip()
                event_year: int | None = None
                event_year_raw = event.get("event_year")
                try:
                    if event_year_raw not in (None, ""):
                        event_year = int(event_year_raw)
                except Exception:
                    event_year = None

                event_id = resolve_event_id(event_index, event_name, event_year)
                if event_id is None:
                    unresolved_events.add(f"{event_name} ({event_year_raw})")
                    continue
                if event_id in filtering_only_event_ids:
                    skipped_filtering_only += 1
                    continue

                old = targets.get(event_id)
                if old is None:
                    targets[event_id] = TargetEvent(
                        event_id=event_id,
                        event_name=event_name,
                        event_year=event_year,
                        source_count=1,
                    )
                else:
                    targets[event_id] = TargetEvent(
                        event_id=old.event_id,
                        event_name=old.event_name or event_name,
                        event_year=old.event_year or event_year,
                        source_count=old.source_count + 1,
                    )

    logger.info("Scanned %s source files from %s", scanned_files, source_dir)
    logger.info("符合条件的赛事总数: %s", len(targets))
    logger.info("Skipped filtering_only events at target-build stage: %s", skipped_filtering_only)
    if unresolved_events:
        logger.warning("Unresolved events (not in events table): %s", len(unresolved_events))
        for name in sorted(unresolved_events)[:20]:
            logger.warning("  - %s", name)
    return sorted(targets.values(), key=lambda e: (e.event_year or 0, e.event_name.lower()))


def _row_fingerprint(page: Any) -> str:
    rows = page.locator("table tbody tr")
    count = min(rows.count(), 10)
    items: list[str] = []
    for i in range(count):
        try:
            text = " ".join((rows.nth(i).inner_text() or "").split())
            if text:
                items.append(text[:180])
        except Exception:
            continue
    return "|".join(items)


def _wait_for_result_change(page: Any, old_fp: str, timeout_sec: float = 12.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            fp = _row_fingerprint(page)
            if fp and fp != old_fp:
                return
        except Exception:
            pass
        time.sleep(0.25)


def _parse_event_search_rows(page: Any) -> list[dict[str, Any]]:
    rows = page.locator("table tbody tr")
    out: list[dict[str, Any]] = []
    for i in range(rows.count()):
        row = rows.nth(i)
        tds = row.locator("td")
        if tds.count() < 3:
            continue

        row_text = " ".join((row.inner_text() or "").split())
        event_id = None
        year = None
        name = ""

        id_text = (tds.nth(0).inner_text() or "").strip()
        year_text = (tds.nth(1).inner_text() or "").strip()
        name_text = (tds.nth(2).inner_text() or "").strip()
        if id_text.isdigit():
            event_id = int(id_text)
        if year_text.isdigit():
            year = int(year_text)
        name = name_text

        matches_link = row.locator("td.vw_tournaments___matches a").first
        if matches_link.count() == 0:
            # fallback: any link containing event-matches/list
            anchors = row.locator("a")
            href = ""
            for j in range(anchors.count()):
                a = anchors.nth(j)
                candidate = (a.get_attribute("href") or "").strip()
                if "/event-matches/list/" in candidate:
                    href = candidate
                    break
        else:
            href = (matches_link.get_attribute("href") or "").strip()
        if not href:
            continue

        out.append(
            {
                "event_id": event_id,
                "year": year,
                "name": name,
                "href": href,
                "row_text": row_text,
            }
        )
    return out


def _find_best_event_row(rows: list[dict[str, Any]], target: TargetEvent) -> dict[str, Any] | None:
    target_norm = normalize_event_name(target.event_name)
    candidates: list[dict[str, Any]] = []

    for row in rows:
        row_norm = normalize_event_name(str(row.get("name") or ""))
        row_year = row.get("year")
        row_eid = row.get("event_id")

        score = 0
        if row_eid is not None and row_eid == target.event_id:
            score += 100
        if row_year is not None and target.event_year is not None and row_year == target.event_year:
            score += 30
        if row_norm == target_norm:
            score += 20
        elif row_norm and target_norm and target_norm in row_norm:
            score += 10
        elif row_norm and target_norm and row_norm in target_norm:
            score += 8

        if score > 0:
            ranked = dict(row)
            ranked["_score"] = score
            candidates.append(ranked)

    if not candidates:
        return None
    candidates.sort(key=lambda x: (x.get("_score", 0), x.get("year") or 0), reverse=True)
    return candidates[0]


def _search_event_and_get_matches_href(page: Any, target: TargetEvent) -> str | None:
    search = page.locator(SEARCH_INPUT).first
    if search.count() == 0:
        raise RuntimeError(f"Search input not found: {SEARCH_INPUT}")

    old_fp = _row_fingerprint(page)
    search.click()
    search.fill("")
    search.fill(target.event_name)
    search.press("Enter")

    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    _wait_for_result_change(page, old_fp, timeout_sec=10.0)

    rows = _parse_event_search_rows(page)
    best = _find_best_event_row(rows, target)
    if best is None:
        return None
    return str(best.get("href") or "")


def _click_end_if_any(page: Any) -> None:
    candidates = [
        "a[title='End']",
        ".pagination a:has-text('End')",
    ]
    for sel in candidates:
        loc = page.locator(sel).first
        try:
            if loc.count() == 0 or not loc.is_visible():
                continue
            href = (loc.get_attribute("href") or "").strip()
            if href:
                page.goto(urljoin(page.url, href), wait_until="domcontentloaded", timeout=45000)
            else:
                move_mouse_to_locator(page, loc)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            return
        except Exception:
            continue


def _click_prev_page_if_any(page: Any) -> bool:
    candidates = [
        "li.page-item:not(.disabled) a[rel='prev']",
        "a[title='Previous']",
        ".pagination a:has-text('Previous')",
        ".pagination a:has-text('‹')",
        ".pagination a:has-text('«')",
    ]
    for sel in candidates:
        loc = page.locator(sel).first
        try:
            if loc.count() == 0 or not loc.is_visible():
                continue
            href = (loc.get_attribute("href") or "").strip()
            if href:
                old_url = page.url
                page.goto(urljoin(page.url, href), wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                return page.url != old_url
            move_mouse_to_locator(page, loc)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            return True
        except Exception:
            continue
    return False


def _normalize_round(value: str) -> str:
    return " ".join((value or "").split()).strip().lower()


def _is_wt_final_item(item: dict[str, Any]) -> bool:
    sub_event = (item.get("sub_event") or "").strip().upper()
    round_raw = (item.get("round") or "").strip()
    return sub_event == "WT" and _normalize_round(round_raw) == "final"


def _to_db_match(event: TargetEvent, item: dict[str, Any]) -> dict[str, Any] | None:
    round_raw = (item.get("round") or "").strip()
    if _normalize_round(round_raw) != "final":
        return None

    side_a = [x for x in (item.get("side_a") or []) if isinstance(x, str) and x.strip()]
    side_b = [x for x in (item.get("side_b") or []) if isinstance(x, str) and x.strip()]
    if not side_a or not side_b:
        return None

    side_a_key = make_side_key(side_a)
    side_b_key = make_side_key(side_b)
    winner_name = (item.get("winner") or "").strip()
    winner_side = infer_winner_side(winner_name, side_a, side_b)
    sub_event = (item.get("sub_event") or "").strip().upper() or "MAIN"

    return {
        "event_id": event.event_id,
        "event_name": event.event_name,
        "event_year": event.event_year,
        "sub_event_type_code": sub_event,
        "stage": (item.get("stage") or "").strip(),
        "round": round_raw,
        "side_a_key": side_a_key,
        "side_b_key": side_b_key,
        "match_score": (item.get("match_score") or "").strip(),
        "games": item.get("games") or [],
        "winner_side": winner_side,
        "winner_name": winner_name,
        "raw_row_text": (item.get("raw_row_text") or "").strip(),
        "side_a": side_a,
        "side_b": side_b,
        "scraped_at": utc_now_iso(),
    }


def _collect_final_matches_from_end(page: Any, event: TargetEvent, max_prev_pages: int) -> list[dict[str, Any]]:
    _click_end_if_any(page)
    seen_urls: set[str] = set()
    final_matches: list[dict[str, Any]] = []
    dedup_keys: set[tuple[Any, ...]] = set()
    found_wt_final = False

    for _ in range(max_prev_pages):
        if page.url in seen_urls:
            break
        seen_urls.add(page.url)

        parsed = parse_detail_matches_from_dom(page, player_name="")
        for item in parsed:
            is_wt_final = _is_wt_final_item(item)
            if not found_wt_final:
                if not is_wt_final:
                    continue
                found_wt_final = True
            elif not is_wt_final:
                return final_matches

            db_item = _to_db_match(event, item)
            if db_item is None:
                continue
            key = (
                db_item["event_id"],
                db_item["stage"],
                db_item["round"],
                db_item["side_a_key"],
                db_item["side_b_key"],
            )
            if key in dedup_keys:
                continue
            dedup_keys.add(key)
            final_matches.append(db_item)

        if not _click_prev_page_if_any(page):
            break

    return final_matches


def scrape_targets(
    page: Any,
    targets: list[TargetEvent],
    output_dir: Path,
    delay_cfg: DelayConfig,
    checkpoint: CheckpointStore,
    force: bool,
    max_prev_pages: int,
    limit_events: int | None,
) -> tuple[int, int, int]:
    saved = 0
    skipped = 0
    failed = 0

    selected_targets = targets[:limit_events] if limit_events and limit_events > 0 else targets

    for idx, target in enumerate(selected_targets, start=1):
        ck = target.checkpoint_key
        if (not force) and checkpoint.is_done(ck):
            skipped += 1
            logger.info("[%s/%s] skip by checkpoint: %s", idx, len(selected_targets), target.event_name)
            continue

        logger.info("[%s/%s] scraping event_id=%s name=%s", idx, len(selected_targets), target.event_id, target.event_name)
        try:
            guarded_goto(page, EVENTS_URL, delay_cfg, f"open events list for {target.event_name}", sleep_first=False)
            human_sleep(delay_cfg.min_request_sec, delay_cfg.max_request_sec, "before event search")
            matches_href = _search_event_and_get_matches_href(page, target)
            if not matches_href:
                checkpoint.mark_failed(ck, "event not found in events search")
                failed += 1
                logger.warning("Event not found in search: %s", target.event_name)
                continue

            matches_url = urljoin(BASE_URL, matches_href)
            guarded_goto(page, matches_url, delay_cfg, f"open matches for {target.event_name}", referer=EVENTS_URL)
            if detect_risk(page):
                raise RiskControlTriggered(str(detect_risk(page)))

            finals = _collect_final_matches_from_end(page, target, max_prev_pages=max_prev_pages)
            payload = {
                "schema_version": "team_match.v1",
                "scraped_at": utc_now_iso(),
                "event_id": target.event_id,
                "event_name": target.event_name,
                "event_year": target.event_year,
                "source_count": target.source_count,
                "matches_url": matches_url,
                "total_final_matches": len(finals),
                "matches": finals,
            }

            output_file = output_dir / f"{target.event_id}.json"
            output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="")
            saved += 1
            checkpoint.mark_done(
                ck,
                meta={
                    "event_id": target.event_id,
                    "event_name": target.event_name,
                    "total_final_matches": len(finals),
                    "output_file": str(output_file),
                },
            )
            logger.info("Saved %s final matches -> %s", len(finals), output_file)
        except RiskControlTriggered as exc:
            checkpoint.mark_failed(ck, f"risk_control: {exc}")
            raise
        except Exception as exc:
            failed += 1
            checkpoint.mark_failed(ck, str(exc))
            logger.error("Failed %s: %s", target.event_name, exc)

    return saved, skipped, failed


def run(args: argparse.Namespace) -> int:
    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    db_path = Path(args.db_path)
    storage_state = Path(args.storage_state)
    checkpoint = CheckpointStore(Path(args.checkpoint))

    if not output_dir.exists():
        logger.error("Output dir does not exist: %s", output_dir)
        return 2

    targets = collect_target_events(source_dir=source_dir, db_path=db_path)
    if not targets:
        logger.warning("No target events found after filtering.")
        return 0

    delay_cfg = DelayConfig(
        min_request_sec=args.min_delay,
        max_request_sec=args.max_delay,
        min_player_gap_sec=3.0,
        max_player_gap_sec=8.0,
    )

    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        logger.error("patchright is required. Install with: pip install patchright && python -m patchright install chromium")
        return 2

    with sync_playwright() as p:
        profile = random.choice(select_browser_profiles())
        context_kwargs: dict[str, Any] = {
            "viewport": random.choice(profile["viewport_choices"]),
            "locale": "en-US",
            "timezone_id": "Asia/Shanghai",
            "user_agent": profile["user_agent"],
            "device_scale_factor": random.choice(profile["dpr_choices"]),
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

        via_cdp, browser, _, page = open_browser_page(
            p,
            use_cdp=True,
            cdp_port=args.cdp_port,
            cdp_only=False,
            launch_kwargs={"headless": args.headless, "slow_mo": args.slow_mo},
            context_kwargs=context_kwargs,
            log_prefix="team-matches",
        )

        if via_cdp:
            verify_cdp_session_or_prompt(page, EVENTS_URL, delay_cfg)
        else:
            ensure_logged_in(page, EVENTS_URL, delay_cfg, storage_state, args.init_session)
            if args.init_session:
                logger.info("Session initialized. Exiting due to --init-session.")
                close_browser_page(via_cdp, browser, page)
                return 0

        try:
            saved, skipped, failed = scrape_targets(
                page=page,
                targets=targets,
                output_dir=output_dir,
                delay_cfg=delay_cfg,
                checkpoint=checkpoint,
                force=bool(args.force),
                max_prev_pages=args.max_prev_pages,
                limit_events=args.limit_events,
            )
        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            close_browser_page(via_cdp, browser, page)
            return 3

        close_browser_page(via_cdp, browser, page)

    logger.info("Completed. saved=%s skipped=%s failed=%s", saved, skipped, failed)
    return 0 if failed == 0 else 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape ITTF team event final matches")
    parser.add_argument("--source-dir", default="data/matches_complete/orig")
    parser.add_argument("--output-dir", default="data/team_matches/orig")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--storage-state", default="data/session/ittf_storage_state.json")
    parser.add_argument("--checkpoint", default="data/checkpoints/team_matches_checkpoint.json")
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--init-session", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--min-delay", type=float, default=3.0)
    parser.add_argument("--max-delay", type=float, default=8.0)
    parser.add_argument("--max-prev-pages", type=int, default=40, help="Max previous pages to traverse after End")
    parser.add_argument("--limit-events", type=int, default=0, help="Debug mode: only scrape first N events")
    parser.add_argument("--force", action="store_true")
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
