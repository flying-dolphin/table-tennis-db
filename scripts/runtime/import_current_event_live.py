#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import current live team ties and rubbers from GetLiveResult.json."""

from __future__ import annotations

import argparse
import json
import re
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


def infer_winner_side(score: str | None) -> str | None:
    parsed = legacy.parse_tie_score(score)
    if not parsed:
        return None
    if parsed[0] > parsed[1]:
        return "A"
    if parsed[1] > parsed[0]:
        return "B"
    return None


def resolve_live_status(raw_status: str | None) -> str:
    return legacy.normalize_status(raw_status)


def resolve_winner_side(status: str, raw_winner_side: str | None, score: str | None) -> str | None:
    if status not in {"completed", "walkover"}:
        return None
    if raw_winner_side in {"A", "B"}:
        return raw_winner_side
    return infer_winner_side(score)


def parse_live_sub_event(item: dict) -> str | None:
    raw = (item.get("sub_event") or "").strip()
    code = legacy.SUB_EVENT_MAP.get(raw)
    if code:
        return code

    name = (item.get("sub_event_name") or "").strip().lower()
    if name.startswith("men's teams"):
        return "MT"
    if name.startswith("women's teams"):
        return "WT"
    if name.startswith("mixed teams"):
        return "XT"
    return None


def parse_live_round_info(item: dict) -> legacy.RoundInfo:
    round_info = legacy.normalize_round(item.get("round"))
    if round_info.stage_code != "UNKNOWN":
        return round_info

    haystack = " ".join(
        str(item.get(key) or "")
        for key in ("round", "sub_event_name", "raw_title", "match_code")
    )

    round_match = re.search(r"Round of\s+(\d+)", haystack, re.IGNORECASE)
    if round_match:
        round_no = int(round_match.group(1))
        return legacy.RoundInfo("MAIN_DRAW", f"R{round_no}", None)

    group_match = re.search(r"Group\s+(\d+)", haystack, re.IGNORECASE)
    if group_match:
        group_no = int(group_match.group(1))
        return legacy.RoundInfo("PRELIMINARY", f"G{group_no}", f"GP{group_no:02d}")

    if re.search(r"Preliminary Round", haystack, re.IGNORECASE):
        return legacy.RoundInfo("PRELIMINARY", "R1", None)

    return round_info


def parse_live_session_label(item: dict) -> str | None:
    session_label = (item.get("session_label") or "").strip()
    if session_label:
        return session_label

    haystack = " ".join(str(item.get(key) or "") for key in ("sub_event_name", "raw_title", "match_code"))
    match = re.search(r"\bMatch\s+(\d+)\b", haystack, re.IGNORECASE)
    if match:
        return f"Match {int(match.group(1))}"
    return None


def build_live_external_match_code(item: dict, sub_event_type_code: str, round_info: legacy.RoundInfo) -> str:
    external_match_code = legacy.normalize_external_match_code(item.get("match_code"))
    if external_match_code:
        return external_match_code

    sides = item.get("sides") if isinstance(item.get("sides"), list) else []
    side_codes = [
        (side.get("organization") or "").strip()
        for side in sides[:2]
        if isinstance(side, dict) and (side.get("organization") or "").strip()
    ]
    round_code = round_info.round_code or "UNKNOWN"
    session = re.sub(r"\W+", "", parse_live_session_label(item) or "UNKNOWN")
    return f"LIVE::{sub_event_type_code}::{round_code}::{session}::{'-'.join(side_codes) or 'UNKNOWN'}"


def find_existing_live_team_tie(
    cursor: sqlite3.Cursor,
    *,
    event_id: int,
    item: dict,
    sub_event_type_code: str,
    round_info: legacy.RoundInfo,
) -> sqlite3.Row | None:
    session_label = parse_live_session_label(item)
    table_no = legacy.normalize_table_label(item.get("table_no"))
    match_no = (
        legacy.parse_match_number(session_label)
        or legacy.parse_match_number(item.get("sub_event_name"))
        or legacy.parse_match_number(item.get("raw_title"))
    )

    sides = item.get("sides") if isinstance(item.get("sides"), list) else []
    side_codes = [
        (side.get("organization") or "").strip()
        for side in sides[:2]
        if isinstance(side, dict) and (side.get("organization") or "").strip()
    ]
    if len(side_codes) < 2:
        return None

    rows = cursor.execute(
        """
        SELECT t.*,
               s1.team_code AS side1_team_code,
               s2.team_code AS side2_team_code
        FROM current_event_team_ties t
        LEFT JOIN current_event_team_tie_sides s1
          ON s1.current_team_tie_id = t.current_team_tie_id AND s1.side_no = 1
        LEFT JOIN current_event_team_tie_sides s2
          ON s2.current_team_tie_id = t.current_team_tie_id AND s2.side_no = 2
        WHERE t.event_id = ?
          AND t.sub_event_type_code = ?
          AND COALESCE(t.stage_code, '') = COALESCE(?, '')
          AND COALESCE(t.round_code, '') = COALESCE(?, '')
        ORDER BY t.current_team_tie_id ASC
        """,
        (
            event_id,
            sub_event_type_code,
            round_info.stage_code,
            round_info.round_code,
        ),
    ).fetchall()

    for row in rows:
        row_side_codes = [str(row["side1_team_code"] or "").strip(), str(row["side2_team_code"] or "").strip()]
        if row_side_codes not in ([side_codes[0], side_codes[1]], [side_codes[1], side_codes[0]]):
            continue

        row_table_no = legacy.normalize_table_label(row["table_no"])
        if table_no and row_table_no and row_table_no == table_no:
            return row

        row_match_no = legacy.parse_match_number(row["session_label"])
        if match_no and row_match_no and row_match_no == match_no:
            return row

        if session_label and (row["session_label"] or "").strip() == session_label:
            return row

    return None


