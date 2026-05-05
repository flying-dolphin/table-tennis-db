#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Schema migration: current event model + historical team ties.

This migration is intentionally additive:
- add matches.team_tie_id
- create historical team_ties tables
- create current_* tables

It does not drop or rewrite existing current-event tables.
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


def backup_database(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(f"{db_path.suffix}.backup.{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def ensure_matches_team_tie_id(cursor: sqlite3.Cursor) -> None:
    if not column_exists(cursor, "matches", "team_tie_id"):
        cursor.execute("ALTER TABLE matches ADD COLUMN team_tie_id INTEGER")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_team_tie ON matches(team_tie_id)")


def create_team_ties_tables(cursor: sqlite3.Cursor) -> None:
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS team_ties (
            team_tie_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id             INTEGER NOT NULL,
            sub_event_type_code  TEXT NOT NULL,
            stage                TEXT,
            stage_zh             TEXT,
            stage_code           TEXT,
            round                TEXT,
            round_zh             TEXT,
            round_code           TEXT,
            group_code           TEXT,
            match_score          TEXT,
            winner_side          TEXT,
            winner_team_code     TEXT,
            status               TEXT NOT NULL DEFAULT 'completed',
            source_type          TEXT NOT NULL,
            source_key           TEXT,
            promoted_from_event_id INTEGER,
            promoted_at          TEXT,
            created_at           TEXT DEFAULT (datetime('now')),
            updated_at           TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (event_id) REFERENCES events(event_id),
            FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
            CHECK (winner_side IN ('A', 'B') OR winner_side IS NULL),
            CHECK (status IN ('scheduled', 'live', 'completed', 'walkover', 'cancelled'))
        );
        CREATE INDEX IF NOT EXISTS idx_team_ties_event
            ON team_ties(event_id, sub_event_type_code);
        CREATE INDEX IF NOT EXISTS idx_team_ties_round
            ON team_ties(event_id, stage_code, round_code);
        CREATE INDEX IF NOT EXISTS idx_team_ties_group
            ON team_ties(event_id, group_code);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_team_ties_source
            ON team_ties(event_id, sub_event_type_code, IFNULL(source_key, ''));

        CREATE TABLE IF NOT EXISTS team_tie_sides (
            team_tie_side_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            team_tie_id          INTEGER NOT NULL,
            side_no              INTEGER NOT NULL,
            team_code            TEXT,
            team_name            TEXT,
            seed                 INTEGER,
            qualifier            INTEGER,
            is_winner            INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (team_tie_id) REFERENCES team_ties(team_tie_id) ON DELETE CASCADE,
            CHECK (side_no IN (1, 2)),
            CHECK (is_winner IN (0, 1)),
            UNIQUE(team_tie_id, side_no)
        );
        CREATE INDEX IF NOT EXISTS idx_team_tie_sides_tie
            ON team_tie_sides(team_tie_id);
        CREATE INDEX IF NOT EXISTS idx_team_tie_sides_team
            ON team_tie_sides(team_code);

        CREATE TABLE IF NOT EXISTS team_tie_side_players (
            team_tie_side_player_id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_tie_side_id        INTEGER NOT NULL,
            player_order            INTEGER NOT NULL,
            player_id               INTEGER,
            player_name             TEXT NOT NULL,
            player_country          TEXT,
            FOREIGN KEY (team_tie_side_id) REFERENCES team_tie_sides(team_tie_side_id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES players(player_id),
            UNIQUE(team_tie_side_id, player_order)
        );
        CREATE INDEX IF NOT EXISTS idx_team_tie_side_players_side
            ON team_tie_side_players(team_tie_side_id);
        CREATE INDEX IF NOT EXISTS idx_team_tie_side_players_player
            ON team_tie_side_players(player_id);
        """
    )


def create_current_tables(cursor: sqlite3.Cursor) -> None:
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS current_event_session_schedule (
            current_session_schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );
        CREATE INDEX IF NOT EXISTS idx_current_event_session_schedule_event
            ON current_event_session_schedule(event_id);
        CREATE INDEX IF NOT EXISTS idx_current_event_session_schedule_date
            ON current_event_session_schedule(local_date);

        CREATE TABLE IF NOT EXISTS current_event_group_standings (
            current_standing_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id              INTEGER NOT NULL,
            stage_label           TEXT NOT NULL,
            team_code             TEXT NOT NULL,
            group_code            TEXT NOT NULL,
            organization_code     TEXT NOT NULL,
            team_name             TEXT,
            qualification_mark    TEXT,
            played                INTEGER,
            won                   INTEGER,
            lost                  INTEGER,
            result                INTEGER,
            rank                  INTEGER,
            score_for             INTEGER,
            score_against         INTEGER,
            games_won             INTEGER,
            games_lost            INTEGER,
            players_json          TEXT,
            source_url            TEXT,
            updated_at            TEXT NOT NULL,
            FOREIGN KEY (event_id) REFERENCES events(event_id),
            UNIQUE(event_id, stage_label, team_code, group_code, organization_code)
        );
        CREATE INDEX IF NOT EXISTS idx_current_event_group_standings_event_team
            ON current_event_group_standings(event_id, team_code);
        CREATE INDEX IF NOT EXISTS idx_current_event_group_standings_stage
            ON current_event_group_standings(event_id, stage_label, group_code, rank);

        CREATE TABLE IF NOT EXISTS current_event_team_ties (
            current_team_tie_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id               INTEGER NOT NULL,
            sub_event_type_code    TEXT NOT NULL,
            stage_label            TEXT,
            stage_code             TEXT,
            round_label            TEXT,
            round_code             TEXT,
            group_code             TEXT,
            external_match_code    TEXT,
            session_label          TEXT,
            scheduled_local_at     TEXT,
            scheduled_utc_at       TEXT,
            table_no               TEXT,
            status                 TEXT NOT NULL DEFAULT 'scheduled',
            source_status          TEXT,
            source_schedule_status TEXT,
            match_score            TEXT,
            winner_side            TEXT,
            winner_team_code       TEXT,
            last_synced_at         TEXT,
            created_at             TEXT DEFAULT (datetime('now')),
            updated_at             TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (event_id) REFERENCES events(event_id),
            FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
            CHECK (winner_side IN ('A', 'B') OR winner_side IS NULL),
            CHECK (status IN ('scheduled', 'live', 'completed', 'walkover', 'cancelled'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_current_event_team_ties_external
            ON current_event_team_ties(event_id, IFNULL(external_match_code, ''));
        CREATE INDEX IF NOT EXISTS idx_current_event_team_ties_event
            ON current_event_team_ties(event_id, sub_event_type_code);
        CREATE INDEX IF NOT EXISTS idx_current_event_team_ties_status
            ON current_event_team_ties(event_id, status);
        CREATE INDEX IF NOT EXISTS idx_current_event_team_ties_round
            ON current_event_team_ties(event_id, stage_code, round_code);
        CREATE INDEX IF NOT EXISTS idx_current_event_team_ties_group
            ON current_event_team_ties(event_id, group_code);

        CREATE TABLE IF NOT EXISTS current_event_team_tie_sides (
            current_team_tie_side_id INTEGER PRIMARY KEY AUTOINCREMENT,
            current_team_tie_id      INTEGER NOT NULL,
            side_no                  INTEGER NOT NULL,
            team_code                TEXT,
            team_name                TEXT,
            seed                     INTEGER,
            qualifier                INTEGER,
            is_winner                INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (current_team_tie_id) REFERENCES current_event_team_ties(current_team_tie_id) ON DELETE CASCADE,
            CHECK (side_no IN (1, 2)),
            CHECK (is_winner IN (0, 1)),
            UNIQUE(current_team_tie_id, side_no)
        );
        CREATE INDEX IF NOT EXISTS idx_current_event_team_tie_sides_tie
            ON current_event_team_tie_sides(current_team_tie_id);
        CREATE INDEX IF NOT EXISTS idx_current_event_team_tie_sides_team
            ON current_event_team_tie_sides(team_code);

        CREATE TABLE IF NOT EXISTS current_event_team_tie_side_players (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            current_team_tie_side_id  INTEGER NOT NULL,
            player_order              INTEGER NOT NULL,
            player_id                 INTEGER,
            player_name               TEXT NOT NULL,
            player_country            TEXT,
            FOREIGN KEY (current_team_tie_side_id) REFERENCES current_event_team_tie_sides(current_team_tie_side_id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES players(player_id),
            UNIQUE(current_team_tie_side_id, player_order)
        );
        CREATE INDEX IF NOT EXISTS idx_current_event_team_tie_side_players_side
            ON current_event_team_tie_side_players(current_team_tie_side_id);
        CREATE INDEX IF NOT EXISTS idx_current_event_team_tie_side_players_player
            ON current_event_team_tie_side_players(player_id);

        CREATE TABLE IF NOT EXISTS current_event_matches (
            current_match_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id               INTEGER NOT NULL,
            current_team_tie_id    INTEGER,
            sub_event_type_code    TEXT NOT NULL,
            stage_label            TEXT,
            stage_code             TEXT,
            round_label            TEXT,
            round_code             TEXT,
            group_code             TEXT,
            external_match_code    TEXT,
            scheduled_local_at     TEXT,
            scheduled_utc_at       TEXT,
            table_no               TEXT,
            session_label          TEXT,
            status                 TEXT NOT NULL DEFAULT 'scheduled',
            source_status          TEXT,
            source_schedule_status TEXT,
            match_score            TEXT,
            games                  TEXT,
            winner_side            TEXT,
            winner_name            TEXT,
            raw_source_payload     TEXT,
            last_synced_at         TEXT,
            created_at             TEXT DEFAULT (datetime('now')),
            updated_at             TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (event_id) REFERENCES events(event_id),
            FOREIGN KEY (current_team_tie_id) REFERENCES current_event_team_ties(current_team_tie_id) ON DELETE SET NULL,
            FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
            CHECK (winner_side IN ('A', 'B') OR winner_side IS NULL),
            CHECK (status IN ('scheduled', 'live', 'completed', 'walkover', 'cancelled'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_current_event_matches_external
            ON current_event_matches(event_id, IFNULL(external_match_code, ''));
        CREATE INDEX IF NOT EXISTS idx_current_event_matches_event
            ON current_event_matches(event_id, sub_event_type_code);
        CREATE INDEX IF NOT EXISTS idx_current_event_matches_team_tie
            ON current_event_matches(current_team_tie_id);
        CREATE INDEX IF NOT EXISTS idx_current_event_matches_status
            ON current_event_matches(event_id, status);
        CREATE INDEX IF NOT EXISTS idx_current_event_matches_round
            ON current_event_matches(event_id, stage_code, round_code);

        CREATE TABLE IF NOT EXISTS current_event_match_sides (
            current_match_side_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            current_match_id       INTEGER NOT NULL,
            side_no                INTEGER NOT NULL,
            team_code              TEXT,
            seed                   INTEGER,
            qualifier              INTEGER,
            placeholder_text       TEXT,
            is_winner              INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (current_match_id) REFERENCES current_event_matches(current_match_id) ON DELETE CASCADE,
            CHECK (side_no IN (1, 2)),
            CHECK (is_winner IN (0, 1)),
            UNIQUE(current_match_id, side_no)
        );
        CREATE INDEX IF NOT EXISTS idx_current_event_match_sides_match
            ON current_event_match_sides(current_match_id);

        CREATE TABLE IF NOT EXISTS current_event_match_side_players (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            current_match_side_id   INTEGER NOT NULL,
            player_order            INTEGER NOT NULL,
            player_id               INTEGER,
            player_name             TEXT NOT NULL,
            player_country          TEXT,
            FOREIGN KEY (current_match_side_id) REFERENCES current_event_match_sides(current_match_side_id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES players(player_id),
            UNIQUE(current_match_side_id, player_order)
        );
        CREATE INDEX IF NOT EXISTS idx_current_event_match_side_players_side
            ON current_event_match_side_players(current_match_side_id);
        CREATE INDEX IF NOT EXISTS idx_current_event_match_side_players_player
            ON current_event_match_side_players(player_id);

        CREATE TABLE IF NOT EXISTS current_event_brackets (
            current_bracket_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id               INTEGER NOT NULL,
            sub_event_type_code    TEXT NOT NULL,
            draw_code              TEXT,
            bracket_code           TEXT,
            stage_code             TEXT,
            round_code             TEXT,
            round_order            INTEGER,
            bracket_position       INTEGER,
            external_unit_code     TEXT,
            scheduled_date         TEXT,
            scheduled_time         TEXT,
            match_score            TEXT,
            winner_side            TEXT,
            status                 TEXT,
            side_a_previous_unit   TEXT,
            side_b_previous_unit   TEXT,
            side_a_team_code       TEXT,
            side_b_team_code       TEXT,
            side_a_placeholder     TEXT,
            side_b_placeholder     TEXT,
            raw_source_payload     TEXT,
            last_synced_at         TEXT,
            created_at             TEXT DEFAULT (datetime('now')),
            updated_at             TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (event_id) REFERENCES events(event_id),
            FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
            CHECK (winner_side IN ('A', 'B') OR winner_side IS NULL)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_current_event_brackets_unit
            ON current_event_brackets(event_id, sub_event_type_code, IFNULL(external_unit_code, ''));
        CREATE INDEX IF NOT EXISTS idx_current_event_brackets_event
            ON current_event_brackets(event_id, sub_event_type_code);
        CREATE INDEX IF NOT EXISTS idx_current_event_brackets_round
            ON current_event_brackets(event_id, stage_code, round_code, round_order);
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Schema migration: current event model + historical team ties.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--no-backup", action="store_true", help="Skip creating a database backup.")
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
        ensure_matches_team_tie_id(cursor)
        create_team_ties_tables(cursor)
        create_current_tables(cursor)
        conn.commit()
        print("Committed.")

        snapshots = {
            "team_ties": "SELECT COUNT(*) FROM team_ties",
            "current_event_session_schedule": "SELECT COUNT(*) FROM current_event_session_schedule",
            "current_event_group_standings": "SELECT COUNT(*) FROM current_event_group_standings",
            "current_event_team_ties": "SELECT COUNT(*) FROM current_event_team_ties",
            "current_event_matches": "SELECT COUNT(*) FROM current_event_matches",
            "current_event_brackets": "SELECT COUNT(*) FROM current_event_brackets",
        }
        print("Snapshot:")
        for label, sql in snapshots.items():
            count = cursor.execute(sql).fetchone()[0]
            print(f"  {label}: {count}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
