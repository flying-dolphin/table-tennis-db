#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
归一化 stage / round 字段。

读取 data/stage_round_mapping.json，把原始 stage / round 文本映射到规范 code，
并写入：
    matches.stage_code              matches.round_code
    event_draw_matches.stage_code   event_draw_matches.round_code

同时维护字典表 stage_codes 和 round_codes（来自 mapping JSON 的 stage_codes /
round_codes 列表）。

用法:
    python normalize_stage_round.py                  # 真正执行
    python normalize_stage_round.py --dry-run        # 只报告，不写库
    python normalize_stage_round.py --rebuild-dict   # 字典表 truncate 后重建
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import config

    PROJECT_ROOT = Path(config.PROJECT_ROOT)
    DEFAULT_DB_PATH = Path(config.DB_PATH)
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"

DEFAULT_MAPPING_PATH = PROJECT_ROOT / "data" / "stage_round_mapping.json"


# ── 字典表与列结构 ───────────────────────────────────────────────────────────

DICT_DDL = """
CREATE TABLE IF NOT EXISTS stage_codes (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    name_zh     TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS round_codes (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    name_zh     TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'unknown',
    sort_order  INTEGER NOT NULL DEFAULT 0
);
"""


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def ensure_dictionary_tables(cursor: sqlite3.Cursor) -> None:
    cursor.executescript(DICT_DDL)


