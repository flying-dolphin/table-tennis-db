#!/usr/bin/env python3
"""
Scrape ITTF player profiles by searching player name on players-profiles page.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from lib.anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.browser_session import ensure_logged_in
from lib.checkpoint import CheckpointStore
from lib.navigation_runtime import verify_cdp_session_or_prompt
from lib.page_ops import guarded_goto
from scrape_matches import click_go, open_or_select_autocomplete
from scrape_profiles import scrape_player_profile

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
    parser.add_argument("--players-file", required=True, help="JSON file with players to scrape")
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
        english_name = _normalize_space(str(item.get("english_name") or item.get("name") or ""))
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


def run(args: argparse.Namespace) -> int:
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        logger.error("patchright is required. Install with: pip install patchright && python -m patchright install chromium")
        return 2

    players_file = Path(args.players_file)
    if not players_file.exists():
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

                if checkpoint.is_done(ck_key) and not args.force:
                    logger.info("[%d/%d] Skip by checkpoint: %s (%s)", idx, len(players), english_name, expected_country or "N/A")
                    continue

                logger.info("[%d/%d] Searching profile: %s (%s)", idx, len(players), english_name, expected_country or "N/A")

                try:
                    guarded_goto(page, SEARCH_URL, delay_cfg, f"open profiles search page for {english_name}")
                    if not open_or_select_autocomplete(page, english_name, expected_country):
                        raise RuntimeError("autocomplete option not selected")

                    human_sleep(2.0, 4.0, "before click Go on profile search")
                    if not click_go(page):
                        raise RuntimeError("Go button not found on profile search page")

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
                    if not selected_name:
                        selected_name = english_name

                    if _normalize_name_key(selected_name) != _normalize_name_key(english_name):
                        raise RuntimeError(f"selected name mismatch: expected={english_name}, got={selected_name}")

                    if expected_country and selected_country and expected_country.upper() != selected_country.upper():
                        raise RuntimeError(f"selected country mismatch: expected={expected_country}, got={selected_country}")

                    player_id = _extract_player_id_from_page(page)
                    if not player_id:
                        raise RuntimeError("player_id not found after search submit")

                    profile_url = page.url
                    player_info = {
                        "player_id": player_id,
                        "name": selected_name,
                        "english_name": selected_name,
                        "country": selected_country or expected_country,
                        "country_code": selected_country or expected_country,
                        "rank": 0,
                        "points": 0,
                        "change": 0,
                    }

                    profile_data, _ = scrape_player_profile(
                        page,
                        profile_url,
                        player_info,
                        delay_cfg,
                        profile_orig_dir,
                        avatar_dir,
                        db_path,
                        checkpoint=None,
                        force=args.force,
                        category="search",
                    )

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
