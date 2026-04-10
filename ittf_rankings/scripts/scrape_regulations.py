#!/usr/bin/env python3
"""
ITTF regulations scraper.

Strategy:
- Prefer lightweight requests-based discovery for PDF links
- Fall back to Playwright page loading when static discovery fails
- Save discovered PDF URLs and downloaded files metadata for downstream processing
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from lib.anti_bot import DelayConfig, RiskControlTriggered
from lib.browser_session import ensure_logged_in
from lib.capture import save_json
from lib.page_ops import guarded_goto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_regulations_scraper")

RANKINGS_URL = "https://ittf.com/rankings"
KNOWN_PATTERNS = [
    "ITTF-Table-Tennis-World-Ranking-Regulations",
    "World-Ranking-Regulations",
    "ITTF-Ranking-Regulations",
]
SEARCH_URL = "https://results.ittf.link/index.php/matches/players-matches-per-event"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF regulations scraper")
    parser.add_argument("--storage-state", default="data/session/ittf_storage_state.json")
    parser.add_argument("--init-session", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--output", default="data/regulations/latest_regulations.json")
    parser.add_argument("--download-dir", default="../docs")
    parser.add_argument("--skip-download", action="store_true")
    return parser


def discover_pdf_links_via_requests() -> list[str]:
    import requests
    from bs4 import BeautifulSoup

    response = requests.get(
        RANKINGS_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" not in href.lower():
            continue
        if not any(pattern in href for pattern in KNOWN_PATTERNS):
            continue
        links.append(urljoin(RANKINGS_URL, href))
    return sorted(set(links))


def discover_pdf_links_via_playwright(args: argparse.Namespace) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Please install Playwright first: pip install playwright && playwright install")
        return []

    storage_state = Path(args.storage_state)
    delay_cfg = DelayConfig(3.0, 8.0, 5.0, 10.0)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slow_mo)
        context = browser.new_context(storage_state=str(storage_state) if storage_state.exists() else None)
        page = context.new_page()

        try:
            ensure_logged_in(page, SEARCH_URL, delay_cfg, storage_state, args.init_session)
            guarded_goto(page, RANKINGS_URL, delay_cfg, "open rankings page for regulations discovery")
            anchors = page.locator("a")
            links: list[str] = []
            for i in range(anchors.count()):
                href = anchors.nth(i).get_attribute("href")
                if not href:
                    continue
                if ".pdf" not in href.lower():
                    continue
                if not any(pattern in href for pattern in KNOWN_PATTERNS):
                    continue
                links.append(urljoin(RANKINGS_URL, href))
        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            browser.close()
            return []

        browser.close()
    return sorted(set(links))


def download_latest_pdf(url: str, download_dir: Path) -> Path:
    import requests

    download_dir.mkdir(parents=True, exist_ok=True)
    filename = url.split("/")[-1] or "latest_regulations.pdf"
    pdf_path = download_dir / filename

    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    response.raise_for_status()
    pdf_path.write_bytes(response.content)
    return pdf_path


def run(args: argparse.Namespace) -> int:
    output_path = Path(args.output)

    try:
        links = discover_pdf_links_via_requests()
        discovery_method = "requests"
    except Exception as exc:
        logger.warning("Static PDF discovery failed, falling back to Playwright: %s", exc)
        links = discover_pdf_links_via_playwright(args)
        discovery_method = "playwright"

    if not links:
        logger.error("No regulations PDF links discovered")
        return 2

    latest_pdf = links[0]
    downloaded_to = None
    if not args.skip_download:
        try:
            downloaded_to = str(download_latest_pdf(latest_pdf, Path(args.download_dir)).resolve())
            logger.info("Downloaded latest regulations PDF: %s", downloaded_to)
        except Exception as exc:
            logger.warning("Failed to download latest regulations PDF: %s", exc)

    payload = {
        "source_url": RANKINGS_URL,
        "discovery_method": discovery_method,
        "pdf_links": links,
        "latest_pdf": latest_pdf,
        "downloaded_to": downloaded_to,
    }
    save_json(output_path, payload)
    logger.info("Saved regulations discovery JSON: %s", output_path)
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = run(args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
