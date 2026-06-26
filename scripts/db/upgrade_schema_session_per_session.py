#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迁移：current_event_session_schedule 支持 per-session（每天多个时段各一行）。

变更：
- 加列 session_index / session_title / start_time / table_label。
- 唯一约束由 UNIQUE(event_id, day_index) 改为 UNIQUE(event_id, session_index)。
  （SQLite 无法直接改约束，需重建表并迁移数据。）
- 旧的「每天一条」数据 session_index 回填为 day_index。

幂等：可重复执行；已迁移则跳过。运行前自动备份数据库。

用法:
    python scripts/db/upgrade_schema_session_per_session.py
    python scripts/db/upgrade_schema_session_per_session.py --db /path/to/ittf.db
    python scripts/db/upgrade_schema_session_per_session.py --no-backup
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

sys.path.insert(0, str(Path(__file__).parent))
try:
    import config

    DEFAULT_DB_PATH = Path(config.DB_PATH)
except ImportError:
    DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "db" / "ittf.db"


NEW_TABLE_SQL = """
CREATE TABLE current_event_session_schedule (
    current_session_schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id            INTEGER NOT NULL,
    day_index           INTEGER NOT NULL,
    session_index       INTEGER,
    local_date          TEXT NOT NULL,
    session_title       TEXT,
    start_time          TEXT,
    morning_session_start TEXT,
    afternoon_session_start TEXT,
    venue_raw           TEXT,
    venue_id            INTEGER,
    table_count         INTEGER,
    table_label         TEXT,
    raw_sub_events_text TEXT,
    parsed_rounds_json  TEXT,
    updated_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (venue_id) REFERENCES venues(venue_id),
    UNIQUE(event_id, session_index)
)
"""


def backup_database(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(f"{db_path.suffix}.backup.{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def table_sql(cursor: sqlite3.Cursor, table: str) -> str | None:
    row = cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchone()
    return row[0] if row else None


def already_migrated(sql: str | None) -> bool:
    if not sql:
        return False
    normalized = " ".join(sql.split())
    return "session_index" in normalized and "UNIQUE(event_id, session_index)" in normalized


def migrate(cursor: sqlite3.Cursor) -> dict:
    sql = table_sql(cursor, "current_event_session_schedule")
    if sql is None:
        # 表不存在：直接按新结构创建（全新库会走 schema.sql，这里兜底）
        cursor.executescript(
            NEW_TABLE_SQL
            + ";\nCREATE INDEX IF NOT EXISTS idx_current_event_session_schedule_event"
            " ON current_event_session_schedule(event_id);"
            "\nCREATE INDEX IF NOT EXISTS idx_current_event_session_schedule_date"
            " ON current_event_session_schedule(local_date);"
        )
        return {"action": "created", "rows": 0}

    if already_migrated(sql):
        return {"action": "skipped", "rows": None}

    row_count = cursor.execute(
        "SELECT COUNT(*) FROM current_event_session_schedule"
    ).fetchone()[0]

    cursor.executescript(
        f"""
        ALTER TABLE current_event_session_schedule RENAME TO current_event_session_schedule__old;
        {NEW_TABLE_SQL};
        INSERT INTO current_event_session_schedule (
            current_session_schedule_id, event_id, day_index, session_index, local_date,
            session_title, start_time, morning_session_start, afternoon_session_start,
            venue_raw, venue_id, table_count, table_label,
            raw_sub_events_text, parsed_rounds_json, updated_at
        )
        SELECT
            current_session_schedule_id, event_id, day_index, day_index AS session_index, local_date,
            NULL, NULL, morning_session_start, afternoon_session_start,
            venue_raw, venue_id, table_count, NULL,
            raw_sub_events_text, parsed_rounds_json, updated_at
        FROM current_event_session_schedule__old;
        DROP TABLE current_event_session_schedule__old;
        CREATE INDEX IF NOT EXISTS idx_current_event_session_schedule_event
            ON current_event_session_schedule(event_id);
        CREATE INDEX IF NOT EXISTS idx_current_event_session_schedule_date
            ON current_event_session_schedule(local_date);
        """
    )
    return {"action": "rebuilt", "rows": row_count}


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate current_event_session_schedule to per-session model.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--no-backup", action="store_true", help="Skip database backup before migration.")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1

    if not args.no_backup:
        backup_path = backup_database(args.db)
        print(f"Backup created: {backup_path}")

    conn = sqlite3.connect(str(args.db))
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()
    try:
        print("\n=== current_event_session_schedule: per-session 迁移 ===")
        result = migrate(cursor)
        conn.commit()
        if result["action"] == "skipped":
            print("  已是 per-session 结构，跳过")
        elif result["action"] == "created":
            print("  表不存在，已按新结构创建")
        else:
            print(f"  重建完成，迁移 {result['rows']} 行（session_index 回填为 day_index）")
        print("✅ Committed.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
