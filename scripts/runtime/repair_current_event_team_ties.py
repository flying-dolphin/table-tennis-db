#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repair malformed current_event_team_ties rows for a current event."""

from __future__ import annotations

import argparse
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import wtt_import_shared as shared

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"


@dataclass
class RepairAction:
    current_team_tie_id: int
    reason: str
    updates: dict[str, str | None]
    merge_target_id: int | None = None


@dataclass
class MatchRepairAction:
    current_match_id: int
    reason: str
    updates: dict[str, str | None]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair current_event_team_ties rows.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist repairs. Default is dry-run.",
    )
    return parser.parse_args()


def is_display_time(value: str | None) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    return "T" not in raw


def load_side_codes(cursor: sqlite3.Cursor, current_team_tie_id: int) -> tuple[str | None, str | None]:
    rows = cursor.execute(
        """
        SELECT side_no, team_code
        FROM current_event_team_tie_sides
        WHERE current_team_tie_id = ?
        ORDER BY side_no ASC
        """,
        (current_team_tie_id,),
    ).fetchall()
    side1 = None
    side2 = None
    for row in rows:
        side_no = int(row["side_no"])
        team_code = (row["team_code"] or "").strip() or None
        if side_no == 1:
            side1 = team_code
        elif side_no == 2:
            side2 = team_code
    return side1, side2


def parse_rubber_order(value: str | None) -> int | None:
    raw = (value or "").strip()
    if not raw:
        return None
    rubber = re.search(r"\bRubber\s+(\d+)\b", raw, re.IGNORECASE)
    return int(rubber.group(1)) if rubber else None


def find_schedule_source(cursor: sqlite3.Cursor, row: sqlite3.Row) -> sqlite3.Row | None:
    side_codes = load_side_codes(cursor, int(row["current_team_tie_id"]))
    candidates = cursor.execute(
        """
        SELECT t.*
        FROM current_event_team_ties t
        WHERE t.event_id = ?
          AND t.current_team_tie_id != ?
          AND t.sub_event_type_code = ?
          AND COALESCE(t.stage_code, '') = COALESCE(?, '')
          AND COALESCE(t.round_code, '') = COALESCE(?, '')
          AND t.scheduled_utc_at IS NOT NULL
        ORDER BY t.current_team_tie_id ASC
        """,
        (
            row["event_id"],
            row["current_team_tie_id"],
            row["sub_event_type_code"],
            row["stage_code"],
            row["round_code"],
        ),
    ).fetchall()

    def same_sides(candidate: sqlite3.Row) -> bool:
        candidate_sides = load_side_codes(cursor, int(candidate["current_team_tie_id"]))
        if not all(side_codes) or not all(candidate_sides):
            return False
        return candidate_sides in (side_codes, (side_codes[1], side_codes[0]))

    session_match_no = shared.parse_match_number(row["session_label"])
    table_no = shared.normalize_table_label(row["table_no"])

    for candidate in candidates:
        candidate_match_no = shared.parse_match_number(candidate["session_label"])
        candidate_table_no = shared.normalize_table_label(candidate["table_no"])
        if session_match_no and table_no:
            if candidate_match_no == session_match_no and candidate_table_no == table_no:
                return candidate

    for candidate in candidates:
        candidate_table_no = shared.normalize_table_label(candidate["table_no"])
        if table_no and candidate_table_no == table_no and same_sides(candidate):
            return candidate

    for candidate in candidates:
        candidate_match_no = shared.parse_match_number(candidate["session_label"])
        if session_match_no and candidate_match_no == session_match_no and same_sides(candidate):
            return candidate

    return None


def collect_round_repairs(cursor: sqlite3.Cursor, event_id: int) -> list[RepairAction]:
    rows = cursor.execute(
        """
        SELECT current_team_tie_id
        FROM current_event_team_ties
        WHERE event_id = ?
          AND round_label = '8FNL'
          AND round_code = 'QF'
        ORDER BY current_team_tie_id ASC
        """,
        (event_id,),
    ).fetchall()
    return [
        RepairAction(
            current_team_tie_id=int(row["current_team_tie_id"]),
            reason="round_code",
            updates={"round_code": "R16"},
        )
        for row in rows
    ]


