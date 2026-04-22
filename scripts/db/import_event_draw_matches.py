#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build event_draw_matches from matches.

This is a derived table for displaying main-draw brackets. It preserves the
raw ITTF labels in matches and stores only the display round/classification.

Bronze rules:
1. Explicit bronze labels are included as Bronze.
2. For non-WTT events (events.category_code NOT LIKE 'WTT_%'), Position Draw
   round 2 is included only when both sides are SemiFinal losers.
3. For non-WTT events with exactly two Final rows, the row matching both
   SemiFinal losers is reclassified as Bronze.
"""

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import config

    DB_PATH = config.DB_PATH
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"


ROUND_ORDER = {
    "R256": 5,
    "R128": 10,
    "R64": 20,
    "R32": 30,
    "R16": 40,
    "QuarterFinal": 50,
    "SemiFinal": 60,
    "Bronze": 70,
    "Final": 80,
}


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS event_draw_matches (
    draw_match_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id            INTEGER NOT NULL,
    event_id            INTEGER NOT NULL,
    sub_event_type_code TEXT NOT NULL,
    draw_stage          TEXT NOT NULL DEFAULT 'Main Draw',
    draw_round          TEXT NOT NULL,
    round_order         INTEGER NOT NULL,
    source_stage        TEXT,
    source_round        TEXT,
    bronze_source       TEXT,
    bronze_verified     INTEGER NOT NULL DEFAULT 0,
    validation_note     TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
    CHECK (bronze_verified IN (0, 1)),
    UNIQUE(match_id)
)
"""


CREATE_INDEX_SQL = [
    """
    CREATE INDEX IF NOT EXISTS idx_event_draw_matches_event
    ON event_draw_matches(event_id, sub_event_type_code, round_order)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_event_draw_matches_match
    ON event_draw_matches(match_id)
    """,
]


@dataclass(frozen=True)
class MatchRow:
    match_id: int
    event_id: int
    category_code: Optional[str]
    sub_event_type_code: str
    stage: str
    round: str
    side_a_key: str
    side_b_key: str
    winner_side: Optional[str]


@dataclass(frozen=True)
class DrawRow:
    match_id: int
    event_id: int
    sub_event_type_code: str
    draw_round: str
    round_order: int
    source_stage: str
    source_round: str
    bronze_source: Optional[str]
    bronze_verified: int
    validation_note: Optional[str]


def normalize_round(stage: str, round_name: str) -> Optional[str]:
    stage_key = (stage or "").strip().lower()
    round_key = (round_name or "").strip().lower()

    if "bronze" in stage_key or "bronze" in round_key:
        return "Bronze"

    aliases = {
        "final": "Final",
        "f": "Final",
        "semifinal": "SemiFinal",
        "semi final": "SemiFinal",
        "sf": "SemiFinal",
        "quarterfinal": "QuarterFinal",
        "quarter final": "QuarterFinal",
        "qf": "QuarterFinal",
        "r16": "R16",
        "round of 16": "R16",
        "round 16": "R16",
        "r32": "R32",
        "round of 32": "R32",
        "round 32": "R32",
        "r64": "R64",
        "round of 64": "R64",
        "round 64": "R64",
        "r128": "R128",
        "round of 128": "R128",
        "round 128": "R128",
        "r256": "R256",
        "256": "R256",
        "round of 256": "R256",
        "round 256": "R256",
    }
    return aliases.get(round_key)


def pair_key(side_a_key: str, side_b_key: str) -> Tuple[str, str]:
    return tuple(sorted((side_a_key, side_b_key)))


def loser_side_key(match: MatchRow) -> Optional[str]:
    winner = (match.winner_side or "").strip().upper()
    if winner == "A":
        return match.side_b_key
    if winner == "B":
        return match.side_a_key
    return None


def is_non_wtt(category_code: Optional[str]) -> bool:
    return category_code is not None and not category_code.startswith("WTT_")


def is_main_draw_stage(stage: str) -> bool:
    return (stage or "").strip() == "Main Draw"


def is_position_round_2(match: MatchRow) -> bool:
    stage = (match.stage or "").strip()
    round_name = (match.round or "").strip()
    return stage == "Position Draw" and round_name in {"2", "Round 2"}


