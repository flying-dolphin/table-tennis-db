#!/usr/bin/env python3
"""
Offline audit and repair for match JSON files under data/matches_complete.

Capabilities:
- Re-parse raw_row_text according to docs/design/database.md
- Repair all_players_in_row / side_a / side_b
- Remove deprecated teammates / opponents fields
- Recompute player_name normalization, perspective, winner, result_for_player
- Backfill english_name / country / country_zh when missing

Usage:
    python scripts/repair_matches_offline.py --check
    python scripts/repair_matches_offline.py --fix
    python scripts/repair_matches_offline.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PLAYER_WITH_COUNTRY_RE = re.compile(
    r"([A-Z][A-Za-z]*(?:[-'\s][A-Za-z]+)*)\s*\(([A-Z]{3})\)"
)
SCORE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?")
STAGE_TOKENS = {
    "main draw",
    "qualification",
    "qualifying",
    "group",
    "final",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_DIR = PROJECT_ROOT / "data" / "matches_complete"
DEFAULT_DICT_PATH = PROJECT_ROOT / "scripts" / "data" / "translation_dict_v2.json"


def normalize_words(text: str) -> tuple[str, ...]:
    return tuple(sorted(token.lower() for token in WORD_RE.findall(text or "")))


def strip_country(player_with_country: str) -> str:
    match = PLAYER_WITH_COUNTRY_RE.search(player_with_country or "")
    if match:
        return match.group(1).strip()
    return (player_with_country or "").strip()


def is_same_person(left: str, right: str) -> bool:
    left_clean = strip_country(left)
    right_clean = strip_country(right)
    if left_clean.lower() == right_clean.lower():
        return True
    words = normalize_words(left_clean)
    return bool(words) and words == normalize_words(right_clean)


def is_sub_event_token(token: str) -> bool:
    token = (token or "").strip()
    return bool(re.fullmatch(r"[A-Z0-9]{2,8}", token))


def is_stage_token(token: str) -> bool:
    return (token or "").strip().lower() in STAGE_TOKENS


def extract_players(segment: str) -> list[str]:
    return [match.group(0).strip() for match in PLAYER_WITH_COUNTRY_RE.finditer(segment or "")]


def parse_raw_row_text(raw_row_text: str) -> dict[str, Any]:
    tokens = [segment.strip() for segment in (raw_row_text or "").split("|")]
    sub_event_idx = -1
    for idx in range(2, len(tokens) - 1):
        if is_sub_event_token(tokens[idx]) and is_stage_token(tokens[idx + 1]):
            sub_event_idx = idx
            break

    if sub_event_idx == -1:
        all_players: list[str] = []
        seen: set[str] = set()
        for player in extract_players(raw_row_text):
            if player not in seen:
                seen.add(player)
                all_players.append(player)
        return {
            "sub_event": "",
            "side_a": all_players[:1],
            "side_b": all_players[1:],
            "all_players_in_row": all_players,
            "winner": "",
        }

    participant_tokens = tokens[2:sub_event_idx]
    side_a: list[str] = []
    side_b: list[str] = []

    if len(participant_tokens) >= 4:
        for token in participant_tokens[:2]:
            side_a.extend(extract_players(token))
        for token in participant_tokens[2:4]:
            side_b.extend(extract_players(token))
    elif len(participant_tokens) >= 2:
        side_a.extend(extract_players(participant_tokens[0]))
        side_b.extend(extract_players(participant_tokens[1]))
    elif participant_tokens:
        side_a.extend(extract_players(participant_tokens[0]))
        for token in participant_tokens[1:]:
            side_b.extend(extract_players(token))

    all_players = side_a + side_b
    winner_tokens = [token for token in tokens[sub_event_idx + 5:] if token]
    winner = " / ".join(winner_tokens)

    return {
        "sub_event": tokens[sub_event_idx],
        "side_a": side_a,
        "side_b": side_b,
        "all_players_in_row": all_players,
        "winner": winner,
    }


def parse_score(match_score: str) -> tuple[int | None, int | None]:
    score_match = SCORE_RE.match(match_score or "")
    if not score_match:
        return None, None
    return int(score_match.group(1)), int(score_match.group(2))


def infer_winner_from_score(side_a: list[str], side_b: list[str], match_score: str) -> str:
    score_a, score_b = parse_score(match_score)
    if score_a is None or score_b is None:
        return ""
    if score_a > score_b:
        winners = [strip_country(name) for name in side_a]
    elif score_b > score_a:
        winners = [strip_country(name) for name in side_b]
    else:
        winners = []
    return " / ".join(winners)


def pick_canonical_player_name(data: dict[str, Any]) -> str:
    current_name = (data.get("player_name") or "").strip()
    current_words = normalize_words(current_name)
    if not current_words:
        return current_name

    for year_info in (data.get("years") or {}).values():
        if not isinstance(year_info, dict):
            continue
        for event in year_info.get("events", []):
            for match in event.get("matches", []):
                for candidate in match.get("side_a", []):
                    candidate_name = strip_country(candidate)
                    if normalize_words(candidate_name) == current_words and candidate_name != current_name:
                        return candidate_name
    return current_name


def load_location_dict(dict_path: Path) -> dict[str, str]:
    data = json.loads(dict_path.read_text(encoding="utf-8"))
    entries = data.get("entries", {})
    result: dict[str, str] = {}
    for normalized, payload in entries.items():
        categories = payload.get("categories", [])
        if "locations" in categories:
            result[normalized] = payload.get("translated", "")
    return result


def repair_match(match: dict[str, Any], player_name: str) -> tuple[dict[str, Any], list[str]]:
    changes: list[str] = []
    parsed = parse_raw_row_text(match.get("raw_row_text", ""))
    new_side_a = parsed["side_a"]
    new_side_b = parsed["side_b"]
    new_all_players = parsed["all_players_in_row"]
    new_sub_event = parsed["sub_event"] or (match.get("sub_event") or "")

    if match.get("all_players_in_row", []) != new_all_players:
        match["all_players_in_row"] = new_all_players
        changes.append("all_players_in_row")

    if match.get("side_a", []) != new_side_a:
        match["side_a"] = new_side_a
        changes.append("side_a")

    if match.get("side_b", []) != new_side_b:
        match["side_b"] = new_side_b
        changes.append("side_b")

    if new_sub_event and match.get("sub_event", "") != new_sub_event:
        match["sub_event"] = new_sub_event
        changes.append("sub_event")

    if "teammates" in match:
        del match["teammates"]
        changes.append("remove_teammates")

    if "opponents" in match:
        del match["opponents"]
        changes.append("remove_opponents")

    perspective = "unknown"
    result_for_player = "unknown"
    score_a, score_b = parse_score(match.get("match_score", ""))
    if any(is_same_person(player_name, candidate) for candidate in new_side_a):
        perspective = "side_a"
        if score_a is not None and score_b is not None:
            result_for_player = "win" if score_a > score_b else "loss"
    elif any(is_same_person(player_name, candidate) for candidate in new_side_b):
        perspective = "side_b"
        if score_a is not None and score_b is not None:
            result_for_player = "win" if score_b > score_a else "loss"

    if match.get("perspective") != perspective:
        match["perspective"] = perspective
        changes.append("perspective")

    if match.get("result_for_player") != result_for_player:
        match["result_for_player"] = result_for_player
        changes.append("result_for_player")

    if "result" in match:
        del match["result"]
        changes.append("remove_result")

    winner = parsed["winner"] or infer_winner_from_score(new_side_a, new_side_b, match.get("match_score", ""))
    if match.get("winner", "") != winner:
        match["winner"] = winner
        changes.append("winner")

    return match, changes


def repair_file(file_path: Path, location_dict: dict[str, str]) -> dict[str, Any]:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    file_changes: Counter[str] = Counter()
    records_checked = 0
    records_changed = 0

    original_player_name = (data.get("player_name") or "").strip()

    for year_info in (data.get("years") or {}).values():
        if not isinstance(year_info, dict):
            continue
        for event in year_info.get("events", []):
            for match in event.get("matches", []):
                records_checked += 1
                _, changes = repair_match(match, original_player_name)
                if changes:
                    records_changed += 1
                    file_changes.update(changes)

    canonical_player_name = pick_canonical_player_name(data)
    if canonical_player_name and canonical_player_name != original_player_name:
        data["player_name"] = canonical_player_name
        file_changes.update(["player_name"])
        if data.get("english_name", "").strip() == original_player_name:
            data["english_name"] = canonical_player_name
            file_changes.update(["english_name_sync"])

        for year_info in (data.get("years") or {}).values():
            if not isinstance(year_info, dict):
                continue
            for event in year_info.get("events", []):
                for match in event.get("matches", []):
                    _, changes = repair_match(match, canonical_player_name)
                    if changes:
                        file_changes.update(changes)

    if "english_name" not in data:
        data["english_name"] = data.get("player_name", "")
        file_changes.update(["english_name"])

    if "country" not in data:
        data["country"] = data.get("country_code", "")
        file_changes.update(["country"])

    if file_path.parent.name == "cn" and "country_zh" not in data:
        country_code = (data.get("country_code") or "").strip()
        translated = location_dict.get(country_code.lower())
        if translated:
            data["country_zh"] = translated
            file_changes.update(["country_zh"])

    return {
        "data": data,
        "records_checked": records_checked,
        "records_changed": records_changed,
        "changes": file_changes,
    }


def summarize_discrepancies(file_path: Path, location_dict: dict[str, str]) -> dict[str, Any]:
    repaired = repair_file(file_path, location_dict)
    return {
        "file": str(file_path),
        "records_checked": repaired["records_checked"],
        "records_changed": repaired["records_changed"],
        "changes": repaired["changes"],
        "data": repaired["data"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline repair for matches_complete JSON files")
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    parser.add_argument("--locale", default="cn")
    parser.add_argument("--check", action="store_true", help="Check only")
    parser.add_argument("--fix", action="store_true", help="Repair files in place")
    parser.add_argument("--dry-run", action="store_true", help="Preview fixes without writing")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    args = parser.parse_args()

    mode = "fix" if args.fix else "check"
    target_dir = args.base_dir / args.locale
    location_dict = load_location_dict(args.dict_path)

    files_checked = 0
    files_changed = 0
    records_checked = 0
    records_changed = 0
    aggregate_changes: Counter[str] = Counter()
    changed_files: list[tuple[str, Counter[str]]] = []

    for file_path in sorted(target_dir.glob("*.json")):
        files_checked += 1
        summary = summarize_discrepancies(file_path, location_dict)
        records_checked += summary["records_checked"]
        records_changed += summary["records_changed"]
        aggregate_changes.update(summary["changes"])

        if summary["changes"]:
            files_changed += 1
            changed_files.append((file_path.name, summary["changes"]))
            if mode == "fix" and not args.dry_run:
                file_path.write_text(
                    json.dumps(summary["data"], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    print("=" * 80)
    print(f"MODE: {mode.upper()} {'(DRY RUN)' if args.dry_run else ''}".strip())
    print(f"TARGET: {target_dir}")
    print(f"FILES CHECKED: {files_checked}")
    print(f"FILES CHANGED: {files_changed}")
    print(f"RECORDS CHECKED: {records_checked}")
    print(f"RECORDS CHANGED: {records_changed}")
    print("=" * 80)

    if aggregate_changes:
        print("CHANGE COUNTS:")
        for key, count in aggregate_changes.most_common():
            print(f"  {key}: {count}")
    else:
        print("No discrepancies found.")

    if changed_files:
        print("=" * 80)
        print("SAMPLE CHANGED FILES:")
        for file_name, change_counter in changed_files[:20]:
            details = ", ".join(f"{key}={value}" for key, value in change_counter.most_common())
            print(f"  {file_name}: {details}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
