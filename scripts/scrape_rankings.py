#!/usr/bin/env python3
"""
ITTF ranking scraper — Women's Singles Top N.

Scrapes the Women's Singles ranking page and extracts each athlete row plus the
in-page points breakdown table embedded in the hidden detail rows.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.anti_bot import DelayConfig, RiskControlTriggered
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.capture import save_json
from lib.name_normalizer import normalize_player_name
from lib.navigation_runtime import open_page_with_verification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_ranking_scraper")

RANKINGS_INDEX_URL = "https://www.ittf.com/rankings/"
CANONICAL_WOMENS_SINGLES_URL = "https://www.ittf.com/index.php/ittf-rankings/ittf-ranking-women-singles"


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF ranking scraper (Women's Singles)")
    parser.add_argument("--top", type=int, default=100, help="Number of top players to scrape (default: 100)")
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP port of an existing Chrome to reuse (default: 9222)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--slow-mo", type=int, default=100, help="Slow motion delay in ms")
    parser.add_argument("--output-dir", default="data/rankings/orig", help="Output directory")
    parser.add_argument("--checkpoint", default="data/rankings/checkpoint_rankings.json", help="Checkpoint file path")
    parser.add_argument("--force", action="store_true", help="Ignore checkpoint, rescrape all")
    parser.add_argument("--rebuild-checkpoint", action="store_true", help="Rebuild checkpoint from existing output files")
    return parser


# ---------------------------------------------------------------------------
# URL discovery
# ---------------------------------------------------------------------------


def find_womens_singles_url(page: Any) -> str | None:
    """Find the Women's Singles ranking URL on the rankings index page."""
    try:
        page.locator("a[href*='ittf-ranking-women-singles']:not([href*='-2'])").first.wait_for(timeout=15000)
    except Exception:
        pass

    links = page.locator("a")
    for idx in range(links.count()):
        try:
            link = links.nth(idx)
            href = link.get_attribute("href") or ""
            href_lower = href.lower()
            text = _normalize_space(link.inner_text()).replace("’", "'").lower()

            if "ittf-ranking-women-singles" in href_lower and "-2" not in href_lower:
                full_url = href if href.startswith("http") else f"https://www.ittf.com{href}"
                logger.info("Found Women's Singles URL by href: %s -> %s", text, full_url)
                return full_url

            if ("women's singles" in text or ("women" in text and "singles" in text)) and "-2" not in href_lower:
                full_url = href if href.startswith("http") else f"https://www.ittf.com{href}"
                logger.info("Found Women's Singles URL by text: %s -> %s", text, full_url)
                return full_url
        except Exception:
            continue

    logger.warning("Could not find Women's Singles link on the index page, falling back to canonical URL")
    return CANONICAL_WOMENS_SINGLES_URL


# ---------------------------------------------------------------------------
# Ranking parsing
# ---------------------------------------------------------------------------


def _parse_signed_change(text: str, class_name: str = "") -> int:
    cleaned = _normalize_space(text)
    digits = re.sub(r"[^\d+-]", "", cleaned)
    if not digits:
        return 0

    class_name = (class_name or "").lower()
    if "rankdown" in class_name or "down" in class_name or "↓" in cleaned:
        return -abs(int(digits.replace("+", "")))
    if "rankup" in class_name or "up" in class_name or "↑" in cleaned:
        return abs(int(digits.replace("+", "")))

    try:
        return int(digits)
    except ValueError:
        return 0


def _first_existing_text(row: Any, selectors: list[str]) -> tuple[str, Any | None]:
    for selector in selectors:
        try:
            loc = row.locator(selector).first
            if loc.count() > 0:
                return _normalize_space(loc.inner_text()), loc
        except Exception:
            continue
    return "", None


def _extract_location(cell: Any) -> str:
    if cell is None:
        return ""
    try:
        return _normalize_space(cell.inner_text())
    except Exception:
        return ""


def _extract_category_from_cell(cell: Any) -> str:
    if cell is None:
        return ""

    try:
        inner = _normalize_space(cell.inner_text())
        if inner:
            return inner
    except Exception:
        pass

    try:
        node = cell.locator("p, span").first
        if node.count() > 0:
            class_name = node.get_attribute("class") or ""
            match = re.search(r"ev-([a-z0-9_-]+)", class_name, re.IGNORECASE)
            if match:
                return match.group(1).upper()
            text = _normalize_space(node.inner_text())
            if text:
                return text
    except Exception:
        pass

    return ""


