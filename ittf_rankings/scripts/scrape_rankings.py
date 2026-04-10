#!/usr/bin/env python3
"""
ITTF ranking scraper based on the shared Playwright utilities.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from lib.anti_bot import DelayConfig, RiskControlTriggered
from lib.browser_session import ensure_logged_in
from lib.capture import save_json
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
CATEGORY_META = {
    "women": "女子单打",
    "men": "男子单打",
    "women_doubles": "女子双打",
    "men_doubles": "男子双打",
    "mixed": "混合双打",
}
SEARCH_URL = f"{BASE_URL}/index.php/matches/players-matches-per-event"

COUNTRY_NAMES = {
    "CHN": "中国", "JPN": "日本", "KOR": "韩国", "GER": "德国",
    "FRA": "法国", "USA": "美国", "HKG": "中国香港", "TPE": "中国台北",
    "MAC": "中国澳门", "SGP": "新加坡", "BRA": "巴西", "EGY": "埃及",
    "IND": "印度", "ROU": "罗马尼亚", "AUT": "奥地利", "NED": "荷兰",
    "SWE": "瑞典", "POL": "波兰", "ESP": "西班牙", "ITA": "意大利",
    "ENG": "英格兰", "WAL": "威尔士", "SCO": "苏格兰", "AUS": "澳大利亚",
    "NZL": "新西兰", "CAN": "加拿大", "MEX": "墨西哥", "ARG": "阿根廷",
    "PUR": "波多黎各", "DOM": "多米尼加", "CZE": "捷克", "RUS": "俄罗斯",
    "UKR": "乌克兰", "TUR": "土耳其", "IRI": "伊朗", "THA": "泰国",
    "VIE": "越南", "INA": "印度尼西亚", "MAS": "马来西亚", "PHI": "菲律宾",
    "PAK": "巴基斯坦", "KAZ": "哈萨克斯坦", "UZB": "乌兹别克斯坦",
    "SIN": "新加坡", "AIN": "中立运动员", "POR": "葡萄牙",
}
CONTINENT_NAMES = {
    "ASIA": "亚洲", "EUROPE": "欧洲", "AMERICA": "美洲", "AFRICA": "非洲", "OCEANIA": "大洋洲",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF ranking scraper")
    parser.add_argument("--category", choices=sorted(RANKING_URLS.keys()), default="women")
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--storage-state", default="data/session/ittf_storage_state.json")
    parser.add_argument("--init-session", action="store_true", help="Open browser for manual login and save storage state")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--snapshot-dir", default="data/ranking_snapshots")
    parser.add_argument("--output", default=None)
    return parser


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_int(text: str, default: int = 0) -> int:
    cleaned = re.sub(r"[^\d+-]", "", text or "")
    if cleaned in {"", "+", "-"}:
        return default
    try:
        return int(cleaned)
    except ValueError:
        return default


def translate_country(code: str, fallback: str = "") -> str:
    if code in COUNTRY_NAMES:
        return COUNTRY_NAMES[code]
    return fallback or code


def translate_continent(code: str, fallback: str = "") -> str:
    if code in CONTINENT_NAMES:
        return CONTINENT_NAMES[code]
    return fallback or code


def extract_player_id_from_href(href: str | None) -> str | None:
    if not href:
        return None
    match = re.search(r"player_id_raw=(\d+)", href)
    if match:
        return match.group(1)
    return None


def parse_ranking_rows(page: Any, top_n: int) -> list[dict[str, Any]]:
    rankings: list[dict[str, Any]] = []
    tables = page.locator("table")
    if tables.count() == 0:
        return rankings

    target_table = tables.first
    rows = target_table.locator("tbody tr")
    row_count = rows.count()

    for idx in range(row_count):
        row = rows.nth(idx)
        cells = row.locator("td")
        if cells.count() < 5:
            continue

        cell_texts = [normalize_space(cells.nth(i).inner_text()) for i in range(cells.count())]
        rank = parse_int(cell_texts[0], default=-1)
        if rank <= 0:
            continue

        name_link = None
        try:
            name_link = cells.nth(4).locator("a").first
        except Exception:
            name_link = None

        english_name = normalize_space(cell_texts[4]) if len(cell_texts) > 4 else ""
        href = None
        if name_link and name_link.count() > 0:
            try:
                href = name_link.get_attribute("href")
            except Exception:
                href = None

        player = {
            "rank": rank,
            "name": english_name,
            "english_name": english_name,
            "points": parse_int(cell_texts[3] if len(cell_texts) > 3 else "0"),
            "change": parse_int(cell_texts[1] if len(cell_texts) > 1 else "0"),
            "country": translate_country(cell_texts[5] if len(cell_texts) > 5 else "", cell_texts[5] if len(cell_texts) > 5 else ""),
            "country_code": cell_texts[5] if len(cell_texts) > 5 else "",
            "continent": translate_continent(cell_texts[6] if len(cell_texts) > 6 else "", cell_texts[6] if len(cell_texts) > 6 else ""),
            "player_id": extract_player_id_from_href(href),
            "profile_url": f"{BASE_URL}{href}" if href and href.startswith("/") else href,
        }
        rankings.append(player)

        if len(rankings) >= top_n:
            break

    return rankings


def extract_update_meta(page: Any, category: str) -> tuple[str, str]:
    body_text = normalize_space(page.locator("body").inner_text())

    week_match = re.search(r"(20\d{2}\s*Week\s*\d+)", body_text, re.IGNORECASE)
    if not week_match:
        week_match = re.search(r"(Week\s*\d+)\D+(20\d{2})", body_text, re.IGNORECASE)
    week = week_match.group(1) if week_match else ""

    update_match = re.search(r"(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})", body_text)
    update_date = update_match.group(1) if update_match else ""

    if not update_date:
        title_text = normalize_space(page.title())
        update_date = title_text if title_text else ""

    return week, update_date or category


def build_output(rankings: list[dict[str, Any]], category: str, week: str, update_date: str) -> dict[str, Any]:
    return {
        "update_date": update_date,
        "week": week,
        "category": CATEGORY_META[category],
        "category_key": category,
        "total_players": len(rankings),
        "rankings": rankings,
    }


def run(args: argparse.Namespace) -> int:
    storage_state = Path(args.storage_state)
    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    output_path = Path(args.output) if args.output else Path(f"data/{args.category}_top{args.top}.json")

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

            rankings = parse_ranking_rows(page, args.top)
            if not rankings:
                logger.error("Parsed 0 ranking rows from page: %s", target_url)
                browser.close()
                return 5

            week, update_date = extract_update_meta(page, args.category)
            payload = build_output(rankings, args.category, week, update_date)
            save_json(output_path, payload)
            logger.info("Saved ranking JSON: %s", output_path)
        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            browser.close()
            return 4

        browser.close()

    logger.info("Ranking scrape completed: %s rows", len(rankings))
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = run(args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
