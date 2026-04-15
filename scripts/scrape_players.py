#!/usr/bin/env python3
"""
ITTF player scraper — Men's / Women's Singles Top N.

Scrapes the ITTF ranking page for the specified gender and extracts
only the player name and association (country) for each athlete.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.anti_bot import DelayConfig, RiskControlTriggered
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.capture import save_json
from lib.navigation_runtime import open_page_with_verification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_player_scraper")

RANKINGS_INDEX_URL = "https://www.ittf.com/rankings/"

GENDER_CONFIG = {
    "female": {
        "label": "Women's Singles",
        "href_key": "ittf-ranking-women-singles",
        "canonical_url": "https://www.ittf.com/index.php/ittf-rankings/ittf-ranking-women-singles",
        "filename_prefix": "women_singles",
    },
    "male": {
        "label": "Men's Singles",
        "href_key": "ittf-ranking-men-singles",
        "canonical_url": "https://www.ittf.com/index.php/ittf-rankings/ittf-ranking-men-singles",
        "filename_prefix": "men_singles",
    },
}


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF player scraper (name + assoc)")
    parser.add_argument(
        "--gender",
        choices=["male", "female"],
        required=True,
        help="Gender category to scrape: 'male' (Men's Singles) or 'female' (Women's Singles)",
    )
    parser.add_argument("--top", type=int, default=100, help="Number of top players to scrape (default: 100)")
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP port of an existing Chrome to reuse (default: 9222)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--slow-mo", type=int, default=100, help="Slow motion delay in ms")
    parser.add_argument("--output-dir", default="data/players/orig", help="Output directory")
    return parser


# ---------------------------------------------------------------------------
# URL discovery
# ---------------------------------------------------------------------------


def find_ranking_url(page: Any, gender: str) -> str | None:
    """Find the ranking URL for the given gender on the rankings index page."""
    cfg = GENDER_CONFIG[gender]
    href_key = cfg["href_key"]
    label = cfg["label"].lower().replace("'", "\u2019").replace("\u2019", "'")

    try:
        page.locator(f"a[href*='{href_key}']:not([href*='-2'])").first.wait_for(timeout=15000)
    except Exception:
        pass

    links = page.locator("a")
    for idx in range(links.count()):
        try:
            link = links.nth(idx)
            href = link.get_attribute("href") or ""
            href_lower = href.lower()
            text = _normalize_space(link.inner_text()).replace("\u2019", "'").lower()

            if href_key in href_lower and "-2" not in href_lower:
                full_url = href if href.startswith("http") else f"https://www.ittf.com{href}"
                logger.info("Found %s URL by href: %s -> %s", cfg["label"], text, full_url)
                return full_url

            gender_word = "women" if gender == "female" else "men"
            if (gender_word in text and "singles" in text) and "-2" not in href_lower:
                full_url = href if href.startswith("http") else f"https://www.ittf.com{href}"
                logger.info("Found %s URL by text: %s -> %s", cfg["label"], text, full_url)
                return full_url
        except Exception:
            continue

    logger.warning("Could not find %s link on the index page, falling back to canonical URL", cfg["label"])
    return cfg["canonical_url"]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _first_text(row: Any, selectors: list[str]) -> str:
    for selector in selectors:
        try:
            loc = row.locator(selector).first
            if loc.count() > 0:
                return _normalize_space(loc.inner_text())
        except Exception:
            continue
    return ""


def _parse_player_row(row: Any) -> dict[str, str] | None:
    """Extract only name and assoc from a ranking row."""
    cells = row.locator("td")
    if cells.count() < 2:
        return None

    # Verify there is a rank number (to skip header-like rows)
    rank_text = _first_text(
        row,
        [
            "span.rank",
            "td.fab_rank_ws___Position",
            "td.fab_rank_ms___Position",
            "td.fab_rank_ws___Num",
            "td.fab_rank_ms___Num",
            "td:nth-of-type(1)",
        ],
    )
    if not re.search(r"\d+", rank_text):
        return None

    name = _first_text(
        row,
        [
            "td.fab_rank_ws___Name",
            "td.fab_rank_ms___Name",
            "td:nth-of-type(2)",
        ],
    )
    if not name:
        return None

    assoc = _first_text(
        row,
        [
            "td.rcellc.assoc",
            "td.fab_rank_ws___Country",
            "td.fab_rank_ms___Country",
            "td.fab_rank_ws___Flag",
            "td.fab_rank_ms___Flag",
            "td:nth-of-type(3)",
        ],
    )

    return {"name": name, "assoc": assoc}


def parse_players(page: Any, top_n: int) -> list[dict[str, str]]:
    """Parse player name + assoc from the ranking table."""
    players: list[dict[str, str]] = []

    rows = page.locator("tr.rrow")
    if rows.count() == 0:
        rows = page.locator("table#list_58_com_fabrik_58 tr.fabrik_row")

    row_count = rows.count()
    if row_count == 0:
        logger.error("No ranking rows found on page")
        return players

    for idx in range(min(row_count, top_n)):
        row = rows.nth(idx)
        player = _parse_player_row(row)
        if player is not None:
            players.append(player)

    return players[:top_n]


# ---------------------------------------------------------------------------
# Run / Save
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = GENDER_CONFIG[args.gender]
    players: list[dict[str, str]] = []

    delay_cfg = DelayConfig(
        min_request_sec=3.0,
        max_request_sec=8.0,
        min_player_gap_sec=5.0,
        max_player_gap_sec=10.0,
    )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Please install Playwright: pip install playwright && playwright install")
        return 2

    with sync_playwright() as p:
        via_cdp, browser, context, page = open_browser_page(
            p,
            use_cdp=True,
            cdp_port=args.cdp_port,
            launch_kwargs={"headless": args.headless, "slow_mo": args.slow_mo},
            context_kwargs={},
            log_prefix="players",
        )

        try:
            logger.info("Navigating to ITTF rankings index: %s", RANKINGS_INDEX_URL)
            open_page_with_verification(
                page,
                RANKINGS_INDEX_URL,
                delay_cfg,
                "open rankings index",
                sleep_first=False,
                require_real_content=True,
                manual_prompt_lines=[
                    "Page does not appear to have loaded real content (possible Cloudflare challenge).",
                    "If you see a verification page, please complete it in the browser.",
                ],
                manual_prompt="Press ENTER after the real page has loaded...",
            )

            ranking_url = find_ranking_url(page, args.gender)
            if not ranking_url:
                logger.error("Could not find %s link on %s", cfg["label"], RANKINGS_INDEX_URL)
                close_browser_page(via_cdp, browser, page)
                return 3

            logger.info("Navigating to %s ranking: %s", cfg["label"], ranking_url)
            open_page_with_verification(
                page,
                ranking_url,
                delay_cfg,
                f"open {cfg['label']} ranking",
                require_real_content=True,
                manual_prompt_lines=[
                    "Page does not appear to have loaded real content (possible Cloudflare challenge).",
                    "If you see a verification page, please complete it in the browser.",
                ],
                manual_prompt="Press ENTER after the real page has loaded...",
            )

            logger.info("Parsing players (top %d)...", args.top)
            players = parse_players(page, args.top)
            if not players:
                logger.error("Parsed 0 players")
                close_browser_page(via_cdp, browser, page)
                return 5

            logger.info("Parsed %d players", len(players))
            output_path = _save_output(output_dir, players, args.gender, args.top)
            logger.info("Saved player data: %s", output_path)

        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            close_browser_page(via_cdp, browser, page)
            return 4
        finally:
            close_browser_page(via_cdp, browser, page)

    logger.info("Player scrape completed: %d players", len(players))
    return 0


def _save_output(
    output_dir: Path,
    players: list[dict[str, str]],
    gender: str,
    top_n: int,
) -> Path:
    cfg = GENDER_CONFIG[gender]
    payload = {
        "category": cfg["filename_prefix"],
        "scraped_at": datetime.now().isoformat(),
        "top_n": top_n,
        "total_players": len(players),
        "players": players,
    }

    filename = f"{cfg['filename_prefix']}_top{top_n}.json"
    output_path = output_dir / filename
    save_json(output_path, payload)
    return output_path


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = run(args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
