#!/usr/bin/env python3
"""
Normalize bronze-match labels for ITTF Mixed Team World Cup Chengdu 2024/2025.

Why this exists:
- 2024 bronze-match rubbers were mislabeled by the source as Main Draw / Final.
- 2025 bronze-match rubbers were labeled as Position Draw / 2.
- Downstream draw reconstruction and event presentation become unstable unless
  these two events share a consistent Main Draw / Bronze representation.

This script rewrites only the special event payloads under data/event_matches:
- orig/ITTF_Mixed_Team_World_Cup_Chengdu_2024_2979.json
- cn/ITTF_Mixed_Team_World_Cup_Chengdu_2024_2979.json
- orig/ittf_mixed_team_world_cup_chengdu_2025_3263.json
- cn/ittf_mixed_team_world_cup_chengdu_2025_3263.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent

TARGETS = {
    "2979": {
        "orig": PROJECT_ROOT / "data" / "event_matches" / "orig" / "ITTF_Mixed_Team_World_Cup_Chengdu_2024_2979.json",
        "cn": PROJECT_ROOT / "data" / "event_matches" / "cn" / "ITTF_Mixed_Team_World_Cup_Chengdu_2024_2979.json",
        "bronze_teams": {"ROU", "HKG"},
        "from_stage": "Main Draw",
        "from_round": "Final",
    },
    "3263": {
        "orig": PROJECT_ROOT / "data" / "event_matches" / "orig" / "ittf_mixed_team_world_cup_chengdu_2025_3263.json",
        "cn": PROJECT_ROOT / "data" / "event_matches" / "cn" / "ittf_mixed_team_world_cup_chengdu_2025_3263.json",
        "bronze_teams": {"KOR", "GER"},
        "from_stage": "Position Draw",
        "from_round": "2",
    },
}

BRONZE_STAGE = "Main Draw"
BRONZE_ROUND = "Bronze"
BRONZE_STAGE_ZH = "正赛"
BRONZE_ROUND_ZH = "铜牌赛"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_team_codes(match: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for side_key in ("side_a", "side_b"):
        for entry in match.get(side_key) or []:
            text = str(entry or "").strip()
            if "(" not in text or not text.endswith(")"):
                continue
            code = text.rsplit("(", 1)[1][:-1].strip().upper()
            if code:
                codes.add(code)
    return codes


def fix_payload(payload: dict[str, Any], with_zh: bool) -> Counter:
    event_id = str(payload.get("event_id") or "").strip()
    config = TARGETS.get(event_id)
    if config is None:
        raise ValueError(f"Unsupported event_id={event_id!r}")

    matches = payload.get("matches")
    if not isinstance(matches, list):
        raise ValueError("Payload missing matches list")

    stats: Counter = Counter()
    for idx, match in enumerate(matches, start=1):
        if not isinstance(match, dict):
            raise ValueError(f"matches[{idx}] is not an object")

        team_codes = extract_team_codes(match)
        stage = str(match.get("stage") or "").strip()
        round_name = str(match.get("round") or "").strip()
        is_target = (
            stage == config["from_stage"]
            and round_name == config["from_round"]
            and team_codes == config["bronze_teams"]
        )

        if is_target:
            match["stage"] = BRONZE_STAGE
            match["round"] = BRONZE_ROUND
            if with_zh:
                match["stage_zh"] = BRONZE_STAGE_ZH
                match["round_zh"] = BRONZE_ROUND_ZH
            stats["bronze_rows_rewritten"] += 1
        updated_stage = str(match.get("stage") or "").strip()
        updated_round = str(match.get("round") or "").strip()
        stats[f"stage::{updated_stage}"] += 1
        stats[f"round::{updated_round}"] += 1

    expected_rows = 4 if event_id == "2979" else 5
    if stats["bronze_rows_rewritten"] != expected_rows:
        raise ValueError(
            f"event_id={event_id} rewritten bronze rows mismatch: {stats['bronze_rows_rewritten']} != {expected_rows}"
        )

    return stats


def print_stats(label: str, event_id: str, stats: Counter) -> None:
    print(f"[{label}] event_id={event_id}")
    print(f"  bronze_rows_rewritten: {stats['bronze_rows_rewritten']}")
    print(f"  Main Draw: {stats['stage::Main Draw']}")
    print(f"  Position Draw: {stats['stage::Position Draw']}")
    print(f"  Bronze: {stats['round::Bronze']}")
    print(f"  Final: {stats['round::Final']}")


def run(dry_run: bool) -> int:
    for event_id, config in TARGETS.items():
        orig_payload = load_json(config["orig"])
        cn_payload = load_json(config["cn"])

        orig_stats = fix_payload(orig_payload, with_zh=False)
        cn_stats = fix_payload(cn_payload, with_zh=True)

        print_stats("orig", event_id, orig_stats)
        print_stats("cn", event_id, cn_stats)

        if dry_run:
            continue

        save_json(config["orig"], orig_payload)
        save_json(config["cn"], cn_payload)
        print(f"Updated:\n- {config['orig']}\n- {config['cn']}")

    if dry_run:
        print("Dry run only; no files written.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fix bronze labels for Mixed Team World Cup Chengdu 2024/2025")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print stats without writing files")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    sys.exit(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
