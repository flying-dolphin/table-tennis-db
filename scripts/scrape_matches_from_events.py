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
import json
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


def get_event_title_from_page(page: Any) -> str:
    selectors = [
        ".notranslate .span-class",
        "span.span-class",
    ]
    for selector in selectors:
        loc = page.locator(selector).first
        try:
            if loc.count() == 0 or not loc.is_visible():
                continue
            text = " ".join((loc.inner_text() or "").split()).strip()
            if text:
                return text
        except Exception:
            continue
    return ""


def output_filename(event_name: str, event_id: str) -> str:
    base = sanitize_filename((event_name or "event").replace(" ", "_"))
    return f"{base}_{event_id}.json"


def collect_existing_event_ids(output_dir: Path) -> set[str]:
    event_ids: set[str] = set()
    if not output_dir.exists():
        return event_ids

    for path in output_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skip unreadable existing output %s: %s", path, exc)
            continue

        event_id = str(payload.get("event_id") or "").strip()
        if event_id:
            event_ids.add(event_id)
            continue

        match = re.search(r"_(\d+)\.json$", path.name)
        if match:
            event_ids.add(match.group(1))
    return event_ids


def select_display_100(page: Any) -> bool:
    return select_display_value(page, "100")


def select_display_value(page: Any, value: str) -> bool:
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
            if current_value == value:
                logger.info("Display # already %s via selector: %s", value, selector)
                time.sleep(random.uniform(1.0, 2.0))
                return True

            loc.select_option(value)
            logger.info("Selected Display # = %s via selector: %s", value, selector)
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(random.uniform(1.0, 2.0))
            return True
        except Exception as exc:
            logger.warning("Failed to select Display # = %s via %s: %s", value, selector, exc)
    return False


def page_has_no_records_message(page: Any) -> bool:
    risk = detect_risk(page)
    if risk:
        raise RiskControlTriggered(risk)

    try:
        empty = page.locator(".emptyDataMessage").first
        if empty.count() > 0 and empty.is_visible():
            text = " ".join((empty.inner_text() or "").split()).strip().lower()
            return text == "no records"
    except Exception:
        return False
    return False


def diagnose_current_page(page: Any) -> str:
    try:
        row_count = page.locator("table tbody tr").count()
    except Exception:
        row_count = -1

    empty_text = ""
    try:
        empty = page.locator(".emptyDataMessage").first
        if empty.count() > 0 and empty.is_visible():
            empty_text = " ".join((empty.inner_text() or "").split()).strip()
    except Exception:
        empty_text = ""

    pagination = get_pagination_or_total_info(page)
    return f"rows={row_count} emptyDataMessage={empty_text!r} pagination={pagination} url={page.url}"


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


def get_total_only_info(page: Any) -> tuple[int, int, int] | None:
    selectors = [
        ".limit.row p",
        ".limit p",
        ".pagination-info",
    ]
    for selector in selectors:
        try:
            elements = page.locator(selector).all()
            for el in elements:
                if not el.is_visible():
                    continue
                text = " ".join((el.inner_text() or "").split()).strip()
                if re.search(r"\bPage\s+\d+\s+of\s+\d+\s+Total:", text, re.IGNORECASE):
                    continue
                match = re.fullmatch(r"Total:\s*(\d+)", text, re.IGNORECASE)
                if match:
                    return 1, 1, int(match.group(1))
        except Exception:
            continue
    return None


def get_pagination_or_total_info(page: Any) -> tuple[int | None, int | None, int | None]:
    current_page, total_pages, total_records = get_pagination_info(page)
    if current_page is not None and total_pages is not None and total_records is not None:
        return current_page, total_pages, total_records
    total_only = get_total_only_info(page)
    if total_only:
        return total_only
    return None, None, None


def wait_for_pagination_or_total_info(page: Any, timeout_sec: float = 20.0) -> tuple[int, int, int]:
    deadline = time.time() + timeout_sec
    last_info: tuple[int | None, int | None, int | None] = (None, None, None)
    while time.time() < deadline:
        last_info = get_pagination_or_total_info(page)
        current_page, total_pages, total_records = last_info
        if current_page is not None and total_pages is not None and total_records is not None:
            return current_page, total_pages, total_records
        time.sleep(0.4)
    raise RuntimeError(f"Cannot read pagination/total info, last={last_info}, url={page.url}")


