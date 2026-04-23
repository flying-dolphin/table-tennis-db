#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoothly upgrade selected SQLite tables to match the current schema.

Targets:
- event_categories
- event_type_mapping
- events
- events_calendar
"""

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import config

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


TARGET_TABLES = {
    "event_categories",
    "event_type_mapping",
    "events",
    "events_calendar",
}


def table_exists(cursor, name):
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    )
    return cursor.fetchone() is not None


def index_exists(cursor, name):
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name = ?",
        (name,),
    )
    return cursor.fetchone() is not None


def get_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def backup_database(db_path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(f"{db_path.suffix}.backup.{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def category_classification_sql(category_expr, name_expr):
    age_group_expr = f"""
        CASE
            WHEN UPPER({category_expr}) LIKE '%YOUTH%'
              OR UPPER({category_expr}) LIKE '%U21%'
              OR UPPER({category_expr}) LIKE '%JUNIOR%'
              OR UPPER({category_expr}) LIKE '%CADET%'
              OR UPPER({category_expr}) LIKE '%WJTTC%'
            THEN 'YOUTH'
            ELSE 'SENIOR'
        END
    """
    event_series_expr = f"""
        CASE
            WHEN UPPER({category_expr}) LIKE 'WTT_%'
              OR UPPER({category_expr}) IN ('YOUTH_GRAND_SMASH', 'YOUTH_STAR_CONTENDER', 'YOUTH_CONTENDER')
            THEN 'WTT'
            WHEN UPPER({category_expr}) LIKE '%OLYMPIC%'
            THEN 'OLYMPIC'
            WHEN UPPER({category_expr}) LIKE 'ITTF%'
              OR UPPER({category_expr}) LIKE 'WORLD_TOUR%'
              OR UPPER({category_expr}) LIKE 'CONTINENTAL%'
              OR UPPER({category_expr}) LIKE 'REGIONAL%'
              OR UPPER({category_expr}) IN ('U21_CONTINENTAL_CHAMPS', 'YOUTH_CONTINENTAL_CHAMPS', 'YOUTH_CONTINENTAL_CUP', 'YOUTH_WORLD_CHAMPS')
              OR UPPER({name_expr}) LIKE '%ITTF%'
              OR UPPER({name_expr}) LIKE '%CONTINENTAL%'
              OR UPPER({name_expr}) LIKE '%REGIONAL%'
              OR UPPER({name_expr}) LIKE '%WORLD TOUR%'
              OR UPPER({name_expr}) LIKE '%WORLD YOUTH%'
            THEN 'ITTF'
            ELSE 'OTHER'
        END
    """
    return age_group_expr, event_series_expr


def ensure_event_categories(cursor):
    columns = get_columns(cursor, "event_categories")
    legacy = "event_type" in columns or "id" not in columns

    if not legacy:
        if "age_group" not in columns:
            cursor.execute(
                "ALTER TABLE event_categories ADD COLUMN age_group TEXT NOT NULL DEFAULT 'SENIOR'"
            )
        if "event_series" not in columns:
            cursor.execute(
                "ALTER TABLE event_categories ADD COLUMN event_series TEXT NOT NULL DEFAULT 'OTHER'"
            )

        age_group_expr, event_series_expr = category_classification_sql("category_id", "category_name")
        cursor.execute(
            f"""
            UPDATE event_categories
            SET
                age_group = {age_group_expr},
                event_series = {event_series_expr}
            """
        )

        if not index_exists(cursor, "idx_event_categories_json_code"):
            cursor.execute(
                "CREATE INDEX idx_event_categories_json_code ON event_categories(json_code)"
            )
        return {"migrated": False, "legacy": False}

    for index_name in ("idx_event_categories_json_code", "idx_event_categories_type_kind"):
        if index_exists(cursor, index_name):
            cursor.execute(f"DROP INDEX {index_name}")

    cursor.execute("ALTER TABLE event_categories RENAME TO event_categories_legacy")
    cursor.execute(
        """
        CREATE TABLE event_categories (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id         TEXT NOT NULL UNIQUE,
            category_name       TEXT NOT NULL,
            category_name_zh    TEXT,
            age_group           TEXT NOT NULL DEFAULT 'SENIOR',
            event_series        TEXT NOT NULL DEFAULT 'OTHER',
            json_code           TEXT,
            points_tier         TEXT,
            points_eligible     INTEGER DEFAULT 0,
            filtering_only      INTEGER DEFAULT 0,
            applicable_formats  TEXT,
            ittf_rule_name      TEXT,
            notes               TEXT,
            sort_order          INTEGER DEFAULT 0
        )
        """
    )
    cursor.execute(
        """
        INSERT INTO event_categories (
            category_id, category_name, category_name_zh, age_group, event_series, json_code,
            points_tier, points_eligible, filtering_only, applicable_formats,
            ittf_rule_name, notes, sort_order
        )
        SELECT
            category_id,
            category_name,
            category_name_zh,
            CASE
                WHEN UPPER(category_id) LIKE '%YOUTH%'
                  OR UPPER(category_id) LIKE '%U21%'
                  OR UPPER(category_id) LIKE '%JUNIOR%'
                  OR UPPER(category_id) LIKE '%CADET%'
                  OR UPPER(category_id) LIKE '%WJTTC%'
                THEN 'YOUTH'
                ELSE 'SENIOR'
            END,
            CASE
                WHEN UPPER(category_id) LIKE 'WTT_%'
                  OR UPPER(category_id) IN ('YOUTH_GRAND_SMASH', 'YOUTH_STAR_CONTENDER', 'YOUTH_CONTENDER')
                THEN 'WTT'
                WHEN UPPER(category_id) LIKE '%OLYMPIC%'
                THEN 'OLYMPIC'
                WHEN UPPER(category_id) LIKE 'ITTF%'
                  OR UPPER(category_id) LIKE 'WORLD_TOUR%'
                  OR UPPER(category_id) LIKE 'CONTINENTAL%'
                  OR UPPER(category_id) LIKE 'REGIONAL%'
                  OR UPPER(category_id) IN ('U21_CONTINENTAL_CHAMPS', 'YOUTH_CONTINENTAL_CHAMPS', 'YOUTH_CONTINENTAL_CUP', 'YOUTH_WORLD_CHAMPS')
                  OR UPPER(category_name) LIKE '%ITTF%'
                  OR UPPER(category_name) LIKE '%CONTINENTAL%'
                  OR UPPER(category_name) LIKE '%REGIONAL%'
                  OR UPPER(category_name) LIKE '%WORLD TOUR%'
                  OR UPPER(category_name) LIKE '%WORLD YOUTH%'
                THEN 'ITTF'
                ELSE 'OTHER'
            END,
            json_code,
            points_tier, COALESCE(points_eligible, 0), COALESCE(filtering_only, 0),
            applicable_formats, ittf_rule_name, notes, COALESCE(sort_order, 0)
        FROM event_categories_legacy
        ORDER BY COALESCE(sort_order, 0), category_id
        """
    )
    cursor.execute(
        "CREATE INDEX idx_event_categories_json_code ON event_categories(json_code)"
    )
    return {"migrated": True, "legacy": True}


def ensure_event_type_mapping(cursor, source_is_legacy):
    if table_exists(cursor, "event_type_mapping"):
        return {"created": False, "rows": None}

    cursor.execute(
        """
        CREATE TABLE event_type_mapping (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type          TEXT NOT NULL,
            event_kind          TEXT,
            event_kind_aliases  TEXT,
            category_id         INTEGER NOT NULL,
            priority            INTEGER DEFAULT 0,
            is_active           INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (category_id) REFERENCES event_categories(id) ON DELETE RESTRICT
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX idx_event_type_mapping_lookup
        ON event_type_mapping(event_type, event_kind, is_active, priority)
        """
    )

    inserted_rows = 0
    if source_is_legacy and table_exists(cursor, "event_categories_legacy"):
        cursor.execute(
            """
            INSERT INTO event_type_mapping (
                event_type, event_kind, event_kind_aliases, category_id, priority, is_active
            )
            SELECT
                l.event_type,
                l.event_kind,
                l.event_kind_aliases,
                n.id,
                10,
                1
            FROM event_categories_legacy l
            JOIN event_categories n ON n.category_id = l.category_id
            """
        )
        inserted_rows = cursor.rowcount

    return {"created": True, "rows": inserted_rows}


def ensure_events(cursor):
    columns = get_columns(cursor, "events")
    needs_rebuild = (
        "event_category_id" not in columns
        or "category_code" not in columns
        or "category_name_zh" not in columns
        or "category_id" in columns
    )

    if not needs_rebuild:
        if not index_exists(cursor, "idx_events_category"):
            cursor.execute("CREATE INDEX idx_events_category ON events(event_category_id)")
        return {"migrated": False}

    for index_name in (
        "idx_events_year",
        "idx_events_type",
        "idx_events_date",
        "idx_events_category",
    ):
        if index_exists(cursor, index_name):
            cursor.execute(f"DROP INDEX {index_name}")

    cursor.execute("ALTER TABLE events RENAME TO events_legacy")
    cursor.execute(
        """
        CREATE TABLE events (
            event_id            INTEGER PRIMARY KEY,
            year                INTEGER NOT NULL,
            name                TEXT NOT NULL,
            name_zh             TEXT,
            event_type_id       INTEGER,
            event_type_name     TEXT,
            event_kind          TEXT,
            event_kind_zh       TEXT,
            event_category_id   INTEGER,
            category_code       TEXT,
            category_name_zh    TEXT,
            total_matches       INTEGER DEFAULT 0,
            start_date          TEXT,
            end_date            TEXT,
            location            TEXT,
            href                TEXT,
            scraped_at          TEXT,
            FOREIGN KEY (event_type_id) REFERENCES event_types(event_type_id),
            FOREIGN KEY (event_category_id) REFERENCES event_categories(id)
        )
        """
    )

    legacy_columns = get_columns(cursor, "events_legacy")
    legacy_has_category_code = "category_id" in legacy_columns

    if legacy_has_category_code:
        cursor.execute(
            """
            INSERT INTO events (
                event_id, year, name, name_zh, event_type_id, event_type_name,
                event_kind, event_kind_zh, event_category_id, category_code,
                category_name_zh, total_matches, start_date, end_date, location,
                href, scraped_at
            )
            SELECT
                e.event_id,
                e.year,
                e.name,
                e.name_zh,
                e.event_type_id,
                e.event_type_name,
                e.event_kind,
                e.event_kind_zh,
                c.id,
                e.category_id,
                c.category_name_zh,
                COALESCE(e.total_matches, 0),
                e.start_date,
                e.end_date,
                e.location,
                e.href,
                e.scraped_at
            FROM events_legacy e
            LEFT JOIN event_categories c ON c.category_id = e.category_id
            """
        )
    else:
        cursor.execute(
            """
            INSERT INTO events (
                event_id, year, name, name_zh, event_type_id, event_type_name,
                event_kind, event_kind_zh, event_category_id, category_code,
                category_name_zh, total_matches, start_date, end_date, location,
                href, scraped_at
            )
            SELECT
                e.event_id,
                e.year,
                e.name,
                e.name_zh,
                e.event_type_id,
                e.event_type_name,
                e.event_kind,
                e.event_kind_zh,
                e.event_category_id,
                e.category_code,
                e.category_name_zh,
                COALESCE(e.total_matches, 0),
                e.start_date,
                e.end_date,
                e.location,
                e.href,
                e.scraped_at
            FROM events_legacy e
            """
        )

    cursor.execute("CREATE INDEX idx_events_year ON events(year)")
    cursor.execute("CREATE INDEX idx_events_type ON events(event_type_id)")
    cursor.execute("CREATE INDEX idx_events_date ON events(start_date)")
    cursor.execute("CREATE INDEX idx_events_category ON events(event_category_id)")
    return {"migrated": True}


def ensure_events_calendar(cursor):
    columns = get_columns(cursor, "events_calendar")
    if "event_type" not in columns:
        cursor.execute("ALTER TABLE events_calendar ADD COLUMN event_type TEXT")
    if "event_kind" not in columns:
        cursor.execute("ALTER TABLE events_calendar ADD COLUMN event_kind TEXT")
    if "event_category_id" not in columns:
        cursor.execute("ALTER TABLE events_calendar ADD COLUMN event_category_id INTEGER")

    cursor.execute(
        """
        UPDATE events_calendar
        SET
            event_type = COALESCE(
                event_type,
                (SELECT e.event_type_name FROM events e WHERE e.event_id = events_calendar.event_id)
            ),
            event_kind = COALESCE(
                event_kind,
                (SELECT e.event_kind FROM events e WHERE e.event_id = events_calendar.event_id)
            ),
            event_category_id = COALESCE(
                event_category_id,
                (SELECT e.event_category_id FROM events e WHERE e.event_id = events_calendar.event_id)
            )
        WHERE event_id IS NOT NULL
        """
    )

    if not index_exists(cursor, "idx_calendar_year"):
        cursor.execute("CREATE INDEX idx_calendar_year ON events_calendar(year)")
    if not index_exists(cursor, "idx_calendar_date"):
        cursor.execute("CREATE INDEX idx_calendar_date ON events_calendar(start_date)")
    if not index_exists(cursor, "idx_calendar_category"):
        cursor.execute("CREATE INDEX idx_calendar_category ON events_calendar(event_category_id)")

    return {"updated": True}


def drop_legacy_tables(cursor):
    for table_name in ("events_legacy", "event_categories_legacy"):
        if table_exists(cursor, table_name):
            cursor.execute(f"DROP TABLE {table_name}")


def verify(cursor):
    checks = {}

    cursor.execute("SELECT COUNT(*) FROM event_categories")
    checks["event_categories"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='event_type_mapping'"
    )
    has_mapping = cursor.fetchone()[0] == 1
    if has_mapping:
        cursor.execute("SELECT COUNT(*) FROM event_type_mapping")
        checks["event_type_mapping"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM events")
    checks["events"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM events_calendar")
    checks["events_calendar"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM events WHERE category_code IS NOT NULL AND event_category_id IS NULL"
    )
    checks["events_unmapped_category_code"] = cursor.fetchone()[0]

    return checks


def upgrade_database(db_path):
    backup_path = backup_database(db_path)
    conn = sqlite3.connect(str(db_path))

    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF")
        cursor.execute("BEGIN")

        category_result = ensure_event_categories(cursor)
        mapping_result = ensure_event_type_mapping(cursor, category_result["legacy"])
        events_result = ensure_events(cursor)
        calendar_result = ensure_events_calendar(cursor)
        drop_legacy_tables(cursor)

        cursor.execute("COMMIT")
        cursor.execute("PRAGMA foreign_keys = ON")

        checks = verify(cursor)
        return {
            "backup_path": str(backup_path),
            "category_result": category_result,
            "mapping_result": mapping_result,
            "events_result": events_result,
            "calendar_result": calendar_result,
            "checks": checks,
        }
    except Exception:
        cursor.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def main():
    db_path = Path(config.DB_PATH)

    print("=" * 70)
    print("Upgrade ITTF Schema")
    print("=" * 70)
    print(f"Database: {db_path}")
    print(f"Targets:  {', '.join(sorted(TARGET_TABLES))}")
    print("=" * 70)

    if not db_path.exists():
        print(f"[ERROR] Database file not found: {db_path}")
        return 1

    result = upgrade_database(db_path)

    print(f"[OK] Backup created: {result['backup_path']}")
    print(f"  event_categories rebuilt: {result['category_result']['migrated']}")
    print(f"  event_type_mapping created: {result['mapping_result']['created']}")
    print(f"  events rebuilt: {result['events_result']['migrated']}")
    print(f"  events_calendar updated: {result['calendar_result']['updated']}")
    print("Verification:")
    for key, value in result["checks"].items():
        print(f"  {key}: {value}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
