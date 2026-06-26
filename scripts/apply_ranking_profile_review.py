#!/usr/bin/env python3
"""Apply manually completed ranking/profile review data."""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.capture import save_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ittf_review_apply")

DEFAULT_DICT_PATH = Path("scripts/data/translation_dict_v2.json")
DEFAULT_DB_PATH = Path("data/db/ittf.db")
DEFAULT_SAME_NAME_PLAYERS_PATH = Path("scripts/data/same_name_players.txt")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dict_key(original: str) -> str:
    return " ".join((original or "").strip().split()).lower()


def _name_key(name: str) -> str:
    return " ".join(sorted((name or "").lower().split()))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_translations(review: dict[str, Any], dict_path: Path) -> int:
    dictionary = _load_json(dict_path) if dict_path.exists() else {"metadata": {}, "entries": {}}
    dictionary.setdefault("metadata", {})
    entries = dictionary.setdefault("entries", {})
    added = 0
    for item in review.get("missing_translations", []):
        if not isinstance(item, dict):
            continue
        original = str(item.get("original") or "").strip()
        translated = str(item.get("translated") or "").strip()
        if not original or not translated:
            continue
        key = _dict_key(original)
        categories = item.get("categories") or ["others"]
        if not isinstance(categories, list):
            categories = ["others"]
        previous = entries.get(key)
        entries[key] = {
            "original": original,
            "translated": translated,
            "categories": categories,
            "source": "manual_review",
            "review_status": "reviewed",
            "updated_at": _utc_now_iso(),
        }
        if previous != entries[key]:
            added += 1
    save_json(dict_path, dictionary)
    return added


def _row_matches(row: dict[str, Any], weekly: dict[str, Any]) -> bool:
    fields = ["rank", "name", "country_code", "points"]
    for field in fields:
        expected = weekly.get(field)
        if expected is None:
            continue
        if str(row.get(field) or "") != str(expected):
            return False
    return True


def _apply_ranking_ids(review: dict[str, Any], ranking_file: Path | None) -> int:
    if ranking_file is None:
        return 0
    ranking = _load_json(ranking_file)
    rows = ranking.get("rankings", [])
    if not isinstance(rows, list):
        raise ValueError(f"ranking file has invalid rankings list: {ranking_file}")

    applied = 0
    for item in review.get("unresolved_player_ids", []):
        if not isinstance(item, dict):
            continue
        resolution = item.get("resolution") or {}
        player_id = str(resolution.get("player_id") or "").strip()
        if not player_id:
            continue
        weekly = item.get("weekly") or {}
        profile_url = str(resolution.get("profile_url") or "").strip() or None
        for row in rows:
            if not isinstance(row, dict) or not _row_matches(row, weekly):
                continue
            row["player_id"] = player_id
            if profile_url:
                row["profile_url"] = profile_url
            row["id_resolution_status"] = "manual"
            applied += 1
            break

    save_json(ranking_file, ranking)
    return applied


def _load_same_name_entries(path: Path) -> set[tuple[int, str, str]]:
    entries: set[tuple[int, str, str]] = set()
    if not path.exists():
        return entries

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",", 2)]
        if len(parts) != 3:
            logger.warning("Skipping invalid same-name player row: %s", raw_line)
            continue
        try:
            player_id = int(parts[0])
        except ValueError:
            logger.warning("Skipping invalid same-name player id: %s", raw_line)
            continue
        entries.add((player_id, parts[1], parts[2].upper()))
    return entries


def _write_same_name_entries(path: Path, entries: set[tuple[int, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(entries, key=lambda item: (_name_key(item[1]), item[2], item[0]))
    path.write_text(
        "\n".join(f"{player_id},{name},{country_code}" for player_id, name, country_code in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )


def _same_name_country_group(db_path: Path, player_name: str, country_code: str) -> list[tuple[int, str, str]]:
    if not db_path.exists():
        return []

    country = (country_code or "").strip().upper()
    if not player_name.strip() or not country:
        return []

    target_key = _name_key(player_name)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT player_id, name, country_code FROM players WHERE UPPER(country_code) = ?",
            (country,),
        ).fetchall()
    finally:
        conn.close()

    matches = [
        (int(player_id), str(name), str(row_country).upper())
        for player_id, name, row_country in rows
        if _name_key(str(name)) == target_key
    ]
    return matches if len({player_id for player_id, _, _ in matches}) > 1 else []


def _apply_same_name_players(review: dict[str, Any], db_path: Path, same_name_players_path: Path) -> int:
    entries = _load_same_name_entries(same_name_players_path)
    before = set(entries)

    for item in review.get("unresolved_player_ids", []):
        if not isinstance(item, dict):
            continue
        resolution = item.get("resolution") or {}
        if not str(resolution.get("player_id") or "").strip():
            continue
        weekly = item.get("weekly") or {}
        player_name = str(weekly.get("name") or "").strip()
        country_code = str(weekly.get("country_code") or "").strip().upper()
        for row in _same_name_country_group(db_path, player_name, country_code):
            entries.add(row)

    if entries != before:
        _write_same_name_entries(same_name_players_path, entries)
    return len(entries - before)


def apply_review(
    review_path: Path,
    *,
    dict_path: Path = DEFAULT_DICT_PATH,
    ranking_file: Path | None = None,
    same_name_players_path: Path = DEFAULT_SAME_NAME_PLAYERS_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, int]:
    review = _load_json(review_path)
    return {
        "translations_added": _apply_translations(review, dict_path),
        "ranking_ids_applied": _apply_ranking_ids(review, ranking_file),
        "same_name_players_added": _apply_same_name_players(review, db_path, same_name_players_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply completed manual review JSON")
    parser.add_argument("--review", required=True, help="Review JSON generated by review_ranking_profile_outputs.py")
    parser.add_argument("--dict-path", default=str(DEFAULT_DICT_PATH))
    parser.add_argument("--ranking-file", default=None, help="Merged ranking JSON to patch with manual player IDs")
    parser.add_argument("--same-name-players", default=str(DEFAULT_SAME_NAME_PLAYERS_PATH))
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    return parser


def run(args: argparse.Namespace) -> int:
    summary = apply_review(
        Path(args.review),
        dict_path=Path(args.dict_path),
        ranking_file=Path(args.ranking_file) if args.ranking_file else None,
        same_name_players_path=Path(args.same_name_players),
        db_path=Path(args.db_path),
    )
    logger.info("Applied translations: %d", summary["translations_added"])
    logger.info("Applied ranking ids: %d", summary["ranking_ids_applied"])
    logger.info("Added same-name player rows: %d", summary["same_name_players_added"])
    return 0


def main() -> None:
    parser = build_parser()
    sys.exit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
