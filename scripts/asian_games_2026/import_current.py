#!/usr/bin/env python3
"""Import the normalized Asian Games snapshot into current_event_* tables."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from scripts.asian_games_2026.common import (
    DEFAULT_DB_PATH,
    EVENT_ID,
    NORMALIZED_ROOT,
    SOURCE_TIME_ZONE,
)
from scripts.asian_games_2026.player_resolution import player_resolver

STATUS_PRIORITY = {"cancelled": 10, "scheduled": 20, "live": 30, "completed": 40, "walkover": 40}


def merge_status(existing: str | None, incoming: str) -> str:
    return existing if STATUS_PRIORITY.get(existing or "", 0) > STATUS_PRIORITY.get(incoming, 0) else incoming


def _upsert_parent(conn: sqlite3.Connection, table: str, id_column: str, item: dict[str, Any], *, tie_id: int | None = None) -> int:
    existing = conn.execute(
        f"SELECT {id_column}, status FROM {table} WHERE event_id = ? AND external_match_code = ?",
        (EVENT_ID, item["external_match_code"]),
    ).fetchone()
    status = merge_status(existing["status"] if existing else None, item["status"])
    common = (
        item.get("sub_event_type_code"), item.get("stage_label"), item.get("stage_code"),
        item.get("round_label"), item.get("round_code"), item.get("group_code"),
        item.get("session_label"), item.get("scheduled_local_at"), item.get("scheduled_utc_at"),
        item.get("table_no"), status, item.get("source_status"), item.get("source_status"),
        item.get("match_score"), item.get("winner_side"),
    )
    if table == "current_event_team_ties":
        if existing:
            conn.execute(
                f"""UPDATE {table} SET sub_event_type_code=?, stage_label=?, stage_code=?, round_label=?,
                    round_code=?, group_code=?, session_label=?, scheduled_local_at=?, scheduled_utc_at=?,
                    table_no=?, status=?, source_status=?, source_schedule_status=?, match_score=?, winner_side=?,
                    winner_team_code=?, last_synced_at=datetime('now'), updated_at=datetime('now')
                    WHERE {id_column}=?""",
                (*common, item.get("winner_team_code"), existing[id_column]),
            )
            return int(existing[id_column])
        cursor = conn.execute(
            f"""INSERT INTO {table} (event_id, sub_event_type_code, stage_label, stage_code, round_label,
                round_code, group_code, external_match_code, session_label, scheduled_local_at, scheduled_utc_at,
                table_no, status, source_status, source_schedule_status, match_score, winner_side, winner_team_code,
                last_synced_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
            (EVENT_ID, *common[:6], item["external_match_code"], *common[6:], item.get("winner_team_code")),
        )
    else:
        raw_payload = json.dumps(item.get("raw_source_payload"), ensure_ascii=False)
        games = json.dumps(item.get("games") or [], ensure_ascii=False)
        if existing:
            conn.execute(
                f"""UPDATE {table} SET current_team_tie_id=?, sub_event_type_code=?, stage_label=?, stage_code=?,
                    round_label=?, round_code=?, group_code=?, session_label=?, scheduled_local_at=?, scheduled_utc_at=?,
                    table_no=?, status=?, source_status=?, source_schedule_status=?, match_score=?, games=?,
                    winner_side=?, winner_name=?, raw_source_payload=?, last_synced_at=datetime('now'), updated_at=datetime('now')
                    WHERE {id_column}=?""",
                (tie_id, *common[:14], games, common[14], item.get("winner_name"), raw_payload, existing[id_column]),
            )
            return int(existing[id_column])
        cursor = conn.execute(
            f"""INSERT INTO {table} (event_id, current_team_tie_id, sub_event_type_code, stage_label, stage_code,
                round_label, round_code, group_code, external_match_code, session_label, scheduled_local_at,
                scheduled_utc_at, table_no, status, source_status, source_schedule_status, match_score, games,
                winner_side, winner_name, raw_source_payload, last_synced_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
            (EVENT_ID, tie_id, *common[:6], item["external_match_code"], *common[6:14], games, common[14], item.get("winner_name"), raw_payload),
        )
    return int(cursor.lastrowid)


def _replace_tie_sides(
    conn: sqlite3.Connection,
    tie_id: int,
    sides: list[dict[str, Any]],
    resolve,
    sub_event_type_code: str | None,
) -> None:
    if not sides:
        return
    conn.execute("DELETE FROM current_event_team_tie_sides WHERE current_team_tie_id=?", (tie_id,))
    for side in sides:
        cursor = conn.execute(
            """INSERT INTO current_event_team_tie_sides
               (current_team_tie_id, side_no, team_code, team_name, is_winner) VALUES (?,?,?,?,?)""",
            (tie_id, side["side_no"], side.get("team_code"), side.get("team_name"), int(bool(side.get("is_winner")))),
        )
        for order, player in enumerate(side.get("nominated_players") or [], start=1):
            conn.execute(
                """INSERT INTO current_event_team_tie_side_players
                   (current_team_tie_side_id, player_order, player_id, player_name, player_country)
                   VALUES (?,?,?,?,?)""",
                (cursor.lastrowid, player.get("order") or order, resolve(player.get("country"), player.get("name"), sub_event_type_code),
                 player.get("name"), player.get("country")),
            )


def _replace_match_sides(
    conn: sqlite3.Connection,
    match_id: int,
    sides: list[dict[str, Any]],
    resolve,
    sub_event_type_code: str | None,
) -> None:
    if not sides:
        return
    conn.execute("DELETE FROM current_event_match_sides WHERE current_match_id=?", (match_id,))
    for side in sides:
        cursor = conn.execute(
            """INSERT INTO current_event_match_sides
               (current_match_id, side_no, team_code, is_winner) VALUES (?,?,?,?)""",
            (match_id, side["side_no"], side.get("team_code"), int(bool(side.get("is_winner")))),
        )
        for order, player in enumerate(side.get("players") or [], start=1):
            conn.execute(
                """INSERT INTO current_event_match_side_players
                   (current_match_side_id, player_order, player_id, player_name, player_country)
                   VALUES (?,?,?,?,?)""",
                (cursor.lastrowid, player.get("order") or order, resolve(player.get("country"), player.get("name"), sub_event_type_code),
                 player.get("name"), player.get("country")),
            )


def collect_unresolved_players(conn: sqlite3.Connection, event_id: int = EVENT_ID) -> list[str]:
    rows = conn.execute(
        """
        WITH observations AS (
            SELECT p.player_name, p.player_country, p.player_id
            FROM current_event_team_tie_side_players p
            JOIN current_event_team_tie_sides s ON s.current_team_tie_side_id = p.current_team_tie_side_id
            JOIN current_event_team_ties t ON t.current_team_tie_id = s.current_team_tie_id
            WHERE t.event_id = ?
            UNION ALL
            SELECT p.player_name, p.player_country, p.player_id
            FROM current_event_match_side_players p
            JOIN current_event_match_sides s ON s.current_match_side_id = p.current_match_side_id
            JOIN current_event_matches m ON m.current_match_id = s.current_match_id
            WHERE m.event_id = ?
        )
        SELECT player_country, player_name, COUNT(*) AS occurrences
        FROM observations
        WHERE player_id IS NULL
        GROUP BY player_country, player_name
        ORDER BY player_country, player_name
        """,
        (event_id, event_id),
    ).fetchall()
    return [
        f"{row[0] or '?'}:{row[1]} ({row[2]})"
        for row in rows
        if row[1]
    ]


def collect_missing_player_translations(conn: sqlite3.Connection, event_id: int = EVENT_ID) -> list[str]:
    rows = conn.execute(
        """
        WITH observations AS (
            SELECT p.player_name, p.player_country, p.player_id
            FROM current_event_team_tie_side_players p
            JOIN current_event_team_tie_sides s ON s.current_team_tie_side_id = p.current_team_tie_side_id
            JOIN current_event_team_ties t ON t.current_team_tie_id = s.current_team_tie_id
            WHERE t.event_id = ?
            UNION ALL
            SELECT p.player_name, p.player_country, p.player_id
            FROM current_event_match_side_players p
            JOIN current_event_match_sides s ON s.current_match_side_id = p.current_match_side_id
            JOIN current_event_matches m ON m.current_match_id = s.current_match_id
            WHERE m.event_id = ?
        )
        SELECT o.player_country, o.player_name, COUNT(*) AS occurrences
        FROM observations o
        JOIN players pl ON pl.player_id = o.player_id
        WHERE o.player_id IS NOT NULL
          AND NULLIF(TRIM(pl.name_zh), '') IS NULL
        GROUP BY o.player_country, o.player_name, o.player_id
        ORDER BY o.player_country, o.player_name
        """,
        (event_id, event_id),
    ).fetchall()
    return [
        f"{row[0] or '?'}:{row[1]} ({row[2]})"
        for row in rows
        if row[1]
    ]


def _replace_brackets(conn: sqlite3.Connection, snapshot: dict[str, Any]) -> int:
    if snapshot.get("event_id") not in (None, EVENT_ID):
        raise ValueError(f"bracket snapshot event_id must be {EVENT_ID}")
    sub_events = [str(code) for code in snapshot.get("sub_events") or []]
    rows = [row for row in snapshot.get("brackets") or [] if isinstance(row, dict)]
    if not sub_events:
        if rows:
            raise ValueError("bracket snapshot with rows must declare sub_events")
        return 0
    invalid_codes = sorted({str(row.get("sub_event_type_code") or "") for row in rows} - set(sub_events))
    if invalid_codes:
        raise ValueError(f"bracket rows outside declared sub_events: {', '.join(invalid_codes)}")
    placeholders = ",".join("?" for _ in sub_events)
    conn.execute(
        f"DELETE FROM current_event_brackets WHERE event_id=? AND sub_event_type_code IN ({placeholders})",
        (EVENT_ID, *sub_events),
    )
    collected_at = snapshot.get("scraped_at")
    conn.executemany(
        """INSERT INTO current_event_brackets (
               event_id, sub_event_type_code, draw_code, bracket_code, stage_code, round_code,
               round_order, bracket_position, external_unit_code, scheduled_date, scheduled_time,
               match_score, winner_side, status, side_a_previous_unit, side_b_previous_unit,
               side_a_team_code, side_b_team_code, side_a_placeholder, side_b_placeholder,
               raw_source_payload, last_synced_at, created_at, updated_at
           ) VALUES (
               :event_id, :sub_event_type_code, :draw_code, :bracket_code, :stage_code, :round_code,
               :round_order, :bracket_position, :external_unit_code, :scheduled_date, :scheduled_time,
               :match_score, :winner_side, :status, :side_a_previous_unit, :side_b_previous_unit,
               :side_a_team_code, :side_b_team_code, :side_a_placeholder, :side_b_placeholder,
               :raw_source_payload, COALESCE(:last_synced_at, datetime('now')), datetime('now'), datetime('now')
           )""",
        [
            {
                **row,
                "event_id": EVENT_ID,
                "raw_source_payload": json.dumps(row.get("raw_source_payload"), ensure_ascii=False),
                "last_synced_at": collected_at,
            }
            for row in rows
        ],
    )
    return len(rows)


def import_snapshot(
    conn: sqlite3.Connection,
    snapshot: dict[str, Any],
    bracket_snapshot: dict[str, Any] | None = None,
) -> dict[str, int]:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if conn.execute("SELECT 1 FROM events WHERE event_id=?", (EVENT_ID,)).fetchone() is None:
        raise ValueError(f"events table has no event_id={EVENT_ID}")
    resolve = player_resolver(conn)
    counts = {"team_ties": 0, "matches": 0, "brackets": 0, "roster_players": 0, "match_players": 0}
    conn.execute("BEGIN")
    try:
        conn.execute(
            """UPDATE events SET time_zone=?, lifecycle_status=CASE WHEN lifecycle_status='completed'
               THEN lifecycle_status ELSE 'in_progress' END, last_synced_at=datetime('now') WHERE event_id=?""",
            (SOURCE_TIME_ZONE, EVENT_ID),
        )
        for tie in snapshot.get("team_ties") or []:
            tie_id = _upsert_parent(conn, "current_event_team_ties", "current_team_tie_id", tie)
            _replace_tie_sides(
                conn,
                tie_id,
                tie.get("sides") or [],
                resolve,
                tie.get("sub_event_type_code"),
            )
            counts["team_ties"] += 1
            counts["roster_players"] += sum(len(s.get("nominated_players") or []) for s in tie.get("sides") or [])
            for match in tie.get("rubbers") or []:
                match_id = _upsert_parent(conn, "current_event_matches", "current_match_id", match, tie_id=tie_id)
                _replace_match_sides(
                    conn,
                    match_id,
                    match.get("sides") or [],
                    resolve,
                    match.get("sub_event_type_code"),
                )
                counts["matches"] += 1
                counts["match_players"] += sum(len(s.get("players") or []) for s in match.get("sides") or [])
        for match in snapshot.get("matches") or []:
            match_id = _upsert_parent(conn, "current_event_matches", "current_match_id", match)
            _replace_match_sides(
                conn,
                match_id,
                match.get("sides") or [],
                resolve,
                match.get("sub_event_type_code"),
            )
            counts["matches"] += 1
            counts["match_players"] += sum(len(s.get("players") or []) for s in match.get("sides") or [])
        if bracket_snapshot is not None:
            counts["brackets"] = _replace_brackets(conn, bracket_snapshot)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 2026 亚运会当前比赛数据")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--input", type=Path, default=NORMALIZED_ROOT / "current_matches.json")
    parser.add_argument("--brackets-input", type=Path, default=NORMALIZED_ROOT / "current_brackets.json")
    args = parser.parse_args()
    unresolved_players: list[str] = []
    missing_player_translations: list[str] = []
    try:
        snapshot = json.loads(args.input.read_text(encoding="utf-8"))
        bracket_snapshot = json.loads(args.brackets_input.read_text(encoding="utf-8"))
        conn = sqlite3.connect(args.db_path)
        try:
            counts = import_snapshot(conn, snapshot, bracket_snapshot)
            unresolved_players = collect_unresolved_players(conn)
            missing_player_translations = collect_missing_player_translations(conn)
        finally:
            conn.close()
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"当前赛事导入失败：{exc}", file=sys.stderr)
        return 1
    print("导入完成：" + ", ".join(f"{key}={value}" for key, value in counts.items()))
    if unresolved_players:
        print("未匹配运动员：" + "、".join(unresolved_players), file=sys.stderr)
    if missing_player_translations:
        print("已匹配但缺少中文名：" + "、".join(missing_player_translations), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
