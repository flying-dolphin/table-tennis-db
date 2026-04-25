#!/usr/bin/env python3
"""
Scrape ITTF player profiles by searching player name on players-profiles page.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.capture import sanitize_filename, save_json
from lib.browser_session import ensure_logged_in
from lib.checkpoint import CheckpointStore
from lib.name_normalizer import normalize_player_name
from lib.navigation_runtime import verify_cdp_session_or_prompt
from lib.page_ops import guarded_goto
from lib.profile_search_ui import click_go, open_or_select_autocomplete
from scrape_profiles import download_player_avatar, extract_profile_info

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_profile_search_scraper")

BASE_URL = "https://results.ittf.link"
SEARCH_URL = f"{BASE_URL}/index.php/players-profiles"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape ITTF profiles by player search")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--players-file", help="JSON file with players to scrape")
    mode.add_argument("--player-name", help="Single player name to search and scrape")
    parser.add_argument("--country-code", help="Country code for --player-name (e.g. CHN)")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP remote debugging port")
    parser.add_argument("--cdp-only", action="store_true", help="Require existing CDP browser only")
    parser.add_argument("--storage-state", default="data/session/ittf_storage_state.json")
    parser.add_argument("--init-session", action="store_true", help="Open browser for manual login and save storage state")

    parser.add_argument("--profile-dir", default="data/player_profiles")
    parser.add_argument("--avatar-dir", default="data/player_avatars")
    parser.add_argument("--db-path", default="data/db/ittf.db")

    parser.add_argument("--checkpoint", default="data/player_profiles/checkpoint_scrape_profiles_from_search.json")
    parser.add_argument("--force", action="store_true", help="Ignore checkpoint completed marks")
    parser.add_argument("--rebuild-checkpoint", action="store_true", help="Reset checkpoint before scraping")

    parser.add_argument("--min-delay", type=float, default=5.0)
    parser.add_argument("--max-delay", type=float, default=10.0)
    parser.add_argument("--min-player-gap", type=float, default=5.0)
    parser.add_argument("--max-player-gap", type=float, default=10.0)
    return parser


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_name_key(value: str) -> str:
    parts = re.findall(r"[a-z0-9]+", (value or "").lower())
    return " ".join(parts)


def _extract_player_name_country(display_value: str) -> tuple[str, str]:
    value = _normalize_space(display_value)
    m = re.match(r"^(.*?)\s*\(([A-Z]{3})\)\s*$", value)
    if not m:
        return value, ""
    return _normalize_space(m.group(1)), m.group(2).upper()


def _extract_player_id_from_url(url: str) -> str | None:
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        for key in ("vw_profiles___player_id_raw", "player_id_raw"):
            values = query.get(key, [])
            if values and re.fullmatch(r"\d+", values[0] or ""):
                return values[0]
    except Exception:
        pass

    m = re.search(r"(?:vw_profiles___)?player_id_raw=(\d+)", url or "")
    if m:
        return m.group(1)
    return None


def _extract_player_id_from_page(page: Any) -> str | None:
    player_id = _extract_player_id_from_url(page.url)
    if player_id:
        return player_id

    candidates = [
        "input[name='vw_profiles___player_id_raw']",
        "input[name='player_id_raw']",
        "input[id*='player_id_raw']",
    ]
    for sel in candidates:
        locator = page.locator(sel).first
        try:
            if locator.count() == 0:
                continue
            value = _normalize_space(locator.input_value() or locator.get_attribute("value") or "")
            if re.fullmatch(r"\d+", value):
                return value
        except Exception:
            continue
    return None


def _extract_name_and_player_id_from_row_name(name_text: str) -> tuple[str, str]:
    value = _normalize_space(name_text)
    m = re.match(r"^(.*?)\s*\(#(\d+)\)\s*$", value)
    if not m:
        return normalize_player_name(value), ""
    return normalize_player_name(_normalize_space(m.group(1))), m.group(2)


def _wait_profile_result_row(page: Any, expected_name: str, timeout_sec: float = 12.0) -> tuple[Any, str, str]:
    expected_key = _normalize_name_key(expected_name)
    deadline = time.time() + timeout_sec
    last_rows = 0

    table = page.locator("table#list_33_com_fabrik_33, table[id^='list_'][id*='_com_fabrik_']").first
    while time.time() < deadline:
        try:
            if table.count() == 0:
                time.sleep(0.25)
                continue
            rows = table.locator("tbody tr.fabrik_row")
            row_count = rows.count()
            last_rows = row_count
            if row_count == 0:
                time.sleep(0.25)
                continue

            fallback_row = None
            fallback_name = ""
            fallback_id = ""
            for idx in range(row_count):
                row = rows.nth(idx)
                name_cell = row.locator("td.vw_profiles___name").first
                if name_cell.count() == 0:
                    continue
                row_name_text = _normalize_space(name_cell.inner_text())
                row_name, row_player_id = _extract_name_and_player_id_from_row_name(row_name_text)
                if not row_name:
                    continue
                if fallback_row is None:
                    fallback_row = row
                    fallback_name = row_name
                    fallback_id = row_player_id
                if _normalize_name_key(row_name) == expected_key and row_player_id:
                    return row, row_name, row_player_id

            if fallback_row is not None and fallback_id:
                logger.info(
                    "Profile result row fallback matched first row: expected=%s got=%s player_id=%s",
                    expected_name,
                    fallback_name,
                    fallback_id,
                )
                return fallback_row, fallback_name, fallback_id
        except Exception:
            pass
        time.sleep(0.25)

    raise RuntimeError(f"profile result row not ready in {timeout_sec:.1f}s (expected={expected_name}, rows={last_rows})")


def _build_single_player(name: str, country_code: str) -> list[dict[str, Any]]:
    return [{
        "english_name": normalize_player_name(_normalize_space(name)),
        "country_code": _normalize_space(country_code).upper(),
        "name_zh": "",
    }]


def _load_players(players_file: Path) -> list[dict[str, Any]]:
    payload = json.loads(players_file.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        players = payload.get("players", [])
    elif isinstance(payload, list):
        players = payload
    else:
        players = []
    if not isinstance(players, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in players:
        if not isinstance(item, dict):
            continue
        english_name = normalize_player_name(_normalize_space(str(item.get("english_name") or item.get("name") or "")))
        if not english_name:
            continue
        country_code = _normalize_space(str(item.get("country_code") or "")).upper()
        cleaned.append(
            {
                "english_name": english_name,
                "country_code": country_code,
                "name_zh": _normalize_space(str(item.get("name_zh") or "")),
            }
        )
    return cleaned


def _slugify(name: str) -> str:
    value = re.sub(r"[^\w\s-]", "", (name or "").lower())
    value = re.sub(r"[\s_-]+", "-", value).strip("-")
    return value or "player"


def _orig_player_key(english_name: str, country_code: str) -> str:
    return f"{_normalize_name_key(english_name)}|{_normalize_space(country_code).upper()}"


def _load_existing_orig_keys(profile_orig_dir: Path) -> set[str]:
    keys: set[str] = set()
    if not profile_orig_dir.exists():
        return keys
    for p in profile_orig_dir.glob("player_*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        english_name = normalize_player_name(_normalize_space(str(data.get("english_name") or data.get("name") or "")))
        country_code = _normalize_space(str(data.get("country_code") or "")).upper()
        if not english_name:
            continue
        keys.add(_orig_player_key(english_name, country_code))
    return keys


def save_player_to_players_table(db_path: Path, profile_data: dict[str, Any]) -> None:
    player_id_raw = profile_data.get("player_id")
    if not re.fullmatch(r"\d+", str(player_id_raw or "")):
        raise RuntimeError(f"invalid player_id for players upsert: {player_id_raw}")
    player_id = int(str(player_id_raw))

    name = _normalize_space(str(profile_data.get("name") or profile_data.get("english_name") or ""))
    if not name:
        raise RuntimeError("missing player name for players upsert")
    country_code = _normalize_space(str(profile_data.get("country_code") or "")).upper()
    if not country_code:
        raise RuntimeError("missing country_code for players upsert")
    slug = f"{_slugify(name)}-{player_id}"

    career_stats = profile_data.get("career_stats") if isinstance(profile_data.get("career_stats"), dict) else {}
    year_stats = profile_data.get("current_year_stats") if isinstance(profile_data.get("current_year_stats"), dict) else {}

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO players (
                player_id, name, slug, country, country_code,
                gender, birth_year, age,
                style, playing_hand, grip,
                avatar_url, avatar_file,
                career_events, career_matches, career_wins, career_losses,
                career_wtt_titles, career_all_titles,
                career_best_rank, career_best_week,
                year_events, year_matches, year_wins, year_losses,
                year_games, year_games_won, year_games_lost,
                year_wtt_titles, year_all_titles,
                scraped_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                name = excluded.name,
                country = excluded.country,
                country_code = excluded.country_code,
                gender = excluded.gender,
                birth_year = excluded.birth_year,
                age = excluded.age,
                style = excluded.style,
                playing_hand = excluded.playing_hand,
                grip = excluded.grip,
                avatar_url = excluded.avatar_url,
                avatar_file = excluded.avatar_file,
                career_events = excluded.career_events,
                career_matches = excluded.career_matches,
                career_wins = excluded.career_wins,
                career_losses = excluded.career_losses,
                career_wtt_titles = excluded.career_wtt_titles,
                career_all_titles = excluded.career_all_titles,
                career_best_rank = excluded.career_best_rank,
                career_best_week = excluded.career_best_week,
                year_events = excluded.year_events,
                year_matches = excluded.year_matches,
                year_wins = excluded.year_wins,
                year_losses = excluded.year_losses,
                year_games = excluded.year_games,
                year_games_won = excluded.year_games_won,
                year_games_lost = excluded.year_games_lost,
                year_wtt_titles = excluded.year_wtt_titles,
                year_all_titles = excluded.year_all_titles,
                scraped_at = excluded.scraped_at,
                updated_at = excluded.updated_at
            """,
            (
                player_id,
                name,
                slug,
                profile_data.get("country"),
                country_code,
                profile_data.get("gender") or "Female",
                profile_data.get("birth_year"),
                profile_data.get("age"),
                profile_data.get("style"),
                profile_data.get("playing_hand"),
                profile_data.get("grip"),
                profile_data.get("avatar_url"),
                profile_data.get("avatar_file_path"),
                int(career_stats.get("events", 0) or 0),
                int(career_stats.get("matches", 0) or 0),
                int(career_stats.get("wins", 0) or 0),
                int(career_stats.get("loses", 0) or 0),
                int(career_stats.get("wtt_senior_titles", 0) or 0),
                int(career_stats.get("all_senior_titles", 0) or 0),
                profile_data.get("career_best_rank"),
                profile_data.get("career_best_week"),
                int(year_stats.get("events", 0) or 0),
                int(year_stats.get("matches", 0) or 0),
                int(year_stats.get("wins", 0) or 0),
                int(year_stats.get("loses", 0) or 0),
                int(year_stats.get("games", 0) or 0),
                int(year_stats.get("games_won", 0) or 0),
                int(year_stats.get("games_lost", 0) or 0),
                int(year_stats.get("wtt_senior_titles", 0) or 0),
                int(year_stats.get("all_senior_titles", 0) or 0),
                profile_data.get("scraped_at"),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def run(args: argparse.Namespace) -> int:
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        logger.error("patchright is required. Install with: pip install patchright && python -m patchright install chromium")
        return 2

    players_file = Path(args.players_file) if args.players_file else None
    if players_file and not players_file.exists():
        logger.error("Players file not found: %s", players_file)
        return 2

    profile_dir = Path(args.profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_orig_dir = profile_dir / "orig"
    profile_orig_dir.mkdir(parents=True, exist_ok=True)

    avatar_dir = Path(args.avatar_dir)
    avatar_dir.mkdir(parents=True, exist_ok=True)

    db_path = Path(args.db_path)
    storage_state = Path(args.storage_state)
    checkpoint = CheckpointStore(Path(args.checkpoint))
    if args.rebuild_checkpoint:
        checkpoint.reset()

    if args.player_name:
        players = _build_single_player(args.player_name, args.country_code or "")
    else:
        players = _load_players(players_file)
    if not players:
        logger.info("No players to scrape.")
        return 0

    delay_cfg = DelayConfig(
        min_request_sec=args.min_delay,
        max_request_sec=args.max_delay,
        min_player_gap_sec=args.min_player_gap,
        max_player_gap_sec=args.max_player_gap,
    )

    logger.info("Loaded %d players for profile search scrape", len(players))
    existing_orig_keys: set[str] = set()
    if not args.force:
        existing_orig_keys = _load_existing_orig_keys(profile_orig_dir)
        logger.info("Loaded %d existing profiles from orig directory", len(existing_orig_keys))
    done_count = 0
    fail_count = 0

    with sync_playwright() as p:
        via_cdp, browser, context, page = open_browser_page(
            p,
            use_cdp=True,
            cdp_port=args.cdp_port,
            cdp_only=args.cdp_only,
            launch_kwargs={"headless": args.headless, "slow_mo": args.slow_mo},
            context_kwargs={},
            log_prefix="profiles-search",
        )

        try:
            if via_cdp:
                verify_cdp_session_or_prompt(page, SEARCH_URL, delay_cfg)
            else:
                ensure_logged_in(page, SEARCH_URL, delay_cfg, storage_state, args.init_session)

            if args.init_session:
                logger.info("Session initialized. Exiting due to --init-session.")
                close_browser_page(via_cdp, browser, page)
                return 0

            for idx, player in enumerate(players, 1):
                english_name = player["english_name"]
                expected_country = player["country_code"]
                ck_key = f"profile-search|{english_name.lower()}|{expected_country}"

                orig_key = _orig_player_key(english_name, expected_country)
                if (not args.force) and (orig_key in existing_orig_keys):
                    logger.info("[%d/%d] Skip by orig file: %s (%s)", idx, len(players), english_name, expected_country or "N/A")
                    continue

                logger.info("[%d/%d] Searching profile: %s (%s)", idx, len(players), english_name, expected_country or "N/A")

                try:
                    guarded_goto(page, SEARCH_URL, delay_cfg, f"open profiles search page for {english_name}")
                    if not open_or_select_autocomplete(page, english_name, expected_country):
                        raise RuntimeError("autocomplete option not selected")

                    human_sleep(2.0, 4.0, "before click Go on profile search")
                    if not click_go(
                        page,
                        prefer_same_form_as="input.vw_profiles___player_idvalue-auto-complete",
                    ):
                        raise RuntimeError("Go button not found on profile search page")

                    # Wait for AJAX content load on current search-result page
                    page.wait_for_load_state("domcontentloaded", timeout=45000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass

                    risk = detect_risk(page)
                    if risk:
                        raise RiskControlTriggered(risk)

                    auto_input = page.locator("input.vw_profiles___player_idvalue-auto-complete").first
                    selected_value = ""
                    try:
                        if auto_input.count() > 0:
                            selected_value = _normalize_space(auto_input.input_value() or auto_input.get_attribute("value") or "")
                    except Exception:
                        selected_value = ""

                    selected_name, selected_country = _extract_player_name_country(selected_value)
                    selected_name = normalize_player_name(selected_name)
                    if not selected_name:
                        selected_name = english_name

                    _, row_name, player_id = _wait_profile_result_row(page, selected_name, timeout_sec=14.0)
                    logger.info("Profile search result: name=%s country=%s player_id=%s", row_name, selected_country or "N/A", player_id or "N/A")

                    if _normalize_name_key(selected_name) != _normalize_name_key(english_name):
                        raise RuntimeError(f"selected name mismatch: expected={english_name}, got={selected_name}")

                    if expected_country and selected_country and expected_country.upper() != selected_country.upper():
                        raise RuntimeError(f"selected country mismatch: expected={expected_country}, got={selected_country}")

                    if not player_id:
                        raise RuntimeError("player_id not found after search submit")

                    profile_url = page.url
                    player_info = {
                        "player_id": player_id,
                        "name": row_name or selected_name,
                        "english_name": row_name or selected_name,
                        "country": selected_country or expected_country,
                        "country_code": selected_country or expected_country,
                        "rank": 0,
                        "points": 0,
                        "change": 0,
                    }

                    profile_data = extract_profile_info(page, player_info, profile_url)
                    avatar_meta = download_player_avatar(page, player_info, avatar_dir)
                    if avatar_meta:
                        profile_data.update(avatar_meta)

                    safe_name = sanitize_filename(player_info.get("english_name", player_info.get("name", player_id)))
                    orig_path = profile_orig_dir / f"player_{player_id}_{safe_name}.json"
                    save_json(orig_path, profile_data)
                    save_player_to_players_table(db_path, profile_data)
                    existing_orig_keys.add(orig_key)

                    if profile_data is None:
                        raise RuntimeError("profile scrape returned empty result")

                    checkpoint.mark_done(
                        ck_key,
                        meta={
                            "player_id": player_id,
                            "profile_url": profile_url,
                        },
                    )
                    done_count += 1
                    human_sleep(delay_cfg.min_player_gap_sec, delay_cfg.max_player_gap_sec, "gap between player searches")

                except RiskControlTriggered:
                    raise
                except Exception as exc:
                    fail_count += 1
                    checkpoint.mark_failed(ck_key, str(exc), meta={"english_name": english_name, "country_code": expected_country})
                    logger.error("Failed profile search for %s (%s): %s", english_name, expected_country or "N/A", exc)
                    human_sleep(2.0, 4.0, "cool down after failure")

            close_browser_page(via_cdp, browser, page)

        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            close_browser_page(via_cdp, browser, page)
            return 4
        except Exception as exc:
            logger.error("Fatal error: %s", exc)
            close_browser_page(via_cdp, browser, page)
            return 4

    logger.info("Completed profile search scrape. success=%d failed=%d", done_count, fail_count)
    return 0 if fail_count == 0 else 1


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        code = run(args)
    except KeyboardInterrupt:
        logger.error("Interrupted by user.")
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
