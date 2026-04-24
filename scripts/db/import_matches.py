#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入比赛数据：matches / match_sides / match_side_players
从 data/event_matches/cn/*.json 导入。

关键逻辑：
1. event_matches 是赛事维度全量数据，优先使用根层 event_id 关联 events。
2. side_a/side_b 作为完整参赛方（支持单双打/团体）。
3. winner_side 以 A/B 记录，球员级信息落在 match_side_players。
4. 不按双方去重；团体/资格赛中同一双方可能多次交手。

导入前置条件：
- `event_id=2860`（ITTF Mixed Team World Cup Chengdu 2023）在源数据里被错误写成整届 `Qualification`
- 正式入库前应先执行 `python scripts/fix_special_event_2860_stage_round.py`
- 否则该赛事会以错误的 stage/round 写入 `matches`
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterator, Optional

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

# 赛事命名里的年份与实际举办年份不一致（如赛季总决赛在次年 1 月举办），
# 这些 event_id 的 raw_row_text 年份检查将被放行。
EVENT_ID_YEAR_MISMATCH_WHITELIST: set[int] = {
    2866,  # WTT Finals Men Doha 2023（实际于 2024 年 1 月举办）
}


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
    cursor.execute("SELECT event_id, name, name_zh, year FROM events")
    by_name_year = {}
    by_name = {}
    by_id = {}
    for event_id, name, name_zh, year in cursor.fetchall():
        by_id[int(event_id)] = {
            "event_id": int(event_id),
            "name": name or "",
            "name_zh": name_zh,
            "year": int(year) if year is not None else None,
        }
        norm_name = normalize_event_name(name or "")
        if not norm_name:
            continue
        if year is not None:
            by_name_year[(norm_name, int(year))] = event_id
        by_name.setdefault(norm_name, set()).add(event_id)
    return {"by_name_year": by_name_year, "by_name": by_name, "by_id": by_id}


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


def parse_raw_event_identity(raw_row_text: str) -> tuple[int | None, str | None]:
    parts = [part.strip() for part in (raw_row_text or "").split("|")]
    raw_year = None
    if parts:
        try:
            raw_year = int(parts[0])
        except (TypeError, ValueError):
            raw_year = None
    raw_event_name = parts[1] if len(parts) > 1 and parts[1] else None
    return raw_year, raw_event_name


def parse_event_id(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_event_matches_payload(data: dict) -> bool:
    return isinstance(data.get("matches"), list) and data.get("event_id") not in (None, "")


def iter_event_matches_payload(
    data: dict,
    json_file: Path,
    event_index: dict,
    result: dict,
) -> Iterator[tuple[dict, dict]]:
    event_id = parse_event_id(data.get("event_id"))
    event_name = (data.get("event") or data.get("event_name") or "").strip()
    event_row = event_index["by_id"].get(event_id) if event_id is not None else None

    if event_id is None:
        result["skipped_files"].append(f"{json_file.name}: missing/invalid event_id")
        return
    if event_row is None:
        result["skipped_files"].append(f"{json_file.name}: event_id={event_id} not found in events")
        result["unmatched_events"].add(event_name or str(event_id))
        return

    if event_name and normalize_event_name(event_name) != normalize_event_name(event_row["name"]):
        result["skipped_files"].append(
            f"{json_file.name}: payload event mismatch for event_id={event_id}: "
            f"payload={event_name!r}, db={event_row['name']!r}"
        )
        return

    event_ctx = {
        "event_id": event_id,
        "event_name": event_row["name"],
        "event_name_zh": event_row["name_zh"],
        "event_year": event_row["year"],
    }

    expected_event_name = normalize_event_name(event_row["name"])
    for row_index, match in enumerate(data.get("matches") or [], 1):
        result["source_rows"] += 1
        raw_year, raw_event_name = parse_raw_event_identity(match.get("raw_row_text") or "")
        if raw_event_name and normalize_event_name(raw_event_name) != expected_event_name:
            result["skipped_raw_event_mismatch"] += 1
            if len(result["raw_event_mismatch_examples"]) < 20:
                result["raw_event_mismatch_examples"].append(
                    f"{json_file.name}#{row_index}: raw={raw_event_name!r}, expected={event_row['name']!r}"
                )
            continue
        if (
            raw_year is not None
            and event_row["year"] is not None
            and raw_year != event_row["year"]
            and event_id not in EVENT_ID_YEAR_MISMATCH_WHITELIST
        ):
            result["skipped_raw_event_mismatch"] += 1
            if len(result["raw_event_mismatch_examples"]) < 20:
                result["raw_event_mismatch_examples"].append(
                    f"{json_file.name}#{row_index}: raw_year={raw_year}, expected_year={event_row['year']}"
                )
            continue
        yield event_ctx, match


def iter_player_matches_payload(data: dict, event_index: dict) -> Iterator[tuple[dict, dict]]:
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
            event_ctx = {
                "event_id": event_id,
                "event_name": event_name,
                "event_name_zh": event_name_zh,
                "event_year": event_year,
            }
            for match in event.get("matches", []):
                yield event_ctx, match


def ensure_matches_table_allows_repeated_keys(cursor):
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='matches'")
    row = cursor.fetchone()
    table_sql = row[0] if row else ""
    compact_sql = re.sub(r"\s+", " ", table_sql or "").lower()
    if "unique(event_id, sub_event_type_code, stage, round, side_a_key, side_b_key)" not in compact_sql:
        return False

    cursor.execute("DROP TABLE matches")
    cursor.execute(
        """
        CREATE TABLE matches (
            match_id            INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id            INTEGER NOT NULL,
            event_name          TEXT,
            event_name_zh       TEXT,
            event_year          INTEGER,
            sub_event_type_code TEXT NOT NULL,
            stage               TEXT,
            stage_zh            TEXT,
            round               TEXT,
            round_zh            TEXT,
            side_a_key          TEXT NOT NULL,
            side_b_key          TEXT NOT NULL,
            match_score         TEXT,
            games               TEXT,
            winner_side         TEXT,
            winner_name         TEXT NOT NULL,
            raw_row_text        TEXT NOT NULL,
            scraped_at          TEXT,
            FOREIGN KEY (event_id) REFERENCES events(event_id),
            FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
            CHECK (winner_side IN ('A', 'B') OR winner_side IS NULL)
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_event ON matches(event_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_sub_event ON matches(sub_event_type_code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_year ON matches(event_year)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_winner_side ON matches(winner_side)")
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_matches_event_round_sides
        ON matches(event_id, sub_event_type_code, stage, round, side_a_key, side_b_key)
        """
    )
    return True


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

    score_text = (match.get("match_score") or "").strip()
    score_match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", score_text)
    if score_match:
        side_a_score = int(score_match.group(1))
        side_b_score = int(score_match.group(2))
        if side_a_score > side_b_score:
            return "A"
        if side_b_score > side_a_score:
            return "B"

    return None


def import_matches(db_path: str, matches_dir: str) -> dict:
    result = {
        "full_refresh": True,
        "source_rows": 0,
        "total_in_files": 0,
        "inserted": 0,
        "repeated_match_keys": 0,
        "skipped_no_event": 0,
        "skipped_no_side": 0,
        "skipped_filtering_only": 0,
        "skipped_raw_event_mismatch": 0,
        "unresolved_winner_side": 0,
        "unmatched_events": set(),
        "unmatched_players": set(),
        "auto_added_sub_event_codes": set(),
        "skipped_files": [],
        "raw_event_mismatch_examples": [],
        "errors": [],
        "rebuilt_matches_table": False,
    }

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Full refresh mode: clear derived data and existing match data.
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event_draw_matches'")
    if cursor.fetchone():
        cursor.execute("DELETE FROM event_draw_matches")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sub_events'")
    if cursor.fetchone():
        cursor.execute("DELETE FROM sub_events")
    cursor.execute("DELETE FROM match_side_players")
    cursor.execute("DELETE FROM match_sides")
    cursor.execute("DELETE FROM matches")
    result["rebuilt_matches_table"] = ensure_matches_table_allows_repeated_keys(cursor)
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

        if is_event_matches_payload(data):
            records = iter_event_matches_payload(data, json_file, event_index, result)
        else:
            records = iter_player_matches_payload(data, event_index)

        for event_ctx, match in records:
            result["total_in_files"] += 1
            file_count += 1

            event_id = event_ctx["event_id"]
            event_name = event_ctx["event_name"]
            event_name_zh = event_ctx["event_name_zh"]
            event_year = event_ctx["event_year"]
            if event_id is None:
                result["unmatched_events"].add(event_name)

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
            dedup_key = make_dedup_key(str(event_id or event_name), sub_event, stage, round_, side_a_key, side_b_key)
            if dedup_key in seen_keys:
                result["repeated_match_keys"] += 1
            else:
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
    parser = argparse.ArgumentParser(description="Import matches from event_matches/cn into SQLite")
    parser.add_argument(
        "--source-dir",
        default=str(PROJECT_ROOT / "data" / "event_matches" / "cn"),
        help="Directory containing event_match.v1 JSON files",
    )
    cli_args = parser.parse_args()
    matches_dir = Path(cli_args.source_dir)

    print("=" * 70)
    print("Import Matches")
    print("=" * 70)
    print(f"Database:      {DB_PATH}")
    print(f"Source dir:    {matches_dir}")
    print("=" * 70 + "\n")

    if not Path(DB_PATH).exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    result = import_matches(str(DB_PATH), str(matches_dir))

    print(f"\n{'='*70}")
    print("Results:")
    print(f"  Full refresh mode:       {result['full_refresh']}")
    print(f"  Rebuilt matches table:   {result['rebuilt_matches_table']}")
    print(f"  Source rows scanned:     {result['source_rows']}")
    print(f"  Rows after validation:   {result['total_in_files']}")
    print(f"  Inserted:                {result['inserted']}")
    print(f"  Repeated match keys:     {result['repeated_match_keys']}")
    print(f"  Skipped (no event_id):   {result['skipped_no_event']}")
    print(f"  Skipped (no sides):      {result['skipped_no_side']}")
    print(f"  Skipped (filtering_only):{result['skipped_filtering_only']}")
    print(f"  Skipped raw mismatch:    {result['skipped_raw_event_mismatch']}")
    print(f"  Unresolved winner_side:  {result['unresolved_winner_side']}")

    if result["skipped_files"]:
        print(f"\n  Skipped files ({len(result['skipped_files'])}):")
        for item in result["skipped_files"][:20]:
            print(f"    - {item}")
        if len(result["skipped_files"]) > 20:
            print(f"    ... and {len(result['skipped_files']) - 20} more")

    if result["raw_event_mismatch_examples"]:
        print("\n  Raw event mismatch examples:")
        for item in result["raw_event_mismatch_examples"]:
            print(f"    - {item}")

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
