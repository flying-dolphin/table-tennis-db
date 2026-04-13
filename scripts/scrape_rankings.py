#!/usr/bin/env python3
"""
ITTF ranking scraper — Women's Singles Top N.

Scrapes ranking data from https://www.ittf.com/rankings/, including
each player's points breakdown details.

Supports checkpoint-based resume for long-running scrapes.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep
from lib.capture import save_json
from lib.checkpoint import CheckpointStore
from lib.page_ops import guarded_goto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_ranking_scraper")

RANKINGS_INDEX_URL = "https://www.ittf.com/rankings/"


def _player_key(player: dict[str, Any]) -> str:
    """Best-effort stable player key for checkpointing/caching."""
    url = (player.get("player_url") or "").strip()
    name = (player.get("name") or "").strip()
    country = (player.get("country") or "").strip()
    if url:
        m = re.search(r"(\d{4,})", url)
        if m:
            return f"id:{m.group(1)}"
    raw = f"{name}|{country}|{url}"
    return "h:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _find_latest_output_file(output_dir: Path) -> Path | None:
    candidates = list(output_dir.glob("women_singles_top*_week*.json"))
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    except Exception:
        return candidates[-1]


def _load_cached_breakdowns(output_dir: Path) -> tuple[str | None, dict[str, list[dict[str, Any]]]]:
    """Load cached points_breakdown from the latest output file (best-effort)."""
    latest = _find_latest_output_file(output_dir)
    if not latest or not latest.exists():
        return None, {}

    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return None, {}

    ranking_date = payload.get("ranking_date")
    rankings = payload.get("rankings") or []
    if not isinstance(rankings, list):
        return ranking_date, {}

    cached: dict[str, list[dict[str, Any]]] = {}
    for p in rankings:
        if not isinstance(p, dict):
            continue
        breakdown = p.get("points_breakdown") or []
        if not breakdown:
            continue
        cached[_player_key(p)] = breakdown

    return ranking_date, cached

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF ranking scraper (Women's Singles)")
    parser.add_argument("--top", type=int, default=100, help="Number of top players to scrape (default: 100)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--slow-mo", type=int, default=100, help="Slow motion delay in ms")
    parser.add_argument("--output-dir", default="data/rankings/orig", help="Output directory")
    parser.add_argument("--checkpoint", default="data/rankings/checkpoint_rankings.json", help="Checkpoint file path")
    parser.add_argument("--force", action="store_true", help="Ignore checkpoint, rescrape all")
    parser.add_argument("--rebuild-checkpoint", action="store_true", help="Rebuild checkpoint from existing output files")
    parser.add_argument("--no-translate", action="store_true", help="Skip translation")
    return parser


# ---------------------------------------------------------------------------
# Ranking list parsing
# ---------------------------------------------------------------------------

def find_womens_singles_url(page: Any) -> str | None:
    """Find the Women's Singles ranking link on the ITTF rankings index page."""
    # 显式等待关键链接出现，避免在 Cloudflare 重定向验证期间短暂的白屏阶段过早解析
    try:
        page.locator("a", has_text=re.compile(r"women.*singles", re.IGNORECASE)).first.wait_for(timeout=15000)
    except Exception:
        pass

    # Look for links containing "women" and "singles" text
    links = page.locator("a")
    count = links.count()
    for i in range(count):
        try:
            link = links.nth(i)
            text = (link.inner_text() or "").strip().lower()
            href = link.get_attribute("href") or ""
            # Match variations: "Women's Singles", "Women Singles", etc.
            if "women" in text and "singles" in text and href:
                full_url = href if href.startswith("http") else f"https://www.ittf.com{href}"
                logger.info("Found Women's Singles link: %s -> %s", text, full_url)
                return full_url
        except Exception:
            continue

    logger.warning("Could not find Women's Singles link by text, trying href patterns...")
    # Fallback: look for href patterns
    for i in range(count):
        try:
            link = links.nth(i)
            href = (link.get_attribute("href") or "").lower()
            if "women" in href and "singles" in href and "ranking" in href:
                full_url = href if href.startswith("http") else f"https://www.ittf.com{href}"
                logger.info("Found Women's Singles link by href: %s", full_url)
                return full_url
        except Exception:
            continue

    return None


