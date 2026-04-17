#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入 sub_events（赛事子项目冠军）。

数据来源：
- matches 表中 stage='Main Draw' 且 round='Final' 的比赛记录

关键规则：
1. 单打：champion_player_ids 通常为单个 ID
2. 双打/团体：尽量从 raw_row_text 解析完整冠军成员，使用逗号分隔
3. 如果成员无法完全匹配到 players，仍写入 champion_name，并记录未匹配信息
"""

import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


def normalize_name_key(name: str) -> str:
    parts = sorted(name.lower().split())
    return " ".join(parts)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def parse_player_token(token: str) -> Optional[Tuple[str, str]]:
    match = PLAYER_TOKEN_RE.match(token.strip())
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def parse_players_from_raw(raw_row_text: str) -> List[Tuple[str, str]]:
    parts = [p.strip() for p in raw_row_text.split("|")]
    players: List[Tuple[str, str]] = []
    for part in parts:
        parsed = parse_player_token(part)
        if parsed:
            players.append(parsed)
    return players


def split_sides(players: List[Tuple[str, str]]) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    if len(players) == 2:
        return [players[0]], [players[1]]
    if len(players) >= 4 and len(players) % 2 == 0:
        half = len(players) // 2
        return players[:half], players[half:]
    return [], []


def build_player_index(cursor) -> Dict[Tuple[str, str], int]:
    cursor.execute("SELECT player_id, name, country_code FROM players")
    index: Dict[Tuple[str, str], int] = {}
    for player_id, name, country_code in cursor.fetchall():
        index[(name, country_code)] = player_id
        index[(normalize_name_key(name), country_code)] = player_id
    return index


def lookup_player_id(index: Dict[Tuple[str, str], int], name: str, country_code: Optional[str]) -> Optional[int]:
    if not name:
        return None
    cc = country_code or ""
    pid = index.get((name, cc))
    if pid is not None:
        return pid
    return index.get((normalize_name_key(name), cc))


def pick_winner_side(
    winner_name: str,
    winner_id: Optional[int],
    player_a_name: str,
    player_a_id: Optional[int],
    player_b_name: str,
    player_b_id: Optional[int],
    side_a: List[Tuple[str, str]],
    side_b: List[Tuple[str, str]],
) -> Optional[str]:
    normalized_winner = normalize_text(winner_name or "")

    if normalized_winner:
        a_hit = any(normalize_text(name) in normalized_winner for name, _ in side_a)
        b_hit = any(normalize_text(name) in normalized_winner for name, _ in side_b)
        if a_hit and not b_hit:
            return "A"
        if b_hit and not a_hit:
            return "B"

        if normalize_text(player_a_name) and normalize_text(player_a_name) in normalized_winner:
            return "A"
        if normalize_text(player_b_name) and normalize_text(player_b_name) in normalized_winner:
            return "B"

    if winner_id is not None:
        if player_a_id is not None and winner_id == player_a_id:
            return "A"
        if player_b_id is not None and winner_id == player_b_id:
            return "B"

    return None


def import_sub_events(db_path: str) -> dict:
    result = {
        "final_matches": 0,
        "sub_events_upserted": 0,
        "duplicate_finals": 0,
        "unresolved_winner_side": 0,
        "unmatched_champion_members": set(),
    }

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    player_index = build_player_index(cursor)

    cursor.execute(
        """
        SELECT
            match_id,
            event_id,
            sub_event_type_code,
            player_a_id,
            player_a_name,
            player_a_country,
            player_b_id,
            player_b_name,
            player_b_country,
            winner_id,
            winner_name,
            raw_row_text
        FROM matches
        WHERE stage = 'Main Draw'
          AND round = 'Final'
          AND event_id IS NOT NULL
        ORDER BY event_id, sub_event_type_code, match_id
        """
    )
    rows = cursor.fetchall()
    result["final_matches"] = len(rows)

    seen = set()
    for row in rows:
        (
            _match_id,
            event_id,
            sub_event_type_code,
            player_a_id,
            player_a_name,
            player_a_country,
            player_b_id,
            player_b_name,
            player_b_country,
            winner_id,
            winner_name,
            raw_row_text,
        ) = row

        key = (event_id, sub_event_type_code)
        if key in seen:
            result["duplicate_finals"] += 1
            continue
        seen.add(key)

        parsed_players = parse_players_from_raw(raw_row_text or "")
        side_a, side_b = split_sides(parsed_players)
        if not side_a or not side_b:
            side_a = [(player_a_name or "", player_a_country or "")]
            side_b = [(player_b_name or "", player_b_country or "")]

        winner_side = pick_winner_side(
            winner_name=winner_name or "",
            winner_id=winner_id,
            player_a_name=player_a_name or "",
            player_a_id=player_a_id,
            player_b_name=player_b_name or "",
            player_b_id=player_b_id,
            side_a=side_a,
            side_b=side_b,
        )

        if winner_side is None:
            result["unresolved_winner_side"] += 1
            continue

        winners = side_a if winner_side == "A" else side_b
        champion_names: List[str] = []
        # Keep positional alignment with champion_names:
        # unmatched members are represented as empty string.
        champion_ids: List[str] = []
        champion_countries: List[str] = []

        for name, country in winners:
            name = name.strip()
            country = (country or "").strip()
            if not name:
                continue

            champion_names.append(name)
            if country:
                champion_countries.append(country)

            pid = lookup_player_id(player_index, name, country)
            if pid is not None:
                champion_ids.append(str(pid))
            else:
                champion_ids.append("")
                result["unmatched_champion_members"].add(f"{name} ({country})")

        if not champion_names and winner_name:
            champion_names = [winner_name.strip()]
            champion_ids = [str(winner_id)] if winner_id is not None else [""]

        # Country code can be compacted safely for display.
        champion_countries = list(dict.fromkeys(champion_countries))

        cursor.execute(
            """
            INSERT INTO sub_events (
                event_id, sub_event_type_code, champion_player_ids, champion_name, champion_country_code
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(event_id, sub_event_type_code) DO UPDATE SET
                champion_player_ids = excluded.champion_player_ids,
                champion_name = excluded.champion_name,
                champion_country_code = excluded.champion_country_code
            """,
            (
                event_id,
                sub_event_type_code,
                ",".join(champion_ids) if champion_ids else None,
                ",".join(champion_names) if champion_names else None,
                ",".join(champion_countries) if champion_countries else None,
            ),
        )
        result["sub_events_upserted"] += 1

    conn.commit()
    conn.close()
    return result


def verify_sub_events(db_path: str):
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM sub_events")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sub_events WHERE champion_player_ids IS NOT NULL")
    with_ids = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT sub_event_type_code, COUNT(*)
        FROM sub_events
        GROUP BY sub_event_type_code
        ORDER BY COUNT(*) DESC, sub_event_type_code
        """
    )
    dist = cursor.fetchall()

    print("\nVerification:")
    print(f"  sub_events total: {total}")
    print(f"  with champion_player_ids: {with_ids} ({with_ids * 100 // max(total, 1)}%)")
    print("  by sub_event_type_code:")
    for code, cnt in dist[:12]:
        print(f"    {code:5s}: {cnt:5d}")

    conn.close()


if __name__ == "__main__":
    print("=" * 70)
    print("Import Sub Events")
    print("=" * 70)
    print(f"Database: {DB_PATH}")
    print("=" * 70 + "\n")

    if not Path(DB_PATH).exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    result = import_sub_events(str(DB_PATH))

    print("Results:")
    print(f"  Final matches scanned:        {result['final_matches']}")
    print(f"  sub_events upserted:          {result['sub_events_upserted']}")
    print(f"  duplicate finals skipped:     {result['duplicate_finals']}")
    print(f"  unresolved winner side:       {result['unresolved_winner_side']}")

    unmatched = sorted(result["unmatched_champion_members"])
    if unmatched:
        print(f"  unmatched champion members:   {len(unmatched)}")
        for item in unmatched[:20]:
            print(f"    - {item}")
        if len(unmatched) > 20:
            print(f"    ... and {len(unmatched) - 20} more")

    verify_sub_events(str(DB_PATH))
    sys.exit(0)
