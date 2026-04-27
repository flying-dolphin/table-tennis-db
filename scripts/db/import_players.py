#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入球员数据：players
从 data/player_profiles/cn/*.json 导入
"""

import sqlite3
import sys
import json
import re
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = CURRENT_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import config
from lib.career_best import normalize_career_best_month

# Windows 编码兼容
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def slugify(name: str) -> str:
    """将姓名转换为 URL 友好的 slug"""
    # 转小写，替换空格为连字符
    slug = name.lower().strip()
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    return slug


def import_players(db_path: str, player_profiles_dir: str) -> dict:
    """
    导入球员数据

    Returns:
        {
            'inserted': int,
            'skipped': int,
            'errors': list
        }
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        player_cols = {row[1] for row in cursor.execute("PRAGMA table_info(players)")}
        if 'career_best_month' not in player_cols:
            cursor.execute("ALTER TABLE players ADD COLUMN career_best_month TEXT")
            player_cols.add('career_best_month')
        if 'career_best_week' in player_cols:
            legacy_rows = cursor.execute("""
                SELECT player_id, career_best_week
                FROM players
                WHERE career_best_month IS NULL AND career_best_week IS NOT NULL
            """).fetchall()
            for row_player_id, career_best_week in legacy_rows:
                normalized = normalize_career_best_month(str(career_best_week), 'week').month
                if normalized:
                    cursor.execute(
                        "UPDATE players SET career_best_month = ? WHERE player_id = ?",
                        (normalized, row_player_id),
                    )

        player_profiles_path = Path(player_profiles_dir)
        json_files = sorted(player_profiles_path.glob('player_*.json'))

        inserted = 0
        skipped = 0
        errors = []

        for i, json_file in enumerate(json_files, 1):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                player_id = data.get('player_id')
                name = data.get('name') or data.get('english_name')
                name_zh = data.get('name_zh')
                country_code = data.get('country_code')

                if not player_id or not name or not country_code:
                    skipped += 1
                    print(f"  [{i:3d}] SKIP (missing fields): {json_file.name}")
                    continue

                slug = slugify(name)

                # 职业生涯统计
                career_stats = data.get('career_stats', {})
                current_year_stats = data.get('current_year_stats', {})

                career_best_month = data.get('career_best_month')
                if not career_best_month and data.get('career_best_week'):
                    career_best_month = normalize_career_best_month(str(data.get('career_best_week')), 'week').month

                cursor.execute("""
                    INSERT OR REPLACE INTO players (
                        player_id, name, name_zh, slug, country, country_code,
                        gender, birth_year, age,
                        style, style_zh, playing_hand, playing_hand_zh, grip, grip_zh,
                        avatar_url, avatar_file,
                        career_events, career_matches, career_wins, career_losses,
                        career_wtt_titles, career_all_titles,
                        career_best_rank, career_best_month,
                        year_events, year_matches, year_wins, year_losses,
                        year_games, year_games_won, year_games_lost,
                        year_wtt_titles, year_all_titles,
                        scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    player_id, name, name_zh, slug,
                    data.get('country_zh'), country_code,
                    data.get('gender'), data.get('birth_year'), data.get('age'),
                    data.get('style'), data.get('style_zh'),
                    data.get('playing_hand'), data.get('playing_hand_zh'),
                    data.get('grip'), data.get('grip_zh'),
                    data.get('avatar_url'), data.get('avatar_file_path'),
                    career_stats.get('events', 0),
                    career_stats.get('matches', 0),
                    career_stats.get('wins', 0),
                    career_stats.get('loses', 0),
                    career_stats.get('wtt_senior_titles', 0),
                    career_stats.get('all_senior_titles', 0),
                    data.get('career_best_rank'),
                    career_best_month,
                    current_year_stats.get('events', 0),
                    current_year_stats.get('matches', 0),
                    current_year_stats.get('wins', 0),
                    current_year_stats.get('loses', 0),
                    current_year_stats.get('games', 0),
                    current_year_stats.get('games_won', 0),
                    current_year_stats.get('games_lost', 0),
                    current_year_stats.get('wtt_senior_titles', 0),
                    current_year_stats.get('all_senior_titles', 0),
                    data.get('scraped_at')
                ))

                print(f"  [{i:3d}] {name:30s} ({country_code}) -> slug: {slug}")
                inserted += 1

            except Exception as e:
                error_msg = f"{json_file.name}: {str(e)}"
                errors.append(error_msg)
                print(f"  [{i:3d}] ERROR: {error_msg}")

        conn.commit()
        conn.close()

        return {
            'inserted': inserted,
            'skipped': skipped,
            'errors': errors
        }

    except Exception as e:
        print(f"[ERROR] Failed to import players: {e}")
        return {'inserted': 0, 'skipped': 0, 'errors': [str(e)]}


def verify_players(db_path: str):
    """验证球员数据"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM players;")
        count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT country_code) FROM players;")
        country_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM players WHERE avatar_file IS NOT NULL;
        """)
        avatar_count = cursor.fetchone()[0]

        print(f"\nVerification:")
        print(f"  Total players:         {count}")
        print(f"  Countries:             {country_count}")
        print(f"  With avatars:          {avatar_count}")

        conn.close()
    except Exception as e:
        print(f"[VERIFY FAILED] {e}")


if __name__ == '__main__':
    db_path = Path(config.DB_PATH)
    player_profiles_dir = config.PROJECT_ROOT / "data" / "player_profiles" / "cn"

    print("=" * 70)
    print("Import Players")
    print("=" * 70)
    print(f"Database:           {db_path}")
    print(f"Player profiles dir: {player_profiles_dir}")
    print("=" * 70 + "\n")

    if not db_path.exists():
        print(f"[ERROR] Database file not found: {db_path}")
        sys.exit(1)

    if not player_profiles_dir.exists():
        print(f"[ERROR] Player profiles directory not found: {player_profiles_dir}")
        sys.exit(1)

    print("Importing players...")
    result = import_players(str(db_path), str(player_profiles_dir))

    print(f"\nResults:")
    print(f"  Inserted: {result['inserted']}")
    print(f"  Skipped:  {result['skipped']}")
    if result['errors']:
        print(f"  Errors:   {len(result['errors'])}")
        for error in result['errors'][:5]:
            print(f"    - {error}")
        if len(result['errors']) > 5:
            print(f"    ... and {len(result['errors']) - 5} more")

    verify_players(str(db_path))

    sys.exit(0 if not result['errors'] else 1)
