#!/usr/bin/env python3
"""
ITTF ranking scraper scaffold based on the shared Playwright utilities.

Current scope:
- open the requested ranking page
- verify page access and basic table presence
- save raw HTML snapshot for parser development

Next step:
- implement structured ranking row parsing and JSON output
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from lib.anti_bot import DelayConfig, RiskControlTriggered
from lib.browser_session import ensure_logged_in
from lib.page_ops import guarded_goto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_ranking_scraper")

BASE_URL = "https://results.ittf.link"
RANKING_URLS = {
    "women": f"{BASE_URL}/ittf-rankings/ittf-ranking-women-singles",
    "men": f"{BASE_URL}/ittf-rankings/ittf-ranking-men-singles",
    "women_doubles": f"{BASE_URL}/ittf-rankings/ittf-ranking-women-doubles",
    "men_doubles": f"{BASE_URL}/ittf-rankings/ittf-ranking-men-doubles",
    "mixed": f"{BASE_URL}/ittf-rankings/ittf-ranking-mixed-doubles",
}
SEARCH_URL = f"{BASE_URL}/index.php/matches/players-matches-per-event"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF ranking scraper scaffold")
    parser.add_argument("--category", choices=sorted(RANKING_URLS.keys()), default="women")
    parser.add_argument("--storage-state", default="data/session/ittf_storage_state.json")
    parser.add_argument("--init-session", action="store_true", help="Open browser for manual login and save storage state")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--snapshot-dir", default="data/ranking_snapshots")
    parser.add_argument("--cdp-port", type=int, default=9222)
    return parser


def run(args: argparse.Namespace) -> int:
    storage_state = Path(args.storage_state)
    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    delay_cfg = DelayConfig(
        min_request_sec=3.0,
        max_request_sec=8.0,
        min_player_gap_sec=5.0,
        max_player_gap_sec=10.0,
    )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Please install Playwright first: pip install playwright && playwright install")
        return 2

    target_url = RANKING_URLS[args.category]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slow_mo)
        context = browser.new_context(storage_state=str(storage_state) if storage_state.exists() else None)
        page = context.new_page()

        try:
            ensure_logged_in(page, SEARCH_URL, delay_cfg, storage_state, args.init_session)
            guarded_goto(page, target_url, delay_cfg, f"open ranking page: {args.category}")

            table_count = page.locator("table").count()
            if table_count == 0:
                logger.error("No table found on ranking page: %s", target_url)
                browser.close()
                return 3

            html = page.content()
            snapshot_path = snapshot_dir / f"{args.category}.html"
            snapshot_path.write_text(html, encoding="utf-8")
            logger.info("Saved ranking snapshot: %s", snapshot_path)
        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            browser.close()
            return 4

        browser.close()

    logger.info("Ranking scaffold completed")
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = run(args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