def parse_ranking_table(page: Any, top_n: int) -> list[dict[str, Any]]:
    """Parse the ranking table from the current page.

    Returns a list of player dicts with: rank, name, country, points, player_url.
    Handles pagination if needed to collect up to top_n players.
    """
    rankings: list[dict[str, Any]] = []

    while len(rankings) < top_n:
        rows_added = _parse_current_page_rows(page, rankings, top_n)
        if rows_added == 0 and len(rankings) == 0:
            logger.error("No ranking rows found on page")
            break
        if len(rankings) >= top_n:
            break
        # Try next page
        if not _click_next_page(page):
            logger.info("No more pages, collected %d players", len(rankings))
            break
        human_sleep(2.0, 4.0, "wait for next page")

    return rankings[:top_n]


def _parse_current_page_rows(
    page: Any,
    rankings: list[dict[str, Any]],
    top_n: int,
) -> int:
    """Parse ranking rows from the current page and append to rankings list.

    The ITTF ranking page uses a table structure. We look for tables and try
    to identify the ranking table by its content (has numeric ranks, player
    names, country codes, and points).

    Returns the number of rows added.
    """
    added = 0

    # Try to find the ranking table
    tables = page.locator("table")
    table_count = tables.count()
    if table_count == 0:
        logger.warning("No tables found on page")
        return 0

    # Try each table to find the one with ranking data
    for t_idx in range(table_count):
        table = tables.nth(t_idx)
        rows = table.locator("tbody tr")
        row_count = rows.count()
        if row_count == 0:
            rows = table.locator("tr")
            row_count = rows.count()
        if row_count < 2:
            continue

        for r_idx in range(row_count):
            if len(rankings) >= top_n:
                break
            row = rows.nth(r_idx)
            player = _try_parse_row(page, row)
            if player:
                rankings.append(player)
                added += 1

        if added > 0:
            break  # Found the right table

    return added


def _try_parse_row(page: Any, row: Any) -> dict[str, Any] | None:
    """Try to parse a single table row as a ranking entry.

    Returns a player dict or None if the row doesn't look like a ranking entry.
    """
    cells = row.locator("td")
    cell_count = cells.count()
    if cell_count < 3:
        return None

    # Collect all cell texts
    cell_texts = []
    for i in range(cell_count):
        try:
            cell_texts.append(cells.nth(i).inner_text().strip())
        except Exception:
            cell_texts.append("")

    # Find rank (first cell that looks like a number)
    rank = None
    rank_idx = -1
    for i, text in enumerate(cell_texts):
        cleaned = re.sub(r"[^\d]", "", text)
        if cleaned and 1 <= int(cleaned) <= 9999:
            rank = int(cleaned)
            rank_idx = i
            break

    if rank is None or rank_idx < 0:
        return None

    # The remaining cells after rank should contain: name, country, points
    # Try to identify them heuristically
    name = ""
    country = ""
    points = 0
    player_url = None

    # Look for the player name - usually has a link
    for i in range(rank_idx + 1, cell_count):
        cell = cells.nth(i)
        link = cell.locator("a").first
        try:
            if link.count() > 0:
                name = link.inner_text().strip()
                href = link.get_attribute("href") or ""
                if href and name:
                    player_url = href if href.startswith("http") else f"https://www.ittf.com{href}"
                    break
        except Exception:
            continue

    # If no link found, try text-based approach
    if not name:
        # Name is usually the longest text cell after rank
        remaining = [(i, cell_texts[i]) for i in range(rank_idx + 1, cell_count)]
        remaining.sort(key=lambda x: len(x[1]), reverse=True)
        if remaining:
            name = remaining[0][1]

    # Look for country code (2-3 uppercase letters)
    for i in range(rank_idx + 1, cell_count):
        text = cell_texts[i].strip()
        # Also check for flag image title attribute
        try:
            img = cells.nth(i).locator("img").first
            if img.count() > 0:
                title = img.get_attribute("title") or img.get_attribute("alt") or ""
                if title and len(title) <= 5:
                    country = title.strip()
                    continue
        except Exception:
            pass
        if re.fullmatch(r"[A-Z]{2,3}", text):
            country = text

    # Look for points (numeric value, usually > 100 for top players)
    for i in range(cell_count - 1, rank_idx, -1):
        text = re.sub(r"[,\s]", "", cell_texts[i])
        if text.isdigit() and int(text) > 0:
            points = int(text)
            break

    if not name:
        return None

    return {
        "rank": rank,
        "name": name,
        "country": country,
        "points": points,
        "player_url": player_url,
        "points_breakdown": [],  # Filled in later
    }


