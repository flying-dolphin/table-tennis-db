#!/usr/bin/env python3
"""
ITTF Events Calendar Scraper

抓取 ITTF 官网历年赛事日历页面，提取赛事名称、时间和地点，
并将原始结果保存到 orig 目录。

用法:
    python scrape_events_calendar.py --year 2026
    python scrape_events_calendar.py --year 2025 --output data/events_calendar/orig/events_calendar_2025.json

URL 格式: https://www.ittf.com/{year}-events-calendar/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.browser_runtime import close_browser_page, open_browser_page
from lib.browser_session import ensure_logged_in
from lib.checkpoint import CheckpointStore, utc_now_iso
from lib.anti_bot import DelayConfig, RiskControlTriggered
from lib.navigation_runtime import open_page_with_verification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_events_calendar")


# ── 默认配置 ────────────────────────────────────────────────────────────────

BASE_URL = "https://www.ittf.com"
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "data" / "events_calendar" / "orig"
DEFAULT_FROM_YEAR = 2024  # 最早抓取的年份


# ── 页面解析 ────────────────────────────────────────────────────────────────

def parse_events_calendar(page: Any) -> list[dict[str, Any]]:
    logger.info("Current page URL during parse: %s", getattr(page, 'url', ''))
    """
    从 ITTF 赛事日历页面解析所有赛事信息。

    当前 ITTF 年度赛历页面的主体内容是一个按月份分组的列表，
    每条赛事记录通常是一个 li/a 文本节点，格式类似：
    02-05 Jan: WTT Youth Contender Vadodara 2026 (IND)
    """
    events: list[dict[str, Any]] = []

    selectors_to_try = [
        ".content.page-content li",
        ".page-content li",
        ".content li",
        "main li",
        "article li",
        # 保留旧兜底
        "table.events-calendar tbody tr",
        "table tbody tr",
        "table tr",
        ".event-item",
        ".event-row",
        ".calendar-event",
    ]

    rows = None
    for selector in selectors_to_try:
        try:
            candidates = page.locator(selector)
            count = candidates.count()
            if count > 0:
                logger.info("Found %s rows with selector: %s", count, selector)
                rows = candidates.all()
                break
        except Exception:
            continue

    if not rows:
        logger.warning("No event rows found with standard selectors, trying fallback")
        content_text = ""
        for selector in [".content.page-content", ".page-content", ".content", "body"]:
            try:
                content_text = page.locator(selector).first.inner_text()
                if content_text and content_text.strip():
                    logger.info("Fallback text source: %s (len=%s)", selector, len(content_text))
                    break
            except Exception:
                continue
        return _parse_events_from_text(content_text)

    for row in rows:
        try:
            row_text = " ".join((row.inner_text() or "").split())
            event = _parse_event_line(row_text)
            if event:
                links = row.locator("a").all()
                if links:
                    link_text = " ".join(" ".join((link.inner_text() or "").split()) for link in links)
                    if link_text and not event["name"]:
                        event["name"] = link_text
                    href = links[0].get_attribute("href") or ""
                    event["href"] = href
                    if href and ("/event/" in href or "/tournament/" in href):
                        event["slug"] = href.split("/")[-1].rstrip("/")
                events.append(event)
        except Exception as exc:
            logger.debug("Failed to parse row: %s", exc)
            continue

    return _dedupe_events(events)


def _is_date_string(text: str) -> bool:
    """判断文本是否是日期格式"""
    if not text:
        return False
    # 常见日期模式
    date_indicators = [
        "jan", "feb", "mar", "apr", "may", "jun",
        "jul", "aug", "sep", "oct", "nov", "dec",
        "january", "february", "march", "april", "june",
        "july", "august", "september", "october", "november", "december",
        "2024", "2025", "2026", "2027", "2028",
    ]
    text_lower = text.lower()
    # 至少包含月份或年份
    has_month = any(m in text_lower for m in ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])
    has_year = any(y in text for y in ["2024", "2025", "2026", "2027", "2028", "2029", "2030"])
    return has_month or has_year


def _is_location_string(text: str) -> bool:
    """判断文本是否是地点格式"""
    if not text:
        return False
    # 地点通常包含国家缩写、冠名赞助商名称等
    # 排除明显是日期的文本
    if _is_date_string(text):
        return False
    # 包含大写字母和空格的通常是地点或赛事名称
    if len(text) > 3 and any(c.isupper() for c in text):
        # 排除纯数字
        if text.replace(" ", "").isdigit():
            return False
        return True
    return False


def _extract_date_from_text(text: str) -> str:
    """从文本中提取日期"""
    import re
    patterns = [
        r"(\w+\s+\d{1,2}\s*-\s*\w+\s+\d{1,2},?\s*\d{4})",
        r"(\d{1,2}\s+\w+\s*-\s*\d{1,2}\s+\w+\s+\d{4})",
        r"(\w+\s+\d{1,2},?\s*\d{4})",
        r"(\d{1,2}\s+\w+\s+\d{4})",
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{1,2}\s*[\-–]\s*\d{1,2}\s+\w+)",
        r"(\d{1,2}\s+\w+\s*[\-–]\s*\d{1,2}\s+\w+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _parse_event_line(line: str) -> dict[str, Any] | None:
    import re

    text = " ".join((line or "").split())
    if not text:
        return None

    if text.lower() in {
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    }:
        return None

    if text.startswith("Notes:") or text.startswith("STARTS IN"):
        return None

    match = re.match(
        r"^(?P<date>.+?):\s*(?P<name>.+?)\s*\((?P<location>[A-Z]{3}|TBD)\)\**\s*(?P<status>.*)$",
        text,
    )
    if not match:
        return None

    date = match.group("date").strip()
    name = match.group("name").strip()
    location = match.group("location").strip()
    status = match.group("status").strip()

    if date.startswith("Week "):
        return None

    return {
        "name": name,
        "date": date,
        "location": location,
        "slug": "",
        "href": "",
        "raw_text": text,
        "status": status,
    }


def _parse_events_from_text(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        event = _parse_event_line(line)
        if event:
            events.append(event)
    return _dedupe_events(events)


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique_events = []
    for event in events:
        key = f"{event.get('date', '')}|{event.get('name', '')}|{event.get('location', '')}"
        if key and key not in seen:
            seen.add(key)
            unique_events.append(event)
    return unique_events


# ── 主流程 ──────────────────────────────────────────────────────────────────

def scrape_events_calendar(
    year: int,
    output_dir: Path,
    headless: bool = False,
    slow_mo: int = 100,
    cdp_port: int = 9222,
    force: bool = False,
) -> dict[str, Any]:
    """
    抓取指定年份的 ITTF 赛事日历。

    Args:
        year: 年份
        output_dir: 输出目录
        headless: 是否无头模式运行
        slow_mo: 慢动作延迟（毫秒）
        cdp_port: CDP 端口，用于连接已有 Chrome
    Returns:
        结果字典
    """
    calendar_url = f"{BASE_URL}/{year}-events-calendar/"
    logger.info("Target URL: %s", calendar_url)

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_output_file = output_dir / f"events_calendar_{year}.json"
    checkpoint_scrape_file = output_dir / f"checkpoint_scrape_{year}.json"

    scrape_checkpoint = CheckpointStore(checkpoint_scrape_file)
    ck_scrape_key = f"events_calendar_scrape_{year}"

    # Bootstrap checkpoints from existing output files when checkpoint is missing/empty.
    if (not checkpoint_scrape_file.exists()) or (not scrape_checkpoint.has_any_completed()):
        if raw_output_file.exists():
            try:
                raw_data = json.loads(raw_output_file.read_text(encoding="utf-8"))
                expected_total = len(raw_data.get("events", []))
                if expected_total > 0:
                    scrape_checkpoint.mark_done(ck_scrape_key, meta={"bootstrapped_from": str(raw_output_file)})
            except Exception:
                pass

    # 检查是否已完成。
    if not force and scrape_checkpoint.is_done(ck_scrape_key):
        logger.info("Year %s already scraped, loading from output file", year)
        if raw_output_file.exists():
            raw_data = json.loads(raw_output_file.read_text(encoding="utf-8"))
            return {"success": True, "data": raw_data, "source": "cache", "output_file": str(raw_output_file)}
        else:
            logger.warning("Output file not found, will re-scrape")

    # 启动浏览器
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        try:
            from patchright.sync_api import sync_playwright
        except ImportError:
            logger.error("需要 playwright 或 patchright")
            return {"success": False, "error": "playwright not installed"}

    delay_cfg = DelayConfig(
        min_request_sec=3.0,
        max_request_sec=8.0,
        min_player_gap_sec=5.0,
        max_player_gap_sec=15.0,
    )

    scraped_at = utc_now_iso()
    events: list[dict[str, Any]] = []

    with sync_playwright() as p:
        # 优先 CDP 连接已有 Chrome
        via_cdp, browser, context, page = open_browser_page(
            p,
            use_cdp=True,
            cdp_port=cdp_port,
            cdp_only=False,
            launch_kwargs={"headless": headless, "slow_mo": slow_mo},
            context_kwargs={"viewport": {"width": 1280, "height": 900}, "locale": "en-US"},
            log_prefix="events_calendar",
        )
        logger.info("Navigating to %s", calendar_url)
        open_page_with_verification(
            page,
            calendar_url,
            delay_cfg,
            "initial page load",
            check_cloudflare=True,
            manual_prompt_lines=[
                "Cloudflare challenge detected!",
                "Please complete the verification in the browser window.",
            ],
            manual_prompt="Press ENTER after completing Cloudflare verification...",
        )

        # 等待页面加载完成
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            logger.warning("networkidle timeout, using domcontentloaded")
            page.wait_for_load_state("domcontentloaded", timeout=15000)

        # 再次等待赛历主体出现，避免在 CDP 连接场景下过早解析
        try:
            page.locator(".content.page-content li, .page-content li").first.wait_for(timeout=10000)
        except Exception:
            logger.warning("Event list items did not appear before timeout, continuing with fallback parse")

        # 解析赛事
        events = parse_events_calendar(page)
        logger.info("Parsed %s events from page", len(events))

        if not events:
            logger.error("No events found on page, treating as failure")
            # 保存原始页面内容供调试
            body_text = page.inner_text("body")

            close_browser_page(via_cdp, browser, page)

            error_data = {
                "year": year,
                "url": calendar_url,
                "scraped_at": scraped_at,
                "error": "No events parsed from page",
                "raw_page_preview": body_text[:2000],
            }

            scrape_checkpoint.mark_failed(
                ck_scrape_key,
                "No events parsed from page",
                meta={"url": calendar_url},
            )
            return {
                "success": False,
                "error": "No events parsed from page",
                "data": error_data,
            }

        close_browser_page(via_cdp, browser, page)

    # 先保存原始抓取结果（无翻译）
    raw_result_data = {
        "year": year,
        "url": calendar_url,
        "scraped_at": scraped_at,
        "events": events,  # 原始事件数据
        "summary": {
            "total": len(events),
        }
    }
    raw_output_file.write_text(
        json.dumps(raw_result_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="",
    )
    logger.info("原始数据已保存: %s", raw_output_file)

    # 原始抓取完成 checkpoint
    scrape_checkpoint.mark_done(ck_scrape_key)

    return {
        "success": True,
        "data": raw_result_data,
        "output_file": str(raw_output_file),
        "raw_file": str(raw_output_file),
        "translated_file": None,
    }


# ── CLI ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ITTF Events Calendar Scraper - 抓取并翻译 ITTF 赛事日历"
    )
    parser.add_argument(
        "--year", "-y",
        type=int,
        required=True,
        help="年份（如 2026）",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="输出文件路径（默认: data/events_calendar/orig/events_calendar_{year}.json）",
    )
    parser.add_argument(
        "--cdp-port",
        type=int,
        default=9222,
        help="CDP 远程调试端口（默认: 9222）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式运行",
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=100,
        help="慢动作延迟毫秒（默认: 100）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新抓取（忽略 checkpoint）",
    )
    parser.add_argument(
        "--rebuild-checkpoint",
        action="store_true",
        help="基于现有输出文件重建 checkpoint",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # 确定输出路径
    if args.output:
        output_dir = Path(args.output).parent
        output_file = Path(args.output)
    else:
        output_dir = DEFAULT_OUTPUT_DIR
        output_file = output_dir / f"events_calendar_{args.year}.json"

    output_dir.mkdir(parents=True, exist_ok=True)

    # 如果指定了输出文件但不存在，尝试加载
    if args.output and not args.force:
        if output_file.exists():
            data = json.loads(output_file.read_text(encoding="utf-8"))
            logger.info("Loaded existing data from %s: %s events",
                        output_file, data.get("summary", {}).get("total", 0))

    try:
        # Rebuild checkpoints on demand: ensure subsequent runs can skip via checkpoint safely.
        if getattr(args, "rebuild_checkpoint", False) and not args.force:
            out_dir = output_dir
            ck_scrape = CheckpointStore(out_dir / f"checkpoint_scrape_{args.year}.json")
            ck_scrape.reset()
            # Bootstrapping is handled inside scrape_events_calendar() based on output file presence/completeness.

        result = scrape_events_calendar(
            year=args.year,
            output_dir=output_dir,
            headless=args.headless,
            slow_mo=args.slow_mo,
            cdp_port=args.cdp_port,
            force=args.force,
        )

        if result.get("success"):
            data = result.get("data", {})
            summary = data.get("summary", {})
            logger.info("=" * 50)
            logger.info("抓取完成！")
            logger.info("年份: %s", data.get("year"))
            logger.info("赛事数量: %s", summary.get("total", 0))
            logger.info("输出文件: %s", result.get("output_file"))
            logger.info("=" * 50)
        else:
            logger.error("抓取失败: %s", result.get("error", "未知错误"))
            sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("中断 by user")
        sys.exit(130)
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
