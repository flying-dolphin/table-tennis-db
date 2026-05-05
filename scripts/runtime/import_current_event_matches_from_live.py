#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import live individual rubbers into current_event_matches tables."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

import wtt_import_shared as legacy

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"


def live_result_path(event_dir: Path) -> Path:
    path = event_dir / "GetLiveResult.json"
    if path.exists():
        return path
    return event_dir / "match_results" / "GetLiveResult.json"


def load_live_matches(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    matches = payload.get("matches") if isinstance(payload, dict) else None
    return matches if isinstance(matches, list) else []


def infer_winner_side(score: str | None) -> str | None:
    parsed = legacy.parse_tie_score(score)
    if not parsed:
        return None
    if parsed[0] > parsed[1]:
        return "A"
    if parsed[1] > parsed[0]:
        return "B"
    return None


def infer_player_country(name: str, roster_by_name: dict[str, str]) -> str | None:
    return roster_by_name.get(name.strip().upper())


def build_roster_country_map(cursor: sqlite3.Cursor, current_team_tie_id: int) -> dict[str, str]:
    rows = cursor.execute(
        """
        SELECT p.player_name, p.player_country
        FROM current_event_team_tie_side_players p
        JOIN current_event_team_tie_sides s
          ON s.current_team_tie_side_id = p.current_team_tie_side_id
        WHERE s.current_team_tie_id = ?
        """,
        (current_team_tie_id,),
    ).fetchall()
    return {
        str(row[0]).strip().upper(): str(row[1])
        for row in rows
        if row[0] and row[1]
    }


def replace_match_children(
    cursor: sqlite3.Cursor,
    current_match_id: int,
    side_a: dict,
    side_b: dict,
) -> None:
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
    cursor.execute("DELETE FROM current_event_match_sides WHERE current_match_id = ?", (current_match_id,))

    for side_no, side in ((1, side_a), (2, side_b)):
        cursor.execute(
            """
            INSERT INTO current_event_match_sides (
                current_match_id, side_no, team_code, seed, qualifier, placeholder_text, is_winner
            ) VALUES (?, ?, ?, NULL, NULL, NULL, ?)
            """,
            (
                current_match_id,
                side_no,
                side.get("team_code"),
                1 if side.get("is_winner") else 0,
            ),
        )
        current_match_side_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO current_event_match_side_players (
                current_match_side_id, player_order, player_id, player_name, player_country
            ) VALUES (?, 1, NULL, ?, ?)
            """,
            (
                current_match_side_id,
                side.get("player_name"),
                side.get("player_country"),
            ),
        )


def upsert_live_rubber(
    cursor: sqlite3.Cursor,
    *,
    event_id: int,
    tie_row: sqlite3.Row,
    live_match: dict,
    individual_match: dict,
    rubber_order: int,
) -> None:
    external_match_code = f"{tie_row['external_match_code']}::R{rubber_order}"
    winner_side = infer_winner_side(individual_match.get("match_score"))
    status = "live"
    roster_by_name = build_roster_country_map(cursor, int(tie_row["current_team_tie_id"]))

    existing = cursor.execute(
        """
        SELECT current_match_id
        FROM current_event_matches
        WHERE event_id = ? AND external_match_code = ?
        """,
        (event_id, external_match_code),
    ).fetchone()

    values = (
        event_id,
        int(tie_row["current_team_tie_id"]),
        tie_row["sub_event_type_code"],
        tie_row["stage_label"],
        tie_row["stage_code"],
        tie_row["round_label"],
        tie_row["round_code"],
        tie_row["group_code"],
        external_match_code,
        tie_row["scheduled_local_at"],
        tie_row["scheduled_utc_at"],
        live_match.get("table_no") or tie_row["table_no"],
        f"{live_match.get('session_label') or tie_row['session_label']} / Rubber {rubber_order}",
        status,
        live_match.get("source_status"),
        tie_row["source_schedule_status"],
        individual_match.get("match_score"),
        json.dumps(individual_match.get("games") or [], ensure_ascii=False),
        winner_side,
        None,
        json.dumps(individual_match, ensure_ascii=False),
    )

    if existing:
        current_match_id = int(existing[0])
        update_values = values[1:8] + values[9:] + (current_match_id,)
        cursor.execute(
            """
            UPDATE current_event_matches
            SET current_team_tie_id = ?, sub_event_type_code = ?, stage_label = ?, stage_code = ?, round_label = ?,
                round_code = ?, group_code = ?, scheduled_local_at = ?, scheduled_utc_at = ?, table_no = ?,
                session_label = ?, status = ?, source_status = ?, source_schedule_status = ?, match_score = ?,
                games = ?, winner_side = ?, winner_name = ?, raw_source_payload = ?, last_synced_at = datetime('now'),
                updated_at = datetime('now')
            WHERE current_match_id = ?
            """,
            update_values,
        )
    else:
        cursor.execute(
            """
            INSERT INTO current_event_matches (
                event_id, current_team_tie_id, sub_event_type_code, stage_label, stage_code, round_label, round_code,
                group_code, external_match_code, scheduled_local_at, scheduled_utc_at, table_no, session_label,
                status, source_status, source_schedule_status, match_score, games, winner_side, winner_name,
                raw_source_payload, last_synced_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))
            """,
            values,
        )
        current_match_id = int(cursor.lastrowid)

    side_a = {
        "team_code": ((live_match.get("sides") or [{}])[0].get("organization") if len(live_match.get("sides") or []) >= 1 else None),
        "player_name": individual_match.get("player_a"),
        "player_country": infer_player_country(individual_match.get("player_a") or "", roster_by_name),
        "is_winner": winner_side == "A",
    }
    side_b = {
        "team_code": ((live_match.get("sides") or [{}, {}])[1].get("organization") if len(live_match.get("sides") or []) >= 2 else None),
        "player_name": individual_match.get("player_b"),
        "player_country": infer_player_country(individual_match.get("player_b") or "", roster_by_name),
        "is_winner": winner_side == "B",
    }
    replace_match_children(cursor, current_match_id, side_a, side_b)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import live rubbers into current_event_matches.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--live-event-data-root", type=Path, default=DEFAULT_LIVE_EVENT_DATA_DIR)
    args = parser.parse_args()

    event_dir = args.live_event_data_root.resolve() / str(args.event_id)
    path = live_result_path(event_dir)
    if not path.exists():
        print(f"missing live result file: {path}", file=sys.stderr)
        return 1

    live_matches = load_live_matches(path)
    conn = sqlite3.connect(str(args.db_path.resolve()))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        conn.execute("BEGIN")
        imported = 0
        for live_match in live_matches:
            external_tie_code = legacy.normalize_external_match_code(live_match.get("match_code"))
            if not external_tie_code:
                continue
            tie_row = cursor.execute(
                """
                SELECT *
                FROM current_event_team_ties
                WHERE event_id = ? AND external_match_code = ?
                """,
                (args.event_id, external_tie_code),
            ).fetchone()
            if not tie_row:
                continue
            for rubber_order, individual_match in enumerate(live_match.get("individual_matches") or [], start=1):
                if not isinstance(individual_match, dict) or not individual_match.get("player_a") or not individual_match.get("player_b"):
                    continue
                upsert_live_rubber(
                    cursor,
                    event_id=args.event_id,
                    tie_row=tie_row,
                    live_match=live_match,
                    individual_match=individual_match,
                    rubber_order=rubber_order,
                )
                imported += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Imported {imported} live rubbers for event {args.event_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
