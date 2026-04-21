#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入 sub_events（赛事子项目冠军）。

数据来源：
- matches 表中 stage='Main Draw' 且 round='Final' 的比赛记录

关键规则：
1. 单打：champion_player_ids 通常为单个 ID
2. 团体赛：同一 (event_id, sub_event_type_code) 的 Final 可能包含多场子比赛，按胜场数判冠军
3. 如果冠军胜场数平局，报错退出（不做回退）
4. 如果成员无法完全匹配到 players，仍写入 champion_name，并记录未匹配信息
"""

import argparse
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


def normalize_name_key(name: str) -> str:
    parts = sorted(name.lower().split())
    return " ".join(parts)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


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
    winner_side: Optional[str],
    winner_name: str,
    side_a: List[Tuple[str, str]],
    side_b: List[Tuple[str, str]],
) -> Optional[str]:
    normalized_winner_side = (winner_side or "").strip().upper()
    if normalized_winner_side in {"A", "B"}:
        return normalized_winner_side

    normalized_winner = normalize_text(winner_name or "")

    if normalized_winner:
        a_hit = any(normalize_text(name) in normalized_winner for name, _ in side_a)
        b_hit = any(normalize_text(name) in normalized_winner for name, _ in side_b)
        if a_hit and not b_hit:
            return "A"
        if b_hit and not a_hit:
            return "B"

    return None


def make_team_key(side_players: List[Tuple[str, str]]) -> str:
    countries = sorted({(country or "").strip().upper() for _, country in side_players if (country or "").strip()})
    # Team finals usually have stable country identity but varying lineups across rubber matches.
    # Only use country aggregation for single-country teams; otherwise fall back to full roster.
    if len(countries) == 1:
        return f"C:{countries[0]}"

    members = sorted(
        {
            f"{normalize_text(name)}|{(country or '').strip().upper()}"
            for name, country in side_players
            if name.strip()
        }
    )
    return f"R:{'||'.join(members)}"


def resolve_champion_country_code(
    event_id: int,
    sub_event_type_code: str,
    champion_names: List[str],
    champion_countries: List[str],
) -> str:
    deduped = list(dict.fromkeys([c.strip().upper() for c in champion_countries if c.strip()]))
    if len(deduped) <= 1:
        return deduped[0] if deduped else ""
    if sub_event_type_code in {"WD", "XD", "CXD", "CGD", "JGD","JXD","U19WD","U19XD","U15WD","U15XD","U21WD","U21XD"}:
        # WD/XD may legitimately contain players from different countries.
        return ",".join(sorted(deduped))

    print("\n[CONFLICT] Champion country code conflict detected.")
    print(f"  event_id: {event_id}")
    print(f"  sub_event_type_code: {sub_event_type_code}")
    print(f"  champion members: {', '.join(champion_names) if champion_names else '(empty)'}")
    print(f"  detected country codes: {', '.join(deduped)}")
    print("  Please input final champion country code (e.g. CHN):")

    while True:
        user_input = input("  champion_country_code> ").strip().upper()
        if not user_input:
            print("  [ERROR] Empty input is not allowed. Please enter a country code.")
            continue
        return user_input


def _record_problem(result: dict, event_id: int, sub_event_type_code: str, issue_type: str, detail: str) -> None:
    result["problem_events"].append(
        {
            "event_id": event_id,
            "sub_event_type_code": sub_event_type_code,
            "issue_type": issue_type,
            "detail": detail,
        }
    )


def import_sub_events(db_path: str, dry_run: bool = False) -> dict:
    result = {
        "full_refresh": True,
        "dry_run": dry_run,
        "final_matches": 0,
        "sub_events_inserted": 0,
        "duplicate_finals": 0,
        "unresolved_winner_side": 0,
        "unmatched_champion_members": set(),
        "manual_country_overrides": 0,
        "multi_country_champions": 0,
        "problem_events": [],
    }

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    player_index = build_player_index(cursor)

    # Full refresh mode: clear previous sub_events and reset AUTOINCREMENT.
    if not dry_run:
        cursor.execute("DELETE FROM sub_events")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'sub_events'")

    cursor.execute(
        """
        SELECT
            m.match_id,
            m.event_id,
            m.sub_event_type_code,
            m.winner_side,
            m.winner_name,
            ms.side_no,
            msp.player_name,
            msp.player_country
        FROM matches m
        JOIN events e ON e.event_id = m.event_id
        JOIN event_categories ec ON ec.id = e.event_category_id
        JOIN match_sides ms ON ms.match_id = m.match_id
        LEFT JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
        WHERE m.stage = 'Main Draw'
          AND m.round = 'Final'
          AND m.event_id IS NOT NULL
          AND COALESCE(ec.points_eligible, 0) = 1
        ORDER BY m.event_id, m.sub_event_type_code, m.match_id, ms.side_no, msp.player_order
        """
    )
    rows = cursor.fetchall()
    match_map = {}
    for (
        match_id,
        event_id,
        sub_event_type_code,
        winner_side,
        winner_name,
        side_no,
        player_name,
        player_country,
    ) in rows:
        current = match_map.setdefault(
            match_id,
            {
                "event_id": event_id,
                "sub_event_type_code": sub_event_type_code,
                "winner_side": winner_side,
                "winner_name": winner_name,
                "side_a": [],
                "side_b": [],
            },
        )
        if player_name:
            if side_no == 1:
                current["side_a"].append((player_name, player_country or ""))
            elif side_no == 2:
                current["side_b"].append((player_name, player_country or ""))

    result["final_matches"] = len(match_map)

    grouped_finals: Dict[Tuple[int, str], List[dict]] = {}
    for match_data in match_map.values():
        key = (match_data["event_id"], match_data["sub_event_type_code"])
        grouped_finals.setdefault(key, []).append(match_data)

    for (event_id, sub_event_type_code), final_matches in grouped_finals.items():
        wins_by_team: Dict[str, int] = {}
        team_roster_by_key: Dict[str, List[Tuple[str, str]]] = {}
        wins_by_side = {"A": 0, "B": 0}
        side_rosters = {"A": [], "B": []}

        for match_data in final_matches:
            winner_side = pick_winner_side(
                winner_side=match_data["winner_side"],
                winner_name=match_data["winner_name"] or "",
                side_a=match_data["side_a"],
                side_b=match_data["side_b"],
            )
            if winner_side is None:
                result["unresolved_winner_side"] += 1
                _record_problem(
                    result,
                    event_id,
                    sub_event_type_code,
                    "unresolved_winner_side",
                    "cannot infer winner side from winner_side/winner_name and side rosters",
                )
                continue

            side_a = match_data["side_a"]
            side_b = match_data["side_b"]

            if sub_event_type_code in {"WT", "XT"}:
                wins_by_side[winner_side] += 1
                side_rosters["A"].extend(side_a)
                side_rosters["B"].extend(side_b)
                continue

            team_a_key = make_team_key(side_a)
            team_b_key = make_team_key(side_b)
            winner_team_key = team_a_key if winner_side == "A" else team_b_key

            wins_by_team[winner_team_key] = wins_by_team.get(winner_team_key, 0) + 1

            if team_a_key not in team_roster_by_key:
                team_roster_by_key[team_a_key] = []
            if team_b_key not in team_roster_by_key:
                team_roster_by_key[team_b_key] = []
            team_roster_by_key[team_a_key].extend(side_a)
            team_roster_by_key[team_b_key].extend(side_b)

        if sub_event_type_code in {"WT", "XT"}:
            side_a_wins = wins_by_side["A"]
            side_b_wins = wins_by_side["B"]
            if side_a_wins == 0 and side_b_wins == 0:
                continue
            if side_a_wins == side_b_wins:
                msg = (
                    f"Tie detected for team final champion: event_id={event_id}, "
                    f"sub_event_type_code={sub_event_type_code}, wins_by_side={wins_by_side}"
                )
                _record_problem(result, event_id, sub_event_type_code, "champion_tie", msg)
                if dry_run:
                    continue
                raise RuntimeError(msg)
            champion_side = "A" if side_a_wins > side_b_wins else "B"
            champion_roster = side_rosters[champion_side]
        else:
            if not wins_by_team:
                continue

            max_wins = max(wins_by_team.values())
            champion_team_keys = [team_key for team_key, wins in wins_by_team.items() if wins == max_wins]
            if len(champion_team_keys) != 1:
                msg = (
                    f"Tie detected for team final champion: event_id={event_id}, "
                    f"sub_event_type_code={sub_event_type_code}, wins={wins_by_team}"
                )
                _record_problem(result, event_id, sub_event_type_code, "champion_tie", msg)
                if dry_run:
                    continue
                raise RuntimeError(msg)

            champion_team_key = champion_team_keys[0]
            champion_roster = team_roster_by_key.get(champion_team_key, [])

        champion_members: List[Tuple[str, str]] = []
        seen_members = set()
        for name, country in champion_roster:
            cleaned_name = (name or "").strip()
            cleaned_country = (country or "").strip()
            if not cleaned_name:
                continue
            member_key = (normalize_text(cleaned_name), cleaned_country.upper())
            if member_key in seen_members:
                continue
            seen_members.add(member_key)
            champion_members.append((cleaned_name, cleaned_country))

        champion_names: List[str] = []
        champion_ids: List[str] = []
        champion_countries: List[str] = []

        for name, country in champion_members:
            champion_names.append(name)
            if country:
                champion_countries.append(country)

            pid = lookup_player_id(player_index, name, country)
            if pid is not None:
                champion_ids.append(str(pid))
            else:
                champion_ids.append("")
                result["unmatched_champion_members"].add(f"{name} ({country})")

        deduped_countries = list(dict.fromkeys([c.strip().upper() for c in champion_countries if c.strip()]))
        needs_manual_country = len(deduped_countries) > 1 and sub_event_type_code not in {
            "WD",
            "XD",
            "CXD",
            "CGD",
            "JGD",
            "JXD",
            "U19WD",
            "U19XD",
            "U15WD",
            "U15XD",
            "U21WD",
            "U21XD",
        }
        if len(deduped_countries) > 1:
            if sub_event_type_code in {"WD", "XD"}:
                result["multi_country_champions"] += 1
            else:
                result["manual_country_overrides"] += 1

        if needs_manual_country:
            detail = (
                f"champion members={','.join(champion_names) if champion_names else '(empty)'}; "
                f"country_codes={','.join(deduped_countries)}"
            )
            _record_problem(result, event_id, sub_event_type_code, "manual_country_override", detail)
            if dry_run:
                continue

        resolved_country = resolve_champion_country_code(
            event_id=event_id,
            sub_event_type_code=sub_event_type_code,
            champion_names=champion_names,
            champion_countries=champion_countries,
        )

        if not dry_run:
            cursor.execute(
                """
                INSERT INTO sub_events (
                    event_id, sub_event_type_code, champion_player_ids, champion_name, champion_country_code
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    sub_event_type_code,
                    ",".join(champion_ids) if champion_ids else None,
                    ",".join(champion_names) if champion_names else None,
                    resolved_country if resolved_country else None,
                ),
            )
            result["sub_events_inserted"] += 1

    if not dry_run:
        conn.commit()
    conn.close()
    return result


