#!/usr/bin/env python3
"""Build a manual review file for ranking/profile data gaps."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.capture import save_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ittf_review_builder")

DEFAULT_RANK_LOG = Path("scripts/logs/translate_ranks.log")
DEFAULT_PROFILE_LOG = Path("scripts/logs/translate_profiles.log")
DEFAULT_OUTPUT = Path("data/review/ranking_profile_review.json")

FIELD_CATEGORIES = {
    "name": ["players"],
    "country": ["locations"],
    "location": ["locations"],
    "event": ["events"],
    "category": ["terms"],
    "expires_on": ["terms"],
    "position": ["terms"],
    "gender": ["terms"],
    "style": ["terms"],
    "playing_hand": ["terms"],
    "grip": ["terms"],
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _translation_entry(scope: str, field: str, original: str, source: str) -> dict[str, Any]:
    return {
        "scope": scope,
        "field": field,
        "original": original,
        "translated": None,
        "categories": FIELD_CATEGORIES.get(field, ["others"]),
        "source": source,
    }


def _dedupe_translations(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for entry in entries:
        key = (str(entry.get("scope")), str(entry.get("field")), str(entry.get("original")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def parse_rank_translation_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    current_field: str | None = None
    section_re = re.compile(r"^---\s+(.+?)\s+\(\d+\)\s+---$")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("==="):
            continue
        match = section_re.match(line)
        if match:
            current_field = match.group(1).strip()
            continue
        if current_field:
            entries.append(_translation_entry("ranking", current_field, line, str(path)))
    return _dedupe_translations(entries)


def parse_profile_translation_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    missing_re = re.compile(r"Missing translation \[(?P<field>[^\]]+)\].*?: (?P<value>.+)$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = missing_re.search(line)
        if not match:
            continue
        raw_value = match.group("value").strip()
        if (raw_value.startswith("'") and raw_value.endswith("'")) or (raw_value.startswith('"') and raw_value.endswith('"')):
            raw_value = raw_value[1:-1]
        entries.append(_translation_entry("profile", match.group("field").strip(), raw_value, str(path)))
    return _dedupe_translations(entries)


def load_unresolved_player_ids(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("unresolved", [])
    if not isinstance(rows, list):
        return []
    review_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        review_rows.append(
            {
                "reason": row.get("reason"),
                "weekly": row.get("weekly", {}),
                "candidate_count": row.get("candidate_count", 0),
                "candidates": row.get("candidates", []),
                "resolution": {
                    "player_id": None,
                    "profile_url": None,
                },
            }
        )
    return review_rows


def build_review(
    ranking_unresolved: Path | None,
    rank_translation_log: Path = DEFAULT_RANK_LOG,
    profile_translation_log: Path = DEFAULT_PROFILE_LOG,
) -> dict[str, Any]:
    missing = []
    missing.extend(parse_rank_translation_log(rank_translation_log))
    missing.extend(parse_profile_translation_log(profile_translation_log))
    return {
        "generated_at": _utc_now_iso(),
        "instructions": {
            "unresolved_player_ids": "Fill resolution.player_id and resolution.profile_url for rows that should be patched.",
            "missing_translations": "Fill translated for entries that should be added to translation_dict_v2.json.",
        },
        "unresolved_player_ids": load_unresolved_player_ids(ranking_unresolved),
        "missing_translations": _dedupe_translations(missing),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build manual review JSON for ranking/profile gaps")
    parser.add_argument("--ranking-unresolved", default=None, help="Merged ranking unresolved report JSON")
    parser.add_argument("--rank-translation-log", default=str(DEFAULT_RANK_LOG))
    parser.add_argument("--profile-translation-log", default=str(DEFAULT_PROFILE_LOG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def run(args: argparse.Namespace) -> int:
    review = build_review(
        Path(args.ranking_unresolved) if args.ranking_unresolved else None,
        Path(args.rank_translation_log),
        Path(args.profile_translation_log),
    )
    output = Path(args.output)
    save_json(output, review)
    logger.info("Saved review file: %s", output)
    logger.info(
        "Review items: %d unresolved ids, %d missing translations",
        len(review["unresolved_player_ids"]),
        len(review["missing_translations"]),
    )
    return 0


def main() -> None:
    parser = build_parser()
    sys.exit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
