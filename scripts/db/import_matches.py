#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入比赛数据：matches / match_sides / match_side_players
从 data/matches_complete/cn/*.json 导入。

关键逻辑：
1. side_a/side_b 作为完整参赛方（支持单双打/团体）。
2. 去重按完整 side 阵容，而不是“第一人”。
3. winner_side 以 A/B 记录，球员级信息落在 match_side_players。
"""

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
    DB_PATH = config.DB_PATH
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DB_PATH = PROJECT_ROOT / "scripts" / "db" / "ittf.db"


PLAYER_TOKEN_RE = re.compile(r"^(.+?)\s*\((\w+)\)$")


def normalize_event_name(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"\s+presented\s+by\s+.*$", "", s)
    s = re.sub(r"[,.]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_name_key(name: str) -> str:
    parts = sorted(name.lower().split())
    return " ".join(parts)


def parse_player_str(player_str: str):
    m = PLAYER_TOKEN_RE.match(player_str.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return player_str.strip(), None


def parse_raw_row_players(raw_text: str):
    parts = [p.strip() for p in raw_text.split("|")]
    players = []
    for part in parts:
        parsed = parse_player_str(part)
        if parsed[1]:
            players.append(parsed)
    return players


def parse_raw_row_sides(raw_text: str):
    players = parse_raw_row_players(raw_text)
    if len(players) == 2:
        return [players[0]], [players[1]]
    if len(players) >= 4 and len(players) % 2 == 0:
        half = len(players) // 2
        return players[:half], players[half:]
    return [], []


def parse_sides(match: dict, raw_row_text: str):
    side_a = [parse_player_str(item) for item in (match.get("side_a") or []) if isinstance(item, str) and item.strip()]
    side_b = [parse_player_str(item) for item in (match.get("side_b") or []) if isinstance(item, str) and item.strip()]

    if side_a and side_b:
        return side_a, side_b

    raw_a, raw_b = parse_raw_row_sides(raw_row_text)
    if not side_a:
        side_a = raw_a
    if not side_b:
        side_b = raw_b
    return side_a, side_b


def make_side_key(side: list[tuple[str, Optional[str]]]) -> str:
    keys = []
    for name, country in side:
        n = (name or "").strip().lower()
        c = (country or "").strip().lower()
        keys.append(f"{n}|{c}")
    keys.sort()
    return "||".join(keys)


def make_dedup_key(event_name: str, sub_event: str, stage: str, round_: str, side_a_key: str, side_b_key: str) -> str:
    pair = sorted([side_a_key, side_b_key])
    return f"{normalize_event_name(event_name)}|{sub_event}|{stage}|{round_}|{pair[0]}|{pair[1]}"


def build_event_index(cursor):
    cursor.execute("SELECT event_id, name, year FROM events")
    by_name_year = {}
    by_name = {}
    for event_id, name, year in cursor.fetchall():
        norm_name = normalize_event_name(name or "")
        if not norm_name:
            continue
        if year is not None:
            by_name_year[(norm_name, int(year))] = event_id
        by_name.setdefault(norm_name, set()).add(event_id)
    return {"by_name_year": by_name_year, "by_name": by_name}


def load_sub_event_codes(cursor):
    cursor.execute("SELECT code FROM sub_event_types")
    return {str(row[0]).strip().upper() for row in cursor.fetchall() if row and row[0]}


def load_filtering_only_event_ids(cursor):
    cursor.execute(
        """
        SELECT e.event_id
        FROM events e
        JOIN event_categories c ON c.id = e.event_category_id
        WHERE c.filtering_only = 1
        """
    )
    return {int(row[0]) for row in cursor.fetchall() if row and row[0] is not None}


def ensure_sub_event_code(cursor, known_codes: set[str], code: str, auto_added_codes: set[str]):
    normalized = (code or "").strip().upper()
    if not normalized:
        return ""
    if normalized in known_codes:
        return normalized

    cursor.execute(
        """
        INSERT OR IGNORE INTO sub_event_types (code, name, name_zh)
        VALUES (?, ?, ?)
        """,
        (normalized, normalized, normalized),
    )
    known_codes.add(normalized)
    auto_added_codes.add(normalized)
    return normalized


def resolve_event_id(event_index: dict, event_name: str, event_year: int | None):
    norm_event = normalize_event_name(event_name)
    if not norm_event:
        return None
    if event_year is not None:
        event_id = event_index["by_name_year"].get((norm_event, event_year))
        if event_id is not None:
            return event_id
    candidates = sorted(event_index["by_name"].get(norm_event, set()))
    if len(candidates) == 1:
        return candidates[0]
    return None


def resolve_player_id(player_index: dict, name: str, country: Optional[str]):
    if not name:
        return None
    cc = country or ""
    pid = player_index.get((name, cc))
    if pid is None:
        pid = player_index.get((normalize_name_key(name), cc))
    return pid


def infer_winner_side(match: dict, side_a: list[tuple[str, Optional[str]]], side_b: list[tuple[str, Optional[str]]]):
    winner_name = (match.get("winner") or "").strip().lower()

    if winner_name:
        hit_a = any(name.lower() in winner_name for name, _ in side_a if name)
        hit_b = any(name.lower() in winner_name for name, _ in side_b if name)
        if hit_a and not hit_b:
            return "A"
        if hit_b and not hit_a:
            return "B"

    perspective = (match.get("perspective") or "").strip().lower()
    result_for_player = (match.get("result_for_player") or "").strip().lower()
    if perspective in {"side_a", "side_b"} and result_for_player in {"win", "loss", "w", "l"}:
        did_win = result_for_player in {"win", "w"}
        if perspective == "side_a":
            return "A" if did_win else "B"
        return "B" if did_win else "A"

    return None


def import_matches(db_path: str, matches_dir: str) -> dict:
    result = {
        "full_refresh": True,
        "total_in_files": 0,
        "inserted": 0,
        "duplicates": 0,
        "skipped_no_event": 0,
        "skipped_no_side": 0,
        "skipped_filtering_only": 0,
        "unresolved_winner_side": 0,
        "unmatched_events": set(),
        "unmatched_players": set(),
        "auto_added_sub_event_codes": set(),
        "errors": [],
    }

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Full refresh mode: clear existing match data and reset AUTOINCREMENT.
    cursor.execute("DELETE FROM match_side_players")
    cursor.execute("DELETE FROM match_sides")
    cursor.execute("DELETE FROM matches")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('matches', 'match_sides', 'match_side_players')")

    cursor.execute("SELECT player_id, name, country_code FROM players")
    player_index = {}
    for player_id, name, country_code in cursor.fetchall():
        player_index[(name, country_code)] = player_id
        player_index[(normalize_name_key(name), country_code)] = player_id
    print(f"Player index: {len(player_index)} entries")

    event_index = build_event_index(cursor)
    print(f"Event index:  {len(event_index['by_name_year'])} name+year entries")
    known_sub_event_codes = load_sub_event_codes(cursor)
    print(f"Sub-event codes: {len(known_sub_event_codes)}")
    filtering_only_event_ids = load_filtering_only_event_ids(cursor)
    print(f"Filtering-only events: {len(filtering_only_event_ids)}")

    seen_keys = set()

    matches_path = Path(matches_dir)
    json_files = sorted(matches_path.glob("*.json"))
    print(f"Match files: {len(json_files)}\n")

    insert_match_sql = """
        INSERT INTO matches (
            event_id, event_name, event_name_zh, event_year,
            sub_event_type_code, stage, stage_zh, round, round_zh,
            side_a_key, side_b_key,
            match_score, games, winner_side, winner_name, raw_row_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    insert_side_sql = """
        INSERT INTO match_sides (
            match_id, side_no, side_key, is_winner
        ) VALUES (?, ?, ?, ?)
    """
    insert_side_player_sql = """
        INSERT INTO match_side_players (
            match_side_id, player_order, player_id, player_name, player_country
        ) VALUES (?, ?, ?, ?, ?)
    """

    for file_idx, json_file in enumerate(json_files, 1):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            result["errors"].append(f"Load {json_file.name}: {e}")
            continue

        file_count = 0
        file_inserted = 0

        for year_data in (data.get("years") or {}).values():
            for event in year_data.get("events", []):
                event_name = event.get("event_name", "")
                event_name_zh = event.get("event_name_zh")
                event_year = event.get("event_year")
                if event_year:
                    try:
                        event_year = int(event_year)
                    except (ValueError, TypeError):
                        event_year = None

                event_id = resolve_event_id(event_index, event_name, event_year)
                if event_id is None:
                    result["unmatched_events"].add(event_name)

                for match in event.get("matches", []):
                    result["total_in_files"] += 1
                    file_count += 1

                    sub_event = (match.get("sub_event") or "").strip()
                    if not sub_event:
                        raw_sub_event = (match.get("raw_row_text") or "").strip()
                        for token in [p.strip() for p in raw_sub_event.split("|")]:
                            normalized_token = token.upper()
                            if normalized_token in known_sub_event_codes:
                                sub_event = normalized_token
                                break
                    if not sub_event:
                        sub_event = "MAIN"
                    sub_event = ensure_sub_event_code(
                        cursor,
                        known_sub_event_codes,
                        sub_event,
                        result["auto_added_sub_event_codes"],
                    )

                    stage = (match.get("stage") or "").strip()
                    round_ = (match.get("round") or "").strip()
                    raw_row_text = (match.get("raw_row_text") or "").strip()

                    side_a, side_b = parse_sides(match, raw_row_text)
                    if not side_a or not side_b:
                        result["skipped_no_side"] += 1
                        continue

                    side_a_key = make_side_key(side_a)
                    side_b_key = make_side_key(side_b)
                    dedup_key = make_dedup_key(event_name, sub_event, stage, round_, side_a_key, side_b_key)
                    if dedup_key in seen_keys:
                        result["duplicates"] += 1
                        continue
                    seen_keys.add(dedup_key)

                    if event_id is None:
                        result["skipped_no_event"] += 1
                        continue
                    if event_id in filtering_only_event_ids:
                        result["skipped_filtering_only"] += 1
                        continue

                    winner_side = infer_winner_side(match, side_a, side_b)
                    if winner_side is None:
                        result["unresolved_winner_side"] += 1

                    games = match.get("games", [])
                    games_json = json.dumps(games, ensure_ascii=False) if games else None
                    winner_name = (match.get("winner") or "").strip()

                    cursor.execute(
                        insert_match_sql,
                        (
                            event_id,
                            event_name,
                            event_name_zh,
                            event_year,
                            sub_event,
                            stage,
                            match.get("stage_zh"),
                            round_,
                            match.get("round_zh"),
                            side_a_key,
                            side_b_key,
                            match.get("match_score", ""),
                            games_json,
                            winner_side,
                            winner_name,
                            raw_row_text,
                        ),
                    )
                    match_id = cursor.lastrowid

                    for side_no, side_key, side_players in (
                        (1, side_a_key, side_a),
                        (2, side_b_key, side_b),
                    ):
                        is_winner = 1 if winner_side == ("A" if side_no == 1 else "B") else 0
                        cursor.execute(insert_side_sql, (match_id, side_no, side_key, is_winner))
                        match_side_id = cursor.lastrowid

                        for player_order, (player_name, player_country) in enumerate(side_players, 1):
                            player_id = resolve_player_id(player_index, player_name, player_country)
                            if player_id is None and player_name and player_country:
                                result["unmatched_players"].add(f"{player_name} ({player_country})")
                            cursor.execute(
                                insert_side_player_sql,
                                (match_side_id, player_order, player_id, player_name, player_country),
                            )

                    file_inserted += 1
                    result["inserted"] += 1

        if file_idx % 20 == 0 or file_idx == len(json_files):
            print(
                f"  [{file_idx:3d}/{len(json_files)}] {json_file.name:35s} "
                f"{file_count:4d} matches, {file_inserted:4d} new"
            )

    conn.commit()
    conn.close()
    return result


def verify_matches(db_path: str):
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM matches")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM match_sides")
    total_sides = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM match_side_players")
    total_side_players = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM matches WHERE winner_side IS NOT NULL")
    with_winner_side = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM match_side_players WHERE player_id IS NOT NULL")
    with_player_id = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT event_id) FROM matches")
    unique_events = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT sub_event_type_code, COUNT(*) as cnt
        FROM matches GROUP BY sub_event_type_code ORDER BY cnt DESC
        """
    )
    sub_event_dist = cursor.fetchall()

    print("\nVerification:")
    print(f"  Total matches:         {total}")
    print(f"  Total sides:           {total_sides}")
    print(f"  Total side players:    {total_side_players}")
    print(f"  With winner_side:      {with_winner_side} ({with_winner_side*100//max(total,1)}%)")
    print(f"  side players w/ id:    {with_player_id} ({with_player_id*100//max(total_side_players,1)}%)")
    print(f"  Unique events:         {unique_events}")
    print("\n  Sub-event distribution:")
    for code, cnt in sub_event_dist:
        print(f"    {code:5s}: {cnt:6d}")

    conn.close()


if __name__ == "__main__":
    matches_dir = PROJECT_ROOT / "data" / "matches_complete" / "cn"

    print("=" * 70)
    print("Import Matches")
    print("=" * 70)
    print(f"Database:      {DB_PATH}")
    print(f"Matches dir:   {matches_dir}")
    print("=" * 70 + "\n")

    if not Path(DB_PATH).exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    result = import_matches(str(DB_PATH), str(matches_dir))

    print(f"\n{'='*70}")
    print("Results:")
    print(f"  Full refresh mode:       {result['full_refresh']}")
    print(f"  Total in files:          {result['total_in_files']}")
    print(f"  Unique (inserted):       {result['inserted']}")
    print(f"  Duplicates:              {result['duplicates']}")
    print(f"  Skipped (no event_id):   {result['skipped_no_event']}")
    print(f"  Skipped (no sides):      {result['skipped_no_side']}")
    print(f"  Skipped (filtering_only):{result['skipped_filtering_only']}")
    print(f"  Unresolved winner_side:  {result['unresolved_winner_side']}")

    if result["unmatched_events"]:
        events_list = sorted(result["unmatched_events"])
        print(f"\n  Unmatched events ({len(events_list)}):")
        for e in events_list[:15]:
            print(f"    - {e}")
        if len(events_list) > 15:
            print(f"    ... and {len(events_list)-15} more")

    if result["unmatched_players"]:
        players_list = sorted(result["unmatched_players"])
        print(f"\n  Unmatched players ({len(players_list)}):")
        for p in players_list[:20]:
            print(f"    - {p}")
        if len(players_list) > 20:
            print(f"    ... and {len(players_list)-20} more")

    if result["errors"]:
        print(f"\n  Errors ({len(result['errors'])}):")
        for e in result["errors"][:10]:
            print(f"    - {e}")

    if result["auto_added_sub_event_codes"]:
        auto_codes = sorted(result["auto_added_sub_event_codes"])
        print(f"\n  [WARNING] Auto-added sub_event_types ({len(auto_codes)}):")
        for code in auto_codes[:30]:
            print(f"    - {code}")
        if len(auto_codes) > 30:
            print(f"    ... and {len(auto_codes)-30} more")

    verify_matches(str(DB_PATH))
