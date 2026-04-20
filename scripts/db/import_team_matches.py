#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import team matches into matches/match_sides/match_side_players.

Source:
  data/team_matches/orig/*.json

Dedup/update key (as requested):
  event_id, stage, round, side_a_key, side_b_key

If existing row is found by this key, update it and print updated match_id.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import config

    PROJECT_ROOT = config.PROJECT_ROOT
    DB_PATH = Path(config.DB_PATH)
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"


PLAYER_TOKEN_RE = re.compile(r"^(.+?)\s*\((\w+)\)$")


def parse_player_str(player_str: str) -> tuple[str, Optional[str]]:
    m = PLAYER_TOKEN_RE.match((player_str or "").strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return (player_str or "").strip(), None


def normalize_name_key(name: str) -> str:
    parts = sorted((name or "").lower().split())
    return " ".join(parts)


def make_side_key(side: list[tuple[str, Optional[str]]]) -> str:
    tokens: list[str] = []
    for name, country in side:
        tokens.append(f"{(name or '').strip().lower()}|{(country or '').strip().lower()}")
    tokens.sort()
    return "||".join(tokens)


def parse_raw_row_players(raw_text: str) -> list[tuple[str, Optional[str]]]:
    parts = [p.strip() for p in (raw_text or "").split("|")]
    out: list[tuple[str, Optional[str]]] = []
    for part in parts:
        player = parse_player_str(part)
        if player[1]:
            out.append(player)
    return out


def parse_raw_row_sides(raw_text: str) -> tuple[list[tuple[str, Optional[str]]], list[tuple[str, Optional[str]]]]:
    players = parse_raw_row_players(raw_text)
    if len(players) == 2:
        return [players[0]], [players[1]]
    if len(players) >= 4 and len(players) % 2 == 0:
        half = len(players) // 2
        return players[:half], players[half:]
    return [], []


def parse_sides(match: dict) -> tuple[list[tuple[str, Optional[str]]], list[tuple[str, Optional[str]]]]:
    side_a = [parse_player_str(x) for x in (match.get("side_a") or []) if isinstance(x, str) and x.strip()]
    side_b = [parse_player_str(x) for x in (match.get("side_b") or []) if isinstance(x, str) and x.strip()]
    if side_a and side_b:
        return side_a, side_b
    raw_a, raw_b = parse_raw_row_sides(match.get("raw_row_text") or "")
    return (side_a or raw_a), (side_b or raw_b)


def resolve_player_id(player_index: dict, name: str, country: Optional[str]) -> int | None:
    if not name:
        return None
    cc = country or ""
    found = player_index.get((name, cc))
    if found is not None:
        return found
    return player_index.get((normalize_name_key(name), cc))


def infer_winner_side(match: dict, side_a: list[tuple[str, Optional[str]]], side_b: list[tuple[str, Optional[str]]]) -> str | None:
    winner_side = (match.get("winner_side") or "").strip().upper()
    if winner_side in {"A", "B"}:
        return winner_side

    winner_name = (match.get("winner_name") or "").strip().lower()
    if not winner_name:
        return None

    hit_a = any((name or "").lower() in winner_name for name, _ in side_a if name)
    hit_b = any((name or "").lower() in winner_name for name, _ in side_b if name)
    if hit_a and not hit_b:
        return "A"
    if hit_b and not hit_a:
        return "B"
    return None


def load_sub_event_codes(cursor: sqlite3.Cursor) -> set[str]:
    cursor.execute("SELECT code FROM sub_event_types")
    return {str(row[0]).strip().upper() for row in cursor.fetchall() if row and row[0]}


def ensure_sub_event_code(cursor: sqlite3.Cursor, known: set[str], code: str, auto_added: set[str]) -> str:
    normalized = (code or "").strip().upper()
    if not normalized:
        normalized = "MAIN"
    if normalized in known:
        return normalized
    cursor.execute(
        """
        INSERT OR IGNORE INTO sub_event_types (code, name, name_zh)
        VALUES (?, ?, ?)
        """,
        (normalized, normalized, normalized),
    )
    known.add(normalized)
    auto_added.add(normalized)
    return normalized


def import_team_matches(db_path: Path, source_dir: Path) -> dict:
    result = {
        "files": 0,
        "total_in_files": 0,
        "inserted": 0,
        "updated": 0,
        "skipped_no_event_id": 0,
        "skipped_no_side": 0,
        "skipped_no_key": 0,
        "unresolved_winner_side": 0,
        "unmatched_players": set(),
        "auto_added_sub_event_codes": set(),
        "errors": [],
        "updated_match_ids": [],
    }

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute("SELECT player_id, name, country_code FROM players")
    player_index: dict[tuple[str, str], int] = {}
    for player_id, name, country_code in cursor.fetchall():
        player_index[(name, country_code)] = player_id
        player_index[(normalize_name_key(name), country_code)] = player_id

    known_sub_event_codes = load_sub_event_codes(cursor)
    source_files = sorted(source_dir.glob("*.json"))
    result["files"] = len(source_files)

    insert_match_sql = """
        INSERT INTO matches (
            event_id, event_name, event_name_zh, event_year,
            sub_event_type_code, stage, stage_zh, round, round_zh,
            side_a_key, side_b_key, match_score, games, winner_side, winner_name, raw_row_text, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    update_match_sql = """
        UPDATE matches
        SET event_name = ?, event_year = ?, sub_event_type_code = ?, stage = ?, round = ?,
            side_a_key = ?, side_b_key = ?, match_score = ?, games = ?, winner_side = ?, winner_name = ?,
            raw_row_text = ?, scraped_at = ?
        WHERE match_id = ?
    """
    find_existing_sql = """
        SELECT match_id
        FROM matches
        WHERE event_id = ?
          AND IFNULL(stage, '') = IFNULL(?, '')
          AND IFNULL(round, '') = IFNULL(?, '')
          AND side_a_key = ?
          AND side_b_key = ?
        ORDER BY match_id DESC
    """
    insert_side_sql = """
        INSERT INTO match_sides (match_id, side_no, side_key, is_winner)
        VALUES (?, ?, ?, ?)
    """
    insert_side_player_sql = """
        INSERT INTO match_side_players (match_side_id, player_order, player_id, player_name, player_country)
        VALUES (?, ?, ?, ?, ?)
    """

    for idx, path in enumerate(source_files, start=1):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            result["errors"].append(f"Load {path.name}: {exc}")
            continue

        event_id = payload.get("event_id")
        if event_id in (None, ""):
            result["errors"].append(f"{path.name}: missing event_id")
            continue
        try:
            event_id = int(event_id)
        except Exception:
            result["errors"].append(f"{path.name}: invalid event_id={event_id}")
            continue

        event_name = (payload.get("event_name") or "").strip()
        event_year_raw = payload.get("event_year")
        try:
            event_year = int(event_year_raw) if event_year_raw not in (None, "") else None
        except Exception:
            event_year = None

        matches = payload.get("matches") or []
        for match in matches:
            result["total_in_files"] += 1
            side_a, side_b = parse_sides(match)
            if not side_a or not side_b:
                result["skipped_no_side"] += 1
                continue

            stage = (match.get("stage") or "").strip()
            round_ = (match.get("round") or "").strip()
            side_a_key = (match.get("side_a_key") or "").strip() or make_side_key(side_a)
            side_b_key = (match.get("side_b_key") or "").strip() or make_side_key(side_b)
            if not side_a_key or not side_b_key:
                result["skipped_no_key"] += 1
                continue

            sub_event = ensure_sub_event_code(
                cursor,
                known_sub_event_codes,
                (match.get("sub_event_type_code") or match.get("sub_event") or "MAIN"),
                result["auto_added_sub_event_codes"],
            )
            winner_side = infer_winner_side(match, side_a, side_b)
            if winner_side is None:
                result["unresolved_winner_side"] += 1

            games = match.get("games") or []
            games_json = json.dumps(games, ensure_ascii=False) if games else None
            winner_name = (match.get("winner_name") or match.get("winner") or "").strip()
            raw_row_text = (match.get("raw_row_text") or "").strip()
            scraped_at = (match.get("scraped_at") or payload.get("scraped_at") or "").strip() or None

            cursor.execute(find_existing_sql, (event_id, stage, round_, side_a_key, side_b_key))
            existing_ids = [int(row[0]) for row in cursor.fetchall()]

            if existing_ids:
                match_id = existing_ids[0]
                cursor.execute(
                    update_match_sql,
                    (
                        event_name,
                        event_year,
                        sub_event,
                        stage,
                        round_,
                        side_a_key,
                        side_b_key,
                        (match.get("match_score") or "").strip(),
                        games_json,
                        winner_side,
                        winner_name,
                        raw_row_text,
                        scraped_at,
                        match_id,
                    ),
                )
                cursor.execute("DELETE FROM match_sides WHERE match_id = ?", (match_id,))
                result["updated"] += 1
                result["updated_match_ids"].append(match_id)
                print(f"[UPDATE] match_id={match_id} event_id={event_id} stage={stage} round={round_}")
            else:
                cursor.execute(
                    insert_match_sql,
                    (
                        event_id,
                        event_name,
                        None,
                        event_year,
                        sub_event,
                        stage,
                        None,
                        round_,
                        None,
                        side_a_key,
                        side_b_key,
                        (match.get("match_score") or "").strip(),
                        games_json,
                        winner_side,
                        winner_name,
                        raw_row_text,
                        scraped_at,
                    ),
                )
                match_id = int(cursor.lastrowid)
                result["inserted"] += 1

            for side_no, side_key, side_players in (
                (1, side_a_key, side_a),
                (2, side_b_key, side_b),
            ):
                is_winner = 1 if winner_side == ("A" if side_no == 1 else "B") else 0
                cursor.execute(insert_side_sql, (match_id, side_no, side_key, is_winner))
                match_side_id = int(cursor.lastrowid)
                for player_order, (player_name, player_country) in enumerate(side_players, start=1):
                    player_id = resolve_player_id(player_index, player_name, player_country)
                    if player_id is None and player_name and player_country:
                        result["unmatched_players"].add(f"{player_name} ({player_country})")
                    cursor.execute(
                        insert_side_player_sql,
                        (match_side_id, player_order, player_id, player_name, player_country),
                    )

        if idx % 20 == 0 or idx == len(source_files):
            print(f"[{idx:3d}/{len(source_files)}] {path.name}")

    conn.commit()
    conn.close()
    return result


if __name__ == "__main__":
    source_dir = PROJECT_ROOT / "data" / "team_matches" / "orig"
    print("=" * 70)
    print("Import Team Matches")
    print("=" * 70)
    print(f"Database:      {DB_PATH}")
    print(f"Source dir:    {source_dir}")
    print("=" * 70)

    if not DB_PATH.exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)
    if not source_dir.exists():
        print(f"[ERROR] Source dir not found: {source_dir}")
        sys.exit(1)

    result = import_team_matches(DB_PATH, source_dir)

    print("\n" + "=" * 70)
    print("Results:")
    print(f"  Files:                    {result['files']}")
    print(f"  Total in files:           {result['total_in_files']}")
    print(f"  Inserted:                 {result['inserted']}")
    print(f"  Updated:                  {result['updated']}")
    print(f"  Skipped no side:          {result['skipped_no_side']}")
    print(f"  Skipped no key:           {result['skipped_no_key']}")
    print(f"  Unresolved winner_side:   {result['unresolved_winner_side']}")

    if result["updated_match_ids"]:
        print(f"\n  Updated match IDs ({len(result['updated_match_ids'])}):")
        for mid in result["updated_match_ids"]:
            print(f"    - {mid}")

    if result["unmatched_players"]:
        players = sorted(result["unmatched_players"])
        print(f"\n  Unmatched players ({len(players)}):")
        for p in players[:20]:
            print(f"    - {p}")
        if len(players) > 20:
            print(f"    ... and {len(players) - 20} more")

    if result["auto_added_sub_event_codes"]:
        codes = sorted(result["auto_added_sub_event_codes"])
        print(f"\n  Auto-added sub_event_types ({len(codes)}):")
        for code in codes:
            print(f"    - {code}")

    if result["errors"]:
        print(f"\n  Errors ({len(result['errors'])}):")
        for err in result["errors"][:20]:
            print(f"    - {err}")