def collect_time_repairs(cursor: sqlite3.Cursor, event_id: int) -> list[RepairAction]:
    rows = cursor.execute(
        """
        SELECT *
        FROM current_event_team_ties
        WHERE event_id = ?
          AND status = 'live'
          AND (
            scheduled_utc_at IS NULL
            OR external_match_code LIKE 'LIVE::%'
          )
        ORDER BY current_team_tie_id ASC
        """,
        (event_id,),
    ).fetchall()

    repairs: list[RepairAction] = []
    for row in rows:
        source = find_schedule_source(cursor, row)
        if source:
            if (row["external_match_code"] or "").startswith("LIVE::"):
                repairs.append(
                    RepairAction(
                        current_team_tie_id=int(row["current_team_tie_id"]),
                        reason=f"merge_into_tie:{int(source['current_team_tie_id'])}",
                        updates={},
                        merge_target_id=int(source["current_team_tie_id"]),
                    )
                )
                continue
            repairs.append(
                RepairAction(
                    current_team_tie_id=int(row["current_team_tie_id"]),
                    reason=f"time_from_tie:{int(source['current_team_tie_id'])}",
                    updates={
                        "scheduled_local_at": source["scheduled_local_at"],
                        "scheduled_utc_at": source["scheduled_utc_at"],
                    },
                )
            )
            continue
        if is_display_time(row["scheduled_local_at"]):
            repairs.append(
                RepairAction(
                    current_team_tie_id=int(row["current_team_tie_id"]),
                    reason="time_cleared",
                    updates={
                        "scheduled_local_at": None,
                        "scheduled_utc_at": None,
                    },
                )
            )
    return repairs


def collect_session_label_repairs(cursor: sqlite3.Cursor, event_id: int) -> list[RepairAction]:
    rows = cursor.execute(
        """
        SELECT current_team_tie_id, session_label, scheduled_local_at
        FROM current_event_team_ties
        WHERE event_id = ?
        ORDER BY current_team_tie_id ASC
        """,
        (event_id,),
    ).fetchall()
    repairs: list[RepairAction] = []
    for row in rows:
        desired = shared.canonical_session_label(
            row["session_label"],
            scheduled_local_at=row["scheduled_local_at"],
        )
        current = (row["session_label"] or "").strip() or None
        if desired and desired != current:
            repairs.append(
                RepairAction(
                    current_team_tie_id=int(row["current_team_tie_id"]),
                    reason="session_label",
                    updates={"session_label": desired},
                )
            )
    return repairs


def dedupe_repairs(repairs: list[RepairAction]) -> list[RepairAction]:
    merge_ids = {repair.current_team_tie_id for repair in repairs if repair.merge_target_id is not None}
    return [
        repair
        for repair in repairs
        if repair.current_team_tie_id not in merge_ids or repair.merge_target_id is not None
    ]


def collect_match_session_label_repairs(cursor: sqlite3.Cursor, event_id: int) -> list[MatchRepairAction]:
    rows = cursor.execute(
        """
        SELECT
            m.current_match_id,
            m.session_label,
            m.external_match_code,
            m.scheduled_local_at,
            t.session_label AS tie_session_label,
            t.scheduled_local_at AS tie_scheduled_local_at
        FROM current_event_matches m
        JOIN current_event_team_ties t ON t.current_team_tie_id = m.current_team_tie_id
        WHERE m.event_id = ?
        ORDER BY m.current_match_id ASC
        """,
        (event_id,),
    ).fetchall()
    repairs: list[MatchRepairAction] = []
    for row in rows:
        rubber_order = parse_rubber_order(row["external_match_code"]) or parse_rubber_order(row["session_label"])
        if rubber_order is None:
            continue
        base_label = shared.canonical_session_label(
            row["tie_session_label"],
            scheduled_local_at=row["tie_scheduled_local_at"] or row["scheduled_local_at"],
        )
        if not base_label:
            continue
        desired = shared.rubber_session_label(base_label, rubber_order)
        current = (row["session_label"] or "").strip() or None
        if desired != current:
            repairs.append(
                MatchRepairAction(
                    current_match_id=int(row["current_match_id"]),
                    reason="match_session_label",
                    updates={"session_label": desired},
                )
            )
    return repairs


