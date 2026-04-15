#!/usr/bin/env python3
"""
ITTF Events List Scraper

从 https://results.ittf.link/index.php/events 抓取赛事列表，
提取 Event ID, Year, Name, Event Type, Event Kind, Matches, Start Date, End Date。

支持：
- CDP 连接已有 Chrome / 新建浏览器
- 每页显示 100 条以减少翻页
- 基于 --from-date 截止日期停止抓取
- Checkpoint 断点续传
- 页码校验
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import random
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from lib.anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep, move_mouse_to_locator
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.browser_session import ensure_logged_in
from lib.capture import sanitize_filename, save_json
from lib.checkpoint import CheckpointStore, utc_now_iso
from lib.navigation_runtime import verify_cdp_session_or_prompt
from lib.page_ops import click_next_page_if_any, guarded_goto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_events_scraper")

BASE_URL = "https://results.ittf.link"
EVENTS_URL = f"{BASE_URL}/index.php/events"
DEFAULT_FROM_DATE = "2024-01-01"

# UA 配置（与 scrape_matches.py 保持一致）
BROWSER_PROFILES_WINDOWS = [
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"Windows"',
        "viewport_choices": [
            {"width": 1280, "height": 768},
            {"width": 1366, "height": 900},
            {"width": 1440, "height": 900},
            {"width": 1920, "height": 1080},
        ],
        "dpr_choices": [1.0, 1.25, 1.5],
    },
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"Windows"',
        "viewport_choices": [
            {"width": 1280, "height": 768},
            {"width": 1366, "height": 900},
            {"width": 1440, "height": 900},
            {"width": 1920, "height": 1080},
        ],
        "dpr_choices": [1.0, 1.25, 1.5],
    },
]

BROWSER_PROFILES_MACOS = [
    {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"macOS"',
        "viewport_choices": [
            {"width": 1280, "height": 800},
            {"width": 1440, "height": 900},
            {"width": 1512, "height": 982},
        ],
        "dpr_choices": [2.0],
    },
    {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="99"',
        "sec_ch_ua_platform": '"macOS"',
        "viewport_choices": [
            {"width": 1280, "height": 800},
            {"width": 1440, "height": 900},
            {"width": 1512, "height": 982},
        ],
        "dpr_choices": [2.0],
    },
]


def select_browser_profiles() -> list[dict[str, Any]]:
    system = platform.system()
    if system == "Darwin":
        logger.info("OS detected: macOS — using macOS browser profiles")
        return BROWSER_PROFILES_MACOS
    logger.info("OS detected: %s — using Windows browser profiles", system)
    return BROWSER_PROFILES_WINDOWS


def parse_from_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise ValueError(f"Invalid --from-date format '{raw}', expected YYYY-MM-DD")


def _query_selector_all_with_retry(root: Any, selector: str, retries: int = 3, delay_sec: float = 0.4) -> list[Any]:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            nodes = root.query_selector_all(selector)
            return nodes or []
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(delay_sec * (attempt + 1))
    if last_exc:
        raise last_exc
    return []


# ── 页面操作 ──────────────────────────────────────────────────────────────────

def select_display_100(page: Any) -> bool:
    """将 Display # 下拉框改为 100 条/页。"""
    selectors = [
        "select[id^='limit']",
        "select.inputbox.form-select",
        ".limit select",
    ]
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.count() == 0 or not loc.is_visible():
                continue
            loc.select_option("100")
            logger.info("Selected Display # = 100 via selector: %s", sel)
            # 等待页面刷新
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(1.0)
            return True
        except Exception as exc:
            logger.warning("Failed to select 100 via %s: %s", sel, exc)
            continue
    logger.warning("Could not find Display # select element")
    return False


def get_pagination_info(page: Any) -> tuple[int | None, int | None, int | None]:
    """从底部分页信息解析当前页码、总页数、总记录数。

    Expected text: "Page 1 of 19 Total: 1850"
    Returns: (current_page, total_pages, total_records)
    """
    selectors = [
        ".limit.row p",
        ".limit p",
        ".pagination-info",
    ]
    for sel in selectors:
        try:
            elements = page.locator(sel).all()
            for el in elements:
                text = " ".join((el.inner_text() or "").split())
                m = re.search(r"Page\s+(\d+)\s+of\s+(\d+)\s+Total:\s*(\d+)", text, re.IGNORECASE)
                if m:
                    return int(m.group(1)), int(m.group(2)), int(m.group(3))
        except Exception:
            continue

    # 兜底：从整个 body 搜索
    try:
        body = page.inner_text("body") or ""
        m = re.search(r"Page\s+(\d+)\s+of\s+(\d+)\s+Total:\s*(\d+)", body, re.IGNORECASE)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
    except Exception:
        pass

    return None, None, None