def ensure_display_100_with_retry(page: Any) -> None:
    if not select_display_100(page):
        raise RuntimeError("Display # select element not found")

    logger.info("Display # = 100 selected. Current page diagnostics: %s", diagnose_current_page(page))

    logger.warning("Display # = 100 selected; page validity will be checked by parsed records.")


def retry_display_100_once(page: Any, reason: str) -> None:
    logger.warning("%s. Retrying with Display # 50 -> 100. Diagnostics: %s", reason, diagnose_current_page(page))
    if not select_display_value(page, "50"):
        raise RuntimeError("Display # select element not found while retrying value 50")
    time.sleep(2.0)
    if not select_display_100(page):
        raise RuntimeError("Display # select element not found while retrying value 100")


def reload_and_retry_display_100(page: Any, reason: str) -> None:
    logger.warning("%s. Reloading page and retrying Display # 50 -> 100. Diagnostics: %s", reason, diagnose_current_page(page))
    page.reload(wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(random.uniform(1.0, 2.0))

    if not select_display_value(page, "50"):
        raise RuntimeError("Display # select element not found after reload while retrying value 50")
    time.sleep(2.0)
    if not select_display_100(page):
        raise RuntimeError("Display # select element not found after reload while retrying value 100")


def read_initial_page_info(page: Any, event_id: str) -> tuple[int, int, int]:
    try:
        return wait_for_pagination_or_total_info(page, timeout_sec=8.0)
    except RuntimeError:
        logger.warning(
            "Event %s: initial pagination/total info not ready before Display # decision. Diagnostics: %s",
            event_id,
            diagnose_current_page(page),
        )
        raise


def parse_page_matches_with_retry(page: Any, event_id: str, expected_page: int) -> list[dict[str, Any]]:
    for attempt in range(1, 4):
        page_matches = parse_detail_matches_from_dom(page, player_name="")
        if page_matches:
            return page_matches

        if page_has_no_records_message(page):
            reason = f"Event {event_id} page {expected_page}: No records message detected"
        else:
            reason = f"Event {event_id} page {expected_page}: parsed 0 valid records"

        if attempt == 1:
            retry_display_100_once(page, reason)
            continue
        if attempt == 2:
            reload_and_retry_display_100(page, reason)
            continue

        raise RuntimeError(f"{reason} after retry and reload. Diagnostics: {diagnose_current_page(page)}")

    raise RuntimeError(f"Event {event_id} page {expected_page}: failed to parse valid records")


def wait_for_pagination_info_after_retry(page: Any, event_id: str) -> tuple[int, int, int]:
    for attempt in range(1, 4):
        try:
            return wait_for_pagination_or_total_info(page)
        except RuntimeError as exc:
            reason = f"Event {event_id}: cannot read pagination/total info"
            if attempt == 1:
                retry_display_100_once(page, reason)
                continue
            if attempt == 2:
                reload_and_retry_display_100(page, reason)
                continue
            raise RuntimeError(f"{exc}. Diagnostics: {diagnose_current_page(page)}") from exc

    raise RuntimeError(f"Event {event_id}: failed to read pagination/total info")


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
            new_page, _, _ = wait_for_pagination_info_after_retry(page, event_id="unknown")
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

    try:
        first_page, total_pages, total_records = read_initial_page_info(page, event_id)
    except RuntimeError:
        ensure_display_100_with_retry(page)
        first_page, total_pages, total_records = wait_for_pagination_info_after_retry(page, event_id)
    else:
        if total_records >= 50:
            ensure_display_100_with_retry(page)
            first_page, total_pages, total_records = wait_for_pagination_info_after_retry(page, event_id)
        else:
            logger.info(
                "Event %s total=%s < 50, keep current Display # without selecting 100",
                event_id,
                total_records,
            )

    if first_page != 1:
        if not click_start_page_if_needed(page, first_page, expected_page=1):
            raise RuntimeError(f"Expected to start on page 1 after clicking Start, actual={first_page}, url={page.url}")
        first_page, total_pages, total_records = wait_for_pagination_info_after_retry(page, event_id)
        if first_page != 1:
            raise RuntimeError(f"Expected to start on page 1 after clicking Start, actual={first_page}, url={page.url}")
    if total_pages > max_pages:
        raise RuntimeError(f"Refusing to scrape {total_pages} pages because --max-pages={max_pages}")

    matches: list[dict[str, Any]] = []
    last_non_empty_page = 0
    event_name = get_event_title_from_page(page)
    if not event_name:
        raise RuntimeError(f"Cannot determine event title from page, event_id={event_id}, url={page.url}")
    canonical_event = event_name
    stop_reason = ""

    for expected_page in range(1, total_pages + 1):
        current_page, current_total_pages, current_total_records = wait_for_pagination_info_after_retry(page, event_id)
        if current_page > total_pages:
            stop_reason = (
                f"current page {current_page} exceeded first-page total_pages {total_pages}"
            )
            logger.warning("Stop event_id=%s: %s url=%s", event_id, stop_reason, page.url)
            break
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

        page_matches = parse_page_matches_with_retry(page, event_id, expected_page)
        if page_matches:
            last_non_empty_page = expected_page
            for item in page_matches:
                item_event = event_name_from_match(item)
                if item_event:
                    item.setdefault("event", item_event)
                if canonical_event and item_event != canonical_event:
                    stop_reason = (
                        f"event mismatch on page {expected_page}: "
                        f"expected={canonical_event!r} actual={item_event!r}"
                    )
                    logger.warning("Stop event_id=%s: %s url=%s", event_id, stop_reason, page.url)
                    break
                matches.append(item)
        logger.info(
            "Event %s page %s/%s: parsed %s matches (running=%s)",
            event_id,
            expected_page,
            total_pages,
            len(page_matches),
            len(matches),
        )

        if stop_reason:
            break
        if expected_page >= total_pages:
            break
        if not click_next_page_if_any(page):
            raise RuntimeError(f"Next page link not found before page {expected_page + 1}, url={page.url}")
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(random.uniform(1.0, 2.0))

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

    if len(matches) != total_records:
        logger.error(
            "Record count mismatch: url=%s actual=%s page_total=%s last_non_empty_page=%s stop_reason=%s",
            url,
            len(matches),
            total_records,
            last_non_empty_page,
            stop_reason or "",
        )
        raise RuntimeError(
            f"Record count mismatch for event_id={event_id}: "
            f"actual={len(matches)} page_total={total_records} "
            f"last_non_empty_page={last_non_empty_page} stop_reason={stop_reason or ''}"
        )

    output_file = output_dir / output_filename(event_name, event_id)
    save_json(output_file, payload)
    payload["output_file"] = str(output_file)

    if stop_reason:
        logger.warning(
            "Saved event_id=%s after early stop because scraped count matches page total: %s",
            event_id,
            stop_reason,
        )
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
    existing_event_ids = collect_existing_event_ids(output_dir)
    if existing_event_ids and not args.force:
        logger.info("Loaded %s existing event ids from %s", len(existing_event_ids), output_dir)
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
                event_id = event_id_from_url(url)
                if (not args.force) and event_id in existing_event_ids:
                    logger.info(
                        "[%s/%s] Skip existing event_id=%s (use --force to rescrape): %s",
                        idx,
                        len(selected_urls),
                        event_id,
                        url,
                    )
                    continue

                logger.info("[%s/%s] Scraping event matches URL: %s", idx, len(selected_urls), url)
                try:
                    scrape_event_url(
                        page=page,
                        url=url,
                        output_dir=output_dir,
                        delay_cfg=delay_cfg,
                        max_pages=args.max_pages,
                    )
                    existing_event_ids.add(event_id)
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
    parser.add_argument("--force", action="store_true", help="Rescrape even if output for event_id already exists")
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