def _get_table_headers(table: Any) -> list[str]:
    headers: list[str] = []
    try:
        header_cells = table.locator("thead th, thead td")
        if header_cells.count() > 0:
            for idx in range(header_cells.count()):
                headers.append(_normalize_space(header_cells.nth(idx).inner_text()))
            return headers

        first_row = table.locator("tr").first
        cells = first_row.locator("th, td")
        for idx in range(cells.count()):
            headers.append(_normalize_space(cells.nth(idx).inner_text()))
    except Exception:
        pass
    return headers


def _map_breakdown_columns(headers: list[str]) -> dict[str, int]:
    col_map: dict[str, int] = {}
    for idx, header in enumerate(headers):
        normalized = header.lower()
        if "event" in normalized and "event" not in col_map:
            col_map["event"] = idx
        elif "categor" in normalized and "category" not in col_map:
            col_map["category"] = idx
        elif "expir" in normalized and "expires_on" not in col_map:
            col_map["expires_on"] = idx
        elif "position" in normalized and "position" not in col_map:
            col_map["position"] = idx
        elif "point" in normalized and "points" not in col_map:
            col_map["points"] = idx
    return col_map


def _parse_breakdown_row(row: Any, col_map: dict[str, int]) -> dict[str, Any] | None:
    cells = row.locator("td")
    if cells.count() < 2:
        return None

    cell_texts: list[str] = []
    for idx in range(cells.count()):
        try:
            cell_texts.append(_normalize_space(cells.nth(idx).inner_text()))
        except Exception:
            cell_texts.append("")

    def get_col(field: str) -> str:
        col_idx = col_map.get(field)
        if col_idx is None or col_idx >= len(cell_texts):
            return ""
        return cell_texts[col_idx]

    event = get_col("event")
    if not event:
        return None

    category = get_col("category")
    if not category and cells.count() > 1:
        category = _extract_category_from_cell(cells.nth(1))

    points_text = re.sub(r"[,\s]", "", get_col("points"))
    points = int(points_text) if points_text.isdigit() else 0

    return {
        "event": event,
        "category": category,
        "expires_on": get_col("expires_on"),
        "position": get_col("position"),
        "points": points,
    }


def _find_details_row(row: Any) -> Any | None:
    try:
        details = row.locator("xpath=following-sibling::tr[contains(@class,'drow')][1]")
        if details.count() > 0:
            return details.first
    except Exception:
        pass
    return None


def _parse_rrow_row(row: Any, idx: int = 0) -> dict[str, Any] | None:
    start_time = time.time()
    cells = row.locator("td")
    if cells.count() < 4:
        logger.warning("[Row %d] cells.count=%d, returning None", idx, cells.count())
        return None

    rank_text, rank_loc = _first_existing_text(
        row,
        [
            "span.rank",
            "td.fab_rank_ws___Position",
            "td.fab_rank_ws___Num",
            "td:nth-of-type(1) span.rank",
            "td:nth-of-type(1)",
        ],
    )
    rank_match = re.search(r"\d+", rank_text)
    if not rank_match:
        logger.debug("[Row %d] rank_text='%s', no rank match", idx, rank_text)
        return None
    rank = int(rank_match.group())

    change_text, change_loc = _first_existing_text(
        row,
        [
            "span.diff p",
            "td.fab_rank_ws___PositionDifference",
            "td:nth-of-type(1) span.diff p",
            "td:nth-of-type(1) .diff p",
        ],
    )
    change_class = ""
    if change_loc is not None:
        try:
            change_class = change_loc.get_attribute("class") or ""
        except Exception:
            change_class = ""
    rank_change = _parse_signed_change(change_text, change_class)
    if rank_change > 0:
        rank_change_type = "up"
    elif rank_change < 0:
        rank_change_type = "down"
    else:
        rank_change_type = "same"

    name, _ = _first_existing_text(
        row,
        [
            "td.fab_rank_ws___Name",
            "td:nth-of-type(2)",
        ],
    )
    if not name:
        logger.debug("[Row %d] name empty", idx)
        return None

    name = normalize_player_name(name)

    location, location_loc = _first_existing_text(
        row,
        [
            "td.rcellc.assoc",
            "td.fab_rank_ws___Country",
            "td.fab_rank_ws___Flag",
            "td:nth-of-type(3)",
        ],
    )
    if location_loc is not None:
        location = _extract_location(location_loc)

    points_text, _ = _first_existing_text(
        row,
        [
            "td.fab_rank_ws___Points",
            "td.rcellc:last-child",
            "td:nth-of-type(4)",
        ],
    )
    points_text = re.sub(r"[,\s]", "", points_text)
    points = int(points_text) if points_text.isdigit() else 0

    elapsed = time.time() - start_time
    logger.debug("[Row %d] parsed in %.3fs: rank=%d name='%s' points=%d", idx, elapsed, rank, name, points)

    details_row = _find_details_row(row)
    points_breakdown = _parse_breakdown_table(details_row) if details_row is not None else []

    return {
        "rank": rank,
        "rank_change": rank_change,
        "rank_change_type": rank_change_type,
        "change": rank_change,
        "name": name,
        "location": location,
        "country": location,
        "country_code": location,
        "points": points,
        "player_url": None,
        "points_breakdown": points_breakdown,
    }


