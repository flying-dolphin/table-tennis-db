#!/usr/bin/env python3
"""
Backfill start_date / end_date for existing matches_complete JSON files.

完全复用 scrape_matches.py 的球员搜索 + autocomplete 交互流程，
只访问赛事列表页（不进入赛事详情抓比分），然后回填日期字段。

用法:
    python backfill_event_dates.py                    # dry-run
    python backfill_event_dates.py --apply           # 实际写入
    python backfill_event_dates.py --players-file X  # 只处理指定球员
"""

import argparse
import json
import logging
import random
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from lib.anti_bot import DelayConfig, human_sleep
from lib.browser_session import ensure_logged_in
from lib.page_ops import guarded_goto

BASE_URL = "https://results.ittf.link"
SEARCH_URL = f"{BASE_URL}/index.php/matches/players-matches-per-event"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("backfill_event_dates")


# ── 解析函数（与 scrape_matches.py 保持一致）────────────────────────────────────

def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def parse_event_rows(page: Any) -> list[dict[str, Any]]:
    """从当前赛事列表页解析所有行，包含 start_date / end_date。"""
    tables = page.locator("table").all()
    events: list[dict[str, Any]] = []

    for table in tables:
        rows = table.locator("tbody tr").all() or table.locator("tr").all()
        for row in rows:
            cells = row.locator("td").all()
            if len(cells) < 2:
                continue

            first_text = (cells[0].inner_text() or "").strip()
            if not first_text.isdigit():
                continue

            link = cells[0].locator("a").first
            if link.count() == 0:
                continue
            href = link.get_attribute("href")

            cell_texts = [(c.inner_text() or "").strip() for c in cells]
            event_name = cell_texts[1] if len(cell_texts) > 1 else ""
            event_type = cell_texts[2] if len(cell_texts) > 2 else ""
            year_str = cell_texts[3] if len(cell_texts) > 3 else ""
            start_date = cell_texts[4].strip() if len(cell_texts) > 4 else ""
            end_date = cell_texts[5].strip() if len(cell_texts) > 5 else ""

            events.append(
                {
                    "match_count": int(first_text),
                    "event_name": event_name,
                    "event_type": event_type,
                    "event_year": year_str,
                    "start_date": start_date,
                    "end_date": end_date,
                    "href": href,
                }
            )
    return events


def _event_sort_date(event: dict[str, Any]) -> Optional[date]:
    """从 start_date 优先解析，失败时回退 year-12-31。"""
    start = str(event.get("start_date", "") or "").strip()
    if start:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(start, fmt).date()
            except Exception:
                pass

    texts = [
        str(event.get("event_name", "") or ""),
        str(event.get("event_type", "") or ""),
        str(event.get("event_year", "") or ""),
    ]
    for part in texts:
        for m in re.finditer(r"\b(20\d{2})\b", part):
            y = int(m.group(1))
            if 1990 <= y <= 2030:
                return date(y, 12, 31)

    try:
        y = int(str(event.get("event_year", "") or event.get("year", "") or "0"))
        if y > 0:
            return date(y, 12, 31)
    except Exception:
        pass
    return None


# ── scrape_matches.py 中的球员搜索 + autocomplete 逻辑 ────────────────────────

def click_go(page: Any) -> bool:
    """点击 Go 按钮，提交球员搜索。"""
    try:
        btn = page.locator("button[type='submit'], input[type='submit'], .btn-primary, button:has-text('Go')").first
        if btn.count() > 0:
            btn.click()
            return True
    except Exception:
        pass
    try:
        btn = page.locator("form button[type='submit']").first
        if btn.count() > 0:
            btn.click()
            return True
    except Exception:
        pass
    return False