def ensure_normalized_columns(cursor: sqlite3.Cursor) -> None:
    targets = [
        ("matches", "stage_code"),
        ("matches", "round_code"),
        ("event_draw_matches", "stage_code"),
        ("event_draw_matches", "round_code"),
    ]
    for table, column in targets:
        if not column_exists(cursor, table, column):
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    cursor.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_matches_stage_code ON matches(stage_code);
        CREATE INDEX IF NOT EXISTS idx_matches_round_code ON matches(round_code);
        CREATE INDEX IF NOT EXISTS idx_event_draw_matches_stage_code
            ON event_draw_matches(stage_code);
        CREATE INDEX IF NOT EXISTS idx_event_draw_matches_round_code
            ON event_draw_matches(round_code);
        """
    )


def populate_dictionary(cursor: sqlite3.Cursor, mapping: dict, *, rebuild: bool) -> None:
    if rebuild:
        cursor.execute("DELETE FROM stage_codes")
        cursor.execute("DELETE FROM round_codes")

    cursor.executemany(
        """
        INSERT INTO stage_codes (code, name, name_zh, sort_order)
        VALUES (:code, :name, :name_zh, :sort_order)
        ON CONFLICT(code) DO UPDATE SET
            name        = excluded.name,
            name_zh     = excluded.name_zh,
            sort_order  = excluded.sort_order
        """,
        mapping.get("stage_codes", []),
    )
    cursor.executemany(
        """
        INSERT INTO round_codes (code, name, name_zh, kind, sort_order)
        VALUES (:code, :name, :name_zh, :kind, :sort_order)
        ON CONFLICT(code) DO UPDATE SET
            name        = excluded.name,
            name_zh     = excluded.name_zh,
            kind        = excluded.kind,
            sort_order  = excluded.sort_order
        """,
        mapping.get("round_codes", []),
    )


# ── 归一化逻辑 ───────────────────────────────────────────────────────────────


def normalize(
    raw_stage: str | None,
    raw_round: str | None,
    *,
    stage_aliases: dict[str, str],
    round_aliases: dict[str, str],
    rounds_by_stage: dict[str, dict[str, str]],
) -> tuple[str, str]:
    """Return (stage_code, round_code)."""
    s = (raw_stage or "").strip()
    r = (raw_round or "").strip()

    stage_code = stage_aliases.get(s, "UNKNOWN")

    by_stage = rounds_by_stage.get(stage_code, {})
    if r in by_stage:
        round_code = by_stage[r]
    else:
        round_code = round_aliases.get(r, "UNKNOWN")

    return stage_code, round_code


# ── 回填 ─────────────────────────────────────────────────────────────────────


def backfill_table(
    cursor: sqlite3.Cursor,
    table: str,
    pk_col: str,
    stage_col: str,
    round_col: str,
    *,
    stage_aliases: dict[str, str],
    round_aliases: dict[str, str],
    rounds_by_stage: dict[str, dict[str, str]],
    dry_run: bool,
) -> dict:
    cursor.execute(f"SELECT {pk_col}, {stage_col}, {round_col} FROM {table}")
    rows = cursor.fetchall()

    updates: list[tuple[str, str, int]] = []
    unmatched_stage: Counter = Counter()
    unmatched_round: Counter = Counter()
    code_dist: Counter = Counter()

    for pk, raw_stage, raw_round in rows:
        s = (raw_stage or "").strip()
        r = (raw_round or "").strip()
        stage_code, round_code = normalize(
            raw_stage,
            raw_round,
            stage_aliases=stage_aliases,
            round_aliases=round_aliases,
            rounds_by_stage=rounds_by_stage,
        )
        if stage_code == "UNKNOWN" and s:
            unmatched_stage[s] += 1
        if round_code == "UNKNOWN" and r:
            unmatched_round[(s, r)] += 1
        code_dist[(stage_code, round_code)] += 1
        updates.append((stage_code, round_code, pk))

    if not dry_run:
        cursor.executemany(
            f"UPDATE {table} SET stage_code = ?, round_code = ? WHERE {pk_col} = ?",
            updates,
        )

    return {
        "table": table,
        "rows": len(rows),
        "unmatched_stage": unmatched_stage,
        "unmatched_round": unmatched_round,
        "code_dist": code_dist,
    }


def print_report(stats: dict) -> None:
    print(f"\n  [{stats['table']}] {stats['rows']} rows")
    if stats["unmatched_stage"]:
        total = sum(stats["unmatched_stage"].values())
        print(f"    Unmatched stages ({total} rows, top 20):")
        for raw, n in stats["unmatched_stage"].most_common(20):
            print(f"      {raw!r}: {n}")
    if stats["unmatched_round"]:
        total = sum(stats["unmatched_round"].values())
        print(f"    Unmatched rounds ({total} rows, top 20):")
        for (s, r), n in stats["unmatched_round"].most_common(20):
            print(f"      stage={s!r} round={r!r}: {n}")
    if not stats["unmatched_stage"] and not stats["unmatched_round"]:
        print("    All rows matched.")


# ── 入口 ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize stage/round codes.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report only; no schema changes, no UPDATE.")
    parser.add_argument("--rebuild-dict", action="store_true",
                        help="Truncate stage_codes/round_codes before reinsert.")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1
    if not args.mapping.exists():
        print(f"Mapping file not found: {args.mapping}", file=sys.stderr)
        return 1

    with open(args.mapping, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    stage_aliases = mapping["stage_aliases"]
    round_aliases = mapping["round_aliases"]
    rounds_by_stage = mapping["rounds_by_stage"]

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    try:
        if args.dry_run:
            print("[dry-run] skipping schema changes & dictionary refresh.")
        else:
            ensure_dictionary_tables(cursor)
            ensure_normalized_columns(cursor)
            populate_dictionary(cursor, mapping, rebuild=args.rebuild_dict)

        targets = [
            ("matches",            "match_id",      "stage",      "round"),
            ("event_draw_matches", "draw_match_id", "draw_stage", "draw_round"),
        ]

        all_stats = []
        for table, pk_col, stage_col, round_col in targets:
            stats = backfill_table(
                cursor,
                table,
                pk_col,
                stage_col,
                round_col,
                stage_aliases=stage_aliases,
                round_aliases=round_aliases,
                rounds_by_stage=rounds_by_stage,
                dry_run=args.dry_run,
            )
            all_stats.append(stats)

        if args.dry_run:
            conn.rollback()
            print("\n[dry-run] no changes committed.")
        else:
            conn.commit()
            print("\nCommitted.")

        print("\n=== Report ===")
        for stats in all_stats:
            print_report(stats)

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
