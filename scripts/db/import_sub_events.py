#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入 sub_events（赛事子项目冠军）。

数据来源：
- event_draw_matches 表中 draw_stage='Main Draw' 且 draw_round='Final' 的比赛记录

关键规则：
1. 单打：champion_player_ids 通常为单个 ID
2. 团体赛：同一 (event_id, sub_event_type_code) 的 Final 可能包含多场子比赛，按胜场数判冠军
3. 如果冠军胜场数平局，报错退出（不做回退）
4. 如果成员无法完全匹配到 players，仍写入 champion_name，并记录未匹配信息
"""

import argparse
import json
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


MULTI_COUNTRY_SUB_EVENTS = {
    "MD",
    "WD",
    "XD",
    "CMD",
    "CWD",
    "CXD",
    "JBD",
    "JGD",
    "JXD",
    "U19MD",
    "U19WD",
    "U19XD",
    "U15MD",
    "U15WD",
    "U15XD",
    "U21MD",
    "U21WD",
    "U21XD",
}


def is_team_sub_event(sub_event_type_code: str) -> bool:
    code = (sub_event_type_code or "").strip().upper()
    return code in {"MT", "WT", "XT"} or code.endswith("MT") or code.endswith("WT")


def load_manual_event_overrides() -> Dict[Tuple[int, str], str]:
    overrides_dir = PROJECT_ROOT / "web" / "data" / "manual_event_overrides"
    if not overrides_dir.exists():
        return {}

    champion_teams: Dict[Tuple[int, str], str] = {}
    for file_path in overrides_dir.glob("*.json"):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        event_id = payload.get("event_id")
        sub_event_type_code = str(payload.get("sub_event_type_code") or "").strip().upper()
        presentation_mode = str(payload.get("presentation_mode") or "").strip()
        champion_team = str((payload.get("podium") or {}).get("champion") or "").strip().upper()

        if (
            not isinstance(event_id, int)
            or not sub_event_type_code
            or presentation_mode not in {"staged_round_robin", "team_knockout_with_bronze"}
            or not champion_team
        ):
            continue

        champion_teams[(event_id, sub_event_type_code)] = champion_team

    return champion_teams


def parse_match_score(score: str) -> Optional[Tuple[int, int]]:
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", score or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def is_drawn_or_unplayed_score(score: str) -> bool:
    parsed = parse_match_score(score)
    return parsed is not None and parsed[0] == parsed[1]


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


def make_roster_key(side_players: List[Tuple[str, str]]) -> str:
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
    if sub_event_type_code in MULTI_COUNTRY_SUB_EVENTS:
        # Doubles may legitimately contain players from different countries.
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


def team_pair_key(team_a_key: str, team_b_key: str) -> Tuple[str, str]:
    return tuple(sorted((team_a_key, team_b_key)))


def countries_from_team_key(team_key: str) -> set[str]:
    if team_key.startswith("C:"):
        return {team_key[2:]}
    countries = set()
    for member in team_key.removeprefix("R:").split("||"):
        parts = member.rsplit("|", 1)
        if len(parts) == 2 and parts[1]:
            countries.add(parts[1])
    return countries


def majority_country(side_players: List[Tuple[str, str]]) -> Optional[str]:
    counts: Dict[str, int] = {}
    for _name, country in side_players:
        cc = (country or "").strip().upper()
        if not cc:
            continue
        counts[cc] = counts.get(cc, 0) + 1
    if not counts:
        return None
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ordered[0][0]


def group_final_team_ties(final_matches: List[dict]) -> List[List[dict]]:
    groups: List[List[dict]] = []
    current: List[dict] = []
    current_countries: set[str] = set()

    for match_data in sorted(final_matches, key=lambda item: int(item["match_id"])):
        team_a_key = make_team_key(match_data["side_a"])
        team_b_key = make_team_key(match_data["side_b"])
        match_countries = countries_from_team_key(team_a_key) | countries_from_team_key(team_b_key)

        if current and current_countries.isdisjoint(match_countries):
            groups.append(current)
            current = []
            current_countries = set()

        current.append(match_data)
        current_countries.update(match_countries)

    if current:
        groups.append(current)
    return groups


def team_group_pair_key(matches: List[dict]) -> Tuple[str, str]:
    side_a_players: List[Tuple[str, str]] = []
    side_b_players: List[Tuple[str, str]] = []
    for match_data in matches:
        side_a_players.extend(match_data["side_a"])
        side_b_players.extend(match_data["side_b"])
    side_a_country = majority_country(side_a_players) or make_team_key(side_a_players)
    side_b_country = majority_country(side_b_players) or make_team_key(side_b_players)
    return team_pair_key(f"C:{side_a_country}" if not side_a_country.startswith(("C:", "R:")) else side_a_country,
                         f"C:{side_b_country}" if not side_b_country.startswith(("C:", "R:")) else side_b_country)


def resolve_team_tie_by_side(
    matches: List[dict],
    result: dict,
    event_id: int,
    sub_event_type_code: str,
) -> tuple[Optional[List[Tuple[str, str]]], Optional[str], Dict[str, int]]:
    wins_by_side = {"A": 0, "B": 0}
    side_rosters = {"A": [], "B": []}

    for match_data in matches:
        side_a = match_data["side_a"]
        side_b = match_data["side_b"]
        side_rosters["A"].extend(side_a)
        side_rosters["B"].extend(side_b)

        winner_side = pick_winner_side(
            winner_side=match_data["winner_side"],
            winner_name=match_data["winner_name"] or "",
            side_a=side_a,
            side_b=side_b,
        )
        if winner_side is None:
            if is_drawn_or_unplayed_score(match_data.get("match_score") or ""):
                result["skipped_unfinished_team_rubbers"] += 1
                continue
            result["unresolved_winner_side"] += 1
            _record_problem(
                result,
                event_id,
                sub_event_type_code,
                "unresolved_winner_side",
                "cannot infer winner side from winner_side/winner_name and side rosters",
            )
            continue
        wins_by_side[winner_side] += 1

    if wins_by_side["A"] == wins_by_side["B"]:
        return None, None, wins_by_side

    champion_side = "A" if wins_by_side["A"] > wins_by_side["B"] else "B"
    return side_rosters[champion_side], majority_country(side_rosters[champion_side]), wins_by_side


def collect_override_team_champion_rosters(
    cursor,
    champion_team_by_event: Dict[Tuple[int, str], str],
) -> Dict[Tuple[int, str], tuple[List[Tuple[str, str]], str]]:
    if not champion_team_by_event:
        return {}

    cursor.execute(
        """
        SELECT
            m.match_id,
            m.event_id,
            m.sub_event_type_code,
            ms.side_no,
            msp.player_name,
            msp.player_country
        FROM matches m
        JOIN match_sides ms ON ms.match_id = m.match_id
        LEFT JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
        WHERE m.event_id IS NOT NULL
        ORDER BY m.event_id, m.sub_event_type_code, m.match_id, ms.side_no, msp.player_order
        """
    )
    rows = cursor.fetchall()

    roster_by_event: Dict[Tuple[int, str], List[Tuple[str, str]]] = {}
    seen_by_event: Dict[Tuple[int, str], set[Tuple[str, str]]] = {}

    current_match_key: Optional[Tuple[int, str, int]] = None
    current_sides: Dict[int, List[Tuple[str, str]]] = {1: [], 2: []}

    def flush_current_match() -> None:
        nonlocal current_match_key, current_sides
        if current_match_key is None:
            return

        event_id, sub_event_type_code, _match_id = current_match_key
        event_key = (event_id, sub_event_type_code)
        champion_country = champion_team_by_event.get(event_key)
        if champion_country:
            for side in (current_sides.get(1, []), current_sides.get(2, [])):
                side_countries = {country.strip().upper() for _, country in side if country.strip()}
                if side_countries != {champion_country}:
                    continue
                roster = roster_by_event.setdefault(event_key, [])
                seen = seen_by_event.setdefault(event_key, set())
                for name, country in side:
                    cleaned_name = (name or "").strip()
                    cleaned_country = (country or "").strip().upper()
                    if not cleaned_name or cleaned_country != champion_country:
                        continue
                    member_key = (normalize_text(cleaned_name), cleaned_country)
                    if member_key in seen:
                        continue
                    seen.add(member_key)
                    roster.append((cleaned_name, cleaned_country))

        current_match_key = None
        current_sides = {1: [], 2: []}

    for match_id, event_id, sub_event_type_code, side_no, player_name, player_country in rows:
        match_key = (event_id, sub_event_type_code, match_id)
        if current_match_key != match_key:
            flush_current_match()
            current_match_key = match_key

        if player_name:
            current_sides.setdefault(side_no, []).append((player_name, player_country or ""))

    flush_current_match()

    return {
        event_key: (roster, champion_team_by_event[event_key])
        for event_key, roster in roster_by_event.items()
        if roster
    }


def resolve_team_tie_winner(
    matches: List[dict],
    result: dict,
    event_id: int,
    sub_event_type_code: str,
    count_unresolved: bool,
) -> tuple[Optional[str], Dict[str, List[Tuple[str, str]]], Dict[str, int], int]:
    wins_by_team: Dict[str, int] = {}
    rosters_by_team: Dict[str, List[Tuple[str, str]]] = {}
    skipped_unfinished = 0

    for match_data in matches:
        side_a = match_data["side_a"]
        side_b = match_data["side_b"]
        team_a_key = make_team_key(side_a)
        team_b_key = make_team_key(side_b)
        rosters_by_team.setdefault(team_a_key, []).extend(side_a)
        rosters_by_team.setdefault(team_b_key, []).extend(side_b)

        winner_side = pick_winner_side(
            winner_side=match_data["winner_side"],
            winner_name=match_data["winner_name"] or "",
            side_a=side_a,
            side_b=side_b,
        )
        if winner_side is None:
            if is_drawn_or_unplayed_score(match_data.get("match_score") or ""):
                skipped_unfinished += 1
                result["skipped_unfinished_team_rubbers"] += 1
                continue
            if count_unresolved:
                result["unresolved_winner_side"] += 1
                _record_problem(
                    result,
                    event_id,
                    sub_event_type_code,
                    "unresolved_winner_side",
                    "cannot infer winner side from winner_side/winner_name and side rosters",
                )
            continue

        winner_team_key = team_a_key if winner_side == "A" else team_b_key
        wins_by_team[winner_team_key] = wins_by_team.get(winner_team_key, 0) + 1

    if not wins_by_team:
        return None, rosters_by_team, wins_by_team, skipped_unfinished

    max_wins = max(wins_by_team.values())
    winner_keys = [team_key for team_key, wins in wins_by_team.items() if wins == max_wins]
    if len(winner_keys) != 1:
        return None, rosters_by_team, wins_by_team, skipped_unfinished

    return winner_keys[0], rosters_by_team, wins_by_team, skipped_unfinished


def build_team_semifinal_winner_pairs(cursor) -> dict[Tuple[int, str], set[Tuple[str, str]]]:
    cursor.execute(
        """
        SELECT
            m.match_id,
            edm.event_id,
            edm.sub_event_type_code,
            m.winner_side,
            m.winner_name,
            m.match_score,
            ms.side_no,
            msp.player_name,
            msp.player_country
        FROM event_draw_matches edm
        JOIN matches m ON m.match_id = edm.match_id
        JOIN match_sides ms ON ms.match_id = m.match_id
        LEFT JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
        WHERE edm.draw_stage = 'Main Draw'
          AND edm.draw_round = 'SemiFinal'
        ORDER BY edm.event_id, edm.sub_event_type_code, m.match_id, ms.side_no, msp.player_order
        """
    )
    semifinal_matches: Dict[int, dict] = {}
    for (
        match_id,
        event_id,
        sub_event_type_code,
        winner_side,
        winner_name,
        match_score,
        side_no,
        player_name,
        player_country,
    ) in cursor.fetchall():
        if not is_team_sub_event(sub_event_type_code):
            continue
        current = semifinal_matches.setdefault(
            match_id,
            {
                "match_id": match_id,
                "event_id": event_id,
                "sub_event_type_code": sub_event_type_code,
                "winner_side": winner_side,
                "winner_name": winner_name,
                "match_score": match_score,
                "side_a": [],
                "side_b": [],
            },
        )
        if player_name:
            if side_no == 1:
                current["side_a"].append((player_name, player_country or ""))
            elif side_no == 2:
                current["side_b"].append((player_name, player_country or ""))

    grouped: Dict[Tuple[int, str, Tuple[str, str]], List[dict]] = {}
    for match_data in semifinal_matches.values():
        team_a_key = make_team_key(match_data["side_a"])
        team_b_key = make_team_key(match_data["side_b"])
        key = (
            match_data["event_id"],
            match_data["sub_event_type_code"],
            team_pair_key(team_a_key, team_b_key),
        )
        grouped.setdefault(key, []).append(match_data)

    winners_by_event: Dict[Tuple[int, str], List[str]] = {}
    dummy_result = {"skipped_unfinished_team_rubbers": 0}
    for (event_id, sub_event_type_code, _pair), matches in grouped.items():
        winner_key, _rosters, _wins, _skipped = resolve_team_tie_winner(
            matches,
            dummy_result,
            event_id,
            sub_event_type_code,
            count_unresolved=False,
        )
        if winner_key:
            winners_by_event.setdefault((event_id, sub_event_type_code), []).append(winner_key)

    final_pairs_by_event: dict[Tuple[int, str], set[Tuple[str, str]]] = {}
    for key, winners in winners_by_event.items():
        unique_winners = sorted(set(winners))
        pairs = set()
        for idx, left in enumerate(unique_winners):
            for right in unique_winners[idx + 1 :]:
                pairs.add(team_pair_key(left, right))
        final_pairs_by_event[key] = pairs
    return final_pairs_by_event


def build_non_team_championship_final_pairs(cursor) -> dict[Tuple[int, str], set[Tuple[str, str]]]:
    cursor.execute(
        """
        SELECT
            m.match_id,
            edm.event_id,
            edm.sub_event_type_code,
            edm.draw_round,
            m.winner_side,
            m.winner_name,
            ms.side_no,
            msp.player_name,
            msp.player_country
        FROM event_draw_matches edm
        JOIN matches m ON m.match_id = edm.match_id
        JOIN match_sides ms ON ms.match_id = m.match_id
        LEFT JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
        WHERE edm.draw_stage = 'Main Draw'
          AND edm.draw_round IN ('QuarterFinal', 'SemiFinal', 'Final')
        ORDER BY edm.event_id, edm.sub_event_type_code, edm.draw_round, m.match_id, ms.side_no, msp.player_order
        """
    )

    match_map: Dict[int, dict] = {}
    for (
        match_id,
        event_id,
        sub_event_type_code,
        draw_round,
        winner_side,
        winner_name,
        side_no,
        player_name,
        player_country,
    ) in cursor.fetchall():
        if is_team_sub_event(sub_event_type_code):
            continue
        current = match_map.setdefault(
            match_id,
            {
                "match_id": match_id,
                "event_id": event_id,
                "sub_event_type_code": sub_event_type_code,
                "draw_round": draw_round,
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

    grouped: Dict[Tuple[int, str], Dict[str, List[dict]]] = {}
    for match_data in match_map.values():
        grouped.setdefault(
            (match_data["event_id"], match_data["sub_event_type_code"]),
            {"QuarterFinal": [], "SemiFinal": [], "Final": []},
        )[match_data["draw_round"]].append(match_data)

    championship_pairs_by_event: dict[Tuple[int, str], set[Tuple[str, str]]] = {}
    for event_key, rounds in grouped.items():
        qf_matches = rounds["QuarterFinal"]
        sf_matches = rounds["SemiFinal"]

        if len(qf_matches) < 2 or len(sf_matches) < 2:
            continue

        qf_winners: set[str] = set()
        for match_data in qf_matches:
            winner_side = pick_winner_side(
                winner_side=match_data["winner_side"],
                winner_name=match_data["winner_name"] or "",
                side_a=match_data["side_a"],
                side_b=match_data["side_b"],
            )
            if winner_side == "A":
                qf_winners.add(make_roster_key(match_data["side_a"]))
            elif winner_side == "B":
                qf_winners.add(make_roster_key(match_data["side_b"]))

        if len(qf_winners) < 2:
            continue

        championship_sf_winners: List[str] = []
        for match_data in sf_matches:
            side_a_key = make_roster_key(match_data["side_a"])
            side_b_key = make_roster_key(match_data["side_b"])
            if side_a_key not in qf_winners or side_b_key not in qf_winners:
                continue

            winner_side = pick_winner_side(
                winner_side=match_data["winner_side"],
                winner_name=match_data["winner_name"] or "",
                side_a=match_data["side_a"],
                side_b=match_data["side_b"],
            )
            if winner_side == "A":
                championship_sf_winners.append(side_a_key)
            elif winner_side == "B":
                championship_sf_winners.append(side_b_key)

        unique_winners = sorted(set(championship_sf_winners))
        if len(unique_winners) != 2:
            continue

        championship_pairs_by_event[event_key] = {tuple(unique_winners)}

    return championship_pairs_by_event


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
        "skipped_unfinished_team_rubbers": 0,
        "team_final_ties_selected": 0,
        "team_final_tie_fallbacks": 0,
        "non_team_final_fallbacks": 0,
        "problem_events": [],
    }

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    player_index = build_player_index(cursor)
    team_semifinal_winner_pairs = build_team_semifinal_winner_pairs(cursor)
    non_team_championship_final_pairs = build_non_team_championship_final_pairs(cursor)
    manual_override_champion_teams = load_manual_event_overrides()
    override_team_champion_rosters = collect_override_team_champion_rosters(cursor, manual_override_champion_teams)

    # Full refresh mode: clear previous sub_events and reset AUTOINCREMENT.
    if not dry_run:
        cursor.execute("DELETE FROM sub_events")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'sub_events'")

    cursor.execute(
        """
        SELECT
            m.match_id,
            edm.event_id,
            edm.sub_event_type_code,
            m.winner_side,
            m.winner_name,
            m.match_score,
            ms.side_no,
            msp.player_name,
            msp.player_country
        FROM event_draw_matches edm
        JOIN matches m ON m.match_id = edm.match_id
        JOIN events e ON e.event_id = edm.event_id
        JOIN event_categories ec ON ec.id = e.event_category_id
        JOIN match_sides ms ON ms.match_id = m.match_id
        LEFT JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
        WHERE edm.draw_stage = 'Main Draw'
          AND edm.draw_round = 'Final'
          AND edm.event_id IS NOT NULL
          AND COALESCE(ec.points_eligible, 0) = 1
        ORDER BY edm.event_id, edm.sub_event_type_code, m.match_id, ms.side_no, msp.player_order
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
        match_score,
        side_no,
        player_name,
        player_country,
    ) in rows:
        current = match_map.setdefault(
            match_id,
            {
                "match_id": match_id,
                "event_id": event_id,
                "sub_event_type_code": sub_event_type_code,
                "winner_side": winner_side,
                "winner_name": winner_name,
                "match_score": match_score,
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

    sub_event_rows: Dict[Tuple[int, str], Dict[str, Optional[str]]] = {}

    for (event_id, sub_event_type_code), final_matches in grouped_finals.items():
        champion_country_override: Optional[str] = None
        if is_team_sub_event(sub_event_type_code):
            final_tie_groups = group_final_team_ties(final_matches)
            selected_matches: Optional[List[dict]] = None
            if len(final_tie_groups) == 1:
                selected_matches = final_tie_groups[0]
            else:
                championship_pairs = team_semifinal_winner_pairs.get((event_id, sub_event_type_code), set())
                matching_groups = [group for group in final_tie_groups if team_group_pair_key(group) in championship_pairs]
                if len(matching_groups) == 1:
                    selected_matches = matching_groups[0]
                else:
                    # ITTF result pages usually list the championship final before bronze/placement ties.
                    selected_matches = sorted(final_tie_groups, key=lambda group: min(int(item["match_id"]) for item in group))[0]
                    result["team_final_tie_fallbacks"] += 1

            champion_roster, champion_country_override, wins_by_side = resolve_team_tie_by_side(
                selected_matches,
                result,
                event_id,
                sub_event_type_code,
            )
            result["team_final_ties_selected"] += 1
            if champion_roster is None:
                msg = (
                    f"Tie detected for team final champion: event_id={event_id}, "
                    f"sub_event_type_code={sub_event_type_code}, wins_by_side={wins_by_side}"
                )
                _record_problem(result, event_id, sub_event_type_code, "champion_tie", msg)
                if dry_run:
                    continue
                raise RuntimeError(msg)
        else:
            selected_finals = final_matches
            if len(final_matches) > 1:
                championship_pairs = non_team_championship_final_pairs.get((event_id, sub_event_type_code), set())
                matching_finals = []
                for match_data in final_matches:
                    final_pair = tuple(
                        sorted(
                            (
                                make_roster_key(match_data["side_a"]),
                                make_roster_key(match_data["side_b"]),
                            )
                        )
                    )
                    if final_pair in championship_pairs:
                        matching_finals.append(match_data)

                if len(matching_finals) == 1:
                    selected_finals = matching_finals
                else:
                    selected_finals = sorted(final_matches, key=lambda item: int(item["match_id"]))[:1]
                    result["non_team_final_fallbacks"] += 1

            wins_by_team: Dict[str, int] = {}
            team_roster_by_key: Dict[str, List[Tuple[str, str]]] = {}

            for match_data in selected_finals:
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

                # Singles/doubles finals must distinguish roster identity even when both sides
                # share the same country code (e.g., domestic final).
                team_a_key = make_roster_key(side_a)
                team_b_key = make_roster_key(side_b)
                winner_team_key = team_a_key if winner_side == "A" else team_b_key

                wins_by_team[winner_team_key] = wins_by_team.get(winner_team_key, 0) + 1

                if team_a_key not in team_roster_by_key:
                    team_roster_by_key[team_a_key] = []
                if team_b_key not in team_roster_by_key:
                    team_roster_by_key[team_b_key] = []
                team_roster_by_key[team_a_key].extend(side_a)
                team_roster_by_key[team_b_key].extend(side_b)

            if not wins_by_team:
                continue

            max_wins = max(wins_by_team.values())
            champion_team_keys = [team_key for team_key, wins in wins_by_team.items() if wins == max_wins]
            if len(champion_team_keys) != 1:
                msg = (
                    f"Tie detected for final champion: event_id={event_id}, "
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
        needs_manual_country = (
            champion_country_override is None
            and len(deduped_countries) > 1
            and sub_event_type_code not in MULTI_COUNTRY_SUB_EVENTS
        )
        if len(deduped_countries) > 1:
            if champion_country_override is not None or sub_event_type_code in MULTI_COUNTRY_SUB_EVENTS:
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

        resolved_country = champion_country_override or resolve_champion_country_code(
            event_id=event_id,
            sub_event_type_code=sub_event_type_code,
            champion_names=champion_names,
            champion_countries=champion_countries,
        )

        sub_event_rows[(event_id, sub_event_type_code)] = {
            "champion_player_ids": ",".join(champion_ids) if champion_ids else None,
            "champion_name": ",".join(champion_names) if champion_names else None,
            "champion_country_code": resolved_country if resolved_country else None,
        }

    for (event_id, sub_event_type_code), (champion_roster, champion_country_override) in override_team_champion_rosters.items():
        champion_names: List[str] = []
        champion_ids: List[str] = []

        for name, country in champion_roster:
            champion_names.append(name)
            pid = lookup_player_id(player_index, name, country)
            if pid is not None:
                champion_ids.append(str(pid))
            else:
                champion_ids.append("")
                result["unmatched_champion_members"].add(f"{name} ({country})")

        if not champion_names:
            continue

        sub_event_rows[(event_id, sub_event_type_code)] = {
            "champion_player_ids": ",".join(champion_ids) if champion_ids else None,
            "champion_name": ",".join(champion_names) if champion_names else None,
            "champion_country_code": champion_country_override,
        }

    if not dry_run:
        for (event_id, sub_event_type_code), row in sorted(sub_event_rows.items()):
            cursor.execute(
                """
                INSERT INTO sub_events (
                    event_id, sub_event_type_code, champion_player_ids, champion_name, champion_country_code
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    sub_event_type_code,
                    row["champion_player_ids"],
                    row["champion_name"],
                    row["champion_country_code"],
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
    print(f"  team final ties selected:     {result['team_final_ties_selected']}")
    print(f"  team final tie fallbacks:     {result['team_final_tie_fallbacks']}")
    print(f"  non-team final fallbacks:     {result['non_team_final_fallbacks']}")
    print(f"  skipped unfinished rubbers:   {result['skipped_unfinished_team_rubbers']}")
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