def merge_live_duplicate(cursor: sqlite3.Cursor, source_tie_id: int, target_tie_id: int) -> None:
    source = cursor.execute(
        "SELECT * FROM current_event_team_ties WHERE current_team_tie_id = ?",
        (source_tie_id,),
    ).fetchone()
    target = cursor.execute(
        "SELECT * FROM current_event_team_ties WHERE current_team_tie_id = ?",
        (target_tie_id,),
    ).fetchone()
    if not source or not target:
        return
    target_session_label = shared.canonical_session_label(
        target["session_label"],
        source["session_label"],
        scheduled_local_at=target["scheduled_local_at"],
    ) or target["session_label"]

    cursor.execute(
        """
        UPDATE current_event_team_ties
        SET session_label = ?,
            status = ?,
            source_status = COALESCE(?, source_status),
            match_score = COALESCE(?, match_score),
            winner_side = COALESCE(?, winner_side),
            winner_team_code = COALESCE(?, winner_team_code),
            last_synced_at = COALESCE(?, last_synced_at),
            updated_at = datetime('now')
        WHERE current_team_tie_id = ?
        """,
        (
            target_session_label,
            source["status"],
            source["source_status"],
            source["match_score"],
            source["winner_side"],
            source["winner_team_code"],
            source["last_synced_at"],
            target_tie_id,
        ),
    )

    match_rows = cursor.execute(
        """
        SELECT current_match_id, external_match_code
        FROM current_event_matches
        WHERE current_team_tie_id = ?
        ORDER BY current_match_id ASC
        """,
        (source_tie_id,),
    ).fetchall()
    for match_row in match_rows:
        rubber_order = parse_rubber_order(match_row["external_match_code"]) or parse_rubber_order(
            cursor.execute(
                "SELECT session_label FROM current_event_matches WHERE current_match_id = ?",
                (int(match_row["current_match_id"]),),
            ).fetchone()[0]
        ) or 1
        cursor.execute(
            """
            UPDATE current_event_matches
            SET current_team_tie_id = ?,
                sub_event_type_code = ?,
                stage_label = ?,
                stage_code = ?,
                round_label = ?,
                round_code = ?,
                group_code = ?,
                scheduled_local_at = ?,
                scheduled_utc_at = ?,
                table_no = ?,
                session_label = ?,
                updated_at = datetime('now')
            WHERE current_match_id = ?
            """,
            (
                target_tie_id,
                target["sub_event_type_code"],
                target["stage_label"],
                target["stage_code"],
                target["round_label"],
                target["round_code"],
                target["group_code"],
                target["scheduled_local_at"],
                target["scheduled_utc_at"],
                target["table_no"],
                shared.rubber_session_label(target_session_label, rubber_order),
                int(match_row["current_match_id"]),
            ),
        )

    side_ids = [
        int(row[0])
        for row in cursor.execute(
            "SELECT current_team_tie_side_id FROM current_event_team_tie_sides WHERE current_team_tie_id = ?",
            (source_tie_id,),
        ).fetchall()
    ]
    if side_ids:
        placeholders = ", ".join("?" for _ in side_ids)
        cursor.execute(
            f"DELETE FROM current_event_team_tie_side_players WHERE current_team_tie_side_id IN ({placeholders})",
            side_ids,
        )
    cursor.execute("DELETE FROM current_event_team_tie_sides WHERE current_team_tie_id = ?", (source_tie_id,))
    cursor.execute("DELETE FROM current_event_team_ties WHERE current_team_tie_id = ?", (source_tie_id,))


def apply_repairs(cursor: sqlite3.Cursor, repairs: list[RepairAction]) -> None:
    for repair in repairs:
        if repair.merge_target_id is not None:
            merge_live_duplicate(cursor, repair.current_team_tie_id, repair.merge_target_id)
            continue
        assignments = ", ".join(f"{column} = ?" for column in repair.updates)
        values = list(repair.updates.values()) + [repair.current_team_tie_id]
        cursor.execute(
            f"""
            UPDATE current_event_team_ties
            SET {assignments},
                updated_at = datetime('now')
            WHERE current_team_tie_id = ?
            """,
            values,
        )


def apply_match_repairs(cursor: sqlite3.Cursor, repairs: list[MatchRepairAction]) -> None:
    for repair in repairs:
        assignments = ", ".join(f"{column} = ?" for column in repair.updates)
        values = list(repair.updates.values()) + [repair.current_match_id]
        cursor.execute(
            f"""
            UPDATE current_event_matches
            SET {assignments},
                updated_at = datetime('now')
            WHERE current_match_id = ?
            """,
            values,
        )


def describe_repairs(repairs: list[RepairAction]) -> None:
    if not repairs:
        print("No repairs needed.")
        return
    for repair in repairs:
        updates = ", ".join(f"{key}={value!r}" for key, value in repair.updates.items())
        print(f"{repair.current_team_tie_id}: {repair.reason}: {updates}")


def describe_match_repairs(repairs: list[MatchRepairAction]) -> None:
    if not repairs:
        return
    for repair in repairs:
        updates = ", ".join(f"{key}={value!r}" for key, value in repair.updates.items())
        print(f"match {repair.current_match_id}: {repair.reason}: {updates}")


def main() -> int:
    args = parse_args()
    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    repairs = collect_round_repairs(cursor, args.event_id)
    repairs.extend(collect_time_repairs(cursor, args.event_id))
    repairs.extend(collect_session_label_repairs(cursor, args.event_id))
    repairs = dedupe_repairs(repairs)

    match_repairs = collect_match_session_label_repairs(cursor, args.event_id)

    print(f"Found {len(repairs)} tie repair(s) and {len(match_repairs)} match repair(s) for event {args.event_id}.")
    describe_repairs(repairs)
    describe_match_repairs(match_repairs)

    if not args.apply:
        print("Dry-run only. Re-run with --apply to persist.")
        conn.close()
        return 0

    apply_repairs(cursor, repairs)
    match_repairs = collect_match_session_label_repairs(cursor, args.event_id)
    apply_match_repairs(cursor, match_repairs)
    conn.commit()
    conn.close()
    print("Repairs applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
