#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import GetEventSchedule.json into current event match/team tie tables."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import wtt_import_shared as shared

DEFAULT_DB_PATH = shared.DEFAULT_DB_PATH
DEFAULT_LIVE_EVENT_DATA_DIR = shared.PROJECT_ROOT / "data" / "live_event_data"
TEAM_SUB_EVENTS = {"MT", "WT", "XT"}


def schedule_path(event_dir: Path) -> Path:
    path = event_dir / "GetEventSchedule.json"
    if path.exists():
        return path
    return event_dir / "schedule" / "GetEventSchedule.json"


def synthetic_external_match_code(unit: dict, sub_event_type_code: str, round_info: shared.RoundInfo) -> str:
    starts = ((unit.get("StartList") or {}).get("Start") or [])
    side_codes: list[str] = []
    for start in starts[:2]:
        if not isinstance(start, dict):
            continue
        competitor = start.get("Competitor") or {}
        code = (competitor.get("Code") or competitor.get("Organization") or "TBD").strip()
        side_codes.append(code or "TBD")
    while len(side_codes) < 2:
        side_codes.append("TBD")

    start_at = (unit.get("StartDate") or "").strip() or "UNKNOWN"
    location = (unit.get("Location") or "").strip() or "UNKNOWN"
    round_code = round_info.group_code or round_info.round_code or "UNKNOWN"
    return f"SCHEDULE::{sub_event_type_code}::{round_code}::{start_at}::{location}::{side_codes[0]}-{side_codes[1]}"


def status_priority(status: str | None) -> int:
    return {
        "completed": 40,
        "walkover": 40,
        "live": 30,
        "scheduled": 20,
        "cancelled": 10,
    }.get((status or "").strip().lower(), 0)


def merge_status(existing_status: str | None, incoming_status: str) -> str:
    if status_priority(existing_status) > status_priority(incoming_status):
        return existing_status or incoming_status
    return incoming_status


def resolve_stage_label(round_info: shared.RoundInfo) -> str | None:
    if round_info.stage_code == "PRELIMINARY":
        return "Preliminary"
    if round_info.stage_code == "MAIN_DRAW":
        return "Main Draw"
    if round_info.stage_code == "UNKNOWN":
        return None
    return round_info.stage_code


def load_existing_ties(cursor: sqlite3.Cursor, event_id: int) -> dict[str, sqlite3.Row]:
    rows = cursor.execute(
        """
        SELECT *
        FROM current_event_team_ties
        WHERE event_id = ?
          AND external_match_code IS NOT NULL
        """,
        (event_id,),
    ).fetchall()
    return {
        shared.normalize_external_match_code(row["external_match_code"]): row
        for row in rows
        if shared.normalize_external_match_code(row["external_match_code"])
    }


def load_existing_matches(cursor: sqlite3.Cursor, event_id: int) -> dict[str, sqlite3.Row]:
    rows = cursor.execute(
        """
        SELECT *
        FROM current_event_matches
        WHERE event_id = ?
          AND external_match_code IS NOT NULL
        """,
        (event_id,),
    ).fetchall()
    return {
        shared.normalize_external_match_code(row["external_match_code"]): row
        for row in rows
        if shared.normalize_external_match_code(row["external_match_code"])
    }


def load_player_ids_for_units(cursor: sqlite3.Cursor, units: list[dict]) -> dict[int, int]:
    if_ids: set[int] = set()
    for unit in units:
        starts = ((unit.get("StartList") or {}).get("Start") or [])
        for start in starts[:2]:
            if not isinstance(start, dict):
                continue
            competitor = start.get("Competitor") or {}
            athletes = (((competitor.get("Composition") or {}).get("Athlete")) or [])
            for athlete in athletes:
                if not isinstance(athlete, dict):
                    continue
                desc = athlete.get("Description") or {}
                if_id = shared.int_or_none(desc.get("IfId") or athlete.get("Code"))
                if if_id is not None:
                    if_ids.add(if_id)
    return shared.load_player_ids(cursor, if_ids)


