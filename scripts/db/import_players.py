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


def validate_player_profiles(
    player_profiles_dir: str,
    db_path: str | None = None,
) -> tuple[list[tuple[Path, dict]], list[str]]:
    """Load profile JSON files and validate fields required by the players table."""
    profiles: list[tuple[Path, dict]] = []
    errors: list[str] = []
    existing_country_codes: dict[str, str] = {}

    if db_path and Path(db_path).is_file():
        conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
        try:
            existing_country_codes = {
                str(player_id): str(country_code)
                for player_id, country_code in conn.execute(
                    "SELECT player_id, country_code FROM players WHERE country_code IS NOT NULL"
                )
            }
        finally:
            conn.close()

    for json_file in sorted(Path(player_profiles_dir).glob('player_*.json')):
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{json_file.name}: invalid JSON: {exc}")
            continue

        required_values = {
            'player_id': data.get('player_id'),
            'name': data.get('name') or data.get('english_name'),
            'country_code': data.get('country_code') or existing_country_codes.get(str(data.get('player_id') or '')),
            'gender': data.get('gender'),
        }
        missing_fields = [
            field
            for field, value in required_values.items()
            if not str(value or '').strip()
        ]
        if missing_fields:
            errors.append(f"{json_file.name}: missing required fields: {', '.join(missing_fields)}")
            continue

        profiles.append((json_file, data))

    return profiles, errors


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
    profiles, validation_errors = validate_player_profiles(player_profiles_dir, db_path)
    if validation_errors:
        return {'inserted': 0, 'skipped': 0, 'errors': validation_errors}

    conn = None
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

        inserted = 0
        skipped = 0
        errors = []

        for i, (json_file, data) in enumerate(profiles, 1):
            try:
                player_id = data.get('player_id')
                name = data.get('name') or data.get('english_name')
                name_zh = data.get('name_zh')
                country_code = data.get('country_code')
                country = data.get('country_zh')

                existing_player = None
                if player_id and (not country_code or not country):
                    existing_player = cursor.execute(
                        "SELECT country_code, country FROM players WHERE player_id = ?",
                        (player_id,),
                    ).fetchone()
                    if existing_player:
                        country_code = country_code or existing_player[0]
                        country = country or existing_player[1]

                if not player_id or not name or not country_code:
                    skipped += 1
                    print(f"  [{i:3d}] SKIP (missing fields): {json_file.name}")
                    continue

                slug = str(player_id)

                # 职业生涯统计
                career_stats = data.get('career_stats', {})
                current_year_stats = data.get('current_year_stats', {})

                career_best_month = data.get('career_best_month')
                if not career_best_month and data.get('career_best_week'):
                    career_best_month = normalize_career_best_month(str(data.get('career_best_week')), 'week').month

                cursor.execute("""
                    INSERT INTO players (
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
                    ON CONFLICT(player_id) DO UPDATE SET
                        name = excluded.name,
                        name_zh = excluded.name_zh,
                        slug = excluded.slug,
                        country = excluded.country,
                        country_code = excluded.country_code,
                        gender = excluded.gender,
                        birth_year = excluded.birth_year,
                        age = excluded.age,
                        style = excluded.style,
                        style_zh = excluded.style_zh,
                        playing_hand = excluded.playing_hand,
                        playing_hand_zh = excluded.playing_hand_zh,
                        grip = excluded.grip,
                        grip_zh = excluded.grip_zh,
                        avatar_url = excluded.avatar_url,
                        avatar_file = excluded.avatar_file,
                        career_events = excluded.career_events,
                        career_matches = excluded.career_matches,
                        career_wins = excluded.career_wins,
                        career_losses = excluded.career_losses,
                        career_wtt_titles = excluded.career_wtt_titles,
                        career_all_titles = excluded.career_all_titles,
                        career_best_rank = excluded.career_best_rank,
                        career_best_month = excluded.career_best_month,
                        year_events = excluded.year_events,
                        year_matches = excluded.year_matches,
                        year_wins = excluded.year_wins,
                        year_losses = excluded.year_losses,
                        year_games = excluded.year_games,
                        year_games_won = excluded.year_games_won,
                        year_games_lost = excluded.year_games_lost,
                        year_wtt_titles = excluded.year_wtt_titles,
                        year_all_titles = excluded.year_all_titles,
                        scraped_at = excluded.scraped_at
                """, (
                    player_id, name, name_zh, slug,
                    country, country_code,
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

        if errors:
            conn.rollback()
            inserted = 0
        else:
            conn.commit()
        conn.close()

        return {
            'inserted': inserted,
            'skipped': skipped,
            'errors': errors
        }

    except Exception as e:
        if conn is not None:
            conn.rollback()
            conn.close()
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
    import argparse
    parser = argparse.ArgumentParser(description='导入球员数据')
    parser.add_argument('--dir', type=str, default=None,
                        help='球员 JSON 文件目录（默认：data/player_profiles/cn）')
    parser.add_argument('--validate-only', action='store_true',
                        help='只校验球员 JSON，不写入数据库')
    args = parser.parse_args()

    db_path = Path(config.DB_PATH)
    player_profiles_dir = Path(args.dir) if args.dir else config.PROJECT_ROOT / "data" / "player_profiles" / "cn"

    print("=" * 70)
    print("Import Players")
    print("=" * 70)
    print(f"Database:           {db_path}")
    print(f"Player profiles dir: {player_profiles_dir}")
    print("=" * 70 + "\n")

    if not player_profiles_dir.exists():
        print(f"[ERROR] Player profiles directory not found: {player_profiles_dir}")
        sys.exit(1)

    if args.validate_only:
        profiles, errors = validate_player_profiles(str(player_profiles_dir), str(db_path))
        print(f"Validated profiles: {len(profiles)}")
        print(f"Validation errors: {len(errors)}")
        for error in errors[:5]:
            print(f"  - {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more")
        sys.exit(0 if not errors else 1)

    if not db_path.exists():
        print(f"[ERROR] Database file not found: {db_path}")
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
