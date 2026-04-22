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
    r"[A-Z][^|()]*?(?:\s*\([^()]*\))*\s*\([A-Z]{3}\)"
)
SCORE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_DIR = PROJECT_ROOT / "data" / "matches_complete"
DEFAULT_DICT_PATH = PROJECT_ROOT / "scripts" / "data" / "translation_dict_v2.json"

# raw_row_text 的列结构固定为：
# [0] year | [1] event_name
# [2] player_a | [3] player_a_partner (singles: empty)
# [4] player_b | [5] player_b_partner (singles: empty)
# [6] sub_event | [7] stage | [8] round | [9] score | [10] games | [11] winner | ...
_COL_SUB_EVENT = 6
_COL_STAGE = 7
_COL_ROUND = 8
_COL_WINNER = 11


def normalize_words(text: str) -> tuple[str, ...]:
    return tuple(sorted(token.lower() for token in WORD_RE.findall(text or "")))


def strip_country(player_with_country: str) -> str:
    return re.sub(r"\s*\([A-Z]{3}\)\s*$", "", player_with_country or "").strip()


def is_same_person(left: str, right: str) -> bool:
    left_clean = strip_country(left)
    right_clean = strip_country(right)
    if left_clean.lower() == right_clean.lower():
        return True
    words = normalize_words(left_clean)
    return bool(words) and words == normalize_words(right_clean)


def extract_players(segment: str) -> list[str]:
    return [match.group(0).strip() for match in PLAYER_WITH_COUNTRY_RE.finditer(segment or "")]


def _extract_round_from_text(text: str) -> str:
    """从任意文本中提取 round 信息（正则回退）。

    支持的格式：
    - R1, R2, R16, R32, R64, R128, R256
    - QF, SF, F (Quarter/Semi/Final)
    - QuarterFinal, SemiFinal, Final
    - Round of 8/16/32/64/128
    - Rd 1, Rd 2 (缩写形式)
    - Group A, Group B (分组)
    - Preliminary, Prelim
    - Repechage
    """
    if not text:
        return ""

    patterns = [
        # 精确匹配数字 round (R1-R256)
        r"\b(R\d{1,3})\b",
        # 简写和全名 round
        r"\b(QF|SF|F|QuarterFinal|SemiFinal|Final)\b",
        # "Round of X" 格式
        r"\b(Round\s+of\s+\d+)\b",
        # 缩写形式 (Rd 1, Rd 2)
        r"\b(Rd\s+\d+)\b",
        # 分组 (Group A, Group B 等)
        r"\b(Group\s+[A-Z])\b",
        # 预选和复活赛
        r"\b(Preliminary|Prelim|Repechage)\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result = m.group(1).strip()
            # 规范化格式：R1 (不是 r1)，Group A (不是 group a)
            if result.lower().startswith("r") and result[1:].replace(" ", "").isdigit():
                result = result.upper()
            return result

    return ""


def parse_raw_row_text(raw_row_text: str) -> dict[str, Any]:
    """从 raw_row_text 按固定列位置解析比赛信息。

    列结构固定（单打和双打均相同，单打的搭档列为空字符串占位）：
      [0] year | [1] event_name
      [2] player_a  | [3] player_a_partner
      [4] player_b  | [5] player_b_partner
      [6] sub_event | [7] stage | [8] round | [9] score | [10] games | [11] winner | ...
    """
    tokens = [segment.strip() for segment in (raw_row_text or "").split("|")]

    sub_event = tokens[_COL_SUB_EVENT] if len(tokens) > _COL_SUB_EVENT else ""
    stage = tokens[_COL_STAGE] if len(tokens) > _COL_STAGE else ""

    # round：从固定位置提取，排除与 stage 重复的值
    round_val = ""
    if len(tokens) > _COL_ROUND:
        candidate = tokens[_COL_ROUND]
        if candidate and candidate.lower() != stage.lower():
            round_val = candidate

    # 如果固定位置为空，从整个文本中正则搜索
    if not round_val:
        round_val = _extract_round_from_text(raw_row_text)

    # 提取球员：单打 tokens[2], tokens[4]；双打 tokens[2]+tokens[3], tokens[4]+tokens[5]
    side_a = extract_players(tokens[2]) if len(tokens) > 2 else []
    if len(tokens) > 3 and tokens[3]:
        side_a.extend(extract_players(tokens[3]))

    side_b = extract_players(tokens[4]) if len(tokens) > 4 else []
    if len(tokens) > 5 and tokens[5]:
        side_b.extend(extract_players(tokens[5]))

    all_players = side_a + side_b

    # winner 在固定位置 tokens[11] 起
    winner_tokens = [t for t in tokens[_COL_WINNER:] if t]
    winner = " / ".join(winner_tokens)

    return {
        "sub_event": sub_event,
        "round": round_val,
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

    new_round = parsed.get("round", "")
    if match.get("round", "") != new_round:
        match["round"] = new_round
        changes.append("round")

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


def iter_match_lists(data: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """Return all match lists for both player-level and event-level JSON shapes."""
    match_lists: list[list[dict[str, Any]]] = []

    root_matches = data.get("matches")
    if isinstance(root_matches, list):
        match_lists.append(root_matches)

    years = data.get("years")
    if isinstance(years, dict):
        for year_info in years.values():
            if not isinstance(year_info, dict):
                continue
            for event in year_info.get("events", []):
                if not isinstance(event, dict):
                    continue
                matches = event.get("matches")
                if isinstance(matches, list):
                    match_lists.append(matches)

    return match_lists


def repair_file(file_path: Path, location_dict: dict[str, str]) -> dict[str, Any]:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    file_changes: Counter[str] = Counter()
    records_checked = 0
    records_changed = 0

    original_player_name = (data.get("player_name") or "").strip()

    for match_list in iter_match_lists(data):
        for match in match_list:
            if not isinstance(match, dict):
                continue
            records_checked += 1
            _, changes = repair_match(match, original_player_name)
            if changes:
                records_changed += 1
                file_changes.update(changes)

    canonical_player_name = pick_canonical_player_name(data) if original_player_name else ""
    if original_player_name and canonical_player_name and canonical_player_name != original_player_name:
        data["player_name"] = canonical_player_name
        file_changes.update(["player_name"])
        if data.get("english_name", "").strip() == original_player_name:
            data["english_name"] = canonical_player_name
            file_changes.update(["english_name_sync"])

        for match_list in iter_match_lists(data):
            for match in match_list:
                if not isinstance(match, dict):
                    continue
                _, changes = repair_match(match, canonical_player_name)
                if changes:
                    file_changes.update(changes)

    if original_player_name and "english_name" not in data:
        data["english_name"] = data.get("player_name", "")
        file_changes.update(["english_name"])

    if original_player_name and "country" not in data:
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