def open_or_select_autocomplete(
    page: Any,
    player_name: str,
    country_code: str,
    delay_cfg: DelayConfig,
) -> bool:
    """
    复刻 scrape_matches.py 的球员搜索流程：
    1. 在搜索框输入球员名（带国家代码）
    2. 等待 autocomplete 下拉出现
    3. 点击匹配的 autocomplete 项
    """
    search_key = f"{player_name} ({country_code})"

    # 找到搜索输入框
    input_locators = [
        page.locator("input[id*='player'][id*='search']"),
        page.locator("input[id*='search'][id*='player']"),
        page.locator("input[id='player_name'], input[id='player_name_auto']"),
        page.locator("input[placeholder*='player' i], input[placeholder*='search' i]"),
        page.locator("input[type='text'][id*='player']"),
        page.locator("input.autocomplete-input"),
        page.locator("input.form-control[type='text']"),
    ]
    input_handle = None
    for loc in input_locators:
        try:
            if loc.count() > 0:
                input_handle = loc.first
                break
        except Exception:
            continue

    if not input_handle:
        logger.warning("[autocomplete] 未找到搜索输入框")
        return False

    # 清空并输入球员名
    try:
        input_handle.click(click_count=3)
        input_handle.press("Control+a") if sys.platform != "darwin" else input_handle.press("Meta+a")
        time.sleep(0.1)
        input_handle.type_(search_key, delay=50)
    except Exception:
        try:
            input_handle.fill("")
            time.sleep(0.2)
            input_handle.type_(search_key, delay=50)
        except Exception:
            logger.warning("[autocomplete] 输入失败")
            return False

    human_sleep(1.5, 3.0, "wait for autocomplete dropdown")

    # 等待 autocomplete 出现
    dropdown_selectors = [
        "ul.autocomplete-list li", "ul.typeahead li",
        "div.autocomplete-list li", "div.typeahead li",
        "ul.dropdown-menu li a",
        ".ui-autocomplete li",
        "[role='listbox'] li", "[role='option']",
        "ul.list-group li",
        "div.list-group-item",
        "ul li.dropdown-item",
    ]
    option_handle = None
    for sel in dropdown_selectors:
        try:
            opts = page.locator(sel)
            if opts.count() > 0:
                option_handle = opts.first
                break
        except Exception:
            continue

    if not option_handle:
        logger.warning("[autocomplete] 未找到下拉选项")
        return False

    # 尝试精确匹配
    matched = False
    for attempt in range(5):
        try:
            all_opts = page.locator(
                "ul.autocomplete-list li, ul.typeahead li, [role='listbox'] li, [role='option']"
            ).all()
            count = len(all_opts)
            for idx in range(count):
                opt = all_opts[idx]
                txt = (opt.inner_text() or "").strip()
                if player_name.upper() in txt.upper() and country_code.upper() in txt.upper():
                    try:
                        data_val = opt.get_attribute("data-value")
                        if data_val:
                            opt.click()
                            matched = True
                            logger.info("[autocomplete] 点击了 data-value 选项: %s", data_val)
                            break
                    except Exception:
                        pass
                    try:
                        opt.click()
                        matched = True
                        break
                    except Exception:
                        pass
                if matched:
                    break
            if matched:
                break
        except Exception:
            pass

        # 兜底：直接点击第一个出现的选项
        try:
            first_opt = page.locator("ul.autocomplete-list li, ul.typeahead li").first
            if first_opt.count() > 0:
                first_opt.click()
                matched = True
                logger.info("[autocomplete] 兜底点击第一个选项")
                break
        except Exception:
            pass

        human_sleep(0.5, 1.0, "retry autocomplete")

    if not matched:
        logger.warning("[autocomplete] 未能匹配到球员选项")
        return False

    human_sleep(0.5, 1.2, "after autocomplete selection")
    return True


def select_and_load_player_events(
    page: Any,
    player_name: str,
    country_code: str,
    delay_cfg: DelayConfig,
) -> bool:
    """
    完整流程：
    1. guarded_goto(SEARCH_URL)
    2. open_or_select_autocomplete()
    3. click_go()
    4. 等待页面加载
    """
    logger.info("导航到搜索页: %s", SEARCH_URL)
    try:
        guarded_goto(page, SEARCH_URL, delay_cfg, "open search page")
    except Exception as e:
        logger.warning("guarded_goto 失败: %s，尝试直接 goto", e)
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=20000)

    human_sleep(1.0, 2.0, "search page settle")

    if not open_or_select_autocomplete(page, player_name, country_code, delay_cfg):
        return False

    human_sleep(0.3, 0.8, "before search click")

    if not click_go(page):
        logger.warning("点击 Go 按钮失败")

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass

    human_sleep(1.0, 2.0, "after form submit")
    return True


# ── 分页抓取（与 scrape_matches.py 一致）────────────────────────────────────

