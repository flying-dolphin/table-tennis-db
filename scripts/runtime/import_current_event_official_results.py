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

import wtt_import_shared as shared
from import_current_event_completed import (
    DEFAULT_DB_PATH,
    DEFAULT_LIVE_EVENT_DATA_DIR,
    build_score_a_perspective,
    find_team_tie,
    normalize_round_from_category,
    parse_group_code,
    reset_tie_matches,
    side_team_codes,
    upsert_completed_rubber,
)

SUB_EVENT_TYPE_MAP = {
    "men's team": "MT",
    "women's team": "WT",
    "mixed team": "XT",
}
INDIVIDUAL_SUB_EVENT_TYPE_MAP = {
    "men's singles": "MS",
    "women's singles": "WS",
    "men's doubles": "MD",
    "women's doubles": "WD",
    "mixed doubles": "XD",
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
    if key in INDIVIDUAL_SUB_EVENT_TYPE_MAP:
        return INDIVIDUAL_SUB_EVENT_TYPE_MAP[key]

    raw = (category or "").strip().lower()
    if raw.startswith("men's teams"):
        return "MT"
    if raw.startswith("women's teams"):
        return "WT"
    if raw.startswith("mixed teams"):
        return "XT"
    for name, code in INDIVIDUAL_SUB_EVENT_TYPE_MAP.items():
        if raw.startswith(name):
            return code
    return None


def parse_category(description: str | None, fallback: str | None) -> str:
    raw = (description or "").strip() or (fallback or "").strip() or "Unknown"
    return re.sub(r"\s*-\s*Match\s+\d+(?:\s+M\d+)?\s*$", "", raw, flags=re.IGNORECASE)


def parse_match_number(description: str | None) -> int | None:
    match = re.search(r"\bMatch\s+(\d+)\b", description or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_match_info(match_number: int | None, start_local: str | None) -> str | None:
    if match_number is None:
        return None
    scheduled_local_at = parse_scheduled_local_at(start_local)
    label = shared.format_session_label(match_number, scheduled_local_at)
    if label:
        return label
    if not start_local:
        return f"Match {match_number}"
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            parsed = datetime.strptime(start_local.strip(), fmt)
            return f"Match {match_number} | {parsed.strftime('%d %b, %H:%M')}"
        except ValueError:
            continue
    return f"Match {match_number}"


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


def official_games(match_card: dict) -> str | None:
    for key in ("resultsGameScores", "gameScores"):
        value = match_card.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            return json.dumps(value, ensure_ascii=False)
    return None


def parse_table_name(match_card: dict) -> str | None:
    for key in ("tableName", "tableNumber"):
        value = match_card.get(key)
        if isinstance(value, str) and value.strip():
            return shared.normalize_table_label(value.strip())
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


def parse_individual_competitors(match_card: dict) -> list[dict]:
    competitors = match_card.get("competitiors") or []
    return [item for item in competitors[:2] if isinstance(item, dict)]


def competitor_display_name(competitor: dict) -> str | None:
    value = competitor.get("competitiorName") or competitor.get("competitorName")
    return value.strip() if isinstance(value, str) and value.strip() else None


def competitor_org(competitor: dict) -> str | None:
    value = competitor.get("competitiorOrg") or competitor.get("competitorOrg")
    return value.strip() if isinstance(value, str) and value.strip() else None


def competitor_players(competitor: dict) -> list[dict]:
    players = competitor.get("players") or []
    if isinstance(players, list) and players:
        return [player for player in players if isinstance(player, dict)]
    name = competitor_display_name(competitor)
    org = competitor_org(competitor)
    if not name:
        return []
    return [{"playerName": name, "playerOrgCode": org, "playerPosition": 1}]


def replace_individual_match_children(
    cursor: sqlite3.Cursor,
    current_match_id: int,
    competitors: list[dict],
    winner_side: str | None,
) -> tuple[int, int]:
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

    side_count = 0
    player_count = 0
    for side_no, competitor in enumerate(competitors[:2], start=1):
        cursor.execute(
            """
            INSERT INTO current_event_match_sides (
                current_match_id, side_no, team_code, seed, qualifier, placeholder_text, is_winner
            ) VALUES (?, ?, ?, NULL, NULL, NULL, ?)
            """,
            (
                current_match_id,
                side_no,
                competitor_org(competitor),
                1 if winner_side == ("A" if side_no == 1 else "B") else 0,
            ),
        )
        current_match_side_id = int(cursor.lastrowid)
        side_count += 1

        for player_order, player in enumerate(competitor_players(competitor), start=1):
            name = player.get("playerName") or competitor_display_name(competitor)
            if not name:
                continue
            cursor.execute(
                """
                INSERT INTO current_event_match_side_players (
                    current_match_side_id, player_order, player_id, player_name, player_country
                ) VALUES (?, ?, NULL, ?, ?)
                """,
                (
                    current_match_side_id,
                    player_order,
                    name,
                    player.get("playerOrgCode") or competitor_org(competitor),
                ),
            )
            player_count += 1

    return side_count, player_count


def winner_name_for_side(competitors: list[dict], winner_side: str | None) -> str | None:
    if winner_side not in {"A", "B"}:
        return None
    index = 0 if winner_side == "A" else 1
    if len(competitors) <= index:
        return None
    return competitor_display_name(competitors[index])


def upsert_official_individual_match(
    cursor: sqlite3.Cursor,
    *,
    event_id: int,
    item: dict,
    sub_event_type_code: str,
    category: str,
) -> tuple[bool, int, int]:
    match_card = item.get("match_card") if isinstance(item.get("match_card"), dict) else {}
    competitors = parse_individual_competitors(match_card)
    if len(competitors) < 2:
        return False, 0, 0

    external_match_code = shared.normalize_external_match_code(item.get("documentCode") or match_card.get("documentCode"))
    if not external_match_code:
        return False, 0, 0

    stage_code, round_code = normalize_round_from_category(category)
    group_code = parse_group_code(category)
    raw_score = official_match_score(match_card)
    match_score, winner_side = build_score_a_perspective(raw_score, None, None, True)
    start_local = ((match_card.get("matchDateTime") or {}).get("startDateLocal")) or item.get("startDateLocal")
    match_number = parse_match_number(match_card.get("subEventDescription"))
    scheduled_local_at = parse_scheduled_local_at(start_local)
    session_label = parse_match_info(match_number, start_local)
    raw_payload = json.dumps(item, ensure_ascii=False)

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
        sub_event_type_code,
        category,
        stage_code,
        category,
        round_code,
        group_code,
        external_match_code,
        scheduled_local_at,
        parse_table_name(match_card),
        session_label,
        "completed",
        "Official",
        match_score,
        official_games(match_card),
        winner_side,
        winner_name_for_side(competitors, winner_side),
        raw_payload,
    )

    if existing:
        current_match_id = int(existing["current_match_id"])
        cursor.execute(
            """
            UPDATE current_event_matches
            SET current_team_tie_id = NULL,
                sub_event_type_code = ?,
                stage_label = ?,
                stage_code = ?,
                round_label = ?,
                round_code = ?,
                group_code = ?,
                scheduled_local_at = COALESCE(?, scheduled_local_at),
                table_no = COALESCE(?, table_no),
                session_label = COALESCE(?, session_label),
                status = ?,
                source_status = ?,
                match_score = ?,
                games = ?,
                winner_side = ?,
                winner_name = ?,
                raw_source_payload = ?,
                last_synced_at = datetime('now'),
                updated_at = datetime('now')
            WHERE current_match_id = ?
            """,
            values[1:7] + values[8:] + (current_match_id,),
        )
    else:
        cursor.execute(
            """
            INSERT INTO current_event_matches (
                event_id, current_team_tie_id, sub_event_type_code, stage_label, stage_code, round_label,
                round_code, group_code, external_match_code, scheduled_local_at, scheduled_utc_at, table_no,
                session_label, status, source_status, source_schedule_status, match_score, games, winner_side,
                winner_name, raw_source_payload, last_synced_at, created_at, updated_at
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))
            """,
            values,
        )
        current_match_id = int(cursor.lastrowid)

    side_count, player_count = replace_individual_match_children(cursor, current_match_id, competitors, winner_side)
    return True, side_count, player_count


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
        external_match_code=external_match_code,
        stage_code=stage_code,
        round_code=round_code,
        group_code=group_code,
        team1=team1,
        team2=team2,
        scheduled_local_at=scheduled_local_at,
        match_info=match_info,
        table_no=table_no,
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
            last_synced_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'completed', 'Official', NULL, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))
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
    parser = argparse.ArgumentParser(description="Import completed matches/team ties from GetOfficialResult.json.")
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
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cursor = conn.cursor()
        conn.execute("BEGIN")
        imported_ties = 0
        imported_rubbers = 0
        imported_matches = 0

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

            if sub_event_type_code not in {"MT", "WT", "XT"}:
                ok, _side_count, _player_count = upsert_official_individual_match(
                    cursor,
                    event_id=args.event_id,
                    item=item,
                    sub_event_type_code=sub_event_type_code,
                    category=category,
                )
                if ok:
                    imported_matches += 1
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
            reset_tie_matches(cursor, int(tie_row["current_team_tie_id"]))
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
        f"Imported {imported_matches} official completed matches, "
        f"{imported_ties} official completed team ties and "
        f"{imported_rubbers} official completed rubbers for event {args.event_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