def _parse_fabrik_row(row: Any) -> dict[str, Any] | None:
    cells = row.locator("td")
    if cells.count() == 0:
        return None

    def cell_text(selectors: list[str]) -> tuple[str, Any | None]:
        return _first_existing_text(row, selectors)

    rank_text, _ = cell_text(["td.fab_rank_ws___Position", "td.fab_rank_ws___Num", "td:nth-of-type(2)", "td:nth-of-type(1)"])
    rank_match = re.search(r"\d+", rank_text)
    if not rank_match:
        return None

    change_text, change_loc = cell_text(["td.fab_rank_ws___PositionDifference", "td:nth-of-type(3)"])
    change_class = ""
    if change_loc is not None:
        try:
            change_class = change_loc.get_attribute("class") or ""
        except Exception:
            change_class = ""
    rank_change = _parse_signed_change(change_text, change_class)
    if rank_change > 0:
        rank_change_type = "up"
    elif rank_change < 0:
        rank_change_type = "down"
    else:
        rank_change_type = "same"

    name, _ = cell_text(["td.fab_rank_ws___Name", "td:nth-of-type(5)"])
    if not name:
        return None

    name = normalize_player_name(name)

    location, _ = cell_text(["td.fab_rank_ws___Country", "td:nth-of-type(7)"])
    points_text, _ = cell_text(["td.fab_rank_ws___Points", "td:nth-of-type(4)"])
    points_text = re.sub(r"[,\s]", "", points_text)
    points = int(points_text) if points_text.isdigit() else 0

    details_row = _find_details_row(row)
    points_breakdown = _parse_breakdown_table(details_row) if details_row is not None else []

    return {
        "rank": int(rank_match.group()),
        "rank_change": rank_change,
        "rank_change_type": rank_change_type,
        "change": rank_change,
        "name": name,
        "location": location,
        "country": location,
        "country_code": location,
        "points": points,
        "player_url": None,
        "points_breakdown": points_breakdown,
    }


def parse_ranking_table(page: Any, top_n: int) -> list[dict[str, Any]]:
    """Parse the ranking table from the current page."""
    rankings: list[dict[str, Any]] = []
    start_time = time.time()

    rows = page.locator("tr.rrow")
    if rows.count() == 0:
        rows = page.locator("table#list_58_com_fabrik_58 tr.fabrik_row")

    row_count = rows.count()
    logger.info("Found %d rows, parsing top %d...", row_count, top_n)
    if row_count == 0:
        logger.error("No ranking rows found on page")
        return rankings

    parse_time = time.time()
    for idx in range(min(row_count, top_n)):
        row_start = time.time()
        row = rows.nth(idx)
        player = _parse_rrow_row(row, idx)
        if player is None:
            player = _parse_fabrik_row(row)
        if player is not None:
            rankings.append(player)
        
        if (idx + 1) % 10 == 0 or idx + 1 == min(row_count, top_n):
            elapsed = time.time() - row_start
            logger.info("Parsed %d/%d rows (%.2fs, avg %.3fs/row)", 
                      idx + 1, min(row_count, top_n), elapsed, elapsed / (idx + 1))

    total_time = time.time() - start_time
    logger.info("Parsing complete: %d rankings in %.2fs (avg %.3fs/row)", 
                len(rankings), total_time, total_time / len(rankings) if rankings else 0)
    return rankings[:top_n]


