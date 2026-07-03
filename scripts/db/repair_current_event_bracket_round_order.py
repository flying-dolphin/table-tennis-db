#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-off repair for current_event_brackets.round_order.

This rewrites rows imported with the old current-event ordering where earlier
rounds had larger numbers. The canonical project meaning is now:
larger round_order = later knockout round / closer to champion.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"


def normalize_round(raw_code: str | None) -> tuple[str | None, str | None, int | None]:
    """Keep in sync with scripts/runtime/import_current_event_brackets.py."""
    raw = (raw_code or "").strip().upper()
    mapping = {
        "FNL-": ("MAIN_DRAW", "F", 80),
        "FNL": ("MAIN_DRAW", "F", 80),
        "SFNL": ("MAIN_DRAW", "SF", 60),
        "QFNL": ("MAIN_DRAW", "QF", 50),
        "8FNL": ("MAIN_DRAW", "R16", 40),
        "R32-": ("MAIN_DRAW", "R32", 30),
        "R32": ("MAIN_DRAW", "R32", 30),
        "R64-": ("MAIN_DRAW", "R64", 20),
        "R64": ("MAIN_DRAW", "R64", 20),
        "RND1": ("PRELIMINARY", "R1", 10),
        "RND2": ("PRELIMINARY", "RND2", 20),
        "RND3": ("PRELIMINARY", "RND3", 30),
    }
    if raw in mapping:
        return mapping[raw]
    if raw.startswith("GP") and raw[2:].isdigit():
        return ("MAIN_STAGE1", raw, 100 + int(raw[2:]))
    return (None, raw or None, None)


def repair(db_path: Path, *, dry_run: bool, event_id: int | None) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = """
            SELECT current_bracket_id, event_id, sub_event_type_code, bracket_code,
                   stage_code, round_code, round_order
            FROM current_event_brackets
        """
        params: list[int] = []
        if event_id is not None:
            query += " WHERE event_id = ?"
            params.append(event_id)
        query += " ORDER BY event_id, sub_event_type_code, current_bracket_id"

        rows = conn.execute(query, params).fetchall()
        changes: list[tuple[str | None, str | None, int, int]] = []
        skipped = 0

        for row in rows:
            stage_code, round_code, round_order = normalize_round(row["bracket_code"])
            if round_order is None:
                skipped += 1
                continue
            if (
                row["stage_code"] == stage_code
                and row["round_code"] == round_code
                and row["round_order"] == round_order
            ):
                continue
            changes.append((stage_code, round_code, round_order, row["current_bracket_id"]))

        print(f"Scanned rows: {len(rows)}")
        print(f"Rows to update: {len(changes)}")
        print(f"Rows skipped with unknown bracket_code: {skipped}")

        if dry_run or not changes:
            if dry_run:
                print("Dry run only; no rows updated.")
            return len(changes)

        with conn:
            conn.executemany(
                """
                UPDATE current_event_brackets
                SET stage_code = ?,
                    round_code = ?,
                    round_order = ?,
                    updated_at = datetime('now')
                WHERE current_bracket_id = ?
                """,
                changes,
            )
        print(f"Updated rows: {len(changes)}")
        return len(changes)
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair current_event_brackets.round_order semantics.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path")
    parser.add_argument("--event-id", type=int, help="Limit repair to one event_id")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = parser.parse_args()

    if not args.db.exists():
        parser.error(f"database not found: {args.db}")

    repair(args.db, dry_run=args.dry_run, event_id=args.event_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