def cleanup_non_team_ties(cursor: sqlite3.Cursor, event_id: int) -> int:
    rows = cursor.execute(
        """
        SELECT current_team_tie_id
        FROM current_event_team_ties
        WHERE event_id = ?
          AND sub_event_type_code NOT IN ('MT', 'WT', 'XT')
        """,
        (event_id,),
    ).fetchall()
    tie_ids = [int(row[0]) for row in rows]
    if not tie_ids:
        return 0

    placeholders = ",".join("?" for _ in tie_ids)
    cursor.execute(
        f"""
        DELETE FROM current_event_match_side_players
        WHERE current_match_side_id IN (
            SELECT s.current_match_side_id
            FROM current_event_match_sides s
            JOIN current_event_matches m ON m.current_match_id = s.current_match_id
            WHERE m.current_team_tie_id IN ({placeholders})
        )
        """,
        tie_ids,
    )
    cursor.execute(
        f"""
        DELETE FROM current_event_match_sides
        WHERE current_match_id IN (
            SELECT current_match_id
            FROM current_event_matches
            WHERE current_team_tie_id IN ({placeholders})
        )
        """,
        tie_ids,
    )
    cursor.execute(
        f"DELETE FROM current_event_matches WHERE current_team_tie_id IN ({placeholders})",
        tie_ids,
    )
    cursor.execute(
        f"""
        DELETE FROM current_event_team_tie_side_players
        WHERE current_team_tie_side_id IN (
            SELECT current_team_tie_side_id
            FROM current_event_team_tie_sides
            WHERE current_team_tie_id IN ({placeholders})
        )
        """,
        tie_ids,
    )
    cursor.execute(
        f"DELETE FROM current_event_team_tie_sides WHERE current_team_tie_id IN ({placeholders})",
        tie_ids,
    )
    cursor.execute(
        f"DELETE FROM current_event_team_ties WHERE current_team_tie_id IN ({placeholders})",
        tie_ids,
    )
    return len(tie_ids)


def delete_tie_children(cursor: sqlite3.Cursor, current_team_tie_id: int) -> None:
    cursor.execute(
        """
        DELETE FROM current_event_team_tie_side_players
        WHERE current_team_tie_side_id IN (
            SELECT current_team_tie_side_id
            FROM current_event_team_tie_sides
            WHERE current_team_tie_id = ?
        )
        """,
        (current_team_tie_id,),
    )
    cursor.execute(
        "DELETE FROM current_event_team_tie_sides WHERE current_team_tie_id = ?",
        (current_team_tie_id,),
    )


def insert_tie_children(
    cursor: sqlite3.Cursor,
    current_team_tie_id: int,
    starts: list[dict],
    player_ids: dict[int, int],
    winner_side: str | None,
) -> tuple[int, int]:
    side_count = 0
    player_count = 0
    for side_no, start in enumerate(starts[:2], start=1):
        if not isinstance(start, dict):
            continue
        competitor = start.get("Competitor") or {}
        team_code = (competitor.get("Organization") or "").strip() or None
        team_name = shared.competitor_name(competitor)
        cursor.execute(
            """
            INSERT INTO current_event_team_tie_sides (
                current_team_tie_id, side_no, team_code, team_name, seed, qualifier, is_winner
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                current_team_tie_id,
                side_no,
                team_code,
                team_name,
                shared.int_or_none(competitor.get("Seed")),
                shared.bool_to_int(competitor.get("Qualifier")),
                1 if winner_side == ("A" if side_no == 1 else "B") else 0,
            ),
        )
        current_team_tie_side_id = int(cursor.lastrowid)
        side_count += 1

        athletes = (((competitor.get("Composition") or {}).get("Athlete")) or [])
        for player_order, athlete in enumerate(athletes, start=1):
            if not isinstance(athlete, dict):
                continue
            desc = athlete.get("Description") or {}
            if_id = shared.int_or_none(desc.get("IfId") or athlete.get("Code"))
            cursor.execute(
                """
                INSERT INTO current_event_team_tie_side_players (
                    current_team_tie_side_id, player_order, player_id, player_name, player_country
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    current_team_tie_side_id,
                    player_order,
                    player_ids.get(if_id) if if_id is not None else None,
                    shared.athlete_name(athlete),
                    desc.get("Organization") or team_code,
                ),
            )
            player_count += 1

    return side_count, player_count


def delete_match_children(cursor: sqlite3.Cursor, current_match_id: int) -> None:
    cursor.execute(
        """
        DELETE FROM current_event_match_side_players
        WHERE current_match_side_id IN (
            SELECT current_match_side_id
            FROM current_event_match_sides
            WHERE current_match_id = ?
        )
        """,
        (current_match_id,),
    )
    cursor.execute(
        "DELETE FROM current_event_match_sides WHERE current_match_id = ?",
        (current_match_id,),
    )


