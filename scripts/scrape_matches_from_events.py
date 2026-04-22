#!/usr/bin/env python3
"""
Scrape all matches from ITTF event match-list URLs.

Input URLs look like:
https://results.ittf.link/index.php/event-matches/list/68?resetfilters=1&abc=460&vw_matches___tournament_id_raw[value][]=460

For each URL this script:
- selects Display # = 100
- reads bottom pagination info: Page X of Y Total: Z
- scrapes every page with the same row parser used by scrape_matches.py
- verifies scraped count against the page Total
- writes one JSON file named from the event field and abc event id
"""

from __future__ import annotations

import argparse
import logging
import random
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from lib.anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.browser_session import ensure_logged_in
from lib.capture import sanitize_filename, save_json
from lib.checkpoint import utc_now_iso
from lib.navigation_runtime import verify_cdp_session_or_prompt
from lib.page_ops import click_next_page_if_any, guarded_goto
from scrape_events import get_pagination_info
from scrape_matches import parse_detail_matches_from_dom, select_browser_profiles


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("event_matches_scraper")


BASE_URL = "https://results.ittf.link"
DEFAULT_URLS_FILE = "data/event_matches_url_list.txt"
DEFAULT_OUTPUT_DIR = "data/event_matches/orig"


def load_event_urls(urls_file: Path | None, urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: str) -> None:
        value = raw.strip()
        if not value or value.startswith("#"):
            return
        if value in seen:
            return
        seen.add(value)
        out.append(value)

    if urls_file is not None:
        if not urls_file.exists():
            raise FileNotFoundError(f"urls file not found: {urls_file}")
        for line in urls_file.read_text(encoding="utf-8").splitlines():
            add(line)

    for url in urls:
        add(url)

    return out


