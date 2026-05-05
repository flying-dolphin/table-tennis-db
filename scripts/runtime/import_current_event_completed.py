#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import completed team ties and rubbers from completed_matches.json."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"

CATEGORY_SUB_EVENT_MAP = {
    "men's teams": "MT",
    "women's teams": "WT",
    "mixed teams": "XT",
}


def completed_path(event_dir: Path) -> Path:
    path = event_dir / "completed_matches.json"
    if path.exists():
        return path
    return event_dir / "match_results" / "completed_matches.json"


def parse_sub_event(category: str) -> str | None:
    base = category.lower().split("-")[0].strip()
    return CATEGORY_SUB_EVENT_MAP.get(base)


def parse_group_code(category: str) -> str | None:
    match = re.search(r"Group\s+(\d+)", category, re.IGNORECASE)
    return f"GP{int(match.group(1)):02d}" if match else None


FORFEIT_MARKERS = ("WO", "INJ", "DNS", "DSQ", "RET")
_MARKER_RE = "|".join(FORFEIT_MARKERS)


def parse_score_pair(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.search(r"(\d+)\s*-\s*(\d+)", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def build_score_a_perspective(
    raw_score: str | None,
    forfeit_marker: str | None,
    forfeit_side: str | None,
    team1_is_side_a: bool,
) -> tuple[str | None, str | None]:
    """Return (score_in_a_perspective, winner_side).

    Handles trailing-marker ("3-0 WO") and leading-marker ("0 WO-3") formats.
    Uses explicit forfeit_marker / forfeit_side from the scraper when present;
    otherwise parses the marker and its side from the raw score string.
    """
    if not raw_score:
        return None, None
    raw = raw_score.strip()

    marker = (forfeit_marker or "").strip() or None
    marker_team = (forfeit_side or "").strip() or None
    t1 = t2 = None

    m = re.match(rf"^(\d+)\s*-\s*(\d+)(?:\s+({_MARKER_RE}))?\s*$", raw)
    if m:
        t1, t2 = int(m.group(1)), int(m.group(2))
        if not marker and m.group(3):
            marker = m.group(3)
            marker_team = "team2"
    else:
        m = re.match(rf"^(\d+)\s+({_MARKER_RE})\s*-\s*(\d+)\s*$", raw)
        if m:
            t1, t2 = int(m.group(1)), int(m.group(3))
            if not marker:
                marker = m.group(2)
                marker_team = "team1"
        else:
            return raw, None

    a_score = t1 if team1_is_side_a else t2
    b_score = t2 if team1_is_side_a else t1
    a_has_marker = bool(marker) and marker_team is not None and (
        (marker_team == "team1") == team1_is_side_a
    )
    b_has_marker = bool(marker) and marker_team is not None and not a_has_marker

    if a_has_marker:
        score_str = f"{a_score} {marker}-{b_score}"
    elif b_has_marker:
        score_str = f"{a_score}-{b_score} {marker}"
    elif marker:
        score_str = f"{a_score}-{b_score} {marker}"
    else:
        score_str = f"{a_score}-{b_score}"

    if marker == "WO" and (a_has_marker or b_has_marker):
        winner = "B" if a_has_marker else "A"
    elif a_score > b_score:
        winner = "A"
    elif b_score > a_score:
        winner = "B"
    elif a_has_marker:
        winner = "B"
    elif b_has_marker:
        winner = "A"
    else:
        winner = None

    return score_str, winner


def normalize_round_from_category(category: str) -> tuple[str | None, str | None]:
    raw = category.lower()
    if "group " in raw:
        group_code = parse_group_code(category)
        group_no = int(group_code[2:]) if group_code and group_code[2:].isdigit() else None
        return "PRELIMINARY", f"G{group_no}" if group_no is not None else None
    if "preliminary round" in raw:
        return "PRELIMINARY", "R1"
    mapping = {
        "round of 32": ("MAIN_DRAW", "R32"),
        "round of 16": ("MAIN_DRAW", "R16"),
        "quarter-final": ("MAIN_DRAW", "QF"),
        "quarterfinal": ("MAIN_DRAW", "QF"),
        "semi-final": ("MAIN_DRAW", "SF"),
        "semifinal": ("MAIN_DRAW", "SF"),
        "final": ("MAIN_DRAW", "F"),
    }
    for key, value in mapping.items():
        if key in raw:
            return value
    return None, None


def parse_session_number(match_info: str | None) -> int | None:
    match = re.search(r"Match\s+(\d+)", match_info or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def load_event_year(cursor: sqlite3.Cursor, event_id: int) -> int | None:
    row = cursor.execute(
        """
        SELECT year, start_date
        FROM events
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()
    if not row:
        return None
    if row[0] is not None:
        try:
            return int(row[0])
        except Exception:
            pass
    start_date = row[1]
    if isinstance(start_date, str) and len(start_date) >= 4 and start_date[:4].isdigit():
        return int(start_date[:4])
    return None


def parse_scheduled_local_at(match_info: str | None, event_year: int | None) -> str | None:
    if not match_info or event_year is None:
        return None
    parts = [part.strip() for part in match_info.split("|", 1)]
    if len(parts) < 2 or not parts[1]:
        return None
    value = parts[1]
    for fmt in ("%Y %d %b, %H:%M", "%Y %d %B, %H:%M"):
        try:
            parsed = datetime.strptime(f"{event_year} {value}", fmt)
            return parsed.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None


def find_team_tie(
    cursor: sqlite3.Cursor,
    *,
    event_id: int,
    sub_event_type_code: str,
    group_code: str | None,
    team1: str,
    team2: str,
) -> sqlite3.Row | None:
    sql = """
        SELECT t.*
        FROM current_event_team_ties t
        JOIN current_event_team_tie_sides s1
          ON s1.current_team_tie_id = t.current_team_tie_id AND s1.side_no = 1
        JOIN current_event_team_tie_sides s2
          ON s2.current_team_tie_id = t.current_team_tie_id AND s2.side_no = 2
        WHERE t.event_id = ?
          AND t.sub_event_type_code = ?
          AND (? IS NULL OR t.group_code = ?)
          AND (
            (s1.team_code = ? AND s2.team_code = ?)
            OR (s1.team_code = ? AND s2.team_code = ?)
          )
        ORDER BY t.current_team_tie_id
        LIMIT 1
    """
    return cursor.execute(
        sql,
        (event_id, sub_event_type_code, group_code, group_code, team1, team2, team2, team1),
    ).fetchone()


def find_bracket_round(
    cursor: sqlite3.Cursor,
    *,
    event_id: int,
    sub_event_type_code: str,
    team1: str,
    team2: str,
) -> tuple[str | None, str | None]:
    row = cursor.execute(
        """
        SELECT stage_code, round_code
        FROM current_event_brackets
        WHERE event_id = ?
          AND sub_event_type_code = ?
          AND stage_code IS NOT NULL
          AND round_code IS NOT NULL
          AND (
            (side_a_team_code = ? AND side_b_team_code = ?)
            OR (side_a_team_code = ? AND side_b_team_code = ?)
          )
        ORDER BY
          CASE round_code
            WHEN 'R1' THEN 1
            WHEN 'R32' THEN 2
            WHEN 'R16' THEN 3
            WHEN 'QF' THEN 4
            WHEN 'SF' THEN 5
            WHEN 'F' THEN 6
            ELSE 99
          END,
          current_bracket_id
        LIMIT 1
        """,
        (event_id, sub_event_type_code, team1, team2, team2, team1),
    ).fetchone()
    if not row:
        return None, None
    return row["stage_code"], row["round_code"]


def ensure_team_tie(
    cursor: sqlite3.Cursor,
    *,
    event_id: int,
    sub_event_type_code: str,
    category: str,
    match_info: str | None,
    table_no: str | None,
    team1: str,
    team2: str,
    tie_score: str | None,
    forfeit_marker: str | None,
    forfeit_side: str | None,
    event_year: int | None,
) -> sqlite3.Row:
    group_code = parse_group_code(category)
    stage_code, round_code = normalize_round_from_category(category)
    bracket_stage_code, bracket_round_code = find_bracket_round(
        cursor,
        event_id=event_id,
        sub_event_type_code=sub_event_type_code,
        team1=team1,
        team2=team2,
    )
    stage_code = bracket_stage_code or stage_code
    round_code = bracket_round_code or round_code
    scheduled_local_at = parse_scheduled_local_at(match_info, event_year)
    existing = find_team_tie(
        cursor,
        event_id=event_id,
        sub_event_type_code=sub_event_type_code,
        group_code=group_code,
        team1=team1,
        team2=team2,
    )
    if existing:
        if stage_code or round_code or group_code:
            cursor.execute(
                """
                UPDATE current_event_team_ties
                SET stage_code = COALESCE(stage_code, ?),
                    round_code = COALESCE(round_code, ?),
                    group_code = COALESCE(group_code, ?),
                    scheduled_local_at = COALESCE(scheduled_local_at, ?),
                    updated_at = datetime('now')
                WHERE current_team_tie_id = ?
                """,
                (stage_code, round_code, group_code, scheduled_local_at, int(existing["current_team_tie_id"])),
            )
            return cursor.execute(
                "SELECT * FROM current_event_team_ties WHERE current_team_tie_id = ?",
                (int(existing["current_team_tie_id"]),),
            ).fetchone()
        return existing

    session_no = parse_session_number(match_info)
    synthetic_code = (
        f"COMP::{sub_event_type_code}::{group_code or round_code or 'UNK'}::"
        f"{session_no or 0}::{team1}-{team2}"
    )
    # New tie: team1 maps to side_no=1 (== side A), so team1_is_side_a=True.
    match_score, winner_side = build_score_a_perspective(
        tie_score, forfeit_marker, forfeit_side, team1_is_side_a=True
    )
    winner_team_code = team1 if winner_side == "A" else team2 if winner_side == "B" else None
    status = "walkover" if forfeit_marker == "WO" else "completed"
    cursor.execute(
        """
        INSERT INTO current_event_team_ties (
            event_id, sub_event_type_code, stage_label, stage_code, round_label, round_code, group_code,
            external_match_code, session_label, scheduled_local_at, scheduled_utc_at, table_no,
            status, source_status, source_schedule_status, match_score, winner_side, winner_team_code,
            last_synced_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 'Completed', NULL, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))
        """,
        (
            event_id,
            sub_event_type_code,
            category,
            stage_code,
            category,
            round_code,
            group_code,
            synthetic_code,
            match_info,
            scheduled_local_at,
            table_no,
            status,
            match_score,
            winner_side,
            winner_team_code,
        ),
    )
    current_team_tie_id = int(cursor.lastrowid)
    for side_no, team_code in ((1, team1), (2, team2)):
        cursor.execute(
            """
            INSERT INTO current_event_team_tie_sides (
                current_team_tie_id, side_no, team_code, team_name, seed, qualifier, is_winner
            ) VALUES (?, ?, ?, ?, NULL, NULL, ?)
            """,
            (
                current_team_tie_id,
                side_no,
                team_code,
                team_code,
                1 if winner_side == ("A" if side_no == 1 else "B") else 0,
            ),
        )
    return cursor.execute(
        "SELECT * FROM current_event_team_ties WHERE current_team_tie_id = ?",
        (current_team_tie_id,),
    ).fetchone()


def side_team_codes(cursor: sqlite3.Cursor, current_team_tie_id: int) -> tuple[str | None, str | None]:
    rows = cursor.execute(
        """
        SELECT side_no, team_code
        FROM current_event_team_tie_sides
        WHERE current_team_tie_id = ?
        ORDER BY side_no
        """,
        (current_team_tie_id,),
    ).fetchall()
    mapping = {int(row[0]): row[1] for row in rows}
    return mapping.get(1), mapping.get(2)


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
            (current_match_id, side_no, side["team_code"], 1 if side["is_winner"] else 0),
        )
        current_match_side_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO current_event_match_side_players (
                current_match_side_id, player_order, player_id, player_name, player_country
            ) VALUES (?, 1, NULL, ?, ?)
            """,
            (current_match_side_id, side["player_name"], side["player_country"]),
        )


def upsert_completed_rubber(
    cursor: sqlite3.Cursor,
    *,
    event_id: int,
    tie_row: sqlite3.Row,
    team1_is_side_a: bool,
    game: dict,
    game_order: int,
) -> None:
    external_match_code = f"{tie_row['external_match_code']}::R{game_order}"
    player_a_name = (game.get("player1") or "").strip() if team1_is_side_a else (game.get("player2") or "").strip()
    player_b_name = (game.get("player2") or "").strip() if team1_is_side_a else (game.get("player1") or "").strip()
    raw_game_score = (game.get("gameScore") or "").strip()
    game_forfeit_marker = (game.get("forfeit_marker") or "").strip() or None
    match_score, winner_side = build_score_a_perspective(
        raw_game_score, game_forfeit_marker, None, team1_is_side_a
    )
    set_scores = (game.get("setScores") or "").strip()
    if not team1_is_side_a and set_scores:
        flipped = []
        for part in [p.strip() for p in set_scores.split(",") if p.strip()]:
            parsed = parse_score_pair(part)
            flipped.append(f"{parsed[1]}-{parsed[0]}" if parsed else part)
        set_scores = ",".join(flipped)

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
        tie_row["table_no"],
        f"{tie_row['session_label']} / Rubber {game_order}",
        "completed",
        "Completed",
        tie_row["source_schedule_status"],
        match_score,
        json.dumps([part.strip() for part in set_scores.split(",") if part.strip()], ensure_ascii=False),
        winner_side,
        None,
        json.dumps(game, ensure_ascii=False),
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

    side_a_team_code, side_b_team_code = side_team_codes(cursor, int(tie_row["current_team_tie_id"]))
    side_a = {
        "team_code": side_a_team_code,
        "player_name": player_a_name,
        "player_country": side_a_team_code,
        "is_winner": winner_side == "A",
    }
    side_b = {
        "team_code": side_b_team_code,
        "player_name": player_b_name,
        "player_country": side_b_team_code,
        "is_winner": winner_side == "B",
    }
    replace_match_children(cursor, current_match_id, side_a, side_b)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import completed team ties and rubbers from completed_matches.json.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--live-event-data-root", type=Path, default=DEFAULT_LIVE_EVENT_DATA_DIR)
    args = parser.parse_args()

    event_dir = args.live_event_data_root.resolve() / str(args.event_id)
    path = completed_path(event_dir)
    if not path.exists():
        print(f"missing completed matches file: {path}", file=sys.stderr)
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    matches = payload.get("matches") or []

    conn = sqlite3.connect(str(args.db_path.resolve()))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        event_year = load_event_year(cursor, args.event_id)
        conn.execute("BEGIN")
        imported = 0
        unmatched = 0
        for match in matches:
            sub_event_type_code = parse_sub_event(match.get("category") or "")
            if not sub_event_type_code:
                continue
            team1 = (match.get("team1") or "").strip()
            team2 = (match.get("team2") or "").strip()
            raw_score = (match.get("score") or "").strip()
            forfeit_marker = (match.get("forfeit_marker") or "").strip() or None
            forfeit_side = (match.get("forfeit_side") or "").strip() or None
            tie_row = ensure_team_tie(
                cursor,
                event_id=args.event_id,
                sub_event_type_code=sub_event_type_code,
                category=match.get("category") or "",
                match_info=match.get("matchInfo"),
                table_no=match.get("table"),
                team1=team1,
                team2=team2,
                tie_score=raw_score,
                forfeit_marker=forfeit_marker,
                forfeit_side=forfeit_side,
                event_year=event_year,
            )
            if not tie_row:
                unmatched += 1
                continue
            side_a_team_code, side_b_team_code = side_team_codes(cursor, int(tie_row["current_team_tie_id"]))
            team1_is_side_a = side_a_team_code == team1 and side_b_team_code == team2
            match_score, winner_side = build_score_a_perspective(
                raw_score, forfeit_marker, forfeit_side, team1_is_side_a
            )
            if winner_side == "A":
                winner_team_code = side_a_team_code
            elif winner_side == "B":
                winner_team_code = side_b_team_code
            else:
                winner_team_code = None
            new_status = "walkover" if forfeit_marker == "WO" else "completed"
            cursor.execute(
                """
                UPDATE current_event_team_ties
                SET status = ?,
                    source_status = 'Completed',
                    table_no = COALESCE(?, table_no),
                    session_label = COALESCE(?, session_label),
                    match_score = ?,
                    winner_side = ?,
                    winner_team_code = ?,
                    last_synced_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE current_team_tie_id = ?
                """,
                (
                    new_status,
                    match.get("table"),
                    match.get("matchInfo"),
                    match_score,
                    winner_side,
                    winner_team_code,
                    int(tie_row["current_team_tie_id"]),
                ),
            )
            for side_no in (1, 2):
                is_winner = 1 if winner_side == ("A" if side_no == 1 else "B") else 0
                cursor.execute(
                    """
                    UPDATE current_event_team_tie_sides
                    SET is_winner = ?
                    WHERE current_team_tie_id = ? AND side_no = ?
                    """,
                    (is_winner, int(tie_row["current_team_tie_id"]), side_no),
                )
            for game_order, game in enumerate(match.get("games") or [], start=1):
                upsert_completed_rubber(
                    cursor,
                    event_id=args.event_id,
                    tie_row=tie_row,
                    team1_is_side_a=team1_is_side_a,
                    game=game,
                    game_order=game_order,
                )
                imported += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Imported completed team ties and {imported} completed rubbers for event {args.event_id}; unmatched ties: {unmatched}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