def insert_match_children(
    cursor: sqlite3.Cursor,
    current_match_id: int,
    starts: list[dict],
    player_ids: dict[int, int],
    winner_side: str | None,
) -> tuple[int, int]:
    side_count = 0
    player_count = 0
    for side_no, start in enumerate(starts[:2], start=1):
        if not isinstance(start, dict):
            continue
        competitor = start.get("Competitor") or {}
        cursor.execute(
            """
            INSERT INTO current_event_match_sides (
                current_match_id, side_no, team_code, seed, qualifier, placeholder_text, is_winner
            ) VALUES (?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                current_match_id,
                side_no,
                (competitor.get("Organization") or "").strip() or None,
                shared.int_or_none(competitor.get("Seed")),
                shared.bool_to_int(competitor.get("Qualifier")),
                1 if winner_side == ("A" if side_no == 1 else "B") else 0,
            ),
        )
        current_match_side_id = int(cursor.lastrowid)
        side_count += 1

        athletes = (((competitor.get("Composition") or {}).get("Athlete")) or [])
        for player_order, athlete in enumerate(athletes, start=1):
            if not isinstance(athlete, dict):
                continue
            desc = athlete.get("Description") or {}
            if_id = shared.int_or_none(desc.get("IfId") or athlete.get("Code"))
            cursor.execute(
                """
                INSERT INTO current_event_match_side_players (
                    current_match_side_id, player_order, player_id, player_name, player_country
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    current_match_side_id,
                    player_order,
                    player_ids.get(if_id) if if_id is not None else None,
                    shared.athlete_name(athlete),
                    desc.get("Organization") or (competitor.get("Organization") or "").strip() or None,
                ),
            )
            player_count += 1

    return side_count, player_count


def upsert_schedule_match(
    cursor: sqlite3.Cursor,
    *,
    event_id: int,
    event_time_zone: str | None,
    unit: dict,
    existing_matches: dict[str, sqlite3.Row],
    player_ids: dict[int, int],
    sub_event_type_code: str,
    round_info: shared.RoundInfo,
) -> tuple[bool, int, int]:
    external_match_code = shared.normalize_external_match_code(unit.get("Code"))
    if not external_match_code:
        external_match_code = synthetic_external_match_code(unit, sub_event_type_code, round_info)

    scheduled_local_at, scheduled_utc_at = shared.to_local_and_utc(unit.get("StartDate"), event_time_zone)
    source_schedule_status = (unit.get("ScheduleStatus") or "").strip() or None
    incoming_status = shared.normalize_status(source_schedule_status)
    raw_session_label = shared.text_value(unit.get("ItemName")) or shared.text_value(unit.get("ItemDescription"))
    session_label = shared.canonical_session_label(raw_session_label, scheduled_local_at=scheduled_local_at)
    starts = ((unit.get("StartList") or {}).get("Start") or [])
    existing = existing_matches.get(external_match_code)

    match_values = {
        "sub_event_type_code": sub_event_type_code,
        "stage_label": resolve_stage_label(round_info),
        "stage_code": round_info.stage_code,
        "round_label": unit.get("Round"),
        "round_code": round_info.round_code,
        "group_code": round_info.group_code,
        "external_match_code": external_match_code,
        "session_label": session_label,
        "scheduled_local_at": scheduled_local_at,
        "scheduled_utc_at": scheduled_utc_at,
        "table_no": shared.normalize_table_label(unit.get("Location")),
        "source_schedule_status": source_schedule_status,
    }

    if existing:
        final_status = merge_status(existing["status"], incoming_status)
        cursor.execute(
            """
            UPDATE current_event_matches
            SET current_team_tie_id = NULL,
                sub_event_type_code = ?,
                stage_label = COALESCE(?, stage_label),
                stage_code = COALESCE(?, stage_code),
                round_label = COALESCE(?, round_label),
                round_code = COALESCE(?, round_code),
                group_code = COALESCE(?, group_code),
                session_label = COALESCE(?, session_label),
                scheduled_local_at = COALESCE(?, scheduled_local_at),
                scheduled_utc_at = COALESCE(?, scheduled_utc_at),
                table_no = COALESCE(?, table_no),
                status = ?,
                source_schedule_status = COALESCE(?, source_schedule_status),
                raw_source_payload = ?,
                last_synced_at = datetime('now'),
                updated_at = datetime('now')
            WHERE current_match_id = ?
            """,
            (
                match_values["sub_event_type_code"],
                match_values["stage_label"],
                match_values["stage_code"],
                match_values["round_label"],
                match_values["round_code"],
                match_values["group_code"],
                match_values["session_label"],
                match_values["scheduled_local_at"],
                match_values["scheduled_utc_at"],
                match_values["table_no"],
                final_status,
                match_values["source_schedule_status"],
                json.dumps(unit, ensure_ascii=False),
                int(existing["current_match_id"]),
            ),
        )
        current_match_id = int(existing["current_match_id"])
        winner_side = existing["winner_side"]
    else:
        cursor.execute(
            """
            INSERT INTO current_event_matches (
                event_id, current_team_tie_id, sub_event_type_code, stage_label, stage_code, round_label, round_code,
                group_code, external_match_code, scheduled_local_at, scheduled_utc_at, table_no, session_label,
                status, source_status, source_schedule_status, match_score, games, winner_side, winner_name,
                raw_source_payload, last_synced_at, created_at, updated_at
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, NULL, ?, datetime('now'), datetime('now'), datetime('now'))
            """,
            (
                event_id,
                match_values["sub_event_type_code"],
                match_values["stage_label"],
                match_values["stage_code"],
                match_values["round_label"],
                match_values["round_code"],
                match_values["group_code"],
                match_values["external_match_code"],
                match_values["scheduled_local_at"],
                match_values["scheduled_utc_at"],
                match_values["table_no"],
                match_values["session_label"],
                incoming_status,
                match_values["source_schedule_status"],
                json.dumps(unit, ensure_ascii=False),
            ),
        )
        current_match_id = int(cursor.lastrowid)
        winner_side = None
        existing_matches[external_match_code] = cursor.execute(
            "SELECT * FROM current_event_matches WHERE current_match_id = ?",
            (current_match_id,),
        ).fetchone()

    delete_match_children(cursor, current_match_id)
    side_count, player_count = insert_match_children(cursor, current_match_id, starts, player_ids, winner_side)
    return True, side_count, player_count


