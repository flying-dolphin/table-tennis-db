#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入比赛数据：matches
从 data/matches_complete/cn/*.json 导入

关键逻辑：
1. 从 side_a/side_b 提取球员名和国家（fallback 到 raw_row_text）
2. 通过数据库中的 events 表匹配 event_id
3. 通过 player name + country_code 匹配 player_id
4. 去重：同一场比赛在两个球员文件中各出现一次
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


# ============================================================================
# 工具函数
# ============================================================================

def normalize_event_name(name: str) -> str:
    """规范化赛事名称（与 normalize_events.py 中一致）"""
    s = name.strip().lower()
    s = re.sub(r'\s+presented\s+by\s+.*$', '', s)
    s = re.sub(r'[,.]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def normalize_name_key(name: str) -> str:
    """将名字转为排序后的小写单词集合"""
    parts = sorted(name.lower().split())
    return ' '.join(parts)


def parse_player_str(player_str: str):
    """解析 'SUN Yingsha (CHN)' 格式，返回 (name, country_code)"""
    m = re.match(r'^(.+?)\s*\((\w+)\)$', player_str.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return player_str.strip(), None


def parse_raw_row_text(raw_text: str):
    """
    从 raw_row_text 解析对阵信息（fallback 用）
    格式: "2026 | 赛事名 | 选手A (国家A) | 选手B (国家B) | 项目 | 阶段 | 轮次? | 比分 | 局分... | 胜者"
    """
    parts = [p.strip() for p in raw_text.split('|')]
    if len(parts) < 8:
        return None

    player_a_str = parts[2] if len(parts) > 2 else ''
    player_b_str = parts[3] if len(parts) > 3 else ''
    winner_name = parts[-1] if parts else ''

    a_name, a_country = parse_player_str(player_a_str)
    b_name, b_country = parse_player_str(player_b_str)

    return {
        'player_a_name': a_name,
        'player_a_country': a_country,
        'player_b_name': b_name,
        'player_b_country': b_country,
        'winner_name': winner_name,
    }


def build_event_index(cursor):
    """构建赛事索引，基于数据库中的 events 表匹配 event_id。"""
    cursor.execute("SELECT event_id, name, year FROM events")

    by_name_year = {}
    by_name = {}
    for event_id, name, year in cursor.fetchall():
        norm_name = normalize_event_name(name or "")
        if not norm_name:
            continue

        if year is not None:
            by_name_year[(norm_name, int(year))] = event_id
        by_name.setdefault(norm_name, set()).add(event_id)

    return {
        "by_name_year": by_name_year,
        "by_name": by_name,
    }


def resolve_event_id(event_index: dict, event_name: str, event_year: int | None):
    """优先用 赛事名 + 年份 匹配，不命中时退化到唯一赛事名。"""
    norm_event = normalize_event_name(event_name)
    if not norm_event:
        return None

    if event_year is not None:
        event_id = event_index["by_name_year"].get((norm_event, event_year))
        if event_id is not None:
            return event_id

    candidates = sorted(event_index["by_name"].get(norm_event, set()))
    if len(candidates) == 1:
        return candidates[0]

    return None


def make_dedup_key(event_name: str, sub_event: str, stage: str, round_: str,
                   a_name: str, a_country: str, b_name: str, b_country: str) -> str:
    """生成去重键：将两方按字母排序确保同一场比赛只入库一次"""
    pair = sorted([
        f"{(a_name or '').lower()}|{(a_country or '').lower()}",
        f"{(b_name or '').lower()}|{(b_country or '').lower()}"
    ])
    return f"{normalize_event_name(event_name)}|{sub_event}|{stage}|{round_}|{pair[0]}|{pair[1]}"


# ============================================================================
# 导入逻辑
# ============================================================================

def import_matches(db_path: str, matches_dir: str) -> dict:
    result = {
        'total_in_files': 0,
        'inserted': 0,
        'duplicates': 0,
        'unmatched_events': set(),
        'unmatched_players': set(),
        'errors': [],
    }

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # 加载 player index
    cursor.execute("SELECT player_id, name, country_code FROM players")
    player_index = {}
    for player_id, name, country_code in cursor.fetchall():
        player_index[(name, country_code)] = player_id
        player_index[(normalize_name_key(name), country_code)] = player_id
    print(f"Player index: {len(player_index)} entries")

    event_index = build_event_index(cursor)
    print(f"Event index:  {len(event_index['by_name_year'])} name+year entries")

    # 去重集合
    seen_keys = set()

    matches_path = Path(matches_dir)
    json_files = sorted(matches_path.glob("*.json"))
    print(f"Match files: {len(json_files)}\n")

    batch = []
    BATCH_SIZE = 500

    for file_idx, json_file in enumerate(json_files, 1):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            result['errors'].append(f"Load {json_file.name}: {e}")
            continue

        file_count = 0
        file_inserted = 0

        for year_key, year_data in data.get('years', {}).items():
            for event in year_data.get('events', []):
                event_name = event.get('event_name', '')
                event_name_zh = event.get('event_name_zh')
                event_year = event.get('event_year')
                if event_year:
                    try:
                        event_year = int(event_year)
                    except (ValueError, TypeError):
                        event_year = None

                # 匹配 event_id
                event_id = resolve_event_id(event_index, event_name, event_year)
                if event_id is None:
                    result['unmatched_events'].add(event_name)

                for match in event.get('matches', []):
                    result['total_in_files'] += 1
                    file_count += 1

                    sub_event = match.get('sub_event', '')
                    stage = match.get('stage', '')
                    round_ = match.get('round', '')

                    # 提取球员信息（优先 side_a/side_b，fallback raw_row_text）
                    side_a = match.get('side_a', [])
                    side_b = match.get('side_b', [])
                    winner_name = match.get('winner', '')
                    raw_row_text = match.get('raw_row_text', '')

                    if side_a:
                        a_name, a_country = parse_player_str(side_a[0])
                    elif raw_row_text:
                        parsed = parse_raw_row_text(raw_row_text)
                        if parsed:
                            a_name, a_country = parsed['player_a_name'], parsed['player_a_country']
                        else:
                            a_name, a_country = '', None
                    else:
                        a_name, a_country = '', None

                    if side_b:
                        b_name, b_country = parse_player_str(side_b[0])
                    elif raw_row_text:
                        parsed = parse_raw_row_text(raw_row_text)
                        if parsed:
                            b_name, b_country = parsed['player_b_name'], parsed['player_b_country']
                        else:
                            b_name, b_country = '', None
                    else:
                        b_name, b_country = '', None

                    if not winner_name and raw_row_text:
                        parsed = parse_raw_row_text(raw_row_text)
                        if parsed:
                            winner_name = parsed['winner_name']

                    # 去重
                    dedup_key = make_dedup_key(
                        event_name, sub_event, stage, round_,
                        a_name, a_country, b_name, b_country
                    )
                    if dedup_key in seen_keys:
                        result['duplicates'] += 1
                        continue
                    seen_keys.add(dedup_key)

                    # 匹配 player_id
                    player_a_id = None
                    if a_name and a_country:
                        player_a_id = player_index.get((a_name, a_country))
                        if player_a_id is None:
                            player_a_id = player_index.get((normalize_name_key(a_name), a_country))
                        if player_a_id is None:
                            result['unmatched_players'].add(f"{a_name} ({a_country})")

                    player_b_id = None
                    if b_name and b_country:
                        player_b_id = player_index.get((b_name, b_country))
                        if player_b_id is None:
                            player_b_id = player_index.get((normalize_name_key(b_name), b_country))
                        if player_b_id is None:
                            result['unmatched_players'].add(f"{b_name} ({b_country})")

                    # winner_id
                    winner_id = None
                    if winner_name:
                        # winner 可能是 a 或 b
                        if a_name and normalize_name_key(winner_name) == normalize_name_key(a_name):
                            winner_id = player_a_id
                        elif b_name and normalize_name_key(winner_name) == normalize_name_key(b_name):
                            winner_id = player_b_id

                    # games → JSON 字符串
                    games = match.get('games', [])
                    games_json = json.dumps(games) if games else None

                    batch.append((
                        event_id,
                        event_name,
                        event_name_zh,
                        event_year,
                        sub_event,
                        stage,
                        match.get('stage_zh'),
                        round_,
                        match.get('round_zh'),
                        player_a_id,
                        a_name,
                        a_country,
                        player_b_id,
                        b_name,
                        b_country,
                        match.get('match_score', ''),
                        games_json,
                        winner_id,
                        winner_name or '',
                        raw_row_text,
                    ))
                    file_inserted += 1

                    # 批量插入
                    if len(batch) >= BATCH_SIZE:
                        _flush_batch(cursor, batch)
                        batch.clear()

        if file_idx % 20 == 0 or file_idx == len(json_files):
            print(f"  [{file_idx:3d}/{len(json_files)}] {json_file.name:35s} {file_count:4d} matches, {file_inserted:4d} new")

    # 最后一批
    if batch:
        _flush_batch(cursor, batch)
        batch.clear()

    result['inserted'] = len(seen_keys) - result['duplicates']
    result['inserted'] = len(seen_keys)

    conn.commit()
    conn.close()
    return result


def _flush_batch(cursor, batch):
    """批量插入 matches"""
    cursor.executemany("""
        INSERT OR IGNORE INTO matches (
            event_id, event_name, event_name_zh, event_year,
            sub_event_type_code, stage, stage_zh, round, round_zh,
            player_a_id, player_a_name, player_a_country,
            player_b_id, player_b_name, player_b_country,
            match_score, games, winner_id, winner_name,
            raw_row_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, batch)


def verify_matches(db_path: str):
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM matches")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM matches WHERE player_a_id IS NOT NULL")
    with_a = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM matches WHERE player_b_id IS NOT NULL")
    with_b = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM matches WHERE event_id IS NOT NULL")
    with_event = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT event_id) FROM matches WHERE event_id IS NOT NULL")
    unique_events = cursor.fetchone()[0]

    cursor.execute("""
        SELECT sub_event_type_code, COUNT(*) as cnt
        FROM matches GROUP BY sub_event_type_code ORDER BY cnt DESC
    """)
    sub_event_dist = cursor.fetchall()

    print(f"\nVerification:")
    print(f"  Total matches:      {total}")
    print(f"  With event_id:      {with_event} ({with_event*100//max(total,1)}%)")
    print(f"  With player_a_id:   {with_a} ({with_a*100//max(total,1)}%)")
    print(f"  With player_b_id:   {with_b} ({with_b*100//max(total,1)}%)")
    print(f"  Unique events:      {unique_events}")
    print(f"\n  Sub-event distribution:")
    for code, cnt in sub_event_dist:
        print(f"    {code:5s}: {cnt:6d}")

    conn.close()


if __name__ == '__main__':
    matches_dir = PROJECT_ROOT / "data" / "matches_complete" / "cn"

    print("=" * 70)
    print("Import Matches")
    print("=" * 70)
    print(f"Database:      {DB_PATH}")
    print(f"Matches dir:   {matches_dir}")
    print("=" * 70 + "\n")

    if not Path(DB_PATH).exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    result = import_matches(str(DB_PATH), str(matches_dir))

    print(f"\n{'='*70}")
    print("Results:")
    print(f"  Total in files:    {result['total_in_files']}")
    print(f"  Unique (inserted): {result['inserted']}")
    print(f"  Duplicates:        {result['duplicates']}")

    if result['unmatched_events']:
        events_list = sorted(result['unmatched_events'])
        print(f"\n  Unmatched events ({len(events_list)}):")
        for e in events_list[:15]:
            print(f"    - {e}")
        if len(events_list) > 15:
            print(f"    ... and {len(events_list)-15} more")

    if result['unmatched_players']:
        players_list = sorted(result['unmatched_players'])
        print(f"\n  Unmatched players ({len(players_list)}):")
        for p in players_list[:20]:
            print(f"    - {p}")
        if len(players_list) > 20:
            print(f"    ... and {len(players_list)-20} more")

    if result['errors']:
        print(f"\n  Errors ({len(result['errors'])}):")
        for e in result['errors'][:10]:
            print(f"    - {e}")

    verify_matches(str(DB_PATH))
