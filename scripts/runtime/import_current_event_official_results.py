#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import completed team ties and rubbers from GetOfficialResult.json."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from import_current_event_completed import (
    DEFAULT_DB_PATH,
    DEFAULT_LIVE_EVENT_DATA_DIR,
    build_score_a_perspective,
    find_team_tie,
    normalize_round_from_category,
    parse_group_code,
    side_team_codes,
    upsert_completed_rubber,
)

SUB_EVENT_TYPE_MAP = {
    "men's team": "MT",
    "women's team": "WT",
    "mixed team": "XT",
}


def official_results_path(event_dir: Path) -> Path:
    path = event_dir / "GetOfficialResult.json"
    if path.exists():
        return path
    return event_dir / "match_results" / "GetOfficialResult.json"


def parse_sub_event_type(value: str | None, category: str | None) -> str | None:
    key = (value or "").strip().lower()
    if key in SUB_EVENT_TYPE_MAP:
        return SUB_EVENT_TYPE_MAP[key]

    raw = (category or "").strip().lower()
    if raw.startswith("men's teams"):
        return "MT"
    if raw.startswith("women's teams"):
        return "WT"
    if raw.startswith("mixed teams"):
        return "XT"
    return None


def parse_category(description: str | None, fallback: str | None) -> str:
    raw = (description or "").strip() or (fallback or "").strip() or "Unknown"
    return re.sub(r"\s*-\s*Match\s+\d+(?:\s+M\d+)?\s*$", "", raw, flags=re.IGNORECASE)


