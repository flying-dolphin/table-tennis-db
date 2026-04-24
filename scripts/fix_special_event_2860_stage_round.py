#!/usr/bin/env python3
"""
Fix stage/round labels for event_id=2860 (ITTF Mixed Team World Cup Chengdu 2023).

Why this exists:
- ITTF source rows for this event are all labeled as "Qualification".
- The actual competition format was a two-stage round-robin event:
  Stage 1 group round robin -> top 2 advance -> Stage 2 round robin.
- There was no knockout semifinal/final bracket.

This script rewrites only the special event payloads under data/event_matches:
- orig/ITTF_Mixed_Team_World_Cup_Chengdu_2023_2860.json
- cn/ITTF_Mixed_Team_World_Cup_Chengdu_2023_2860.json

Usage:
  python scripts/fix_special_event_2860_stage_round.py --dry-run
  python scripts/fix_special_event_2860_stage_round.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ORIG_PATH = PROJECT_ROOT / "data" / "event_matches" / "orig" / "ITTF_Mixed_Team_World_Cup_Chengdu_2023_2860.json"
CN_PATH = PROJECT_ROOT / "data" / "event_matches" / "cn" / "ITTF_Mixed_Team_World_Cup_Chengdu_2023_2860.json"
TARGET_EVENT_ID = "2860"

STAGE1_GROUPS: dict[str, set[str]] = {
    "Group 1": {"CHN", "HKG", "SWE", "PUR"},
    "Group 2": {"GER", "POR", "EGY", "SVK"},
    "Group 3": {"JPN", "FRA", "ROU", "USA", "AUS"},
    "Group 4": {"KOR", "TPE", "SGP", "IND", "CAN"},
}

STAGE_LABEL_1 = "Main Draw - Stage 1"
STAGE_LABEL_2 = "Main Draw - Stage 2"
ROUND_LABEL_2 = "Round Robin"

STAGE_ZH = {
    STAGE_LABEL_1: "正赛 - 第一阶段",
    STAGE_LABEL_2: "正赛 - 第二阶段",
}
ROUND_ZH = {
    "Group 1": "第一组",
    "Group 2": "第二组",
    "Group 3": "第三组",
    "Group 4": "第四组",
    ROUND_LABEL_2: "循环赛",
}


def build_stage1_pair_to_group() -> dict[tuple[str, str], str]:
    mapping: dict[tuple[str, str], str] = {}
    for group_name, teams in STAGE1_GROUPS.items():
        team_list = sorted(teams)
        for idx, left in enumerate(team_list):
            for right in team_list[idx + 1 :]:
                mapping[(left, right)] = group_name
    return mapping


STAGE1_PAIR_TO_GROUP = build_stage1_pair_to_group()


def extract_side_country_codes(side: list[str]) -> set[str]:
    codes: set[str] = set()
    for entry in side:
        text = (entry or "").strip()
        if "(" not in text or not text.endswith(")"):
            continue
        country = text.rsplit("(", 1)[1][:-1].strip().upper()
        if country:
            codes.add(country)
    return codes


def classify_match(match: dict[str, Any]) -> tuple[str, str]:
    side_a_codes = extract_side_country_codes(match.get("side_a") or [])
    side_b_codes = extract_side_country_codes(match.get("side_b") or [])

    if len(side_a_codes) != 1 or len(side_b_codes) != 1:
        raise ValueError(
            f"Expected exactly one country code per side, got side_a={sorted(side_a_codes)} side_b={sorted(side_b_codes)}"
        )

    left = next(iter(side_a_codes))
    right = next(iter(side_b_codes))
    pair = tuple(sorted((left, right)))
    group_name = STAGE1_PAIR_TO_GROUP.get(pair)
    if group_name:
        return STAGE_LABEL_1, group_name
    return STAGE_LABEL_2, ROUND_LABEL_2


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fix_payload(payload: dict[str, Any], with_zh: bool) -> tuple[dict[str, Any], Counter]:
    event_id = str(payload.get("event_id") or "").strip()
    if event_id != TARGET_EVENT_ID:
        raise ValueError(f"Unexpected event_id={event_id!r}, expected {TARGET_EVENT_ID}")

    matches = payload.get("matches")
    if not isinstance(matches, list):
        raise ValueError("Payload missing matches list")

    stats: Counter = Counter()
    for idx, match in enumerate(matches, start=1):
        if not isinstance(match, dict):
            raise ValueError(f"matches[{idx}] is not an object")

        new_stage, new_round = classify_match(match)
        old_stage = (match.get("stage") or "").strip()
        old_round = (match.get("round") or "").strip()

        match["stage"] = new_stage
        match["round"] = new_round

        if with_zh:
            match["stage_zh"] = STAGE_ZH[new_stage]
            match["round_zh"] = ROUND_ZH[new_round]

        if old_stage != new_stage:
            stats["stage_changed"] += 1
        if old_round != new_round:
            stats["round_changed"] += 1
        stats[f"stage::{new_stage}"] += 1
        stats[f"round::{new_round}"] += 1

    if stats[f"stage::{STAGE_LABEL_1}"] != 129:
        raise ValueError(f"Stage 1 match count mismatch: {stats[f'stage::{STAGE_LABEL_1}']} != 129")
    if stats[f"stage::{STAGE_LABEL_2}"] != 94:
        raise ValueError(f"Stage 2 match count mismatch: {stats[f'stage::{STAGE_LABEL_2}']} != 94")

    return payload, stats


def print_stats(label: str, stats: Counter) -> None:
    print(f"[{label}]")
    print(f"  stage_changed: {stats['stage_changed']}")
    print(f"  round_changed: {stats['round_changed']}")
    print(f"  {STAGE_LABEL_1}: {stats[f'stage::{STAGE_LABEL_1}']}")
    print(f"  {STAGE_LABEL_2}: {stats[f'stage::{STAGE_LABEL_2}']}")
    print(f"  Group 1: {stats['round::Group 1']}")
    print(f"  Group 2: {stats['round::Group 2']}")
    print(f"  Group 3: {stats['round::Group 3']}")
    print(f"  Group 4: {stats['round::Group 4']}")
    print(f"  {ROUND_LABEL_2}: {stats[f'round::{ROUND_LABEL_2}']}")


def run(dry_run: bool) -> int:
    orig_payload = load_json(ORIG_PATH)
    cn_payload = load_json(CN_PATH)

    orig_fixed, orig_stats = fix_payload(orig_payload, with_zh=False)
    cn_fixed, cn_stats = fix_payload(cn_payload, with_zh=True)

    print_stats("orig", orig_stats)
    print_stats("cn", cn_stats)

    if dry_run:
        print("Dry run only; no files written.")
        return 0

    save_json(ORIG_PATH, orig_fixed)
    save_json(CN_PATH, cn_fixed)
    print(f"Updated:\n- {ORIG_PATH}\n- {CN_PATH}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fix stage/round labels for special event_id=2860")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print stats without writing files")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    sys.exit(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
