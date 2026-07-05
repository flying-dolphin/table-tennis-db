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
import re
import sqlite3
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Pattern, Set, Tuple

if sys.platform == "win32" and getattr(sys.stdout, "encoding", "").lower() != "utf-8":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import config

    PROJECT_ROOT = config.PROJECT_ROOT
    DB_PATH = config.DB_PATH
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"

from _import_summary import write_summary  # noqa: E402


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
    bracket_position    INTEGER,
    side_a_previous_match_id INTEGER,
    side_b_previous_match_id INTEGER,
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
    """
    CREATE INDEX IF NOT EXISTS idx_event_draw_matches_bracket_position
    ON event_draw_matches(event_id, sub_event_type_code, round_order, bracket_position)
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
    bracket_position: Optional[int] = None
    side_a_previous_match_id: Optional[int] = None
    side_b_previous_match_id: Optional[int] = None


@dataclass(frozen=True)
class DrawRule:
    event_ids: Optional[Set[int]]
    stage_pattern: Pattern[str]
    round_pattern: Optional[Pattern[str]]
    draw_round: Optional[str]
    note: str


ROUND_ALIASES = {
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


DRAW_RULES: List[DrawRule] = [
    DrawRule(
        event_ids={910},
        stage_pattern=re.compile(r"^Main Draw - Stage 2 \(5-8th place\)$", re.IGNORECASE),
        round_pattern=None,
        draw_round=None,
        note="exclude placement classification block",
    ),
    DrawRule(
        event_ids={910},
        stage_pattern=re.compile(r"^Main Draw - Stage 2 \(7th place\)$", re.IGNORECASE),
        round_pattern=None,
        draw_round=None,
        note="exclude placement final",
    ),
    DrawRule(
        event_ids={910},
        stage_pattern=re.compile(r"^Main Draw - Stage 2 \(5th place\)$", re.IGNORECASE),
        round_pattern=None,
        draw_round=None,
        note="exclude placement final",
    ),
    DrawRule(
        event_ids={910},
        stage_pattern=re.compile(r"^Main Draw - Stage 2 \(Bronze Match\)$", re.IGNORECASE),
        round_pattern=re.compile(r"^2$", re.IGNORECASE),
        draw_round="Bronze",
        note="asian cup stage-2 bronze naming",
    ),
    DrawRule(
        event_ids={910},
        stage_pattern=re.compile(r"^Main Draw - Stage 2$", re.IGNORECASE),
        round_pattern=re.compile(r"^8$", re.IGNORECASE),
        draw_round="QuarterFinal",
        note="asian cup stage-2 quarterfinal naming",
    ),
    DrawRule(
        event_ids={910},
        stage_pattern=re.compile(r"^Main Draw - Stage 2$", re.IGNORECASE),
        round_pattern=re.compile(r"^4$", re.IGNORECASE),
        draw_round="SemiFinal",
        note="asian cup stage-2 semifinal naming",
    ),
    DrawRule(
        event_ids={910},
        stage_pattern=re.compile(r"^Main Draw - Stage 2$", re.IGNORECASE),
        round_pattern=re.compile(r"^2$", re.IGNORECASE),
        draw_round="Final",
        note="asian cup stage-2 final naming",
    ),
    DrawRule(
        event_ids=None,
        stage_pattern=re.compile(r"^Main Draw$", re.IGNORECASE),
        round_pattern=re.compile(r"^bronze$", re.IGNORECASE),
        draw_round="Bronze",
        note="standard explicit bronze",
    ),
    DrawRule(
        event_ids=None,
        stage_pattern=re.compile(r"^Main Draw$", re.IGNORECASE),
        round_pattern=None,
        draw_round="__ROUND_ALIAS__",
        note="standard knockout aliases",
    ),
]


def normalize_round(match: MatchRow) -> Optional[str]:
    stage = (match.stage or "").strip()
    round_name = (match.round or "").strip()
    stage_key = stage.lower()
    round_key = round_name.lower()

    if "bronze" in stage_key or "bronze" in round_key:
        return "Bronze"

    for rule in DRAW_RULES:
        if rule.event_ids is not None and match.event_id not in rule.event_ids:
            continue
        if not rule.stage_pattern.match(stage):
            continue
        if rule.round_pattern is not None and not rule.round_pattern.match(round_name):
            continue
        if rule.draw_round == "__ROUND_ALIAS__":
            return ROUND_ALIASES.get(round_key)
        return rule.draw_round

    return None


def pair_key(side_a_key: str, side_b_key: str) -> Tuple[str, str]:
    return tuple(sorted((side_a_key, side_b_key)))


def loser_side_key(match: MatchRow) -> Optional[str]:
    winner = (match.winner_side or "").strip().upper()
    if winner == "A":
        return match.side_b_key
    if winner == "B":
        return match.side_a_key
    return None


def winner_side_key(match: MatchRow) -> Optional[str]:
    winner = (match.winner_side or "").strip().upper()
    if winner == "A":
        return match.side_a_key
    if winner == "B":
        return match.side_b_key
    return None


def is_non_wtt(category_code: Optional[str]) -> bool:
    return category_code is not None and not category_code.startswith("WTT_")


def is_main_draw_stage(match: MatchRow) -> bool:
    return normalize_round(match) is not None


def is_position_round_2(match: MatchRow) -> bool:
    stage = (match.stage or "").strip()
    round_name = (match.round or "").strip()
    return stage == "Position Draw" and round_name in {"2", "Round 2"}


def load_matches(cursor, event_id_filter: Optional[int] = None) -> List[MatchRow]:
    sql = """
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
    """
    params: tuple = ()
    if event_id_filter is not None:
        sql += " WHERE m.event_id = ?"
        params = (int(event_id_filter),)
    sql += " ORDER BY m.event_id, m.sub_event_type_code, m.match_id"

    cursor.execute(sql, params)
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
        normalized_round = normalize_round(match)
        if not is_main_draw_stage(match) or normalized_round != "SemiFinal":
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
        if is_main_draw_stage(match) and normalize_round(match) == "Final":
            key = (match.event_id, match.sub_event_type_code)
            counts[key] = counts.get(key, 0) + 1
    return counts


def infer_bracket_links(draw_rows: List[DrawRow], matches: List[MatchRow]) -> List[DrawRow]:
    """Infer historical bracket feeder links from winner side keys.

    Historical ITTF result rows do not carry WTT bracket unit codes. This derives
    a stable display graph from completed results: if a side in round N+1 has the
    same side key as a winner in round N, that side is fed by the earlier match.
    """

    match_by_id = {match.match_id: match for match in matches}
    state: Dict[int, DrawRow] = {
        row.match_id: replace(row, bracket_position=index + 1)
        for index, row in enumerate(
            sorted(draw_rows, key=lambda item: (item.event_id, item.sub_event_type_code, item.round_order, item.match_id))
        )
    }
    groups: Dict[Tuple[int, str], List[DrawRow]] = {}
    for row in state.values():
        groups.setdefault((row.event_id, row.sub_event_type_code), []).append(row)

    for group_rows in groups.values():
        rounds: Dict[int, List[DrawRow]] = {}
        for row in group_rows:
            rounds.setdefault(row.round_order, []).append(row)

        round_orders = sorted(rounds)
        for round_index in range(len(round_orders) - 1):
            prev_rows = sorted(
                rounds[round_orders[round_index]],
                key=lambda item: (item.bracket_position if item.bracket_position is not None else item.match_id, item.match_id),
            )
            next_rows = sorted(
                rounds[round_orders[round_index + 1]],
                key=lambda item: (item.bracket_position if item.bracket_position is not None else item.match_id, item.match_id),
            )

            winner_sources: Dict[str, List[DrawRow]] = {}
            for row in prev_rows:
                match = match_by_id.get(row.match_id)
                winner_key = winner_side_key(match) if match else None
                if winner_key:
                    winner_sources.setdefault(winner_key, []).append(row)

            used_previous_match_ids: Set[int] = set()
            for next_position, row in enumerate(next_rows, start=1):
                match = match_by_id.get(row.match_id)
                if not match:
                    continue

                previous_ids = {"A": row.side_a_previous_match_id, "B": row.side_b_previous_match_id}
                for side_label, side_key, side_no in (
                    ("A", match.side_a_key, 1),
                    ("B", match.side_b_key, 2),
                ):
                    if not side_key:
                        continue
                    feeder = next(
                        (
                            source
                            for source in winner_sources.get(side_key, [])
                            if source.match_id not in used_previous_match_ids
                        ),
                        None,
                    )
                    if feeder is None:
                        continue

                    used_previous_match_ids.add(feeder.match_id)
                    previous_ids[side_label] = feeder.match_id

                state[row.match_id] = replace(
                    state[row.match_id],
                    side_a_previous_match_id=previous_ids["A"],
                    side_b_previous_match_id=previous_ids["B"],
                )

        for round_index in range(len(round_orders) - 1, 0, -1):
            next_rows = sorted(
                (state[row.match_id] for row in rounds[round_orders[round_index]]),
                key=lambda item: (item.bracket_position if item.bracket_position is not None else item.match_id, item.match_id),
            )

            for next_position, row in enumerate(next_rows, start=1):
                state[row.match_id] = replace(state[row.match_id], bracket_position=next_position)
                for previous_match_id, side_no in (
                    (row.side_a_previous_match_id, 1),
                    (row.side_b_previous_match_id, 2),
                ):
                    if previous_match_id is None or previous_match_id not in state:
                        continue
                    state[previous_match_id] = replace(
                        state[previous_match_id],
                        bracket_position=((next_position - 1) * 2) + side_no,
                    )

    return sorted(
        state.values(),
        key=lambda item: (
            item.event_id,
            item.sub_event_type_code,
            item.round_order,
            item.bracket_position if item.bracket_position is not None else item.match_id,
            item.match_id,
        ),
    )


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
        normalized_round = normalize_round(match)
        event_key = (match.event_id, match.sub_event_type_code)
        sides_pair = pair_key(match.side_a_key, match.side_b_key)
        bronze_pairs = semifinal_loser_pairs.get(event_key, set())

        if is_main_draw_stage(match):
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

    return infer_bracket_links(list(draw_rows_by_match_id.values()), matches), result


def ensure_table(cursor) -> None:
    cursor.execute(CREATE_TABLE_SQL)
    cursor.execute("PRAGMA table_info(event_draw_matches)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    for column_name, column_type in (
        ("bracket_position", "INTEGER"),
        ("side_a_previous_match_id", "INTEGER"),
        ("side_b_previous_match_id", "INTEGER"),
    ):
        if column_name not in existing_columns:
            cursor.execute(f"ALTER TABLE event_draw_matches ADD COLUMN {column_name} {column_type}")
    for stmt in CREATE_INDEX_SQL:
        cursor.execute(stmt)


INSERT_DRAW_SQL = """
    INSERT INTO event_draw_matches (
        match_id,
        event_id,
        sub_event_type_code,
        draw_stage,
        draw_round,
        round_order,
        source_stage,
        source_round,
        bracket_position,
        side_a_previous_match_id,
        side_b_previous_match_id,
        bronze_source,
        bronze_verified,
        validation_note
    ) VALUES (?, ?, ?, 'Main Draw', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _draw_row_to_tuple(row: DrawRow) -> tuple:
    return (
        row.match_id,
        row.event_id,
        row.sub_event_type_code,
        row.draw_round,
        row.round_order,
        row.source_stage,
        row.source_round,
        row.bracket_position,
        row.side_a_previous_match_id,
        row.side_b_previous_match_id,
        row.bronze_source,
        row.bronze_verified,
        row.validation_note,
    )


def rebuild_for_event(cursor, event_id: int) -> dict:
    """Per-event rebuild used by promote_current_event.

    Uses the caller's transaction; does NOT commit.
    Only touches rows for the given event_id.
    """
    matches = load_matches(cursor, event_id_filter=int(event_id))
    draw_rows, result = classify_draw_rows(matches)

    cursor.execute("DELETE FROM event_draw_matches WHERE event_id = ?", (int(event_id),))
    if draw_rows:
        cursor.executemany(INSERT_DRAW_SQL, [_draw_row_to_tuple(r) for r in draw_rows])

    result.update(
        {
            "full_refresh": False,
            "event_id": int(event_id),
            "matches_scanned": len(matches),
            "draw_rows": len(draw_rows),
        }
    )
    return result


def import_event_draw_matches(
    db_path: str,
    dry_run: bool = False,
    event_id: Optional[int] = None,
) -> dict:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    if event_id is not None:
        # Per-event mode: 不动其它 event 的数据
        matches = load_matches(cursor, event_id_filter=int(event_id))
        draw_rows, result = classify_draw_rows(matches)
        result.update(
            {
                "full_refresh": False,
                "event_id": int(event_id),
                "dry_run": dry_run,
                "matches_scanned": len(matches),
                "draw_rows": len(draw_rows),
            }
        )
        if dry_run:
            conn.close()
            return result
        ensure_table(cursor)
        cursor.execute("DELETE FROM event_draw_matches WHERE event_id = ?", (int(event_id),))
        if draw_rows:
            cursor.executemany(INSERT_DRAW_SQL, [_draw_row_to_tuple(r) for r in draw_rows])
        conn.commit()
        conn.close()
        return result

    # Full refresh
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

    if draw_rows:
        cursor.executemany(INSERT_DRAW_SQL, [_draw_row_to_tuple(r) for r in draw_rows])
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
    parser.add_argument(
        "--event-id",
        type=int,
        default=None,
        help="Only rebuild a single event's rows (DELETE+INSERT scoped to event_id). Default: full refresh.",
    )
    parser.add_argument(
        "--summary-json",
        default=None,
        help="Write the structured stats dict to this path (or 'auto'). "
        "Used by run_import_wtt_events.sh to aggregate manual-check info.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Import Event Draw Matches")
    print("=" * 70)
    print(f"Database: {DB_PATH}")
    print(f"Dry run:  {args.dry_run}")
    print(f"Event id: {args.event_id if args.event_id is not None else '(full refresh)'}")
    print("=" * 70 + "\n")

    if not Path(DB_PATH).exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    stats = import_event_draw_matches(str(DB_PATH), dry_run=args.dry_run, event_id=args.event_id)

    print("Results:")
    print(f"  Full refresh mode:            {stats['full_refresh']}")
    print(f"  Dry run mode:                 {stats['dry_run']}")
    if not stats["full_refresh"]:
        print(f"  Event id:                     {stats['event_id']}")
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

    if not args.dry_run and stats["full_refresh"]:
        verify_event_draw_matches(str(DB_PATH))

    if args.summary_json:
        summary_path = write_summary(
            stats,
            args.summary_json,
            project_root=PROJECT_ROOT,
            kind="import_event_draw_matches",
            event_id=args.event_id,
        )
        print(f"  Summary JSON written: {summary_path}")

    sys.exit(0)
