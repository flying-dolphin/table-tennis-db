#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入赛事日历数据：events_calendar
从 data/events_calendar/cn/*.json 导入。

规则：
1. 赛历原始 JSON 缺少 event_type / event_kind，优先依赖已入库 events 表补全。
2. 通过 event_id / href / 标准化名称 + 年份匹配 events。
3. 若无法匹配，则保留赛历原始字段，event_type / event_kind / event_category_id 为空。
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


def resolve_event(calendar_event: dict, event_lookup: dict, year: int):
    href = calendar_event.get("href")
    event_id = extract_event_id(href)
    if event_id is not None:
        matched = event_lookup["by_id"].get(event_id)
        if matched:
            return matched

    if href:
        matched = event_lookup["by_href"].get(href)
        if matched:
            return matched

    norm_name = normalize_event_name(calendar_event.get("name", ""))
    if norm_name:
        matched = event_lookup["by_name_year"].get((norm_name, year))
        if matched:
            return matched

        candidates = event_lookup["by_name"].get(norm_name, [])
        if len(candidates) == 1:
            return candidates[0]

    return None


def import_events_calendar(db_path: str, calendar_dir: str) -> dict:
    result = {
        "inserted": 0,
        "matched_events": 0,
        "unmatched_events": set(),
        "errors": [],
    }

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    event_lookup = build_event_lookup(cursor)

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
        scraped_at = data.get("scraped_at")
        events = data.get("events", [])
        print(f"Processing {json_file.name}: {len(events)} calendar events")

        for event in events:
            matched_event = resolve_event(event, event_lookup, year)
            matched_event_id = matched_event["event_id"] if matched_event else extract_event_id(event.get("href"))
            event_type = matched_event["event_type"] if matched_event else None
            event_kind = matched_event["event_kind"] if matched_event else None
            event_category_id = matched_event["event_category_id"] if matched_event else None

            if matched_event:
                result["matched_events"] += 1
            else:
                result["unmatched_events"].add(event.get("name", ""))

            try:
                cursor.execute("""
                    INSERT INTO events_calendar (
                        year, name, name_zh, event_type, event_kind, event_category_id,
                        date_range, date_range_zh, start_date, end_date,
                        location, location_zh, status, href, event_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?)
                """, (
                    year,
                    event.get("name"),
                    event.get("name_zh"),
                    event_type,
                    event_kind,
                    event_category_id,
                    event.get("date"),
                    event.get("date_zh"),
                    event.get("location"),
                    event.get("location_zh"),
                    event.get("status"),
                    event.get("href"),
                    matched_event_id,
                ))
                result["inserted"] += 1
            except sqlite3.Error as exc:
                result["errors"].append(f"{event.get('name')}: {exc}")

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

    print("\nVerification:")
    print(f"  Total calendar rows:   {total}")
    print(f"  Linked to events:      {linked_events} ({linked_events * 100 // max(total, 1)}%)")
    print(f"  With event category:   {typed_events} ({typed_events * 100 // max(total, 1)}%)")

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
    print(f"  Inserted:       {result['inserted']}")
    print(f"  Matched events: {result['matched_events']}")

    if result["unmatched_events"]:
        unmatched = sorted(result["unmatched_events"])
        print(f"\n  Unmatched calendar events ({len(unmatched)}):")
        for event_name in unmatched[:15]:
            print(f"    - {event_name}")
        if len(unmatched) > 15:
            print(f"    ... and {len(unmatched) - 15} more")

    if result["errors"]:
        print(f"\n  Errors ({len(result['errors'])}):")
        for err in result["errors"][:10]:
            print(f"    - {err}")

    verify_events_calendar(str(DB_PATH))

    sys.exit(0 if not result["errors"] else 1)
