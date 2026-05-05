#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Update current_event_team_ties from GetLiveResult.json."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import wtt_import_shared as legacy

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"
TEAM_SUB_EVENTS = {"MT", "WT", "XT"}


def live_result_path(event_dir: Path) -> Path:
    path = event_dir / "GetLiveResult.json"
    if path.exists():
        return path
    return event_dir / "match_results" / "GetLiveResult.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_live_matches(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    matches = payload.get("matches") if isinstance(payload, dict) else None
    return matches if isinstance(matches, list) else []


def winner_team_code_for_side(sides: list[dict], winner_side: str | None) -> str | None:
    if winner_side == "A" and len(sides) >= 1:
        return sides[0].get("organization")
    if winner_side == "B" and len(sides) >= 2:
        return sides[1].get("organization")
    return None


def upsert_sides(cursor: sqlite3.Cursor, current_team_tie_id: int, sides: list[dict], winner_side: str | None) -> None:
    for side_no in (1, 2):
        side = sides[side_no - 1] if len(sides) >= side_no and isinstance(sides[side_no - 1], dict) else {}
        team_code = side.get("organization")
        team_name = side.get("display_name") or team_code
        is_winner = 1 if winner_side == ("A" if side_no == 1 else "B") else 0
        existing = cursor.execute(
            """
            SELECT current_team_tie_side_id
            FROM current_event_team_tie_sides
            WHERE current_team_tie_id = ? AND side_no = ?
            """,
            (current_team_tie_id, side_no),
        ).fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE current_event_team_tie_sides
                SET team_code = COALESCE(?, team_code),
                    team_name = COALESCE(?, team_name),
                    is_winner = ?
                WHERE current_team_tie_side_id = ?
                """,
                (team_code, team_name, is_winner, int(existing[0])),
            )
        else:
            cursor.execute(
                """
                INSERT INTO current_event_team_tie_sides (
                    current_team_tie_id, side_no, team_code, team_name, seed, qualifier, is_winner
                ) VALUES (?, ?, ?, ?, NULL, NULL, ?)
                """,
                (current_team_tie_id, side_no, team_code, team_name, is_winner),
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Update current_event_team_ties from GetLiveResult.json.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--live-event-data-root", type=Path, default=DEFAULT_LIVE_EVENT_DATA_DIR)
    args = parser.parse_args()

    event_dir = args.live_event_data_root.resolve() / str(args.event_id)
    path = live_result_path(event_dir)
    if not path.exists():
        print(f"missing live result file: {path}", file=sys.stderr)
        return 1

    matches = load_live_matches(path)
    now = utc_now_iso()

    conn = sqlite3.connect(str(args.db_path.resolve()))
    try:
        cursor = conn.cursor()
        conn.execute("BEGIN")
        updated = 0
        inserted = 0
        for item in matches:
            if not isinstance(item, dict):
                continue
            external_match_code = legacy.normalize_external_match_code(item.get("match_code"))
            if not external_match_code:
                continue
            sub_event_type_code = legacy.SUB_EVENT_MAP.get((item.get("sub_event") or "").strip())
            if sub_event_type_code not in TEAM_SUB_EVENTS:
                continue
            sides = item.get("sides") if isinstance(item.get("sides"), list) else []
            winner_side = item.get("winner_side")
            winner_team_code = winner_team_code_for_side(sides, winner_side)
            existing = cursor.execute(
                """
                SELECT current_team_tie_id
                FROM current_event_team_ties
                WHERE event_id = ? AND external_match_code = ?
                """,
                (args.event_id, external_match_code),
            ).fetchone()
            if existing:
                current_team_tie_id = int(existing[0])
                cursor.execute(
                    """
                    UPDATE current_event_team_ties
                    SET session_label = COALESCE(?, session_label),
                        table_no = COALESCE(?, table_no),
                        status = ?,
                        source_status = ?,
                        match_score = ?,
                        winner_side = ?,
                        winner_team_code = ?,
                        last_synced_at = ?,
                        updated_at = datetime('now')
                    WHERE current_team_tie_id = ?
                    """,
                    (
                        item.get("session_label"),
                        item.get("table_no"),
                        "live",
                        item.get("source_status"),
                        item.get("score"),
                        winner_side,
                        winner_team_code,
                        now,
                        current_team_tie_id,
                    ),
                )
                updated += 1
            else:
                cursor.execute(
                    """
                    INSERT INTO current_event_team_ties (
                        event_id, sub_event_type_code, stage_label, stage_code, round_label, round_code, group_code,
                        external_match_code, session_label, scheduled_local_at, scheduled_utc_at, table_no,
                        status, source_status, source_schedule_status, match_score, winner_side, winner_team_code,
                        last_synced_at, created_at, updated_at
                    ) VALUES (?, ?, NULL, NULL, NULL, ?, NULL, ?, ?, ?, NULL, ?, ?, ?, NULL, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    """,
                    (
                        args.event_id,
                        sub_event_type_code,
                        item.get("round"),
                        external_match_code,
                        item.get("session_label"),
                        item.get("scheduled_start_local") or item.get("scheduled_start"),
                        item.get("table_no"),
                        "live",
                        item.get("source_status"),
                        item.get("score"),
                        winner_side,
                        winner_team_code,
                        now,
                    ),
                )
                current_team_tie_id = int(cursor.lastrowid)
                inserted += 1
            upsert_sides(cursor, current_team_tie_id, sides, winner_side)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Updated {updated} live team ties, inserted {inserted} new live team ties for event {args.event_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