def parse_match_number(description: str | None) -> int | None:
    match = re.search(r"\bMatch\s+(\d+)\b", description or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_match_info(match_number: int | None, start_local: str | None) -> str | None:
    if match_number is None or not start_local:
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            parsed = datetime.strptime(start_local.strip(), fmt)
            return f"Match {match_number} | {parsed.strftime('%d %b, %H:%M')}"
        except ValueError:
            continue
    return f"Match {match_number}"


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    rows = cursor.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def parse_scheduled_local_at(start_local: str | None) -> str | None:
    if not start_local:
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            parsed = datetime.strptime(start_local.strip(), fmt)
            return parsed.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None


def official_match_score(match_card: dict) -> str | None:
    team_parent = match_card.get("teamParentData") or {}
    extended_info = team_parent.get("extended_info") or {}
    final_result = extended_info.get("final_result") or []
    if final_result and isinstance(final_result[0], dict):
        value = (final_result[0].get("value") or "").strip()
        if value:
            return value

    for key in ("resultOverallScores", "overallScores"):
        value = match_card.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_table_name(match_card: dict) -> str | None:
    for key in ("tableName", "tableNumber"):
        value = match_card.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_team_codes(match_card: dict) -> tuple[str | None, str | None]:
    competitors = match_card.get("competitiors") or []
    teams: list[str | None] = []
    for competitor in competitors[:2]:
        if not isinstance(competitor, dict):
            teams.append(None)
            continue
        value = competitor.get("competitiorOrg")
        teams.append(value.strip() if isinstance(value, str) and value.strip() else None)
    while len(teams) < 2:
        teams.append(None)
    return teams[0], teams[1]


def parse_rubber(match_result: dict) -> dict | None:
    competitors = match_result.get("competitiors") or []
    if len(competitors) < 2:
        return None
    left = competitors[0] if isinstance(competitors[0], dict) else {}
    right = competitors[1] if isinstance(competitors[1], dict) else {}
    player1 = (left.get("competitiorName") or "").strip()
    player2 = (right.get("competitiorName") or "").strip()
    if not player1 or not player2:
        return None
    set_scores = (match_result.get("resultsGameScores") or match_result.get("gameScores") or "").strip()
    return {
        "player1": player1,
        "player2": player2,
        "gameScore": (official_match_score(match_result) or "").strip(),
        "setScores": set_scores,
        "forfeit_marker": "",
    }


def iter_rubbers(match_card: dict) -> list[dict]:
    matches = (((match_card.get("teamParentData") or {}).get("extended_info") or {}).get("matches")) or []
    rubbers: list[dict] = []
    for item in matches:
        if not isinstance(item, dict):
            continue
        match_result = item.get("match_result")
        if not isinstance(match_result, dict):
            continue
        rubber = parse_rubber(match_result)
        if rubber is not None:
            rubbers.append(rubber)
    return rubbers


def ensure_official_team_tie(
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
    external_match_code: str | None,
    scheduled_local_at: str | None,
) -> sqlite3.Row:
    group_code = parse_group_code(category)
    stage_code, round_code = normalize_round_from_category(category)
    existing = find_team_tie(
        cursor,
        event_id=event_id,
        sub_event_type_code=sub_event_type_code,
        group_code=group_code,
        team1=team1,
        team2=team2,
    )
    if existing:
        cursor.execute(
            """
            UPDATE current_event_team_ties
            SET stage_code = COALESCE(stage_code, ?),
                round_code = COALESCE(round_code, ?),
                group_code = COALESCE(group_code, ?),
                scheduled_local_at = COALESCE(scheduled_local_at, ?),
                external_match_code = COALESCE(external_match_code, ?),
                updated_at = datetime('now')
            WHERE current_team_tie_id = ?
            """,
            (
                stage_code,
                round_code,
                group_code,
                scheduled_local_at,
                external_match_code,
                int(existing["current_team_tie_id"]),
            ),
        )
        return cursor.execute(
            "SELECT * FROM current_event_team_ties WHERE current_team_tie_id = ?",
            (int(existing["current_team_tie_id"]),),
        ).fetchone()

    match_score, winner_side = build_score_a_perspective(tie_score, None, None, True)
    winner_team_code = team1 if winner_side == "A" else team2 if winner_side == "B" else None
    cursor.execute(
        """
        INSERT INTO current_event_team_ties (
            event_id, sub_event_type_code, stage_label, stage_code, round_label, round_code, group_code,
            external_match_code, session_label, scheduled_local_at, scheduled_utc_at, table_no,
            status, source_status, source_schedule_status, match_score, winner_side, winner_team_code,
            raw_source_payload, last_synced_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'completed', 'Official', NULL, ?, ?, ?, NULL, datetime('now'), datetime('now'), datetime('now'))
        """,
        (
            event_id,
            sub_event_type_code,
            category,
            stage_code,
            category,
            round_code,
            group_code,
            external_match_code,
            match_info,
            scheduled_local_at,
            table_no,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Import completed team ties and rubbers from GetOfficialResult.json.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--live-event-data-root", type=Path, default=DEFAULT_LIVE_EVENT_DATA_DIR)
    args = parser.parse_args()

    event_dir = args.live_event_data_root.resolve() / str(args.event_id)
    path = official_results_path(event_dir)
    if not path.exists():
        print(f"missing official results file: {path}", file=sys.stderr)
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        print(f"invalid official results payload: {path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(args.db_path.resolve()))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        conn.execute("BEGIN")
        tie_has_raw_source_payload = column_exists(cursor, "current_event_team_ties", "raw_source_payload")
        imported_ties = 0
        imported_rubbers = 0

        for item in payload:
            if not isinstance(item, dict):
                continue
            match_card = item.get("match_card")
            if not isinstance(match_card, dict):
                continue

            category = parse_category(match_card.get("subEventDescription"), match_card.get("subEventName"))
            sub_event_type_code = parse_sub_event_type(item.get("subEventType"), category)
            if not sub_event_type_code:
                continue

            team1, team2 = parse_team_codes(match_card)
            if not team1 or not team2:
                continue

            match_number = parse_match_number(match_card.get("subEventDescription"))
            start_local = ((match_card.get("matchDateTime") or {}).get("startDateLocal"))
            match_info = parse_match_info(match_number, start_local)
            raw_score = official_match_score(match_card)

            tie_row = ensure_official_team_tie(
                cursor,
                event_id=args.event_id,
                sub_event_type_code=sub_event_type_code,
                category=category,
                match_info=match_info,
                table_no=parse_table_name(match_card),
                team1=team1,
                team2=team2,
                tie_score=raw_score,
                external_match_code=(item.get("documentCode") or match_card.get("documentCode") or "").strip() or None,
                scheduled_local_at=parse_scheduled_local_at(start_local),
            )
            if not tie_row:
                continue

            side_a_team_code, side_b_team_code = side_team_codes(cursor, int(tie_row["current_team_tie_id"]))
            team1_is_side_a = side_a_team_code == team1 and side_b_team_code == team2
            match_score, winner_side = build_score_a_perspective(raw_score, None, None, team1_is_side_a)
            if winner_side == "A":
                winner_team_code = side_a_team_code
            elif winner_side == "B":
                winner_team_code = side_b_team_code
            else:
                winner_team_code = None

            if tie_has_raw_source_payload:
                cursor.execute(
                    """
                    UPDATE current_event_team_ties
                    SET status = 'completed',
                        source_status = 'Official',
                        table_no = COALESCE(?, table_no),
                        session_label = COALESCE(?, session_label),
                        match_score = ?,
                        winner_side = ?,
                        winner_team_code = ?,
                        raw_source_payload = ?,
                        last_synced_at = datetime('now'),
                        updated_at = datetime('now')
                    WHERE current_team_tie_id = ?
                    """,
                    (
                        parse_table_name(match_card),
                        match_info,
                        match_score,
                        winner_side,
                        winner_team_code,
                        json.dumps(item, ensure_ascii=False),
                        int(tie_row["current_team_tie_id"]),
                    ),
                )
            else:
                cursor.execute(
                    """
                    UPDATE current_event_team_ties
                    SET status = 'completed',
                        source_status = 'Official',
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
                        parse_table_name(match_card),
                        match_info,
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
            imported_ties += 1

            rubbers = iter_rubbers(match_card)
            for game_order, game in enumerate(rubbers, start=1):
                upsert_completed_rubber(
                    cursor,
                    event_id=args.event_id,
                    tie_row=tie_row,
                    team1_is_side_a=team1_is_side_a,
                    game=game,
                    game_order=game_order,
                )
                imported_rubbers += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(
        f"Imported {imported_ties} official completed team ties and "
        f"{imported_rubbers} official completed rubbers for event {args.event_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