def event_id_from_url(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    values = query.get("abc") or []
    if values and values[0].strip():
        return values[0].strip()

    match = re.search(r"[?&]abc=(\d+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"Cannot parse abc event id from url: {url}")


def event_name_from_match(match: dict[str, Any]) -> str:
    explicit = str(match.get("event") or match.get("event_name") or "").strip()
    if explicit:
        return explicit

    raw_row_text = str(match.get("raw_row_text") or "")
    parts = [part.strip() for part in raw_row_text.split("|")]
    if len(parts) > 1 and parts[1]:
        return parts[1]
    return ""


def output_filename(event_name: str, event_id: str) -> str:
    base = sanitize_filename((event_name or "event").replace(" ", "_"))
    return f"{base}_{event_id}.json"


def select_display_100(page: Any) -> bool:
    selectors = [
        ".limit select[id^='limit']",
        "select[id^='limit']",
        ".limit select.inputbox.form-select",
        "select.inputbox.form-select",
    ]
    for selector in selectors:
        loc = page.locator(selector).first
        try:
            if loc.count() == 0 or not loc.is_visible():
                continue
            current_value = (loc.input_value() or "").strip()
            if current_value == "100":
                logger.info("Display # already 100 via selector: %s", selector)
                time.sleep(random.uniform(1.0, 2.0))
                return True

            loc.select_option("100")
            logger.info("Selected Display # = 100 via selector: %s", selector)
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(random.uniform(1.0, 2.0))
            return True
        except Exception as exc:
            logger.warning("Failed to select Display # = 100 via %s: %s", selector, exc)
    return False


def wait_for_pagination_info(page: Any, timeout_sec: float = 20.0) -> tuple[int, int, int]:
    deadline = time.time() + timeout_sec
    last_info: tuple[int | None, int | None, int | None] = (None, None, None)
    while time.time() < deadline:
        last_info = get_pagination_info(page)
        current_page, total_pages, total_records = last_info
        if current_page is not None and total_pages is not None and total_records is not None:
            return current_page, total_pages, total_records
        time.sleep(0.4)
    raise RuntimeError(f"Cannot read pagination info, last={last_info}, url={page.url}")


def wait_for_table_rows(page: Any, timeout_sec: float = 20.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        risk = detect_risk(page)
        if risk:
            raise RiskControlTriggered(risk)

        try:
            if page.locator("table tbody tr").count() > 0:
                return
            body = (page.inner_text("body") or "").lower()
            if "total: 0" in body or "no records" in body:
                return
        except Exception:
            pass
        time.sleep(0.4)
    raise RuntimeError(f"Timed out waiting for match rows, url={page.url}")


def click_start_page_if_needed(page: Any, current_page: int, expected_page: int = 1) -> bool:
    if current_page == expected_page:
        return True

    selectors = [
        "li.page-item:not(.disabled) a[title='Start']",
        "li.page-item:not(.disabled) a[rel='first']",
        "a[title='Start']",
        "a[rel='first']",
        ".pagination a:has-text('Start')",
    ]
    for selector in selectors:
        loc = page.locator(selector).first
        try:
            if loc.count() == 0 or not loc.is_visible():
                continue

            href = (loc.get_attribute("href") or "").strip()
            if href:
                start_url = urljoin(page.url, href)
                logger.info(
                    "Current page is %s, expected %s. Navigating Start: %s",
                    current_page,
                    expected_page,
                    start_url,
                )
                page.goto(start_url, wait_until="domcontentloaded", timeout=45000)
            else:
                logger.info("Current page is %s, expected %s. Clicking Start.", current_page, expected_page)
                loc.click()

            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            time.sleep(random.uniform(1.0, 2.0))
            wait_for_table_rows(page)
            new_page, _, _ = wait_for_pagination_info(page)
            return new_page == expected_page
        except Exception as exc:
            logger.warning("Failed to jump Start via %s: %s", selector, exc)
            continue
    return False


def scrape_event_url(
    page: Any,
    url: str,
    output_dir: Path,
    delay_cfg: DelayConfig,
    max_pages: int,
) -> dict[str, Any]:
    event_id = event_id_from_url(url)
    guarded_goto(page, url, delay_cfg, f"open event matches {event_id}", sleep_first=False)
    wait_for_table_rows(page)

    if not select_display_100(page):
        raise RuntimeError("Display # select element not found")

    wait_for_table_rows(page)
    first_page, total_pages, total_records = wait_for_pagination_info(page)
    if first_page != 1:
        if not click_start_page_if_needed(page, first_page, expected_page=1):
            raise RuntimeError(f"Expected to start on page 1 after clicking Start, actual={first_page}, url={page.url}")
        first_page, total_pages, total_records = wait_for_pagination_info(page)
        if first_page != 1:
            raise RuntimeError(f"Expected to start on page 1 after clicking Start, actual={first_page}, url={page.url}")
    if total_pages > max_pages:
        raise RuntimeError(f"Refusing to scrape {total_pages} pages because --max-pages={max_pages}")

    matches: list[dict[str, Any]] = []
    last_non_empty_page = 0
    event_name = ""

    for expected_page in range(1, total_pages + 1):
        wait_for_table_rows(page)
        current_page, current_total_pages, current_total_records = wait_for_pagination_info(page)
        if current_page != expected_page:
            raise RuntimeError(
                f"Page index mismatch before scrape: expected={expected_page}, "
                f"actual={current_page}, url={page.url}"
            )
        if current_total_pages != total_pages or current_total_records != total_records:
            logger.warning(
                "Pagination totals changed on %s page %s: initial pages=%s total=%s, current pages=%s total=%s",
                url,
                expected_page,
                total_pages,
                total_records,
                current_total_pages,
                current_total_records,
            )

        page_matches = parse_detail_matches_from_dom(page, player_name="")
        if page_matches:
            last_non_empty_page = expected_page
            if not event_name:
                event_name = event_name_from_match(page_matches[0])
            for item in page_matches:
                item_event = event_name_from_match(item)
                if item_event:
                    item.setdefault("event", item_event)
        matches.extend(page_matches)
        logger.info(
            "Event %s page %s/%s: parsed %s matches (running=%s)",
            event_id,
            expected_page,
            total_pages,
            len(page_matches),
            len(matches),
        )

        if expected_page >= total_pages:
            break
        if not click_next_page_if_any(page):
            raise RuntimeError(f"Next page link not found before page {expected_page + 1}, url={page.url}")
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(random.uniform(1.0, 2.0))

    if not event_name and matches:
        event_name = event_name_from_match(matches[0])
    if not event_name:
        event_name = "event"

    payload = {
        "schema_version": "event_match.v1",
        "scraped_at": utc_now_iso(),
        "source_url": url,
        "final_url": page.url,
        "event_id": event_id,
        "event": event_name,
        "page_total_records": total_records,
        "matches": matches,
    }

    output_file = output_dir / output_filename(event_name, event_id)
    save_json(output_file, payload)
    payload["output_file"] = str(output_file)

    if len(matches) != total_records:
        logger.error(
            "Record count mismatch: url=%s actual=%s page_total=%s last_non_empty_page=%s",
            url,
            len(matches),
            total_records,
            last_non_empty_page,
        )
    else:
        logger.info("Record count verified for %s: %s matches", event_id, len(matches))
    logger.info("Saved event matches: %s", output_file)
    return payload


def run(args: argparse.Namespace) -> int:
    urls_file = Path(args.urls_file) if args.urls_file else None
    urls = load_event_urls(urls_file, args.url)
    if not urls:
        logger.error("No event URLs provided")
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    storage_state = Path(args.storage_state)
    delay_cfg = DelayConfig(
        min_request_sec=args.min_delay,
        max_request_sec=args.max_delay,
        min_player_gap_sec=args.min_event_gap,
        max_player_gap_sec=args.max_event_gap,
    )

    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        logger.error("patchright is required. Install with: pip install patchright && python -m patchright install chromium")
        return 2

    saved = 0
    failed = 0

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

        via_cdp, browser, _, page = open_browser_page(
            p,
            use_cdp=True,
            cdp_port=args.cdp_port,
            cdp_only=False,
            launch_kwargs={"headless": args.headless, "slow_mo": args.slow_mo},
            context_kwargs=context_kwargs,
            log_prefix="event-matches",
        )

        try:
            if via_cdp:
                verify_cdp_session_or_prompt(page, BASE_URL, delay_cfg)
            else:
                ensure_logged_in(page, BASE_URL, delay_cfg, storage_state, args.init_session)
                if args.init_session:
                    logger.info("Session initialized. Exiting due to --init-session.")
                    return 0

            selected_urls = urls[: args.limit] if args.limit and args.limit > 0 else urls
            for idx, url in enumerate(selected_urls, start=1):
                logger.info("[%s/%s] Scraping event matches URL: %s", idx, len(selected_urls), url)
                try:
                    scrape_event_url(
                        page=page,
                        url=url,
                        output_dir=output_dir,
                        delay_cfg=delay_cfg,
                        max_pages=args.max_pages,
                    )
                    saved += 1
                except RiskControlTriggered as exc:
                    logger.error("Risk control triggered: %s", exc)
                    logger.error("Stop immediately to protect account/session.")
                    return 3
                except Exception as exc:
                    failed += 1
                    logger.error("Failed URL %s: %s", url, exc)
                    if args.stop_on_error:
                        return 4

                if idx < len(selected_urls):
                    human_sleep(args.min_event_gap, args.max_event_gap, "gap between event URLs")
        finally:
            close_browser_page(via_cdp, browser, page)

    logger.info("Completed. saved=%s failed=%s", saved, failed)
    return 4 if failed and saved == 0 else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape ITTF event match-list URLs")
    parser.add_argument("--urls-file", default=DEFAULT_URLS_FILE, help="Text file with one event match URL per line")
    parser.add_argument("--url", action="append", default=[], help="Event match URL. Can be repeated.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--storage-state", default="data/session/ittf_storage_state.json")
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP port of an existing Chrome to reuse")
    parser.add_argument("--init-session", action="store_true", help="Open browser for manual login and save storage-state")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--min-delay", type=float, default=3.0)
    parser.add_argument("--max-delay", type=float, default=6.0)
    parser.add_argument("--min-event-gap", type=float, default=5.0)
    parser.add_argument("--max-event-gap", type=float, default=10.0)
    parser.add_argument("--max-pages", type=int, default=500)
    parser.add_argument("--limit", type=int, default=0, help="Only scrape the first N URLs after loading")
    parser.add_argument("--stop-on-error", action="store_true")
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
