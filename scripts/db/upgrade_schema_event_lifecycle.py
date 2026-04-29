#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 迁移：赛事生命周期与日程相关 schema。

新增/变更：
- events 加列 lifecycle_status / time_zone / last_synced_at；
  现有行 lifecycle_status 回填为 'completed'。
- 新建 venues 字典表。
- 新建 event_session_schedule（赛事完整日程，按日纲要）。
- 新建 event_draw_entries / event_draw_entry_players（签表-签位）。
- 新建 event_schedule_matches / event_schedule_match_sides /
  event_schedule_match_side_players（赛程-按场）。

幂等：可重复执行。运行前自动备份数据库。

用法:
    python upgrade_schema_event_lifecycle.py
    python upgrade_schema_event_lifecycle.py --db /path/to/ittf.db
    python upgrade_schema_event_lifecycle.py --no-backup
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import config

    DEFAULT_DB_PATH = Path(config.DB_PATH)
except ImportError:
    DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "db" / "ittf.db"


# ── 工具 ─────────────────────────────────────────────────────────────────────


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def backup_database(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(f"{db_path.suffix}.backup.{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


# ── 迁移步骤 ─────────────────────────────────────────────────────────────────


def add_event_lifecycle_columns(cursor: sqlite3.Cursor) -> dict:
    added: list[str] = []
    if not column_exists(cursor, "events", "lifecycle_status"):
        cursor.execute(
            "ALTER TABLE events ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'upcoming'"
        )
        added.append("lifecycle_status")
    if not column_exists(cursor, "events", "time_zone"):
        cursor.execute("ALTER TABLE events ADD COLUMN time_zone TEXT")
        added.append("time_zone")
    if not column_exists(cursor, "events", "last_synced_at"):
        cursor.execute("ALTER TABLE events ADD COLUMN last_synced_at TEXT")
        added.append("last_synced_at")

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_lifecycle ON events(lifecycle_status)"
    )

    # 回填：所有已完赛历史 event 设为 completed（仅当当前值为默认 'upcoming' 时）
    backfilled = cursor.execute(
        """
        UPDATE events
        SET lifecycle_status = 'completed'
        WHERE lifecycle_status = 'upcoming'
          AND (
               EXISTS (SELECT 1 FROM matches m WHERE m.event_id = events.event_id)
            OR (end_date IS NOT NULL AND end_date < date('now'))
          )
        """
    ).rowcount

    return {"added_columns": added, "backfilled_rows": backfilled}


def create_venues(cursor: sqlite3.Cursor) -> bool:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS venues (
            venue_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            name_zh         TEXT,
            city            TEXT,
            country_code    TEXT,
            time_zone       TEXT NOT NULL,
            aliases         TEXT,
            UNIQUE(name)
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_venues_country ON venues(country_code)"
    )
    return True


def create_session_schedule(cursor: sqlite3.Cursor) -> bool:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS event_session_schedule (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id            INTEGER NOT NULL,
            day_index           INTEGER NOT NULL,
            local_date          TEXT NOT NULL,
            start_local_time    TEXT,
            end_local_time      TEXT,
            venue_raw           TEXT,
            venue_id            INTEGER,
            table_count         INTEGER,
            raw_sub_events_text TEXT,
            parsed_rounds_json  TEXT,
            updated_at          TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (event_id) REFERENCES events(event_id),
            FOREIGN KEY (venue_id) REFERENCES venues(venue_id),
            UNIQUE(event_id, day_index)
        )
        """
    )
    cursor.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_event_session_schedule_event
            ON event_session_schedule(event_id);
        CREATE INDEX IF NOT EXISTS idx_event_session_schedule_date
            ON event_session_schedule(local_date);
        """
    )
    return True