# ── 表格解析 ──────────────────────────────────────────────────────────────────

def _normalize_header(text: str) -> str:
    return " ".join((text or "").split()).strip().lower()


def _build_header_map(table: Any) -> dict[str, int]:
    """从 thead 构建 header -> column index 映射。"""
    header_rows = _query_selector_all_with_retry(table, "thead tr", retries=2)
    if not header_rows:
        header_rows = _query_selector_all_with_retry(table, "tr", retries=2)

    for row in header_rows:
        th_cells = _query_selector_all_with_retry(row, "th", retries=2)
        if not th_cells:
            continue
        header_map: dict[str, int] = {}
        for idx, cell in enumerate(th_cells):
            raw = " ".join((cell.inner_text() or "").split())
            normalized = _normalize_header(raw)
            if normalized and normalized not in header_map:
                header_map[normalized] = idx
        if header_map:
            return header_map
    return {}


# 期望的列名到可能的别名
COLUMN_ALIASES: dict[str, list[str]] = {
    "event_id": ["event id", "id", "#"],
    "year": ["year"],
    "name": ["name", "event name"],
    "event_type": ["event type", "type"],
    "event_kind": ["event kind", "kind"],
    "matches": ["matches", "match", "# matches"],
    "start_date": ["start date", "start", "from"],
    "end_date": ["end date", "end", "to"],
}


def _resolve_column(header_map: dict[str, int], field: str, fallback_index: int | None = None) -> int | None:
    aliases = COLUMN_ALIASES.get(field, [field])
    for alias in aliases:
        idx = header_map.get(alias)
        if idx is not None:
            return idx
    return fallback_index


