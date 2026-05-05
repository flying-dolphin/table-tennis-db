#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import GetEventSchedule.json skeleton into current_event_team_ties tables."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import wtt_import_shared as legacy

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"
TEAM_SUB_EVENTS = {"MT", "WT", "XT"}


def schedule_path(event_dir: Path) -> Path:
    path = event_dir / "GetEventSchedule.json"
    if path.exists():
        return path
    legacy_path = event_dir / "schedule" / "GetEventSchedule.json"
    return legacy_path


def clear_event(cursor: sqlite3.Cursor, event_id: int) -> None:
    cursor.execute(
        """
        DELETE FROM current_event_team_tie_side_players
        WHERE current_team_tie_side_id IN (
            SELECT current_team_tie_side_id
            FROM current_event_team_tie_sides
            WHERE current_team_tie_id IN (
                SELECT current_team_tie_id
                FROM current_event_team_ties
                WHERE event_id = ?
            )
        )
        """,
        (event_id,),
    )
    cursor.execute(
        """
        DELETE FROM current_event_team_tie_sides
        WHERE current_team_tie_id IN (
            SELECT current_team_tie_id
            FROM current_event_team_ties
            WHERE event_id = ?
        )
        """,
        (event_id,),
    )
    cursor.execute("DELETE FROM current_event_team_ties WHERE event_id = ?", (event_id,))


def competitor_team_name(competitor: dict) -> str | None:
    desc = competitor.get("Description") or {}
    return (desc.get("TeamName") or "").strip() or None


def insert_side_players(
    cursor: sqlite3.Cursor,
    current_team_tie_side_id: int,
    athletes: list[dict],
    player_ids: dict[int, int],
) -> int:
    inserted = 0
    ordered = sorted(athletes, key=lambda athlete: athlete.get("Order") or 0)
    for player_order, athlete in enumerate(ordered, start=1):
        if_id = legacy.int_or_none(((athlete.get("Description") or {}).get("IfId")))
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
                legacy.athlete_name(athlete),
                ((athlete.get("Description") or {}).get("Organization")) or None,
            ),
        )
        inserted += 1
    return inserted


def insert_team_tie(
    cursor: sqlite3.Cursor,
    *,
    event_id: int,
    unit: dict,
    event: dict,
    player_ids: dict[int, int],
) -> tuple[int, int]:
    sub_event_type_code = legacy.SUB_EVENT_MAP.get((unit.get("SubEvent") or "").strip())
    if sub_event_type_code not in TEAM_SUB_EVENTS:
        return 0, 0

    round_info = legacy.normalize_round(unit.get("Round"))
    raw_status = unit.get("ScheduleStatus")
    status = legacy.normalize_status(raw_status)
    local_at, utc_at = legacy.to_local_and_utc(unit.get("StartDate"), legacy.infer_time_zone(event))
    session_label = legacy.text_value(unit.get("ItemName")) or legacy.text_value(unit.get("ItemDescription"))
    table_no = ((unit.get("VenueDescription") or {}).get("LocationName")) or unit.get("Location")
    starts = ((unit.get("StartList") or {}).get("Start") or [])

    winner_side = None
    winner_team_code = None
    score = None
    if status == "completed":
        score = unit.get("Result")
        parsed = legacy.parse_tie_score(score)
        if parsed and len(starts) >= 2:
            if parsed[0] > parsed[1]:
                winner_side = "A"
                winner_team_code = ((starts[0].get("Competitor") or {}).get("Organization")) or None
            elif parsed[1] > parsed[0]:
                winner_side = "B"
                winner_team_code = ((starts[1].get("Competitor") or {}).get("Organization")) or None

    cursor.execute(
        """
        INSERT INTO current_event_team_ties (
            event_id, sub_event_type_code, stage_label, stage_code, round_label, round_code, group_code,
            external_match_code, session_label, scheduled_local_at, scheduled_utc_at, table_no,
            status, source_status, source_schedule_status, match_score, winner_side, winner_team_code,
            last_synced_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))
        """,
        (
            event_id,
            sub_event_type_code,
            unit.get("Draw"),
            round_info.stage_code,
            legacy.text_value(unit.get("ItemDescription")) or session_label,
            round_info.round_code,
            round_info.group_code,
            legacy.normalize_external_match_code(unit.get("Code")),
            session_label,
            local_at,
            utc_at,
            table_no,
            status,
            raw_status,
            raw_status,
            score,
            winner_side,
            winner_team_code,
        ),
    )
    current_team_tie_id = int(cursor.lastrowid)

    sides_inserted = 0
    for side_no, start in enumerate(starts[:2], start=1):
        competitor = (start or {}).get("Competitor") or {}
        team_code = (competitor.get("Organization") or "").strip() or None
        seed = legacy.int_or_none(competitor.get("Seed"))
        qualifier = legacy.bool_to_int(competitor.get("Qualifier"))
        is_winner = 1 if winner_side == ("A" if side_no == 1 else "B") else 0
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
                competitor_team_name(competitor),
                seed,
                qualifier,
                is_winner,
            ),
        )
        current_team_tie_side_id = int(cursor.lastrowid)
        athletes = (((competitor.get("Composition") or {}).get("Athlete")) or [])
        sides_inserted += insert_side_players(cursor, current_team_tie_side_id, athletes, player_ids)

    return 1, sides_inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Import GetEventSchedule.json into current_event_team_ties.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--live-event-data-root", type=Path, default=DEFAULT_LIVE_EVENT_DATA_DIR)
    args = parser.parse_args()

    event_dir = args.live_event_data_root.resolve() / str(args.event_id)
    path = schedule_path(event_dir)
    if not path.exists():
        print(f"missing schedule file: {path}", file=sys.stderr)
        return 1

    units = legacy.load_units(path)
    official_result_codes: set[str] = set()
    units = legacy.dedupe_units(units, official_result_codes)

    conn = sqlite3.connect(str(args.db_path.resolve()))
    try:
        cursor = conn.cursor()
        event = legacy.get_event(cursor, args.event_id)
        if not event:
            print(f"event {args.event_id} not found in events", file=sys.stderr)
            return 1

        if_ids: set[int] = set()
        for unit in units:
            sub_event_type_code = legacy.SUB_EVENT_MAP.get((unit.get("SubEvent") or "").strip())
            if sub_event_type_code not in TEAM_SUB_EVENTS:
                continue
            starts = ((unit.get("StartList") or {}).get("Start") or [])
            for start in starts[:2]:
                competitor = (start.get("Competitor") or {})
                athletes = (((competitor.get("Composition") or {}).get("Athlete")) or [])
                for athlete in athletes:
                    if_id = legacy.int_or_none(((athlete.get("Description") or {}).get("IfId")))
                    if if_id is not None:
                        if_ids.add(if_id)
        player_ids = legacy.load_player_ids(cursor, if_ids)

        conn.execute("BEGIN")
        clear_event(cursor, args.event_id)
        tie_count = 0
        roster_count = 0
        for unit in units:
            inserted_ties, inserted_players = insert_team_tie(
                cursor,
                event_id=args.event_id,
                unit=unit,
                event=event,
                player_ids=player_ids,
            )
            tie_count += inserted_ties
            roster_count += inserted_players
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Imported {tie_count} team ties and {roster_count} tie-side players for event {args.event_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
