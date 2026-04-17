#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入赛事数据：events
从 data/events_list/cn/*.json 导入，同时匹配 event_categories / event_type_mapping。
"""

import sqlite3
import sys
import json
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


def resolve_event_category(cursor, event_type: str, event_kind: str | None):
    """根据 event_type + event_kind 匹配标准赛事分类。"""
    cursor.execute("""
        SELECT
            c.id,
            c.category_id,
            c.category_name_zh
        FROM event_type_mapping m
        JOIN event_categories c ON m.category_id = c.id
        WHERE m.event_type = ?
          AND ((m.event_kind = ?) OR (m.event_kind IS NULL AND ? IS NULL))
          AND m.is_active = 1
        ORDER BY m.priority DESC, m.id ASC
        LIMIT 1
    """, (event_type, event_kind, event_kind))
    row = cursor.fetchone()
    if row:
        return {
            'event_category_id': row[0],
            'category_code': row[1],
            'category_name_zh': row[2],
        }
    return {
        'event_category_id': None,
        'category_code': None,
        'category_name_zh': None,
    }


def import_events(db_path: str, events_dir: str) -> dict:
    result = {'inserted': 0, 'skipped': 0, 'errors': []}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    events_path = Path(events_dir)
    json_files = sorted(events_path.glob("*.json"))

    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            result['errors'].append(f"Failed to load {json_file.name}: {e}")
            continue

        events = data.get('events', [])
        print(f"Processing {json_file.name}: {len(events)} events")

        for event in events:
            event_id = event.get('event_id')
            name = event.get('name', '')
            if not event_id or not name:
                result['skipped'] += 1
                continue

            event_type_name = event.get('event_type', '')
            event_kind = event.get('event_kind')
            category_info = resolve_event_category(cursor, event_type_name, event_kind)

            # 解析 matches 数量
            matches_str = event.get('matches', '0')
            try:
                total_matches = int(matches_str)
            except (ValueError, TypeError):
                total_matches = 0

            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO events (
                        event_id, year, name, name_zh,
                        event_type_name,
                        event_kind, event_kind_zh,
                        event_category_id, category_code, category_name_zh,
                        total_matches, start_date, end_date, location,
                        href, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_id,
                    int(event.get('year', 0)),
                    name,
                    event.get('name_zh'),
                    event_type_name,
                    event_kind,
                    event.get('event_kind_zh'),
                    category_info['event_category_id'],
                    category_info['category_code'],
                    category_info['category_name_zh'],
                    total_matches,
                    event.get('start_date'),
                    event.get('end_date'),
                    event.get('location'),
                    event.get('href'),
                    data.get('scraped_at'),
                ))
                result['inserted'] += 1
            except sqlite3.Error as e:
                result['errors'].append(f"event_id={event_id}: {e}")

    conn.commit()
    conn.close()
    return result


def verify_events(db_path: str):
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM events")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM events WHERE event_category_id IS NOT NULL")
    typed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM events WHERE name_zh IS NOT NULL")
    translated = cursor.fetchone()[0]

    cursor.execute("""
        SELECT MIN(year), MAX(year) FROM events
    """)
    min_year, max_year = cursor.fetchone()

    cursor.execute("""
        SELECT e.category_name_zh, COUNT(*) as cnt
        FROM events e
        GROUP BY e.category_name_zh
        ORDER BY cnt DESC
        LIMIT 10
    """)
    type_dist = cursor.fetchall()

    print(f"\nVerification:")
    print(f"  Total events:      {total}")
    print(f"  With event_type:   {typed} ({typed*100//total}%)")
    print(f"  With Chinese name: {translated} ({translated*100//total}%)")
    print(f"  Year range:        {min_year} - {max_year}")
    print(f"\n  Top event types:")
    for name, cnt in type_dist:
        print(f"    {name or '(unmapped)':40s} {cnt:5d}")

    conn.close()


if __name__ == '__main__':
    events_dir = PROJECT_ROOT / "data" / "events_list" / "cn"

    print("=" * 70)
    print("Import Events")
    print("=" * 70)
    print(f"Database:   {DB_PATH}")
    print(f"Events dir: {events_dir}")
    print("=" * 70 + "\n")

    if not Path(DB_PATH).exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    if not events_dir.exists():
        print(f"[ERROR] Events directory not found: {events_dir}")
        sys.exit(1)

    result = import_events(str(DB_PATH), str(events_dir))

    print(f"\nResults:")
    print(f"  Inserted: {result['inserted']}")
    print(f"  Skipped:  {result['skipped']}")
    if result['errors']:
        print(f"  Errors:   {len(result['errors'])}")
        for err in result['errors'][:10]:
            print(f"    - {err}")

    verify_events(str(DB_PATH))

    sys.exit(0 if not result['errors'] else 1)