def load_matches(cursor) -> List[MatchRow]:
    cursor.execute(
        """
        SELECT
            m.match_id,
            m.event_id,
            e.category_code,
            m.sub_event_type_code,
            COALESCE(m.stage, '') AS stage,
            COALESCE(m.round, '') AS round_name,
            m.side_a_key,
            m.side_b_key,
            m.winner_side
        FROM matches m
        JOIN events e ON e.event_id = m.event_id
        ORDER BY m.event_id, m.sub_event_type_code, m.match_id
        """
    )
    rows = []
    for (
        match_id,
        event_id,
        category_code,
        sub_event_type_code,
        stage,
        round_name,
        side_a_key,
        side_b_key,
        winner_side,
    ) in cursor.fetchall():
        rows.append(
            MatchRow(
                match_id=int(match_id),
                event_id=int(event_id),
                category_code=category_code,
                sub_event_type_code=str(sub_event_type_code),
                stage=stage or "",
                round=round_name or "",
                side_a_key=side_a_key or "",
                side_b_key=side_b_key or "",
                winner_side=winner_side,
            )
        )
    return rows


def build_semifinal_loser_pairs(matches: Iterable[MatchRow]) -> Dict[Tuple[int, str], Set[Tuple[str, str]]]:
    losers_by_event: Dict[Tuple[int, str], List[str]] = {}
    for match in matches:
        normalized_round = normalize_round(match.stage, match.round)
        if not is_main_draw_stage(match.stage) or normalized_round != "SemiFinal":
            continue
        loser_key = loser_side_key(match)
        if loser_key:
            key = (match.event_id, match.sub_event_type_code)
            losers_by_event.setdefault(key, []).append(loser_key)

    pairs_by_event: Dict[Tuple[int, str], Set[Tuple[str, str]]] = {}
    for key, losers in losers_by_event.items():
        unique_losers = sorted(set(losers))
        pairs: Set[Tuple[str, str]] = set()
        for idx, left in enumerate(unique_losers):
            for right in unique_losers[idx + 1 :]:
                pairs.add(pair_key(left, right))
        pairs_by_event[key] = pairs
    return pairs_by_event


def build_final_counts(matches: Iterable[MatchRow]) -> Dict[Tuple[int, str], int]:
    counts: Dict[Tuple[int, str], int] = {}
    for match in matches:
        if is_main_draw_stage(match.stage) and normalize_round(match.stage, match.round) == "Final":
            key = (match.event_id, match.sub_event_type_code)
            counts[key] = counts.get(key, 0) + 1
    return counts


def classify_draw_rows(matches: List[MatchRow]) -> Tuple[List[DrawRow], dict]:
    result = {
        "main_draw_inserted": 0,
        "explicit_bronze": 0,
        "position_bronze": 0,
        "final_reclassified_bronze": 0,
        "position_candidates": 0,
        "position_rejected": 0,
        "unsupported_main_round": 0,
        "duplicate_match_ids": 0,
    }

    semifinal_loser_pairs = build_semifinal_loser_pairs(matches)
    final_counts = build_final_counts(matches)
    draw_rows_by_match_id: Dict[int, DrawRow] = {}

    def add_row(row: DrawRow) -> None:
        if row.match_id in draw_rows_by_match_id:
            result["duplicate_match_ids"] += 1
            return
        draw_rows_by_match_id[row.match_id] = row

    for match in matches:
        normalized_round = normalize_round(match.stage, match.round)
        event_key = (match.event_id, match.sub_event_type_code)
        sides_pair = pair_key(match.side_a_key, match.side_b_key)
        bronze_pairs = semifinal_loser_pairs.get(event_key, set())

        if is_main_draw_stage(match.stage):
            if normalized_round is None:
                result["unsupported_main_round"] += 1
                continue

            bronze_source = None
            bronze_verified = 0
            validation_note = None
            draw_round = normalized_round

            if normalized_round == "Bronze":
                bronze_source = "explicit_bronze"
                bronze_verified = 1 if sides_pair in bronze_pairs else 0
                validation_note = (
                    "explicit bronze label; sides verified as semifinal losers"
                    if bronze_verified
                    else "explicit bronze label; semifinal loser pair not found"
                )
                result["explicit_bronze"] += 1
            elif (
                normalized_round == "Final"
                and is_non_wtt(match.category_code)
                and final_counts.get(event_key) == 2
                and sides_pair in bronze_pairs
            ):
                draw_round = "Bronze"
                bronze_source = "final_reclassified"
                bronze_verified = 1
                validation_note = "Final row reclassified because sides are semifinal losers"
                result["final_reclassified_bronze"] += 1

            add_row(
                DrawRow(
                    match_id=match.match_id,
                    event_id=match.event_id,
                    sub_event_type_code=match.sub_event_type_code,
                    draw_round=draw_round,
                    round_order=ROUND_ORDER[draw_round],
                    source_stage=match.stage,
                    source_round=match.round,
                    bronze_source=bronze_source,
                    bronze_verified=bronze_verified,
                    validation_note=validation_note,
                )
            )
            result["main_draw_inserted"] += 1
            continue

        if is_non_wtt(match.category_code) and is_position_round_2(match):
            result["position_candidates"] += 1
            if sides_pair not in bronze_pairs:
                result["position_rejected"] += 1
                continue

            add_row(
                DrawRow(
                    match_id=match.match_id,
                    event_id=match.event_id,
                    sub_event_type_code=match.sub_event_type_code,
                    draw_round="Bronze",
                    round_order=ROUND_ORDER["Bronze"],
                    source_stage=match.stage,
                    source_round=match.round,
                    bronze_source="position_draw_round2",
                    bronze_verified=1,
                    validation_note="Position Draw round 2 verified as semifinal loser pair",
                )
            )
            result["position_bronze"] += 1

    return list(draw_rows_by_match_id.values()), result