def delete_current_event_team_tie(cursor: sqlite3.Cursor, current_team_tie_id: int) -> None:
    side_ids = [
        int(row[0])
        for row in cursor.execute(
            """
            SELECT current_team_tie_side_id
            FROM current_event_team_tie_sides
            WHERE current_team_tie_id = ?
            """,
            (current_team_tie_id,),
        ).fetchall()
    ]
    if side_ids:
        placeholders = ", ".join("?" for _ in side_ids)
        cursor.execute(
            f"""
            DELETE FROM current_event_team_tie_side_players
            WHERE current_team_tie_side_id IN ({placeholders})
            """,
            side_ids,
        )
    cursor.execute(
        "DELETE FROM current_event_team_tie_sides WHERE current_team_tie_id = ?",
        (current_team_tie_id,),
    )
    cursor.execute(
        "DELETE FROM current_event_matches WHERE current_team_tie_id = ?",
        (current_team_tie_id,),
    )
    cursor.execute(
        "DELETE FROM current_event_team_ties WHERE current_team_tie_id = ?",
        (current_team_tie_id,),
    )


def winner_team_code_for_side(sides: list[dict], winner_side: str | None) -> str | None:
    if winner_side == "A" and len(sides) >= 1:
        return sides[0].get("organization")
    if winner_side == "B" and len(sides) >= 2:
        return sides[1].get("organization")
    return None