def upsert_schedule_unit(
    cursor: sqlite3.Cursor,
    *,
    event_id: int,
    event_time_zone: str | None,
    unit: dict,
    existing_rows: dict[str, sqlite3.Row],
    existing_matches: dict[str, sqlite3.Row],
    player_ids: dict[int, int],
) -> tuple[bool, str | None, int, int]:
    sub_event_type_code = shared.SUB_EVENT_MAP.get((unit.get("SubEvent") or "").strip())
    if not sub_event_type_code:
        return False, None, 0, 0

    round_info = shared.normalize_round(unit.get("Round"))
    if sub_event_type_code not in TEAM_SUB_EVENTS:
        ok, side_count, player_count = upsert_schedule_match(
            cursor,
            event_id=event_id,
            event_time_zone=event_time_zone,
            unit=unit,
            existing_matches=existing_matches,
            player_ids=player_ids,
            sub_event_type_code=sub_event_type_code,
            round_info=round_info,
        )
        return ok, "match", side_count, player_count

    external_match_code = shared.normalize_external_match_code(unit.get("Code"))
    if not external_match_code:
        external_match_code = synthetic_external_match_code(unit, sub_event_type_code, round_info)

    scheduled_local_at, scheduled_utc_at = shared.to_local_and_utc(unit.get("StartDate"), event_time_zone)
    source_schedule_status = (unit.get("ScheduleStatus") or "").strip() or None
    incoming_status = shared.normalize_status(source_schedule_status)
    raw_session_label = shared.text_value(unit.get("ItemName")) or shared.text_value(unit.get("ItemDescription"))
    session_label = shared.canonical_session_label(raw_session_label, scheduled_local_at=scheduled_local_at)
    starts = ((unit.get("StartList") or {}).get("Start") or [])
    existing = existing_rows.get(external_match_code)

    tie_values = {
        "sub_event_type_code": sub_event_type_code,
        "stage_label": resolve_stage_label(round_info),
        "stage_code": round_info.stage_code,
        "round_label": unit.get("Round"),
        "round_code": round_info.round_code,
        "group_code": round_info.group_code,
        "external_match_code": external_match_code,
        "session_label": session_label,
        "scheduled_local_at": scheduled_local_at,
        "scheduled_utc_at": scheduled_utc_at,
        "table_no": shared.normalize_table_label(unit.get("Location")),
        "source_schedule_status": source_schedule_status,
    }

    if existing:
        final_status = merge_status(existing["status"], incoming_status)
        cursor.execute(
            """
            UPDATE current_event_team_ties
            SET sub_event_type_code = ?,
                stage_label = COALESCE(?, stage_label),
                stage_code = COALESCE(?, stage_code),
                round_label = COALESCE(?, round_label),
                round_code = COALESCE(?, round_code),
                group_code = COALESCE(?, group_code),
                session_label = COALESCE(?, session_label),
                scheduled_local_at = COALESCE(?, scheduled_local_at),
                scheduled_utc_at = COALESCE(?, scheduled_utc_at),
                table_no = COALESCE(?, table_no),
                status = ?,
                source_schedule_status = COALESCE(?, source_schedule_status),
                last_synced_at = datetime('now'),
                updated_at = datetime('now')
            WHERE current_team_tie_id = ?
            """,
            (
                tie_values["sub_event_type_code"],
                tie_values["stage_label"],
                tie_values["stage_code"],
                tie_values["round_label"],
                tie_values["round_code"],
                tie_values["group_code"],
                tie_values["session_label"],
                tie_values["scheduled_local_at"],
                tie_values["scheduled_utc_at"],
                tie_values["table_no"],
                final_status,
                tie_values["source_schedule_status"],
                int(existing["current_team_tie_id"]),
            ),
        )
        current_team_tie_id = int(existing["current_team_tie_id"])
        winner_side = existing["winner_side"]
    else:
        cursor.execute(
            """
            INSERT INTO current_event_team_ties (
                event_id, sub_event_type_code, stage_label, stage_code, round_label, round_code, group_code,
                external_match_code, session_label, scheduled_local_at, scheduled_utc_at, table_no,
                status, source_status, source_schedule_status, match_score, winner_side, winner_team_code,
                last_synced_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, datetime('now'), datetime('now'), datetime('now'))
            """,
            (
                event_id,
                tie_values["sub_event_type_code"],
                tie_values["stage_label"],
                tie_values["stage_code"],
                tie_values["round_label"],
                tie_values["round_code"],
                tie_values["group_code"],
                tie_values["external_match_code"],
                tie_values["session_label"],
                tie_values["scheduled_local_at"],
                tie_values["scheduled_utc_at"],
                tie_values["table_no"],
                incoming_status,
                tie_values["source_schedule_status"],
            ),
        )
        current_team_tie_id = int(cursor.lastrowid)
        winner_side = None
        existing_rows[external_match_code] = cursor.execute(
            "SELECT * FROM current_event_team_ties WHERE current_team_tie_id = ?",
            (current_team_tie_id,),
        ).fetchone()

    delete_tie_children(cursor, current_team_tie_id)
    side_count, player_count = insert_tie_children(cursor, current_team_tie_id, starts, player_ids, winner_side)
    return True, "team_tie", side_count, player_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Import GetEventSchedule.json into current event match/team tie tables.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--live-event-data-root", type=Path, default=DEFAULT_LIVE_EVENT_DATA_DIR)
    args = parser.parse_args()

    event_dir = args.live_event_data_root.resolve() / str(args.event_id)
    path = schedule_path(event_dir)
    if not path.exists():
        print(f"missing schedule file: {path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(args.db_path.resolve()))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        event = shared.get_event(cursor, args.event_id)
        if event is None:
            print(f"events table has no event_id={args.event_id}", file=sys.stderr)
            return 1

        units = shared.dedupe_units(shared.load_units(path), set())
        player_ids = load_player_ids_for_units(cursor, units)
        imported_matches = 0
        imported_ties = 0
        skipped = 0
        side_count = 0
        player_count = 0
        existing_rows = load_existing_ties(cursor, args.event_id)
        existing_matches = load_existing_matches(cursor, args.event_id)
        conn.execute("BEGIN")
        cleaned_non_team_ties = cleanup_non_team_ties(cursor, args.event_id)

        for unit in units:
            ok, kind, unit_side_count, unit_player_count = upsert_schedule_unit(
                cursor,
                event_id=args.event_id,
                event_time_zone=shared.infer_time_zone(event),
                unit=unit,
                existing_rows=existing_rows,
                existing_matches=existing_matches,
                player_ids=player_ids,
            )
            if not ok:
                skipped += 1
                continue
            if kind == "team_tie":
                imported_ties += 1
            elif kind == "match":
                imported_matches += 1
            side_count += unit_side_count
            player_count += unit_player_count

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(
        f"Imported {imported_matches} scheduled matches and {imported_ties} schedule team ties "
        f"for event {args.event_id} ({side_count} sides, {player_count} players); "
        f"skipped {skipped} units; cleaned {cleaned_non_team_ties} non-team team ties"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