def ensure_table(cursor) -> None:
    cursor.execute(CREATE_TABLE_SQL)
    for stmt in CREATE_INDEX_SQL:
        cursor.execute(stmt)


def import_event_draw_matches(db_path: str, dry_run: bool = False) -> dict:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    matches = load_matches(cursor)
    draw_rows, result = classify_draw_rows(matches)
    result.update(
        {
            "full_refresh": True,
            "dry_run": dry_run,
            "matches_scanned": len(matches),
            "draw_rows": len(draw_rows),
        }
    )

    if dry_run:
        conn.close()
        return result

    ensure_table(cursor)
    cursor.execute("DELETE FROM event_draw_matches")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'event_draw_matches'")

    cursor.executemany(
        """
        INSERT INTO event_draw_matches (
            match_id,
            event_id,
            sub_event_type_code,
            draw_stage,
            draw_round,
            round_order,
            source_stage,
            source_round,
            bronze_source,
            bronze_verified,
            validation_note
        ) VALUES (?, ?, ?, 'Main Draw', ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.match_id,
                row.event_id,
                row.sub_event_type_code,
                row.draw_round,
                row.round_order,
                row.source_stage,
                row.source_round,
                row.bronze_source,
                row.bronze_verified,
                row.validation_note,
            )
            for row in draw_rows
        ],
    )
    conn.commit()
    conn.close()
    return result


def verify_event_draw_matches(db_path: str) -> None:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM event_draw_matches")
    total = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT draw_round, COUNT(*)
        FROM event_draw_matches
        GROUP BY draw_round, round_order
        ORDER BY round_order
        """
    )
    by_round = cursor.fetchall()

    cursor.execute(
        """
        SELECT COALESCE(bronze_source, '(none)'), COUNT(*)
        FROM event_draw_matches
        WHERE draw_round = 'Bronze'
        GROUP BY bronze_source
        ORDER BY COUNT(*) DESC
        """
    )
    bronze_sources = cursor.fetchall()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM event_draw_matches
        WHERE draw_round = 'Bronze' AND bronze_verified = 1
        """
    )
    verified_bronze = cursor.fetchone()[0]

    print("\nVerification:")
    print(f"  event_draw_matches total: {total}")
    print("  by draw_round:")
    for draw_round, cnt in by_round:
        print(f"    {draw_round:12s}: {cnt:6d}")
    print("  bronze sources:")
    for source, cnt in bronze_sources:
        print(f"    {source:24s}: {cnt:6d}")
    print(f"  verified bronze: {verified_bronze}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import derived main-draw match table")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, do not write event_draw_matches")
    args = parser.parse_args()

    print("=" * 70)
    print("Import Event Draw Matches")
    print("=" * 70)
    print(f"Database: {DB_PATH}")
    print(f"Dry run:  {args.dry_run}")
    print("=" * 70 + "\n")

    if not Path(DB_PATH).exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    stats = import_event_draw_matches(str(DB_PATH), dry_run=args.dry_run)

    print("Results:")
    print(f"  Full refresh mode:            {stats['full_refresh']}")
    print(f"  Dry run mode:                 {stats['dry_run']}")
    print(f"  Matches scanned:              {stats['matches_scanned']}")
    print(f"  Draw rows:                    {stats['draw_rows']}")
    print(f"  Main draw rows considered:    {stats['main_draw_inserted']}")
    print(f"  Explicit bronze rows:         {stats['explicit_bronze']}")
    print(f"  Position Draw R2 candidates:  {stats['position_candidates']}")
    print(f"  Position Draw R2 rejected:    {stats['position_rejected']}")
    print(f"  Position bronze rows:         {stats['position_bronze']}")
    print(f"  Final reclassified bronze:    {stats['final_reclassified_bronze']}")
    print(f"  Unsupported main rounds:      {stats['unsupported_main_round']}")
    print(f"  Duplicate match IDs skipped:  {stats['duplicate_match_ids']}")

    if not args.dry_run:
        verify_event_draw_matches(str(DB_PATH))

    sys.exit(0)
