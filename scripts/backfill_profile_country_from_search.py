#!/usr/bin/env python3
"""
Backfill country/country_code for existing player profile JSON files by using
the first visible autocomplete candidate on the ITTF player search page.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

from lib.anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep, type_like_human
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.browser_session import ensure_logged_in
from lib.navigation_runtime import verify_cdp_session_or_prompt
from lib.page_ops import guarded_goto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_profile_country_backfill")

BASE_URL = "https://results.ittf.link"
SEARCH_URL = f"{BASE_URL}/index.php/players-profiles"
COUNTRY_RE = re.compile(r"\(([A-Z]{3})\)\s*$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill profile country fields from ITTF search autocomplete")
    parser.add_argument("--players-file", default="tmp/profiles_tobe_update.txt")
    parser.add_argument("--profile-dir", default="data/player_profiles/orig")
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without writing files")
    parser.add_argument("--force", action="store_true", help="Re-query and update even when country fields are already non-empty")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP remote debugging port")
    parser.add_argument("--cdp-only", action="store_true", help="Require existing CDP browser only")
    parser.add_argument("--storage-state", default="data/session/ittf_storage_state.json")
    parser.add_argument("--init-session", action="store_true", help="Open browser for manual login and save storage state")
    parser.add_argument("--min-delay", type=float, default=1.0)
    parser.add_argument("--max-delay", type=float, default=2.0)
    parser.add_argument("--min-player-gap", type=float, default=1.0)
    parser.add_argument("--max-player-gap", type=float, default=2.0)
    return parser


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def load_players(players_file: Path) -> list[tuple[str, str]]:
    players: list[tuple[str, str]] = []
    for lineno, raw_line in enumerate(players_file.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",", 1)]
        if len(parts) != 2:
            logger.warning("Skip malformed line %s: %s", lineno, raw_line)
            continue
        player_id, player_name = parts
        if not re.fullmatch(r"\d+", player_id):
            logger.warning("Skip invalid player_id on line %s: %s", lineno, raw_line)
            continue
        player_name = normalize_space(player_name)
        if not player_name:
            logger.warning("Skip empty player_name on line %s: %s", lineno, raw_line)
            continue
        players.append((player_id, player_name))
    return players


def find_profile_path(profile_dir: Path, player_id: str) -> Path | None:
    matches = sorted(profile_dir.glob(f"player_{player_id}_*.json"))
    if not matches:
        return None
    if len(matches) > 1:
        logger.warning("Multiple profile files found for player_id=%s, using first: %s", player_id, matches[0].name)
    return matches[0]


def has_country_fields(profile_data: dict[str, Any]) -> bool:
    return bool(normalize_space(str(profile_data.get("country") or ""))) and bool(
        normalize_space(str(profile_data.get("country_code") or ""))
    )


def extract_country_code(candidate_text: str) -> str:
    match = COUNTRY_RE.search(normalize_space(candidate_text))
    return match.group(1).upper() if match else ""


def split_candidate_name_and_country(candidate_text: str) -> tuple[str, str]:
    normalized = normalize_space(candidate_text)
    match = re.match(r"^(.*?)\s*\(([A-Z]{3})\)\s*$", normalized)
    if not match:
        return normalized, ""
    return normalize_space(match.group(1)), match.group(2).upper()


def fetch_matching_autocomplete_candidate(page: Any, player_name: str) -> str:
    search_input = page.locator("input[type='text']").first
    if search_input.count() == 0:
        raise RuntimeError("search input not found")

    try:
        search_input.click(timeout=2000)
        search_input.fill("")
    except Exception as exc:
        raise RuntimeError(f"failed to reset search input: {exc}") from exc

    type_like_human(page, search_input, player_name)
    time.sleep(1.2)

    for _ in range(20):
        candidates = page.locator(
            "ul.dropdown-menu[role='menu']:visible li > a[data-value], "
            "ul.ui-autocomplete:visible li > a[data-value], "
            "ul[id*='ui-id']:visible li > a[data-value], "
            ".ui-autocomplete:visible li > a[data-value], "
            "[role='listbox']:visible li > a[data-value]"
        )
        try:
            count = min(candidates.count(), 20)
        except Exception:
            count = 0
        for i in range(count):
            item = candidates.nth(i)
            try:
                if not item.is_visible():
                    continue
                text = normalize_space(item.inner_text() or "")
                candidate_name, _ = split_candidate_name_and_country(text)
                if candidate_name == player_name:
                    return text
            except Exception:
                continue
        time.sleep(0.25)

    raise RuntimeError(f"autocomplete exact match not found for {player_name}")


def write_profile(profile_path: Path, profile_data: dict[str, Any]) -> None:
    profile_path.write_text(json.dumps(profile_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    if not profile_dir.exists():
        logger.error("Profile dir not found: %s", profile_dir)
        return 2

    players = load_players(players_file)
    if not players:
        logger.info("No valid players loaded from %s", players_file)
        return 0

    storage_state = Path(args.storage_state)
    delay_cfg = DelayConfig(
        min_request_sec=args.min_delay,
        max_request_sec=args.max_delay,
        min_player_gap_sec=args.min_player_gap,
        max_player_gap_sec=args.max_player_gap,
    )

    updated_count = 0
    skipped_count = 0
    failed_count = 0

    with sync_playwright() as p:
        via_cdp, browser, context, page = open_browser_page(
            p,
            use_cdp=True,
            cdp_port=args.cdp_port,
            cdp_only=args.cdp_only,
            launch_kwargs={"headless": args.headless, "slow_mo": args.slow_mo},
            context_kwargs={},
            log_prefix="profile-country-backfill",
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

            for idx, (player_id, player_name) in enumerate(players, 1):
                profile_path = find_profile_path(profile_dir, player_id)
                if profile_path is None:
                    failed_count += 1
                    logger.error("[%d/%d] Profile file not found for player_id=%s name=%s", idx, len(players), player_id, player_name)
                    continue

                try:
                    profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    failed_count += 1
                    logger.error("[%d/%d] Failed to read profile %s: %s", idx, len(players), profile_path.name, exc)
                    continue

                if not isinstance(profile_data, dict):
                    failed_count += 1
                    logger.error("[%d/%d] Invalid profile JSON object: %s", idx, len(players), profile_path.name)
                    continue

                if has_country_fields(profile_data) and not args.force:
                    skipped_count += 1
                    logger.info(
                        "[%d/%d] Skip existing country fields: %s (%s) file=%s",
                        idx,
                        len(players),
                        player_name,
                        player_id,
                        profile_path.name,
                    )
                    continue

                if has_country_fields(profile_data) and args.force:
                    logger.info(
                        "[%d/%d] Force re-query existing country fields: %s (%s) file=%s current=%s/%s",
                        idx,
                        len(players),
                        player_name,
                        player_id,
                        profile_path.name,
                        normalize_space(str(profile_data.get("country") or "")),
                        normalize_space(str(profile_data.get("country_code") or "")),
                    )

                logger.info("[%d/%d] Query country for %s (%s)", idx, len(players), player_name, player_id)

                try:
                    guarded_goto(page, SEARCH_URL, delay_cfg, f"open profiles search page for {player_name}")
                    candidate_text = fetch_matching_autocomplete_candidate(page, player_name)

                    risk = detect_risk(page)
                    if risk:
                        raise RiskControlTriggered(risk)

                    country_code = extract_country_code(candidate_text)
                    if not country_code:
                        raise RuntimeError(f"country code not found in first candidate: {candidate_text}")

                    logger.info(
                        "[%d/%d] First candidate=%s -> country_code=%s",
                        idx,
                        len(players),
                        candidate_text,
                        country_code,
                    )

                    profile_data["country"] = country_code
                    profile_data["country_code"] = country_code

                    if args.dry_run:
                        logger.info("[%d/%d] Dry-run only, skip write: %s", idx, len(players), profile_path.name)
                    else:
                        write_profile(profile_path, profile_data)
                        logger.info("[%d/%d] Updated profile: %s", idx, len(players), profile_path.name)

                    updated_count += 1
                    human_sleep(delay_cfg.min_player_gap_sec, delay_cfg.max_player_gap_sec, "gap between profile country lookups")

                except RiskControlTriggered:
                    raise
                except Exception as exc:
                    failed_count += 1
                    logger.error("[%d/%d] Failed query for %s (%s): %s", idx, len(players), player_name, player_id, exc)
                    human_sleep(1.5, 3.0, "cool down after failure")

            close_browser_page(via_cdp, browser, page)

        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            close_browser_page(via_cdp, browser, page)
            return 4
        except Exception as exc:
            logger.error("Fatal error: %s", exc)
            close_browser_page(via_cdp, browser, page)
            return 4

    logger.info(
        "Completed profile country backfill. updated=%d skipped=%d failed=%d dry_run=%s",
        updated_count,
        skipped_count,
        failed_count,
        args.dry_run,
    )
    return 0 if failed_count == 0 else 1


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