def _click_next_page(page: Any) -> bool:
    """Try to click the next page button. Returns True if successful."""
    selectors = [
        "a.next",
        "li.next:not(.disabled) a",
        "a[aria-label='Next']",
        "a:has-text('Next')",
        "button:has-text('Next')",
        ".pagination a:has-text('›')",
        ".pagination a:has-text('»')",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                loc.click()
                page.wait_for_load_state("networkidle", timeout=10000)
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Points breakdown scraping
# ---------------------------------------------------------------------------

def scrape_points_breakdown(page: Any, player_url: str, delay_cfg: DelayConfig) -> list[dict[str, Any]]:
    """Navigate to a player's ranking detail page and extract their points breakdown.

    Returns a list of dicts with: event, category, expires_on, position, points.
    """
    breakdown: list[dict[str, Any]] = []

    try:
        guarded_goto(page, player_url, delay_cfg, f"open player ranking detail")
        page.wait_for_load_state("networkidle", timeout=15000)
        human_sleep(1.0, 2.0, "let player page settle")

        # Look for the points breakdown table
        tables = page.locator("table")
        table_count = tables.count()

        for t_idx in range(table_count):
            table = tables.nth(t_idx)
            # Check if this looks like a points breakdown table
            # by looking at headers: Event, Category, Expires on, Position, Points
            headers = _get_table_headers(table)
            if not headers:
                continue

            # Match header patterns (case-insensitive)
            header_lower = [h.lower() for h in headers]
            has_event = any("event" in h for h in header_lower)
            has_points = any("point" in h for h in header_lower)

            if not (has_event and has_points):
                continue

            # Found the points breakdown table — map column indices
            col_map = _map_breakdown_columns(headers)
            rows = table.locator("tbody tr")
            row_count = rows.count()

            for r_idx in range(row_count):
                row = rows.nth(r_idx)
                entry = _parse_breakdown_row(row, col_map)
                if entry:
                    breakdown.append(entry)

            if breakdown:
                break  # Found the right table

    except RiskControlTriggered:
        raise
    except Exception as exc:
        logger.warning("Failed to scrape points breakdown from %s: %s", player_url, exc)

    return breakdown


def _get_table_headers(table: Any) -> list[str]:
    """Extract header texts from a table element."""
    headers: list[str] = []
    try:
        # Try thead th first
        ths = table.locator("thead th")
        if ths.count() > 0:
            for i in range(ths.count()):
                headers.append(ths.nth(i).inner_text().strip())
            return headers

        # Try first row th/td
        first_row = table.locator("tr").first
        cells = first_row.locator("th, td")
        for i in range(cells.count()):
            headers.append(cells.nth(i).inner_text().strip())
    except Exception:
        pass
    return headers


def _map_breakdown_columns(headers: list[str]) -> dict[str, int]:
    """Map breakdown field names to column indices based on header texts."""
    col_map: dict[str, int] = {}
    for i, h in enumerate(headers):
        h_lower = h.lower().strip()
        if "event" in h_lower and "event" not in col_map:
            col_map["event"] = i
        elif "categor" in h_lower:
            col_map["category"] = i
        elif "expir" in h_lower:
            col_map["expires_on"] = i
        elif "position" in h_lower or "pos" == h_lower:
            col_map["position"] = i
        elif "point" in h_lower:
            col_map["points"] = i
    return col_map


def _parse_breakdown_row(row: Any, col_map: dict[str, int]) -> dict[str, Any] | None:
    """Parse a single points breakdown row."""
    cells = row.locator("td")
    cell_count = cells.count()
    if cell_count < 2:
        return None

    cell_texts = []
    for i in range(cell_count):
        try:
            cell_texts.append(cells.nth(i).inner_text().strip())
        except Exception:
            cell_texts.append("")

    def get_col(field: str) -> str:
        idx = col_map.get(field)
        if idx is not None and idx < len(cell_texts):
            return cell_texts[idx]
        return ""

    event = get_col("event")
    if not event:
        return None

    points_text = re.sub(r"[,\s]", "", get_col("points"))
    points = int(points_text) if points_text.isdigit() else 0

    return {
        "event": event,
        "category": get_col("category"),
        "expires_on": get_col("expires_on"),
        "position": get_col("position"),
        "points": points,
    }


# ---------------------------------------------------------------------------
# Ranking metadata
# ---------------------------------------------------------------------------

def extract_ranking_meta(page: Any) -> tuple[str, str]:
    """Try to extract ranking week and date from the current page.

    Returns (ranking_week, ranking_date) as strings.
    """
    ranking_week = ""
    ranking_date = ""

    try:
        body_text = page.inner_text("body")

        # Look for week info: "Week 16", "Week 16, 2026", etc.
        week_match = re.search(r"Week\s*(\d+)(?:\s*[,/]\s*(20\d{2}))?", body_text, re.IGNORECASE)
        if week_match:
            week_num = week_match.group(1)
            year = week_match.group(2) or str(datetime.now().year)
            ranking_week = f"Week {week_num}, {year}"

        # Look for date: "14 April 2026", "2026-04-14", "April 14, 2026", etc.
        date_match = re.search(
            r"(\d{1,2}\s+\w+\s+20\d{2}|20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\w+\s+\d{1,2},?\s+20\d{2})",
            body_text,
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
# Cloudflare handling
# ---------------------------------------------------------------------------

def _page_has_real_content(page: Any) -> bool:
    """Check if the page has loaded real ITTF content (not a challenge/interstitial)."""
    try:
        title = page.title().lower()
        # Cloudflare / generic interstitials
        if any(kw in title for kw in ["just a moment", "checking", "cloudflare", "attention"]):
            return False

        # Challenge page selectors
        challenge_selectors = [
            "#challenge-form", "#cf-challenge-title", "[data-ray]",
            "#challenge-title", ".challenge-title",
            "iframe[src*='challenges.cloudflare']",
        ]
        for sel in challenge_selectors:
            if page.locator(sel).count() > 0:
                return False

        # Positive check: page should have links or meaningful text
        body_text = page.inner_text("body")
        if len(body_text.strip()) < 100:
            return False

        return True
    except Exception:
        return False


def _navigate_with_cf_handling(page: Any, url: str, delay_cfg: DelayConfig, reason: str, sleep_first: bool = True) -> None:
    """Navigate to URL, wait for Cloudflare/interstitial to be cleared manually if needed."""
    if sleep_first:
        human_sleep(delay_cfg.min_request_sec, delay_cfg.max_request_sec, reason)

    page.goto(url, wait_until="domcontentloaded", timeout=45000)

    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass

    if not _page_has_real_content(page):
        logger.warning("Page does not appear to have loaded real content (possible Cloudflare challenge).")
        logger.warning("If you see a verification page, please complete it in the browser.")
        input("Press ENTER after the real page has loaded...")
        # Wait for page to settle after user interaction
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        human_sleep(2.0, 4.0, "after manual verification")

    # Final risk check
    risk = detect_risk(page)
    if risk:
        raise RiskControlTriggered(risk)


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = Path(args.checkpoint)
    checkpoint = CheckpointStore(checkpoint_path)
    if getattr(args, "rebuild_checkpoint", False):
        checkpoint.reset()

    # If checkpoint is missing/empty, bootstrap from existing output files (orig data).
    cached_date, cached_breakdowns = _load_cached_breakdowns(output_dir)
    if (not checkpoint_path.exists()) or (not checkpoint.has_any_completed()):
        if cached_date and cached_breakdowns:
            with checkpoint.bulk():
                for pk in cached_breakdowns.keys():
                    ck = f"rankings|{cached_date}|player:{pk}|breakdown"
                    if not checkpoint.is_done(ck):
                        checkpoint.mark_done(ck, meta={"bootstrapped_from": "latest_output"})

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
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slow_mo)
        context = browser.new_context()
        page = context.new_page()

        try:
            # Step 1: Navigate to rankings index page (no sleep before first navigation)
            logger.info("Navigating to ITTF rankings index: %s", RANKINGS_INDEX_URL)
            _navigate_with_cf_handling(page, RANKINGS_INDEX_URL, delay_cfg, "open rankings index", sleep_first=False)

            # Step 2: Find and click Women's Singles link
            ws_url = find_womens_singles_url(page)
            if not ws_url:
                logger.error("Could not find Women's Singles link on %s", RANKINGS_INDEX_URL)
                browser.close()
                return 3

            logger.info("Navigating to Women's Singles ranking: %s", ws_url)
            _navigate_with_cf_handling(page, ws_url, delay_cfg, "open women's singles ranking")

            # Step 3: Extract ranking metadata
            ranking_week, ranking_date = extract_ranking_meta(page)
            logger.info("Ranking week: %s, date: %s", ranking_week, ranking_date)

            # Step 4: Parse ranking table
            logger.info("Parsing ranking table (top %d)...", args.top)
            rankings = parse_ranking_table(page, args.top)
            if not rankings:
                logger.error("Parsed 0 ranking rows")
                browser.close()
                return 5

            logger.info("Parsed %d ranking entries", len(rankings))

            # Step 5: Scrape points breakdown for each player
            for idx, player in enumerate(rankings):
                player_url = player.get("player_url")
                if not player_url:
                    logger.warning("[%d/%d] No URL for player: %s", idx + 1, len(rankings), player.get("name"))
                    continue

                pk = _player_key(player)
                ck = f"rankings|{ranking_date}|player:{pk}|breakdown"
                if (not args.force) and checkpoint.is_done(ck):
                    cached = cached_breakdowns.get(pk)
                    if cached:
                        player["points_breakdown"] = cached
                        logger.info("[%d/%d] Skipping (checkpoint+cache): %s", idx + 1, len(rankings), player["name"])
                        continue
                    logger.info("[%d/%d] Checkpoint done but no cache found, will rescrape: %s", idx + 1, len(rankings), player["name"])

                logger.info("[%d/%d] Scraping points breakdown: %s", idx + 1, len(rankings), player["name"])
                try:
                    breakdown = scrape_points_breakdown(page, player_url, delay_cfg)
                    player["points_breakdown"] = breakdown
                    logger.info("  -> %d breakdown entries", len(breakdown))
                    checkpoint.mark_done(ck, meta={"player_url": player_url, "rank": player.get("rank")})
                    cached_breakdowns[pk] = breakdown
                except RiskControlTriggered as exc:
                    logger.error("Risk control triggered at player %s: %s", player["name"], exc)
                    checkpoint.mark_failed(ck, str(exc), meta={"player_url": player_url})
                    # Save partial results before exiting
                    _save_output(output_dir, rankings, ranking_week, ranking_date, args.top)
                    browser.close()
                    return 4
                except Exception as exc:
                    logger.warning("  -> Failed: %s", exc)
                    checkpoint.mark_failed(ck, str(exc), meta={"player_url": player_url})

                # Delay between players
                if idx < len(rankings) - 1:
                    human_sleep(delay_cfg.min_player_gap_sec, delay_cfg.max_player_gap_sec, "between players")

            # Step 6: Save output
            output_path = _save_output(output_dir, rankings, ranking_week, ranking_date, args.top)
            logger.info("Saved ranking data: %s", output_path)

        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            browser.close()
            return 4

        browser.close()

    logger.info("Ranking scrape completed: %d players", len(rankings))
    return 0


def _save_output(
    output_dir: Path,
    rankings: list[dict[str, Any]],
    ranking_week: str,
    ranking_date: str,
    top_n: int,
) -> Path:
    """Build and save the output JSON."""
    # Extract week number for filename
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