def create_draw_entries(cursor: sqlite3.Cursor) -> bool:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS event_draw_entries (
            entry_id            INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id            INTEGER NOT NULL,
            sub_event_type_code TEXT NOT NULL,
            stage_code          TEXT NOT NULL,
            slot_index          INTEGER NOT NULL,
            seed                INTEGER,
            group_code          TEXT,
            team_code           TEXT,
            placeholder_text    TEXT,
            created_at          TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (event_id) REFERENCES events(event_id),
            FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
            FOREIGN KEY (stage_code) REFERENCES stage_codes(code),
            UNIQUE(event_id, sub_event_type_code, stage_code, slot_index)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_draw_entries_event
            ON event_draw_entries(event_id, sub_event_type_code)
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS event_draw_entry_players (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id        INTEGER NOT NULL,
            player_order    INTEGER NOT NULL,
            player_id       INTEGER,
            player_name     TEXT NOT NULL,
            player_country  TEXT,
            FOREIGN KEY (entry_id) REFERENCES event_draw_entries(entry_id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES players(player_id),
            UNIQUE(entry_id, player_order)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_draw_entry_players_player
            ON event_draw_entry_players(player_id)
        """
    )
    return True


def create_schedule_matches(cursor: sqlite3.Cursor) -> bool:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS event_schedule_matches (
            schedule_match_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id            INTEGER NOT NULL,
            sub_event_type_code TEXT NOT NULL,
            stage_code          TEXT NOT NULL,
            round_code          TEXT NOT NULL,
            group_code          TEXT,
            scheduled_local_at  TEXT,
            scheduled_utc_at    TEXT,
            table_no            TEXT,
            session_label       TEXT,
            venue_id            INTEGER,
            status              TEXT NOT NULL DEFAULT 'scheduled',
            match_score         TEXT,
            games               TEXT,
            winner_side         TEXT,
            promoted_match_id   INTEGER,
            last_synced_at      TEXT,
            FOREIGN KEY (event_id) REFERENCES events(event_id),
            FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
            FOREIGN KEY (stage_code) REFERENCES stage_codes(code),
            FOREIGN KEY (round_code) REFERENCES round_codes(code),
            FOREIGN KEY (venue_id) REFERENCES venues(venue_id),
            FOREIGN KEY (promoted_match_id) REFERENCES matches(match_id) ON DELETE SET NULL,
            CHECK (status IN ('scheduled', 'live', 'completed', 'walkover', 'cancelled')),
            CHECK (winner_side IN ('A', 'B') OR winner_side IS NULL)
        )
        """
    )
    cursor.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_event_schedule_matches_event
            ON event_schedule_matches(event_id, sub_event_type_code);
        CREATE INDEX IF NOT EXISTS idx_event_schedule_matches_local_at
            ON event_schedule_matches(scheduled_local_at);
        CREATE INDEX IF NOT EXISTS idx_event_schedule_matches_status
            ON event_schedule_matches(status);
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS event_schedule_match_sides (
            schedule_side_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_match_id   INTEGER NOT NULL,
            side_no             INTEGER NOT NULL,
            entry_id            INTEGER,
            placeholder_text    TEXT,
            team_code           TEXT,
            is_winner           INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (schedule_match_id) REFERENCES event_schedule_matches(schedule_match_id) ON DELETE CASCADE,
            FOREIGN KEY (entry_id) REFERENCES event_draw_entries(entry_id) ON DELETE SET NULL,
            CHECK (side_no IN (1, 2)),
            CHECK (is_winner IN (0, 1)),
            UNIQUE(schedule_match_id, side_no)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_schedule_match_sides_match
            ON event_schedule_match_sides(schedule_match_id)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS event_schedule_match_side_players (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_side_id    INTEGER NOT NULL,
            player_order        INTEGER NOT NULL,
            player_id           INTEGER,
            player_name         TEXT NOT NULL,
            player_country      TEXT,
            FOREIGN KEY (schedule_side_id) REFERENCES event_schedule_match_sides(schedule_side_id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES players(player_id),
            UNIQUE(schedule_side_id, player_order)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_schedule_match_side_players_player
            ON event_schedule_match_side_players(player_id)
        """
    )
    return True


# ── 入口 ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="P0 schema migration: event lifecycle.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip database backup before migration.")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1

    if not args.no_backup:
        backup_path = backup_database(args.db)
        print(f"Backup created: {backup_path}")

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    try:
        print("\n=== events: 加列 + 回填 lifecycle_status ===")
        result = add_event_lifecycle_columns(cursor)
        print(f"  added columns: {result['added_columns'] or '(none, already present)'}")
        print(f"  backfilled rows -> 'completed': {result['backfilled_rows']}")

        print("\n=== venues 字典表 ===")
        create_venues(cursor)
        print("  ok")

        print("\n=== event_session_schedule（按日纲要）===")
        create_session_schedule(cursor)
        print("  ok")

        print("\n=== event_draw_entries / _players（签表-签位）===")
        create_draw_entries(cursor)
        print("  ok")

        print("\n=== event_schedule_matches / _sides / _side_players（赛程-按场）===")
        create_schedule_matches(cursor)
        print("  ok")

        conn.commit()
        print("\n✅ Committed.")

        # 简要快照
        print("\n=== 快照 ===")
        for sql, label in [
            ("SELECT lifecycle_status, COUNT(*) FROM events GROUP BY lifecycle_status", "events.lifecycle_status"),
            ("SELECT COUNT(*) FROM venues", "venues 行数"),
            ("SELECT COUNT(*) FROM event_session_schedule", "event_session_schedule 行数"),
            ("SELECT COUNT(*) FROM event_draw_entries", "event_draw_entries 行数"),
            ("SELECT COUNT(*) FROM event_schedule_matches", "event_schedule_matches 行数"),
        ]:
            rows = list(cursor.execute(sql))
            print(f"  {label}: {rows}")

        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