def parse_event_rows(page: Any, header_map: dict[str, int] | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """解析当前页面的 events 表格行。

    Returns: (events_list, header_map)
    """
    tables = _query_selector_all_with_retry(page, "table", retries=4)
    events: list[dict[str, Any]] = []

    for table in tables:
        if header_map is None:
            header_map = _build_header_map(table)
            if not header_map:
                continue

        rows = _query_selector_all_with_retry(table, "tbody tr", retries=2)
        if not rows:
            rows = _query_selector_all_with_retry(table, "tr", retries=2)

        for row in rows:
            cells = _query_selector_all_with_retry(row, "td", retries=2)
            if len(cells) < 3:
                continue

            def cell_text(idx: int | None) -> str:
                if idx is not None and 0 <= idx < len(cells):
                    return " ".join((cells[idx].inner_text() or "").split())
                return ""

            event_id_idx = _resolve_column(header_map, "event_id", fallback_index=0)
            year_idx = _resolve_column(header_map, "year", fallback_index=1)
            name_idx = _resolve_column(header_map, "name", fallback_index=2)
            event_type_idx = _resolve_column(header_map, "event_type", fallback_index=3)
            event_kind_idx = _resolve_column(header_map, "event_kind", fallback_index=4)
            matches_idx = _resolve_column(header_map, "matches", fallback_index=5)
            start_date_idx = _resolve_column(header_map, "start_date", fallback_index=6)
            end_date_idx = _resolve_column(header_map, "end_date", fallback_index=7)

            event_id_text = cell_text(event_id_idx)
            # event_id 通常是数字，如果不是则跳过（可能是 header 行）
            if not event_id_text or not event_id_text.isdigit():
                continue

            # 检查 name 列是否有链接
            href = ""
            if name_idx is not None and 0 <= name_idx < len(cells):
                link = cells[name_idx].query_selector("a")
                if link:
                    href = (link.get_attribute("href") or "").strip()

            events.append({
                "event_id": int(event_id_text),
                "year": cell_text(year_idx),
                "name": cell_text(name_idx),
                "event_type": cell_text(event_type_idx),
                "event_kind": cell_text(event_kind_idx),
                "matches": cell_text(matches_idx),
                "start_date": cell_text(start_date_idx),
                "end_date": cell_text(end_date_idx),
                "href": href,
            })

        if events:
            break

    return events, header_map or {}


def _parse_event_date(date_str: str) -> date | None:
    """尝试将 event 的日期字符串解析为 date 对象。"""
    text = (date_str or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
        try:
            from datetime import datetime
            return datetime.strptime(text, fmt).date()
        except Exception:
            pass
    # 尝试只解析年份
    m = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    if m:
        try:
            return date(int(m.group(1)), 12, 31)
        except Exception:
            pass
    return None


def dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for e in events:
        eid = e.get("event_id", 0)
        if eid in seen:
            continue
        seen.add(eid)
        out.append(e)
    return out


# ── 核心抓取逻辑 ──────────────────────────────────────────────────────────────

def _build_output_payload(
    all_events: list[dict[str, Any]],
    from_date: date,
    pages_visited: int,
) -> dict[str, Any]:
    return {
        "scraped_at": utc_now_iso(),
        "from_date": from_date.isoformat(),
        "url": EVENTS_URL,
        "total_events": len(all_events),
        "pages_scraped": pages_visited,
        "events": all_events,
    }


def scrape_events(
    page: Any,
    from_date: date,
    delay_cfg: DelayConfig,
    output_file: Path,
    max_pages: int = 100,
) -> list[dict[str, Any]]:
    """遍历分页抓取所有 events，遇到早于 from_date 的记录则停止。
    每翻一页立即增量写入 output_file，防止中断丢失进度。
    """

    # 1. 选择每页显示 100 条
    human_sleep(2.0, 4.0, "before selecting display count")
    if not select_display_100(page):
        logger.warning("Failed to set display to 100, proceeding with default page size")

    # 2. 获取初始分页信息
    current_page, total_pages, total_records = get_pagination_info(page)
    logger.info("Pagination: page=%s total_pages=%s total_records=%s",
                current_page, total_pages, total_records)

    # 3. 从已有输出文件加载已抓取的 event_id，支持断点续传
    existing_event_ids: set[int] = set()
    all_events: list[dict[str, Any]] = []
    if output_file.exists():
        try:
            existing_data = json.loads(output_file.read_text(encoding="utf-8"))
            for e in existing_data.get("events", []):
                eid = e.get("event_id")
                if eid is not None:
                    existing_event_ids.add(eid)
                    all_events.append(e)
            logger.info("Loaded %s existing events from %s", len(all_events), output_file.name)
        except Exception as exc:
            logger.warning("Failed to load existing output: %s", exc)

    header_map: dict[str, int] | None = None
    pages_visited = 0

    for page_num in range(1, max_pages + 1):
        # 校验当前页码
        detected_page, detected_total, _ = get_pagination_info(page)
        if detected_page is not None and detected_page != page_num:
            logger.warning(
                "Page number mismatch: expected=%s detected=%s (pages_visited=%s)",
                page_num, detected_page, pages_visited,
            )

        risk = detect_risk(page)
        if risk:
            # 风控触发前先保存已有数据
            save_json(output_file, _build_output_payload(all_events, from_date, pages_visited))
            raise RiskControlTriggered(risk)

        events, header_map = parse_event_rows(page, header_map)
        pages_visited += 1
        logger.info("Page %s/%s: parsed %s events",
                     page_num, total_pages or "?", len(events))

        if not events:
            logger.info("No events found on page %s, stopping", page_num)
            break

        reached_cutoff = False
        new_on_this_page = 0
        for event in events:
            # 优先用 start_date，其次 end_date，最后 year
            event_date = _parse_event_date(event.get("start_date", ""))
            if event_date is None:
                event_date = _parse_event_date(event.get("end_date", ""))
            if event_date is None:
                year_str = event.get("year", "")
                if year_str and year_str.isdigit():
                    try:
                        event_date = date(int(year_str), 12, 31)
                    except Exception:
                        pass

            if event_date and event_date < from_date:
                reached_cutoff = True
                logger.info(
                    "Reached event date=%s < from_date=%s on page %s, stopping",
                    event_date.isoformat(), from_date.isoformat(), page_num,
                )
                break

            eid = event.get("event_id")
            if eid is not None and eid in existing_event_ids:
                continue
            all_events.append(event)
            if eid is not None:
                existing_event_ids.add(eid)
            new_on_this_page += 1

        # 每页解析完立即写入
        save_json(output_file, _build_output_payload(all_events, from_date, pages_visited))
        logger.info("Incremental save after page %s: %s total events (%s new on this page)",
                     page_num, len(all_events), new_on_this_page)

        if reached_cutoff:
            break

        # 检查是否还有下一页
        if total_pages is not None and page_num >= total_pages:
            logger.info("Reached last page (%s/%s)", page_num, total_pages)
            break

        human_sleep(delay_cfg.min_request_sec, delay_cfg.max_request_sec, f"before page {page_num + 1}")
        if not click_next_page_if_any(page):
            logger.info("No next page button found after page %s", page_num)
            break

    logger.info("Scraping complete: %s events across %s pages", len(all_events), pages_visited)
    return dedupe_events(all_events)


# ── run ───────────────────────────────────────────────────────────────────────

def run(args: argparse.Namespace) -> int:
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        logger.error("patchright is required. Install with: pip install patchright && python -m patchright install chromium")
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    storage_state = Path(args.storage_state)
    checkpoint_file = Path(args.checkpoint)
    from_date = parse_from_date(args.from_date)

    delay_cfg = DelayConfig(
        min_request_sec=args.min_delay,
        max_request_sec=args.max_delay,
        min_player_gap_sec=5.0,
        max_player_gap_sec=15.0,
    )

    checkpoint = CheckpointStore(checkpoint_file)
    ck_key = f"events_list|from={from_date.isoformat()}"

    output_file = output_dir / f"events_from_{from_date.isoformat()}.json"

    # 检查 checkpoint：如果已完成且非 force 模式，直接返回
    if not args.force and checkpoint.is_done(ck_key) and output_file.exists():
        logger.info("Already completed (checkpoint). Output: %s", output_file)
        return 0

    if args.force:
        checkpoint.reset()

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

        via_cdp, browser, context, page = open_browser_page(
            p,
            use_cdp=True,
            cdp_port=args.cdp_port,
            cdp_only=False,
            launch_kwargs={"headless": args.headless, "slow_mo": args.slow_mo},
            context_kwargs=context_kwargs,
            log_prefix="events",
        )
        if not via_cdp:
            logger.info(
                "New browser context: ua=...%s viewport=%sx%s dpr=%.2f",
                profile["user_agent"][-30:],
                chosen_viewport["width"],
                chosen_viewport["height"],
                chosen_dpr,
            )

        if via_cdp:
            verify_cdp_session_or_prompt(page, EVENTS_URL, delay_cfg)
        else:
            try:
                ensure_logged_in(page, EVENTS_URL, delay_cfg, storage_state, args.init_session)
            except Exception:
                close_browser_page(via_cdp, browser, page)
                raise

            if args.init_session:
                logger.info("Session initialized. Exiting due to --init-session.")
                close_browser_page(via_cdp, browser, page)
                return 0

        # 导航到 events 列表页
        guarded_goto(page, EVENTS_URL, delay_cfg, "open events list page")

        page.wait_for_load_state("domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        risk = detect_risk(page)
        if risk:
            close_browser_page(via_cdp, browser, page)
            raise RiskControlTriggered(risk)

        # 等待表格出现
        try:
            page.locator("table").first.wait_for(timeout=15000)
        except Exception:
            logger.warning("Table did not appear before timeout")

        try:
            events = scrape_events(page, from_date, delay_cfg, output_file)
        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            logger.error("Data saved so far in %s", output_file)
            close_browser_page(via_cdp, browser, page)
            return 3
        except Exception as exc:
            logger.error("Scraping failed: %s", exc)
            close_browser_page(via_cdp, browser, page)
            return 4

        close_browser_page(via_cdp, browser, page)

    if not events:
        logger.error("No events captured")
        return 4

    logger.info("Final output: %s events in %s", len(events), output_file)

    checkpoint.mark_done(ck_key, meta={
        "output_file": str(output_file),
        "total_events": len(events),
    })

    logger.info("Completed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF Events List Scraper")
    parser.add_argument("--output-dir", default="data/events_list")
    parser.add_argument("--storage-state", default="data/session/ittf_storage_state.json")
    parser.add_argument("--checkpoint", default="data/checkpoints/events_list_checkpoint.json")
    parser.add_argument("--from-date", default=DEFAULT_FROM_DATE,
                        help="Stop scraping when reaching events before this date (YYYY-MM-DD)")

    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--init-session", action="store_true",
                        help="Open browser for manual login and save storage-state")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)

    parser.add_argument("--min-delay", type=float, default=5.0)
    parser.add_argument("--max-delay", type=float, default=18.0)

    parser.add_argument("--force", action="store_true", help="Ignore checkpoint, re-scrape")
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