def _parse_breakdown_table(drow: Any) -> list[dict[str, Any]]:
    breakdown: list[dict[str, Any]] = []
    try:
        table = drow.locator("table.dtable").first
        if table.count() == 0:
            return breakdown

        headers = _get_table_headers(table)
        col_map = _map_breakdown_columns(headers)
        rows = table.locator("tbody tr")
        for idx in range(rows.count()):
            entry = _parse_breakdown_row(rows.nth(idx), col_map)
            if entry:
                breakdown.append(entry)
    except Exception as exc:
        logger.warning("Failed to parse breakdown table: %s", exc)

    return breakdown


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def extract_ranking_meta(page: Any) -> tuple[str, str]:
    """Extract ranking week and date from the current page."""
    ranking_week = ""
    ranking_date = ""

    try:
        page_html = page.content()

        week_match = re.search(r'"fab_rank_ws___Week"\s*:\s*(\d+)', page_html)
        if week_match:
            week_num = week_match.group(1)
            ranking_week = f"Week {week_num}, {datetime.now().year}"

        date_match = re.search(
            r"(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}\s+\w+\s+20\d{2}|\w+\s+\d{1,2},?\s+20\d{2})",
            page_html,
        )
        if date_match:
            ranking_date = date_match.group(1).strip()
    except Exception as exc:
        logger.warning("Failed to extract ranking meta: %s", exc)

    if not ranking_week:
        ranking_week = f"Week {datetime.now().isocalendar()[1]}, {datetime.now().year}"
    if not ranking_date:
        ranking_date = datetime.now().strftime("%Y-%m-%d")

    return ranking_week, ranking_date


# ---------------------------------------------------------------------------
# Run / Save
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rankings: list[dict[str, Any]] = []

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
            log_prefix="rankings",
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

            ws_url = find_womens_singles_url(page)
            if not ws_url:
                logger.error("Could not find Women's Singles link on %s", RANKINGS_INDEX_URL)
                close_browser_page(via_cdp, browser, page)
                return 3

            logger.info("Navigating to Women's Singles ranking: %s", ws_url)
            open_page_with_verification(
                page,
                ws_url,
                delay_cfg,
                "open women's singles ranking",
                require_real_content=True,
                manual_prompt_lines=[
                    "Page does not appear to have loaded real content (possible Cloudflare challenge).",
                    "If you see a verification page, please complete it in the browser.",
                ],
                manual_prompt="Press ENTER after the real page has loaded...",
            )

            ranking_week, ranking_date = extract_ranking_meta(page)
            logger.info("Ranking week: %s, date: %s", ranking_week, ranking_date)

            logger.info("Parsing ranking table (top %d)...", args.top)
            rankings = parse_ranking_table(page, args.top)
            if not rankings:
                logger.error("Parsed 0 ranking rows")
                close_browser_page(via_cdp, browser, page)
                return 5

            logger.info("Parsed %d ranking entries", len(rankings))
            output_path = _save_output(output_dir, rankings, ranking_week, ranking_date, args.top)
            logger.info("Saved ranking data: %s", output_path)

        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            close_browser_page(via_cdp, browser, page)
            return 4
        finally:
            close_browser_page(via_cdp, browser, page)

    logger.info("Ranking scrape completed: %d players", len(rankings))
    return 0


def _save_output(
    output_dir: Path,
    rankings: list[dict[str, Any]],
    ranking_week: str,
    ranking_date: str,
    top_n: int,
) -> Path:
    week_match = re.search(r"Week\s*(\d+)", ranking_week)
    week_num = week_match.group(1) if week_match else str(datetime.now().isocalendar()[1])

    payload = {
        "category": "women_singles",
        "ranking_week": ranking_week,
        "ranking_date": ranking_date,
        "scraped_at": datetime.now().isoformat(),
        "top_n": top_n,
        "total_players": len(rankings),
        "rankings": rankings,
    }

    filename = f"women_singles_top{top_n}_week{week_num}.json"
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
