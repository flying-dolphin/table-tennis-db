"""Helpers for checking whether ranking players exist in the player database or profiles."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def profile_player_ids(profile_dir: Path | str) -> set[int]:
    ids: set[int] = set()
    directory = Path(profile_dir)
    if not directory.exists():
        return ids
    for path in directory.glob("player_*.json"):
        try:
            player_id = int(json.loads(path.read_text(encoding="utf-8")).get("player_id"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        ids.add(player_id)
    return ids


def database_player_ids(db_path: Path | str) -> set[int]:
    path = Path(db_path)
    if not path.is_file():
        return set()
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return {int(row[0]) for row in connection.execute("SELECT player_id FROM players")}
    finally:
        connection.close()


def ranking_player_ids(ranking_file: Path | str) -> set[int]:
    payload = json.loads(Path(ranking_file).read_text(encoding="utf-8"))
    return {
        int(row["player_id"])
        for row in payload.get("rankings", [])
        if row.get("player_id") not in (None, "")
    }


def missing_ranking_player_ids(
    ranking_file: Path | str,
    db_path: Path | str,
    profile_dir: Path | str,
) -> set[int]:
    return ranking_player_ids(ranking_file) - database_player_ids(db_path) - profile_player_ids(profile_dir)