def print_problem_events(result: dict) -> None:
    problems = result.get("problem_events", [])
    if not problems:
        print("  problem events:              0")
        return

    print(f"  problem events:              {len(problems)}")
    issue_counts: Dict[str, int] = {}
    for item in problems:
        issue = item["issue_type"]
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    print("  problem summary:")
    for issue, cnt in sorted(issue_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"    {issue:24s} {cnt}")

    print("  problem details:")
    for item in problems:
        print(
            f"    - event_id={item['event_id']}, sub_event={item['sub_event_type_code']}, "
            f"issue={item['issue_type']}, detail={item['detail']}"
        )


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
    parser = argparse.ArgumentParser(description="Import sub_events from final matches")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, do not write sub_events")
    cli_args = parser.parse_args()

    print("=" * 70)
    print("Import Sub Events")
    print("=" * 70)
    print(f"Database: {DB_PATH}")
    print(f"Dry run:  {cli_args.dry_run}")
    print("=" * 70 + "\n")

    if not Path(DB_PATH).exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    result = import_sub_events(str(DB_PATH), dry_run=cli_args.dry_run)

    print("Results:")
    print(f"  Full refresh mode:            {result['full_refresh']}")
    print(f"  Dry run mode:                 {result['dry_run']}")
    print(f"  Final matches scanned:        {result['final_matches']}")
    print(f"  sub_events inserted:          {result['sub_events_inserted']}")
    print(f"  duplicate finals skipped:     {result['duplicate_finals']}")
    print(f"  unresolved winner side:       {result['unresolved_winner_side']}")
    print(f"  manual country overrides:     {result['manual_country_overrides']}")
    print(f"  multi-country champions:      {result['multi_country_champions']}")
    print_problem_events(result)

    unmatched = sorted(result["unmatched_champion_members"])
    if unmatched:
        print(f"  unmatched champion members:   {len(unmatched)}")
        for item in unmatched[:20]:
            print(f"    - {item}")
        if len(unmatched) > 20:
            print(f"    ... and {len(unmatched) - 20} more")

    if not cli_args.dry_run:
        verify_sub_events(str(DB_PATH))
    sys.exit(0)