def collect_events_with_pagination(
    page: Any,
    from_date: Optional[date],
    max_pages: int = 50,
) -> list[dict[str, Any]]:
    """抓取所有赛事行，支持翻页；遇到 from_date 截止时停止。"""
    all_events: list[dict[str, Any]] = []
    reached_cutoff = False

    for page_num in range(1, max_pages + 1):
        raw_events = parse_event_rows(page)
        if not raw_events:
            logger.debug("第 %d 页无赛事，停止翻页", page_num)
            break

        for event in raw_events:
            sort_date = _event_sort_date(event)
            if sort_date is None:
                all_events.append(event)
                continue
            if from_date is not None and sort_date < from_date:
                reached_cutoff = True
                logger.info(
                    "  页 %d 赛事 '%s' 日期 %s < 截止 %s，停止翻页",
                    page_num, event.get("event_name", ""), sort_date, from_date
                )
                break
            all_events.append(event)

        if reached_cutoff:
            break

        # 点击下一页
        next_clicked = False
        try:
            next_btn = page.locator("li.page-item:not(.disabled) a[rel='next'], a[rel='next']").first
            if next_btn.count() > 0:
                next_btn.click()
                page.wait_for_load_state("networkidle", timeout=8000)
                next_clicked = True
                human_sleep(0.8, 1.8, "after pagination click")
        except Exception:
            pass

        if not next_clicked:
            try:
                pagination_items = page.locator("li.page-item a").all()
                for item in pagination_items:
                    txt = (item.inner_text() or "").strip()
                    if txt.isdigit() and int(txt) == page_num + 1:
                        item.click()
                        page.wait_for_load_state("networkidle", timeout=8000)
                        next_clicked = True
                        human_sleep(0.8, 1.8, "after page turn")
                        break
            except Exception:
                pass

        if not next_clicked:
            logger.info("第 %d 页未找到下一页按钮，停止翻页", page_num)
            break

    return all_events


# ── 主逻辑 ───────────────────────────────────────────────────────────────────

def event_key(event: dict) -> str:
    # event_year 兼容 parse_event_rows 新格式和 matches_complete 文件中的已有格式
    year = event.get("event_year") or event.get("year") or ""
    return f"{event.get('event_name', '')}||{year}"