def winner_team_code_for_tie(cursor: sqlite3.Cursor, current_team_tie_id: int, winner_side: str | None) -> str | None:
    if winner_side not in {"A", "B"}:
        return None
    side_no = 1 if winner_side == "A" else 2
    row = cursor.execute(
        """
        SELECT team_code
        FROM current_event_team_tie_sides
        WHERE current_team_tie_id = ? AND side_no = ?
        """,
        (current_team_tie_id, side_no),
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def upsert_side_players(
    cursor: sqlite3.Cursor,
    current_team_tie_side_id: int,
    players: list[dict],
    team_code: str | None,
) -> None:
    cursor.execute(
        "DELETE FROM current_event_team_tie_side_players WHERE current_team_tie_side_id = ?",
        (current_team_tie_side_id,),
    )
    for player_order, player in enumerate(players, start=1):
        if not isinstance(player, dict):
            continue
        player_name = (player.get("name") or "").strip()
        if not player_name:
            continue
        cursor.execute(
            """
            INSERT INTO current_event_team_tie_side_players (
                current_team_tie_side_id, player_order, player_id, player_name, player_country
            ) VALUES (?, ?, NULL, ?, ?)
            """,
            (current_team_tie_side_id, player_order, player_name, team_code),
        )


def upsert_sides(cursor: sqlite3.Cursor, current_team_tie_id: int, sides: list[dict], winner_side: str | None) -> None:
    for side_no in (1, 2):
        side = sides[side_no - 1] if len(sides) >= side_no and isinstance(sides[side_no - 1], dict) else {}
        team_code = (side.get("organization") or "").strip() or None
        team_name = (side.get("display_name") or "").strip() or team_code
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
            current_team_tie_side_id = int(existing[0])
            cursor.execute(
                """
                UPDATE current_event_team_tie_sides
                SET team_code = COALESCE(?, team_code),
                    team_name = COALESCE(?, team_name),
                    is_winner = ?
                WHERE current_team_tie_side_id = ?
                """,
                (team_code, team_name, is_winner, current_team_tie_side_id),
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
            current_team_tie_side_id = int(cursor.lastrowid)

        players = side.get("players") if isinstance(side.get("players"), list) else []
        if players:
            upsert_side_players(cursor, current_team_tie_side_id, players, team_code)


def sync_child_matches(cursor: sqlite3.Cursor, current_team_tie_id: int, status: str, source_status: str | None) -> None:
    cursor.execute(
        """
        UPDATE current_event_matches
        SET status = ?,
            source_status = COALESCE(?, source_status),
            last_synced_at = datetime('now'),
            updated_at = datetime('now')
        WHERE current_team_tie_id = ?
        """,
        (status, source_status, current_team_tie_id),
    )


def upsert_live_team_tie(cursor: sqlite3.Cursor, *, event_id: int, item: dict, now: str) -> sqlite3.Row | None:
    sub_event_type_code = parse_live_sub_event(item)
    if sub_event_type_code not in TEAM_SUB_EVENTS:
        return None

    sides = item.get("sides") if isinstance(item.get("sides"), list) else []
    side_codes = [
        (side.get("organization") or "").strip()
        for side in sides[:2]
        if isinstance(side, dict) and (side.get("organization") or "").strip()
    ]
    status = resolve_live_status(item.get("source_status"))
    winner_side = resolve_winner_side(status, item.get("winner_side"), item.get("score"))
    winner_team_code = winner_team_code_for_side(sides, winner_side)
    round_info = parse_live_round_info(item)
    external_match_code = build_live_external_match_code(item, sub_event_type_code, round_info)
    scheduled_start = item.get("scheduled_start")
    session_label = legacy.canonical_session_label(
        item.get("session_label"),
        item.get("sub_event_name"),
        item.get("raw_title"),
        scheduled_local_at=scheduled_start,
    )
    table_no = legacy.normalize_table_label(item.get("table_no"))

    existing = cursor.execute(
        """
        SELECT current_team_tie_id
        FROM current_event_team_ties
        WHERE event_id = ? AND external_match_code = ?
        """,
        (event_id, external_match_code),
    ).fetchone()
    if not existing and not legacy.normalize_external_match_code(item.get("match_code")):
        existing = find_existing_live_team_tie(
            cursor,
            event_id=event_id,
            item=item,
            sub_event_type_code=sub_event_type_code,
            round_info=round_info,
        )

    if existing:
        current_team_tie_id = int(existing[0])
        current_row = cursor.execute(
            """
            SELECT *
            FROM current_event_team_ties
            WHERE current_team_tie_id = ?
            """,
            (current_team_tie_id,),
        ).fetchone()
        if not legacy.normalize_external_match_code(item.get("match_code")):
            duplicate_row = cursor.execute(
                """
                SELECT current_team_tie_id
                FROM current_event_team_ties
                WHERE event_id = ?
                  AND sub_event_type_code = ?
                  AND status = 'live'
                  AND external_match_code LIKE 'LIVE::%'
                  AND COALESCE(round_code, '') = 'UNKNOWN'
                  AND COALESCE(table_no, '') = COALESCE(?, '')
                  AND (
                    EXISTS (
                      SELECT 1
                      FROM current_event_team_tie_sides s1
                      WHERE s1.current_team_tie_id = current_event_team_ties.current_team_tie_id
                        AND s1.side_no = 1
                        AND COALESCE(s1.team_code, '') = ?
                    )
                    AND EXISTS (
                      SELECT 1
                      FROM current_event_team_tie_sides s2
                      WHERE s2.current_team_tie_id = current_event_team_ties.current_team_tie_id
                        AND s2.side_no = 2
                        AND COALESCE(s2.team_code, '') = ?
                    )
                  )
                """,
                (
                    event_id,
                    sub_event_type_code,
                    table_no,
                    side_codes[0],
                    side_codes[1],
                ),
            ).fetchone()
            if duplicate_row and int(duplicate_row[0]) != current_team_tie_id:
                delete_current_event_team_tie(cursor, int(duplicate_row[0]))
        cursor.execute(
            """
            UPDATE current_event_team_ties
            SET session_label = COALESCE(?, session_label),
                table_no = COALESCE(?, table_no),
                stage_code = COALESCE(stage_code, ?),
                round_code = COALESCE(round_code, ?),
                group_code = COALESCE(group_code, ?),
                status = ?,
                source_status = COALESCE(?, source_status),
                match_score = ?,
                winner_side = ?,
                winner_team_code = ?,
                last_synced_at = ?,
                updated_at = datetime('now')
            WHERE current_team_tie_id = ?
            """,
            (
                session_label,
                table_no,
                round_info.stage_code,
                round_info.round_code,
                round_info.group_code,
            status,
            item.get("source_status"),
            item.get("score"),
            winner_side,
            winner_team_code,
                now,
                current_team_tie_id,
            ),
        )
    else:
        cursor.execute(
            """
            INSERT INTO current_event_team_ties (
                event_id, sub_event_type_code, stage_label, stage_code, round_label, round_code, group_code,
                external_match_code, session_label, scheduled_local_at, scheduled_utc_at, table_no,
                status, source_status, source_schedule_status, match_score, winner_side, winner_team_code,
                last_synced_at, created_at, updated_at
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                event_id,
                sub_event_type_code,
                round_info.stage_code,
                item.get("round"),
                round_info.round_code,
                round_info.group_code,
                external_match_code,
                session_label,
                scheduled_start,
                table_no,
                status,
                item.get("source_status"),
                item.get("score"),
                winner_side,
                winner_team_code,
                now,
            ),
        )
        current_team_tie_id = int(cursor.lastrowid)

    upsert_sides(cursor, current_team_tie_id, sides, winner_side)
    sync_child_matches(cursor, current_team_tie_id, status, item.get("source_status"))
    return cursor.execute(
        "SELECT * FROM current_event_team_ties WHERE current_team_tie_id = ?",
        (current_team_tie_id,),
    ).fetchone()


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


def infer_player_country(name: str, roster_by_name: dict[str, str]) -> str | None:
    return roster_by_name.get(name.strip().upper())


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


def sync_team_tie_from_live_match(cursor: sqlite3.Cursor, current_team_tie_id: int, live_match: dict) -> None:
    status = resolve_live_status(live_match.get("source_status"))
    score = live_match.get("score")
    winner_side = resolve_winner_side(status, live_match.get("winner_side"), score)
    winner_team_code = winner_team_code_for_tie(cursor, current_team_tie_id, winner_side)

    cursor.execute(
        """
        UPDATE current_event_team_ties
        SET status = ?,
            source_status = COALESCE(?, source_status),
            match_score = ?,
            winner_side = ?,
            winner_team_code = ?,
            last_synced_at = datetime('now'),
            updated_at = datetime('now')
        WHERE current_team_tie_id = ?
        """,
        (status, live_match.get("source_status"), score, winner_side, winner_team_code, current_team_tie_id),
    )
    sync_child_matches(cursor, current_team_tie_id, status, live_match.get("source_status"))


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
    status = resolve_live_status(live_match.get("source_status"))
    roster_by_name = build_roster_country_map(cursor, int(tie_row["current_team_tie_id"]))
    sides = live_match.get("sides") if isinstance(live_match.get("sides"), list) else []

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
        legacy.normalize_table_label(live_match.get("table_no")) or tie_row["table_no"],
        legacy.rubber_session_label(
            legacy.canonical_session_label(
                tie_row["session_label"],
                live_match.get("session_label"),
                live_match.get("sub_event_name"),
                live_match.get("raw_title"),
                scheduled_local_at=tie_row["scheduled_local_at"],
            ),
            rubber_order,
        ),
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

    side_a_team_code = sides[0].get("organization") if len(sides) >= 1 and isinstance(sides[0], dict) else None
    side_b_team_code = sides[1].get("organization") if len(sides) >= 2 and isinstance(sides[1], dict) else None
    side_a = {
        "team_code": side_a_team_code,
        "player_name": individual_match.get("player_a"),
        "player_country": infer_player_country(individual_match.get("player_a") or "", roster_by_name),
        "is_winner": winner_side == "A",
    }
    side_b = {
        "team_code": side_b_team_code,
        "player_name": individual_match.get("player_b"),
        "player_country": infer_player_country(individual_match.get("player_b") or "", roster_by_name),
        "is_winner": winner_side == "B",
    }
    replace_match_children(cursor, current_match_id, side_a, side_b)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import current live team ties and rubbers from GetLiveResult.json.")
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
    now = utc_now_iso()

    conn = sqlite3.connect(str(args.db_path.resolve()))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        conn.execute("BEGIN")
        imported_ties = 0
        imported_rubbers = 0
        for live_match in live_matches:
            if not isinstance(live_match, dict):
                continue
            tie_row = upsert_live_team_tie(cursor, event_id=args.event_id, item=live_match, now=now)
            if not tie_row:
                continue
            imported_ties += 1
            for rubber_order, individual_match in enumerate(live_match.get("individual_matches") or [], start=1):
                if (
                    not isinstance(individual_match, dict)
                    or not individual_match.get("player_a")
                    or not individual_match.get("player_b")
                ):
                    continue
                upsert_live_rubber(
                    cursor,
                    event_id=args.event_id,
                    tie_row=tie_row,
                    live_match=live_match,
                    individual_match=individual_match,
                    rubber_order=rubber_order,
                )
                imported_rubbers += 1
            sync_team_tie_from_live_match(cursor, int(tie_row["current_team_tie_id"]), live_match)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Imported {imported_ties} live team ties and {imported_rubbers} live rubbers for event {args.event_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
