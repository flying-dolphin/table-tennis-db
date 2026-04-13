#!/usr/bin/env python3
"""
ITTF Events Calendar Scraper

抓取 ITTF 官网历年赛事日历页面，提取赛事名称、时间和地点，
然后调用翻译模块进行中文化处理。

用法:
    python scrape_events_calendar.py --year 2026
    python scrape_events_calendar.py --year 2025 --output data/events_calendar_2025.json
    python scrape_events_calendar.py --year 2024 --apply

URL 格式: https://www.ittf.com/{year}-events-calendar/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.browser_session import ensure_logged_in
from lib.checkpoint import CheckpointStore, utc_now_iso
from lib.anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep
from lib.page_ops import guarded_goto
from lib.translator import Translator, Category

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_events_calendar")


# ── 默认配置 ────────────────────────────────────────────────────────────────

BASE_URL = "https://www.ittf.com"
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "data" / "events_calendar"
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


# ── 翻译处理 ────────────────────────────────────────────────────────────────

# 初始化翻译器（全局实例）
_translator: Translator | None = None


def _get_translator(dry_run: bool = True) -> Translator:
    """获取或创建翻译器实例"""
    global _translator
    if _translator is None:
        _translator = Translator(auto_save=True)
    return _translator


def translate_event(event: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
    """翻译单个赛事信息"""
    translated = event.copy()
    translator = _get_translator(dry_run)

    # 翻译赛事名称
    if event.get("name"):
        if dry_run:
            # dry-run: 只查词典，不调用 API
            result = translator.translate(event["name"], category="events", use_api=False)
            translated["name_zh"] = result
            translated["name_translation_method"] = "dict" if result != event["name"] else "skipped"
        else:
            result = translator.translate(event["name"], category="events", use_api=True)
            translated["name_zh"] = result
            translated["name_translation_method"] = "api" if result != event["name"] else "unchanged"

    # 翻译地点
    if event.get("location"):
        if dry_run:
            result = translator.translate(event["location"], category="locations", use_api=False)
            translated["location_zh"] = result
            translated["location_translation_method"] = "dict" if result != event["location"] else "skipped"
        else:
            result = translator.translate(event["location"], category="locations", use_api=True)
            translated["location_zh"] = result
            translated["location_translation_method"] = "api" if result != event["location"] else "unchanged"

    # 日期标准化
    if event.get("date"):
        translated["date_standardized"] = _standardize_date(event["date"])

    return translated


def _standardize_date(date_str: str) -> str:
    """标准化日期格式"""
    import re
    if not date_str:
        return ""

    # 尝试转换月份为中文
    month_map = {
        "jan": "1月", "january": "1月",
        "feb": "2月", "february": "2月",
        "mar": "3月", "march": "3月",
        "apr": "4月", "april": "4月",
        "may": "5月",
        "jun": "6月", "june": "6月",
        "jul": "7月", "july": "7月",
        "aug": "8月", "august": "8月",
        "sep": "9月", "september": "9月",
        "oct": "10月", "october": "10月",
        "nov": "11月", "november": "11月",
        "dec": "12月", "december": "12月",
    }

    result = date_str
    for eng, chn in month_map.items():
        result = result.lower().replace(eng, chn)

    return result


def translate_all_events(events: list[dict[str, Any]], dry_run: bool = True) -> list[dict[str, Any]]:
    """翻译所有赛事信息"""
    translated_events = []
    for event in events:
        translated = translate_event(event, dry_run=dry_run)
        translated_events.append(translated)
        logger.info("Translated: %s (%s) - %s",
                    event.get("name", ""),
                    translated.get("name_zh", ""),
                    event.get("location", ""))
        # 避免请求过快
        time.sleep(0.5)
    return translated_events


def _is_translated_file_complete(data: dict[str, Any], expected_total: int) -> bool:
    """校验翻译文件是否完整。"""
    events = data.get("events", [])
    if not isinstance(events, list):
        return False

    progress = data.get("progress", {})
    processed = progress.get("processed_events")
    total = progress.get("total_events")
    completed_batches = progress.get("completed_batches")
    total_batches = progress.get("total_batches")

    if progress:
        if processed != len(events):
            return False
        if total != expected_total:
            return False
        if completed_batches is not None and total_batches is not None and completed_batches != total_batches:
            return False

    # 无 progress 的旧文件：至少保证 events 数量完整
    return len(events) == expected_total


# ── 主流程 ──────────────────────────────────────────────────────────────────

def scrape_events_calendar(
    year: int,
    output_dir: Path,
    headless: bool = False,
    slow_mo: int = 100,
    cdp_port: int = 9222,
    skip_translate: bool = False,
    dry_run_translate: bool = True,
) -> dict[str, Any]:
    """
    抓取指定年份的 ITTF 赛事日历。

    Args:
        year: 年份
        output_dir: 输出目录
        headless: 是否无头模式运行
        slow_mo: 慢动作延迟（毫秒）
        cdp_port: CDP 端口，用于连接已有 Chrome
        skip_translate: 跳过翻译步骤
        dry_run_translate: 翻译是否 dry-run

    Returns:
        结果字典
    """
    calendar_url = f"{BASE_URL}/{year}-events-calendar/"
    logger.info("Target URL: %s", calendar_url)

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_output_file = output_dir / f"events_calendar_{year}.json"
    translated_output_file = output_dir / f"events_calendar_{year}_cn.json"
    checkpoint_file = output_dir / f"checkpoint_{year}.json"

    checkpoint = CheckpointStore(checkpoint_file)
    ck_key = f"events_calendar_{year}"

    # 检查是否已完成。仅在不需要补翻译时复用缓存。
    if checkpoint.is_done(ck_key):
        logger.info("Year %s already scraped, loading from output file", year)
        if raw_output_file.exists():
            raw_data = json.loads(raw_output_file.read_text(encoding="utf-8"))
            expected_total = len(raw_data.get("events", []))
            # 检查是否需要翻译
            if not skip_translate and not dry_run_translate:
                # 检查翻译文件是否存在
                if translated_output_file.exists():
                    data = json.loads(translated_output_file.read_text(encoding="utf-8"))
                    if _is_translated_file_complete(data, expected_total):
                        return {"success": True, "data": data, "source": "cache", "output_file": str(translated_output_file)}
                    logger.warning("翻译缓存文件不完整，将基于原始数据重新翻译")
                logger.info("Cached data missing translations, will translate raw data")
            else:
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
        via_cdp, browser, context = _try_connect_cdp(p, cdp_port)

        if not via_cdp:
            # 新启动浏览器
            browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            logger.info("New browser launched (headless=%s)", headless)

        page = context.new_page()
        logger.info("Navigating to %s", calendar_url)
        page.goto(calendar_url, wait_until="domcontentloaded", timeout=30000)
        human_sleep(2.0, 4.0, "initial page load")

        if via_cdp:
            logger.info("Connected to existing Chrome via CDP")
        else:
            # 检测 Cloudflare 或其他风控
            if _check_cloudflare_challenge(page):
                logger.warning("Cloudflare challenge detected!")
                logger.warning("Please complete the verification in the browser window.")
                logger.warning("Press ENTER here after completing verification...")
                input("Press ENTER after completing Cloudflare verification...")
                human_sleep(2.0, 4.0, "after manual verification")

        # 通用风控检测
        risk = detect_risk(page)
        if risk:
            raise RiskControlTriggered(risk)

        # 等待页面加载完成
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            logger.warning("networkidle timeout, using domcontentloaded")
            page.wait_for_load_state("domcontentloaded", timeout=15000)

        human_sleep(2.0, 5.0, "page settle")

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

            # 关闭浏览器
            if via_cdp:
                page.close()
            else:
                browser.close()

            error_data = {
                "year": year,
                "url": calendar_url,
                "scraped_at": scraped_at,
                "error": "No events parsed from page",
                "raw_page_preview": body_text[:2000],
            }

            # 不标记 checkpoint 也不保存文件（避免覆盖有效数据）
            return {
                "success": False,
                "error": "No events parsed from page",
                "data": error_data,
            }

        result_data["summary"]["total"] = len(events)

        # 关闭浏览器
        if via_cdp:
            page.close()
        else:
            browser.close()

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
        encoding="utf-8"
    )
    logger.info("原始数据已保存: %s", raw_output_file)

    # 翻译（如果启用）
    result_data = raw_result_data.copy()
    translated_file_path = None
    if not skip_translate and events:
        logger.info("开始翻译 (dry_run=%s)...", dry_run_translate)
        translated_events = translate_all_events(events, dry_run=dry_run_translate)
        
        translated_result_data = {
            "year": year,
            "url": calendar_url,
            "scraped_at": scraped_at,
            "translated_at": utc_now_iso(),
            "events": translated_events,
            "summary": {
                "total": len(events),
                "with_translation": len(translated_events),
            }
        }
        
        # 保存翻译结果到单独的文件
        if not dry_run_translate:
            translated_output_file.write_text(
                json.dumps(translated_result_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info("翻译数据已保存: %s", translated_output_file)
            translated_file_path = str(translated_output_file)
            result_data = translated_result_data
        else:
            # dry-run 模式下，使用包含翻译标记的结果
            result_data = translated_result_data

    # 标记完成
    checkpoint.mark_done(ck_key)

    return {
        "success": True,
        "data": result_data,
        "output_file": translated_file_path if translated_file_path else str(raw_output_file),
        "raw_file": str(raw_output_file),
        "translated_file": translated_file_path,
    }


def _try_connect_cdp(p: Any, cdp_port: int) -> tuple[bool, Any, Any]:
    """尝试连接已有 Chrome（CDP 模式）"""
    import urllib.request

    cdp_url = f"http://localhost:{cdp_port}"
    try:
        urllib.request.urlopen(f"{cdp_url}/json/version", timeout=2)
    except Exception:
        return False, None, None

    try:
        browser = p.chromium.connect_over_cdp(cdp_url)
        contexts = browser.contexts
        context = contexts[0] if contexts else browser.new_context()
        logger.info("Connected to existing Chrome via CDP at %s", cdp_url)
        return True, browser, context
    except Exception as exc:
        logger.warning("CDP handshake failed: %s", exc)
        return False, None, None


def _check_cloudflare_challenge(page: Any) -> bool:
    """检测 Cloudflare 挑战页面"""
    try:
        # Cloudflare 挑战页面特征
        selectors = [
            "#challenge-title",
            ".challenge-title",
            "#cf-challenge-title",
            "[data-ray]",
            "#challenge-form",
        ]
        for selector in selectors:
            if page.locator(selector).count() > 0:
                return True

        # 检查页面标题或内容
        title = page.title()
        if "Just a moment" in title or "Cloudflare" in title:
            return True

        # 检查 URL 是否包含 challenge
        if "challenges.cloudflare" in page.url:
            return True

    except Exception:
        pass
    return False


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
        help="输出文件路径（默认: data/events_calendar/events_calendar_{year}.json）",
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
        "--skip-translate",
        action="store_true",
        help="跳过翻译步骤",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行翻译（不加此参数则 dry-run）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新抓取（忽略 checkpoint）",
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

    dry_run_translate = not args.apply

    try:
        result = scrape_events_calendar(
            year=args.year,
            output_dir=output_dir,
            headless=args.headless,
            slow_mo=args.slow_mo,
            cdp_port=args.cdp_port,
            skip_translate=args.skip_translate,
            dry_run_translate=dry_run_translate,
        )

        if result.get("success"):
            data = result.get("data", {})
            summary = data.get("summary", {})
            logger.info("=" * 50)
            logger.info("抓取完成！")
            logger.info("年份: %s", data.get("year"))
            logger.info("赛事数量: %s", summary.get("total", 0))
            if not args.skip_translate:
                logger.info("翻译数量: %s", summary.get("with_translation", 0))
                if dry_run_translate:
                    logger.info("(翻译为 dry-run 模式，使用 --apply 执行实际翻译)")
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