def backfill_player(
    page: Any,
    player_file: Path,
    from_year: Optional[int],
    dry_run: bool,
) -> tuple[int, int]:
    """完整流程：搜索球员 → 抓列表 → 回填已有 events。返回 (updated, total_fetched)。"""
    with open(player_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    player_name = data.get("player_name", "")
    country_code = data.get("country_code", "")
    player_id = data.get("player_id") or data.get("player_external_id")

    if not player_name:
        logger.warning("文件 %s 缺少 player_name，跳过", player_file.name)
        return 0, 0

    from_date = date(from_year, 1, 1) if from_year else None
    delay_cfg = DelayConfig(
        min_request_sec=2.0,
        max_request_sec=5.0,
        min_player_gap_sec=1.0,
        max_player_gap_sec=3.0,
    )

    logger.info("处理 %s (%s)", player_name, country_code)

    if not select_and_load_player_events(page, player_name, country_code, delay_cfg):
        logger.warning("  球员搜索加载失败: %s", player_file.name)
        return 0, 0

    events = collect_events_with_pagination(page, from_date)

    if not events:
        logger.info("  无赛事数据")
        return 0, 0

    logger.info("  抓取到 %d 条赛事记录", len(events))

    # 过滤掉无意义的占位事件
    meaningful = [e for e in events if e.get("event_name")]
    new_map: dict[str, dict] = {event_key(e): e for e in meaningful}

    updated = 0
    years = data.get("years", {})
    for year_key, year_data in years.items():
        year_events: list[dict] = year_data.get("events", [])
        for ev in year_events:
            key = event_key(ev)
            if key in new_map:
                new_ev = new_map[key]
                if new_ev.get("start_date") and not ev.get("start_date"):
                    ev["start_date"] = new_ev["start_date"]
                    updated += 1
                if new_ev.get("end_date") and not ev.get("end_date"):
                    ev["end_date"] = new_ev["end_date"]
                    updated += 1

    if updated > 0 and not dry_run:
        with open(player_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("  ✓ 更新了 %d 个条目的日期字段", updated)
    elif updated > 0:
        logger.info("  [dry-run] 本次应更新 %d 个条目", updated)

    return updated, len(events)


def main():
    parser = argparse.ArgumentParser(description="回填 matches_complete 中的 start_date / end_date")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent.parent / "data" / "matches_complete"),
        type=str,
        help="matches_complete 目录 (默认: <script-dir>/../data/matches_complete)",
    )
    parser.add_argument(
        "--players-file",
        type=str,
        default=None,
        help="只处理指定球员文件（文件名或部分匹配）",
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=None,
        help="只抓此年份之后的赛事（如 2014）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入文件；不加此参数则 dry-run",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="每个球员之间等待秒数 (默认: 3.0)",
    )
    parser.add_argument(
        "--storage-state",
        default=str(Path(__file__).parent.parent / "data" / "session" / "ittf_storage_state.json"),
        type=str,
        help="浏览器登录状态文件",
    )
    parser.add_argument(
        "--init-session",
        action="store_true",
        help="强制重新登录（不复用已有 session）",
    )
    parser.add_argument(
        "--cdp-url",
        default=None,
        type=str,
        help="CDP browser 地址，填入则复用已有登录态（如 http://localhost:3456）",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    storage_state = Path(args.storage_state)
    if not output_dir.exists():
        logger.error("目录不存在: %s", output_dir)
        sys.exit(1)

    all_files = sorted(output_dir.glob("*.json"))
    if args.players_file:
        matched = [
            f for f in all_files
            if args.players_file in f.name
        ]
        if not matched:
            logger.error("找不到匹配 '%s' 的文件", args.players_file)
            sys.exit(1)
        files = matched
    else:
        files = all_files

    logger.info("共 %d 个文件待处理 (dry-run=%s)", len(files), not args.apply)

    # delay_cfg 用于 ensure_logged_in（页面加载），独立于球员处理逻辑
    login_delay_cfg = DelayConfig(
        min_request_sec=2.0,
        max_request_sec=5.0,
        min_player_gap_sec=1.0,
        max_player_gap_sec=3.0,
    )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("需要 playwright: pip install playwright && playwright install chromium")
        sys.exit(1)

    use_cdp = bool(args.cdp_url)

    with sync_playwright() as p:
        if use_cdp:
            # 复用 CDP browser，天然携带登录态，不需要 storage_state
            cdp_url = args.cdp_url.rstrip("/")
            try:
                import urllib.request
                resp = urllib.request.urlopen(f"{cdp_url}/json/protocol", timeout=5)
                targets = json.loads(resp.read().decode())
                ws_url = targets[0]["webSocketDebuggerUrl"]
                logger.info("连接 CDP browser: %s", ws_url[:60])
                browser = p.chromium.connect_over_cdp(ws_url)
            except Exception as exc:
                logger.error("无法连接 CDP browser %s: %s", cdp_url, exc)
                sys.exit(1)
        else:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=profile["viewport"],
            locale="en-US",
            timezone_id="Asia/Shanghai",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            device_scale_factor=profile["dpr"],
            color_scheme="light",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        page = context.new_page()
        try:
            if not use_cdp:
                # 非 CDP 模式才需要确保登录
                if storage_state.exists():
                    ensure_logged_in(page, SEARCH_URL, login_delay_cfg, str(storage_state), args.init_session)
                else:
                    ensure_logged_in(page, SEARCH_URL, login_delay_cfg, str(storage_state), True)
            total_updated = 0
            for i, pf in enumerate(files, 1):
                logger.info("[%d/%d] 处理 %s", i, len(files), pf.name)
                try:
                    updated, ev_count = backfill_player(
                        page, pf,
                        from_year=args.from_year,
                        dry_run=not args.apply,
                    )
                    total_updated += updated
                except Exception as e:
                    logger.error("处理 %s 时出错: %s", pf.name, e)

                if i < len(files):
                    wait = args.delay + random.uniform(0, 1.0)
                    logger.info("  等待 %.1f 秒后继续...", wait)
                    time.sleep(wait)
        finally:
            browser.close()

    logger.info("完成，共更新 %d 个 event 条目", total_updated)
    if not args.apply:
        logger.info("(本次为 dry-run，加 --apply 才真正写入)")


if __name__ == "__main__":
    main()
