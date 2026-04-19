#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入赛事日历数据：events_calendar
从 data/events_calendar/cn/*.json 导入。

规则：
1. 通过 name + year 去重，避免重复导入。
2. 优先依赖已入库 events 表补全 event_type / event_kind / category_id。
3. 若 events 表无匹配，通过 event_category_mapping.json 根据 event_type + event_kind 自动分类。
4. 若仍无法分类，保留 event_type / event_kind，category_id 为空。
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

try:
    import config
    PROJECT_ROOT = config.PROJECT_ROOT
    DB_PATH = config.DB_PATH
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DB_PATH = PROJECT_ROOT / "scripts" / "db" / "ittf.db"


def load_category_mapping():
    """加载 event_category_mapping.json，返回 {(event_type, event_kind): category_id} 映射"""
    mapping_file = PROJECT_ROOT / "data" / "event_category_mapping.json"
    if not mapping_file.exists():
        return {}

    with open(mapping_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    result = {}
    for event in data.get('events', []):
        et = event.get('event_type', '')
        ek = event.get('event_kind', '--')
        cat_id = event.get('category_id', '')
        result[(et, ek)] = cat_id
        for alias in event.get('event_kind_aliases', []):
            result[(et, alias)] = cat_id

    return result


def build_category_id_lookup(cursor):
    """构建 category_id -> event_categories.id 的映射"""
    cursor.execute("SELECT id, category_id FROM event_categories")
    return {row[1]: row[0] for row in cursor.fetchall()}


# 全局加载 category_mapping
CATEGORY_MAPPING = load_category_mapping()


def parse_date_range(date_zh: str | None, year: int):
    """解析中文日期范围，返回 (start_date, end_date)"""
    if not date_zh:
        return None, None

    date_zh = date_zh.strip()

    # 处理只有月份的情况，如 "Nov"
    if re.match(r'^[A-Za-z]+$', date_zh):
        return None, None

    # 处理 TBD 情况，如 "26-27 TBD Mar"
    tbd_match = re.search(r'(\d+)-(\d+)\s*TBD\s*([A-Za-z]+)', date_zh, re.IGNORECASE)
    if tbd_match:
        start_day = tbd_match.group(1).zfill(2)
        end_day = tbd_match.group(2).zfill(2)
        month_str = tbd_match.group(3)
        month = month_to_num(month_str)
        if month:
            return f"{year}-{month}-{start_day}", f"{year}-{month}-{end_day}"
        return None, None

    # 解析中文日期范围，格式如 "01-07至01-11" 或 "29 Apr – 2 May"
    # 先统一分隔符
    date_zh = date_zh.replace('–', '-').replace('—', '-')

    # 匹配格式: MM-DD至MM-DD 或 DD Mon – DD Mon
    range_match = re.search(r'(\d+)\s*([A-Za-z]+)\s*[-至]\s*(\d+)\s*([A-Za-z]+)', date_zh, re.IGNORECASE)
    if range_match:
        start_day = range_match.group(1).zfill(2)
        start_month_str = range_match.group(2)
        end_day = range_match.group(3).zfill(2)
        end_month_str = range_match.group(4)

        start_month = month_to_num(start_month_str)
        end_month = month_to_num(end_month_str)

        if start_month and end_month:
            # 处理跨年情况
            if end_month < start_month and start_month >= 10:  # 10-12月可能跨年到次年
                end_year = year + 1
            else:
                end_year = year

            start_date = f"{year}-{start_month}-{start_day}"
            end_date = f"{end_year}-{end_month}-{end_day}"
            return start_date, end_date
        return None, None

    # 匹配格式: MM-DD至MM-DD (纯数字格式)
    simple_match = re.search(r'(\d+)-(\d+)\s*至\s*(\d+)-(\d+)', date_zh)
    if simple_match:
        start_month = simple_match.group(1).zfill(2)
        start_day = simple_match.group(2).zfill(2)
        end_month = simple_match.group(3).zfill(2)
        end_day = simple_match.group(4).zfill(2)

        # 判断是否跨年
        if int(end_month) < int(start_month) and int(start_month) >= 10:
            end_year = year + 1
        else:
            end_year = year

        return f"{year}-{start_month}-{start_day}", f"{end_year}-{end_month}-{end_day}"

    return None, None


def month_to_num(month_str: str) -> str | None:
    """将英文月份转换为数字字符串"""
    month_map = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
        'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
        'january': '01', 'february': '02', 'march': '03', 'april': '04',
        'june': '06', 'july': '07', 'august': '08', 'september': '09',
        'october': '10', 'november': '11', 'december': '12',
    }
    return month_map.get(month_str.lower())


def normalize_event_name(name: str) -> str:
    """规范化赛事名称，尽量与 events / matches 侧保持一致。"""
    if not name:
        return ""

    s = name.strip().lower()
    s = re.sub(r"\s+presented\s+by\s+.*$", "", s)
    s = re.sub(r"[,.]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def extract_event_id(href: str | None):
    if not href:
        return None

    patterns = [
        r"eventId=(\d+)",
        r"/tournament/(\d+)/",
    ]
    for pattern in patterns:
        match = re.search(pattern, href)
        if match:
            return int(match.group(1))
    return None


def build_event_lookup(cursor):
    cursor.execute("""
        SELECT
            event_id,
            year,
            name,
            href,
            event_type_name,
            event_kind,
            event_category_id
        FROM events
    """)

    by_id = {}
    by_href = {}
    by_name_year = {}
    by_name = {}

    for row in cursor.fetchall():
        event = {
            "event_id": row[0],
            "year": row[1],
            "name": row[2],
            "href": row[3],
            "event_type": row[4],
            "event_kind": row[5],
            "event_category_id": row[6],
        }
        norm_name = normalize_event_name(event["name"])

        by_id[event["event_id"]] = event
        if event["href"]:
            by_href[event["href"]] = event
        if norm_name and event["year"] is not None:
            by_name_year[(norm_name, event["year"])] = event
        if norm_name:
            by_name.setdefault(norm_name, []).append(event)

    return {
        "by_id": by_id,
        "by_href": by_href,
        "by_name_year": by_name_year,
        "by_name": by_name,
    }


def build_calendar_lookup(cursor):
    """构建已导入calendar记录的查找表，按 normalize_event_name(name) + year 去重"""
    cursor.execute("""
        SELECT year, name, href, event_id
        FROM events_calendar
    """)

    by_name_year = {}
    by_href = {}
    by_event_id = {}

    for row in cursor.fetchall():
        year, name, href, event_id = row
        if name:
            by_name_year[(normalize_event_name(name), year)] = row
        if href:
            by_href[href] = row
        if event_id:
            by_event_id[event_id] = row

    return {
        "by_name_year": by_name_year,
        "by_href": by_href,
        "by_event_id": by_event_id,
    }


def classify_event_by_name(name: str) -> tuple[str | None, str | None]:
    """
    根据赛事名称自动分类，返回 (event_type, event_kind)
    用于 events 表无匹配时对新 event 进行分类
    """
    if not name:
        return None, None

    # WTT events — Youth 必须在成年组前判断，避免被成年组拦截
    if 'WTT Champions' in name:
        return 'WTT Champions', '--'
    elif 'WTT Finals' in name:
        return 'WTT Finals', '--'
    elif 'WTT Youth Grand Smash' in name or ('Youth Smash' in name):
        return 'WTT Youth Grand Smash', '--'
    elif 'WTT Grand Smash' in name or (('Singapore' in name or 'China' in name or 'United States' in name) and 'Smash' in name and 'Youth' not in name):
        return 'WTT Grand Smash', '--'
    elif 'WTT Youth Star Contender' in name:
        return 'WTT Youth Contender Series', 'WTT Youth Star Contender'
    elif 'WTT Youth Contender' in name:
        return 'WTT Youth Contender Series', 'WTT Youth Contender'
    elif 'WTT Star Contender' in name:
        return 'WTT Contender Series', 'WTT Star Contender'
    elif 'WTT Contender' in name:
        return 'WTT Contender Series', 'WTT Contender'
    elif 'WTT Feeder' in name:
        return 'WTT Feeder Series', '--'

    # ITTF World Team Championships
    elif 'World Team Championships Finals' in name or 'WTTTC Finals' in name:
        return 'ITTF WTTC', 'WTTC Finals'
    elif 'World Team Championships' in name or 'World Team Table Tennis Championships' in name:
        return 'ITTF WTTC', '--'

    # ITTF World Table Tennis Championships (individual) — new naming
    elif 'World Table Tennis Championships' in name:
        return 'ITTF WTTC', '--'

    # ITTF Mixed Team World Cup — 必须在通用 World Cup 前判断
    elif 'Mixed Team World Cup' in name:
        return 'ITTF Mixed Team World Cup', '--'

    # ITTF World Cup
    elif "ITTF Men's & Women's World Cup" in name or 'World Cup' in name:
        return 'ITTF World Cup', '--'

    # ITTF World Youth Championships
    elif 'World Youth Championships' in name or 'World Junior' in name:
        return 'ITTF World Youth Championships', '--'

    # Olympic Qualification
    elif 'Olympic Qualification' in name or 'Olympic Qualifier' in name:
        return 'Olympic Games', 'Qualification'

    # Youth Olympic Games
    elif 'Youth Olympic Games' in name:
        return 'Youth Olympic Games', '--'

    # Olympic Games
    elif 'Olympic Games' in name:
        return 'Olympic Games', '--'

    # Multi-sport events
    elif 'Asian Games' in name or 'Asian Para Games' in name:
        return 'Multi sport events', '--'
    elif 'Pan American Games' in name:
        return 'Continental Games', '--'
    elif 'South American Games' in name or 'South American Youth Games' in name:
        return 'Multi sport events', '--'
    elif 'African Games' in name:
        return 'Continental Games', '--'
    elif 'Central American and Caribbean Games' in name:
        return 'Multi sport events', '--'
    elif 'Parasouth American Games' in name:
        return 'Multi sport events', '--'
    elif 'Solidarity Games' in name:
        return 'Multi sport events', '--'

    # ITTF Para events
    elif 'World Para Championships' in name:
        return 'ITTF Para', 'World Para Championships'
    elif 'World Para Elite' in name:
        return 'ITTF Para', 'World Para Elite'
    elif 'World Para Challenger' in name:
        return 'ITTF Para', 'World Para Challenger'
    elif 'World Para Future' in name:
        return 'ITTF Para', 'World Para Future'

    # ITTF Masters/World Masters
    elif 'World Masters' in name or 'Masters Championships' in name:
        return 'ITTF Masters', '--'

    # ETTU / Continental events
    elif 'ETTU' in name or 'Europe ' in name:
        if 'Top 16' in name or 'Top 10' in name:
            return 'Continental', 'Senior Cup'
        elif 'U21' in name:
            return 'Continental', 'U21 Championships'
        elif 'U13' in name:
            return 'Continental', 'Youth Championships'
        elif 'European' in name and 'Youth' in name:
            return 'Continental', 'Youth Championships'
        elif 'European' in name and 'Individual' in name:
            return 'Continental', 'Senior Championships'
        elif 'European' in name and 'Team' in name:
            return 'Continental', 'Senior Championships'
        elif 'Championships' in name:
            return 'Continental', 'Senior Championships'
        return 'Continental', 'Senior Championships'

    # ITTF Regional events
    elif 'ITTF-Africa' in name:
        if 'North' in name or 'South' in name or 'East' in name or 'West' in name or 'Central' in name:
            return 'Regional', 'Senior Championships'
        elif 'Youth' in name:
            return 'Continental', 'Youth Championships'
        elif 'Cup' in name:
            return 'Continental', 'Senior Cup'
        elif 'Championships' in name:
            return 'Continental', 'Senior Championships'
        return 'Continental', 'Senior Championships'

    elif 'ITTF-Americas' in name or 'ITTF-ATTU' in name or 'ITTF-Oceania' in name:
        if 'North American' in name:
            return 'Regional', 'Senior Championships'
        elif 'South American' in name:
            return 'Continental', 'Youth Championships' if 'Youth' in name else 'Senior Championships'
        elif 'Central American' in name or 'Caribbean' in name:
            return 'Continental', 'Youth Championships' if 'Youth' in name else 'Senior Championships'
        elif 'Asian' in name or 'ATTU' in name:
            return 'Continental', 'Youth Championships' if 'Youth' in name else 'Senior Championships'
        elif 'Oceania' in name:
            if 'Hopes' in name:
                return 'Continental', 'Youth Championships'
            return 'Continental', 'Senior Championships'
        elif 'Masters' in name:
            return 'Continental', 'Senior Championships'
        elif 'Cup' in name:
            return 'Continental', 'Senior Cup'
        elif 'Championships' in name:
            return 'Continental', 'Senior Championships'
        return 'Continental', 'Senior Championships'

    # Special qualifier events
    elif 'Special Event Qualifier' in name or 'Qualification' in name:
        return 'Regional', 'Senior Championships'

    # Catch all
    return 'Continental', 'Senior Championships'


def resolve_event_v2(calendar_event: dict, event_lookup: dict, year: int):
    """
    事件匹配逻辑：
    1. 先通过标准化名称 + year 匹配
    2. 再通过 href 匹配
    3. 最后通过 event_id 匹配
    """
    norm_name = normalize_event_name(calendar_event.get("name", ""))

    # 1. 先尝试按标准化名称 + year 匹配
    if norm_name:
        matched = event_lookup["by_name_year"].get((norm_name, year))
        if matched:
            return matched
        # 如果没有精确匹配，尝试模糊匹配（名称相同，年份不同）
        candidates = [v for k, v in event_lookup["by_name_year"].items()
                      if k[0] == norm_name]
        if len(candidates) == 1:
            return candidates[0]

    # 2. 通过 href 匹配
    href = calendar_event.get("href")
    if href:
        matched = event_lookup["by_href"].get(href)
        if matched:
            return matched

    # 3. 通过 event_id 匹配（从href解析）
    event_id = extract_event_id(href)
    if event_id is not None:
        matched = event_lookup["by_id"].get(event_id)
        if matched:
            return matched

    return None


def import_events_calendar(db_path: str, calendar_dir: str) -> dict:
    result = {
        "inserted": 0,
        "skipped": 0,
        "matched_events": 0,
        "classified_by_name": 0,
        "errors": [],
    }

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # 构建 events 表查找表
    event_lookup = build_event_lookup(cursor)

    # 构建 category_id -> 数字 id 的映射
    cat_id_lookup = build_category_id_lookup(cursor)

    # 构建已导入 calendar 记录查找表（用于去重）
    calendar_lookup = build_calendar_lookup(cursor)

    calendar_path = Path(calendar_dir)
    json_files = sorted(calendar_path.glob("*.json"))

    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            result["errors"].append(f"Failed to load {json_file.name}: {exc}")
            continue

        year = int(data.get("year", 0))
        events = data.get("events", [])
        print(f"Processing {json_file.name}: {len(events)} calendar events")

        for event in events:
            event_name = event.get("name", "")
            href = event.get("href", "")

            # 检查是否已存在（按 normalize_event_name(name) + year 判断）
            norm_name = normalize_event_name(event_name)
            existing = calendar_lookup["by_name_year"].get((norm_name, year)) if norm_name else None

            if existing:
                result["skipped"] += 1
                continue

            # 尝试匹配 events 表
            matched_event = resolve_event_v2(event, event_lookup, year)

            # 从 href 解析 event_id
            event_id_from_href = extract_event_id(href)
            matched_event_id = matched_event["event_id"] if matched_event else event_id_from_href

            # 获取 event_type, event_kind, category_id
            if matched_event:
                event_type = matched_event["event_type"]
                event_kind = matched_event["event_kind"]
                # events.event_category_id 已是数字外键，直接使用
                event_category_id = matched_event["event_category_id"]
                result["matched_events"] += 1
            else:
                # 通过名称自动分类
                event_type, event_kind = classify_event_by_name(event_name)
                # 通过 event_type + event_kind 查找 category_id，再转换为数字 id
                cat_id_str = CATEGORY_MAPPING.get((event_type or '', event_kind or '--'))
                event_category_id = cat_id_lookup.get(cat_id_str) if cat_id_str else None
                result["classified_by_name"] += 1

            # 解析 date_zh 获取 start_date 和 end_date
            start_date, end_date = parse_date_range(event.get("date_zh"), year)

            try:
                cursor.execute("""
                    INSERT INTO events_calendar (
                        year, name, name_zh, event_type, event_kind, event_category_id,
                        date_range, date_range_zh, start_date, end_date,
                        location, location_zh, status, href, event_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    year,
                    event_name,
                    event.get("name_zh"),
                    event_type,
                    event_kind,
                    event_category_id,
                    event.get("date"),
                    event.get("date_zh"),
                    start_date,
                    end_date,
                    event.get("location"),
                    event.get("location_zh"),
                    event.get("status"),
                    href,
                    matched_event_id,
                ))
                result["inserted"] += 1
            except sqlite3.Error as exc:
                result["errors"].append(f"{event_name}: {exc}")

    conn.commit()
    conn.close()
    return result


def verify_events_calendar(db_path: str):
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM events_calendar")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM events_calendar WHERE event_id IS NOT NULL")
    linked_events = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM events_calendar WHERE event_category_id IS NOT NULL")
    typed_events = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM events_calendar WHERE start_date IS NOT NULL")
    with_dates = cursor.fetchone()[0]

    print("\nVerification:")
    print(f"  Total calendar rows:   {total}")
    print(f"  With start_date:      {with_dates} ({with_dates * 100 // max(total, 1)}%)")
    print(f"  Linked to events:     {linked_events} ({linked_events * 100 // max(total, 1)}%)")
    print(f"  With event category:  {typed_events} ({typed_events * 100 // max(total, 1)}%)")

    conn.close()


if __name__ == "__main__":
    calendar_dir = PROJECT_ROOT / "data" / "events_calendar" / "cn"

    print("=" * 70)
    print("Import Events Calendar")
    print("=" * 70)
    print(f"Database:      {DB_PATH}")
    print(f"Calendar dir:  {calendar_dir}")
    print("=" * 70 + "\n")

    if not Path(DB_PATH).exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    if not calendar_dir.exists():
        print(f"[ERROR] Calendar directory not found: {calendar_dir}")
        sys.exit(1)

    result = import_events_calendar(str(DB_PATH), str(calendar_dir))

    print("\nResults:")
    print(f"  Inserted:             {result['inserted']}")
    print(f"  Skipped (dup):       {result['skipped']}")
    print(f"  Matched events:      {result['matched_events']}")
    print(f"  Classified by name:  {result['classified_by_name']}")

    if result["errors"]:
        print(f"\n  Errors ({len(result['errors'])}):")
        for err in result["errors"][:10]:
            print(f"    - {err}")

    verify_events_calendar(str(DB_PATH))

    sys.exit(0 if not result["errors"] else 1)
