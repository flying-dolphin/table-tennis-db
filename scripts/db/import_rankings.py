#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入排名数据：ranking_snapshots / ranking_entries / points_breakdown
从 data/rankings/cn/*.json 导入
"""

import sqlite3
import sys
import json
import re
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


def normalize_name_key(name: str) -> str:
    """将名字转为排序后的小写单词集合，用于不区分姓名顺序的匹配。
    'HARIMOTO Miwa' 和 'Miwa HARIMOTO' 都变成 'harimoto miwa'
    """
    parts = sorted(name.lower().split())
    return ' '.join(parts)


def build_player_index(cursor) -> dict:
    """构建多种键 → player_id 的索引，支持不同名字格式的匹配。

    索引键：
    1. (name, country_code) — 精确匹配
    2. (normalized_name_key, country_code) — 不区分姓名顺序
    """
    cursor.execute("SELECT player_id, name, country_code FROM players")
    index = {}
    for player_id, name, country_code in cursor.fetchall():
        # 精确匹配
        index[(name, country_code)] = player_id
        # 不区分姓名顺序
        norm_key = normalize_name_key(name)
        index[(norm_key, country_code)] = player_id
    return index


def lookup_player(player_index: dict, name: str, country_code: str):
    """查找 player_id，按优先级尝试多种匹配方式"""
    # 1. 精确匹配
    pid = player_index.get((name, country_code))
    if pid:
        return pid
    # 2. 不区分姓名顺序
    norm_key = normalize_name_key(name)
    return player_index.get((norm_key, country_code))


def normalize_expires_date(date_str: str) -> str:
    """将 '2026-May-25' 格式转为 '2026-05-25'"""
    if not date_str:
        return None
    # 已经是 ISO 格式
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    # 转换月份
    months = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
    }
    m = re.match(r'(\d{4})-(\w+)-(\d{1,2})', date_str)
    if m:
        year, month_str, day = m.groups()
        month = months.get(month_str, '01')
        return f"{year}-{month}-{int(day):02d}"
    return date_str


def import_rankings(db_path: str, rankings_dir: str) -> dict:
    result = {
        'snapshots': 0,
        'entries': 0,
        'breakdowns': 0,
        'unmatched_players': [],
        'errors': [],
    }

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    player_index = build_player_index(cursor)
    print(f"Player index: {len(player_index)} entries")

    rankings_path = Path(rankings_dir)
    json_files = sorted(rankings_path.glob("*.json"))

    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            result['errors'].append(f"Failed to load {json_file.name}: {e}")
            continue

        category = data.get('category', '')
        ranking_week = data.get('ranking_week', '')
        ranking_date = data.get('ranking_date', '')
        scraped_at = data.get('scraped_at', '')
        total_players = data.get('total_players', 0)

        print(f"\nProcessing {json_file.name}")
        print(f"  Category: {category}, Week: {ranking_week}, Date: {ranking_date}")

        # 1. 插入 ranking_snapshot
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO ranking_snapshots
                (category, ranking_week, ranking_date, total_players, scraped_at)
                VALUES (?, ?, ?, ?, ?)
            """, (category, ranking_week, ranking_date, total_players, scraped_at))
            snapshot_id = cursor.lastrowid
            result['snapshots'] += 1
        except sqlite3.Error as e:
            result['errors'].append(f"Snapshot insert failed: {e}")
            continue

        # 2. 插入 ranking_entries 和 points_breakdown
        rankings = data.get('rankings', [])
        entries_count = 0
        bd_count = 0
        unmatched_in_file = set()

        for r in rankings:
            name = r.get('name', '')
            country_code = r.get('country_code', '')

            # 匹配 player_id
            player_id = lookup_player(player_index, name, country_code)
            if player_id is None:
                if name not in unmatched_in_file:
                    unmatched_in_file.add(name)
                    result['unmatched_players'].append({
                        'name': name,
                        'country_code': country_code,
                        'rank': r.get('rank'),
                    })
                continue  # 跳过无法匹配的球员

            rank = r.get('rank')
            points = r.get('points', 0)
            rank_change = r.get('rank_change', 0)

            # 插入 ranking_entry
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO ranking_entries
                    (snapshot_id, player_id, rank, points, rank_change)
                    VALUES (?, ?, ?, ?, ?)
                """, (snapshot_id, player_id, rank, points, rank_change))
                entries_count += 1
            except sqlite3.Error as e:
                result['errors'].append(f"Entry {name}: {e}")
                continue

            # 插入 points_breakdown
            for pb in r.get('points_breakdown', []):
                expires_on = normalize_expires_date(pb.get('expires_on'))
                # 优先使用中文版到期日（已经是 ISO 格式）
                if pb.get('expires_on_zh'):
                    expires_on = pb['expires_on_zh']

                try:
                    cursor.execute("""
                        INSERT INTO points_breakdown
                        (snapshot_id, player_id, event_name, event_name_zh,
                         event_type_code, category_name_zh,
                         position, position_zh, points, expires_on)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        snapshot_id,
                        player_id,
                        pb.get('event', ''),
                        pb.get('event_zh'),
                        pb.get('category'),
                        pb.get('category_zh'),
                        pb.get('position'),
                        pb.get('position_zh'),
                        pb.get('points', 0),
                        expires_on,
                    ))
                    bd_count += 1
                except sqlite3.Error as e:
                    result['errors'].append(f"Breakdown {name}/{pb.get('event')}: {e}")

        result['entries'] += entries_count
        result['breakdowns'] += bd_count

        print(f"  Entries: {entries_count}/{len(rankings)}")
        print(f"  Breakdowns: {bd_count}")
        if unmatched_in_file:
            print(f"  Unmatched players: {len(unmatched_in_file)}")

    conn.commit()
    conn.close()
    return result


def verify_rankings(db_path: str):
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM ranking_snapshots")
    snapshots = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM ranking_entries")
    entries = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM points_breakdown")
    breakdowns = cursor.fetchone()[0]

    cursor.execute("""
        SELECT rs.ranking_week, rs.ranking_date, COUNT(re.entry_id) as player_count
        FROM ranking_snapshots rs
        LEFT JOIN ranking_entries re ON rs.snapshot_id = re.snapshot_id
        GROUP BY rs.snapshot_id
    """)
    snapshot_details = cursor.fetchall()

    print(f"\nVerification:")
    print(f"  Snapshots:   {snapshots}")
    print(f"  Entries:     {entries}")
    print(f"  Breakdowns:  {breakdowns}")
    print(f"  Avg breakdowns per player: {breakdowns/entries:.1f}" if entries else "")
    for week, date, count in snapshot_details:
        print(f"  Snapshot: {week} ({date}) -> {count} players")

    conn.close()


if __name__ == '__main__':
    rankings_dir = PROJECT_ROOT / "data" / "rankings" / "cn"

    print("=" * 70)
    print("Import Rankings")
    print("=" * 70)
    print(f"Database:     {DB_PATH}")
    print(f"Rankings dir: {rankings_dir}")
    print("=" * 70 + "\n")

    if not Path(DB_PATH).exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    result = import_rankings(str(DB_PATH), str(rankings_dir))

    print(f"\n{'='*70}")
    print("Results:")
    print(f"  Snapshots:   {result['snapshots']}")
    print(f"  Entries:     {result['entries']}")
    print(f"  Breakdowns:  {result['breakdowns']}")

    if result['unmatched_players']:
        print(f"\n  Unmatched players ({len(result['unmatched_players'])}):")
        for p in result['unmatched_players'][:20]:
            print(f"    #{p['rank']:3d} {p['name']:30s} ({p['country_code']})")

    if result['errors']:
        print(f"\n  Errors ({len(result['errors'])}):")
        for e in result['errors'][:10]:
            print(f"    - {e}")

    verify_rankings(str(DB_PATH))

    sys.exit(0 if not result['errors'] else 1)
