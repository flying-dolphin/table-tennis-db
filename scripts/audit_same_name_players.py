#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit same-name players for conservative match import resolution."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "scripts" / "data" / "same_name_players.txt"
DEFAULT_COUNTRY_HISTORY_PATH = PROJECT_ROOT / "data" / "player_country_history.json"


def normalize_name_key(name: str) -> str:
    return " ".join(sorted((name or "").lower().split()))


def load_existing_entries(path: Path) -> set[tuple[int, str, str]]:
    entries: set[tuple[int, str, str]] = set()
    if not path.exists():
        return entries

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",", 2)]
        if len(parts) != 3:
            continue
        try:
            player_id = int(parts[0])
        except ValueError:
            continue
        name = parts[1]
        country_code = parts[2].upper()
        if name and country_code:
            entries.add((player_id, name, country_code))
    return entries


def write_entries(path: Path, entries: set[tuple[int, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(entries, key=lambda item: (normalize_name_key(item[1]), item[2], item[0]))
    path.write_text(
        "\n".join(f"{player_id},{name},{country_code}" for player_id, name, country_code in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )


def load_players(db_path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT player_id, name, country_code FROM players").fetchall()
    finally:
        conn.close()
    return [
        {
            "player_id": int(player_id),
            "name": str(name or "").strip(),
            "country_code": str(country_code or "").strip().upper(),
        }
        for player_id, name, country_code in rows
        if player_id is not None and str(name or "").strip() and str(country_code or "").strip()
    ]


def load_country_history(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    history: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("player_name") or "").strip()
        current_country = str(item.get("current_country") or "").strip().upper()
        historical_country = str(item.get("historical_country") or "").strip().upper()
        if name and current_country and historical_country:
            history.append(
                {
                    "player_name": name,
                    "current_country": current_country,
                    "historical_country": historical_country,
                }
            )
    return history


def discover_same_name_entries(db_path: Path, country_history_path: Path) -> set[tuple[int, str, str]]:
    players = load_players(db_path)
    effective_rows: list[tuple[int, str, str]] = [
        (player["player_id"], player["name"], player["country_code"])
        for player in players
    ]

    by_current_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for player in players:
        by_current_key.setdefault((normalize_name_key(player["name"]), player["country_code"]), []).append(player)

    for item in load_country_history(country_history_path):
        for player in by_current_key.get((normalize_name_key(item["player_name"]), item["current_country"]), []):
            effective_rows.append((player["player_id"], player["name"], item["historical_country"]))

    groups: dict[tuple[str, str], list[tuple[int, str, str]]] = {}
    for player_id, name, country_code in effective_rows:
        groups.setdefault((normalize_name_key(name), country_code), []).append((player_id, name, country_code))

    discovered: set[tuple[int, str, str]] = set()
    for rows in groups.values():
        if len({player_id for player_id, _, _ in rows}) > 1:
            discovered.update(rows)
    return discovered


def audit_same_name_players(
    *,
    db_path: Path,
    output_path: Path,
    country_history_path: Path,
    update: bool,
) -> dict[str, int]:
    existing = load_existing_entries(output_path)
    discovered = discover_same_name_entries(db_path, country_history_path)
    merged = existing | discovered
    added = merged - existing

    if update and merged != existing:
        write_entries(output_path, merged)

    return {
        "existing_entries": len(existing),
        "discovered_entries": len(discovered),
        "added_entries": len(added),
        "total_entries": len(merged),
        "updated": int(update and merged != existing),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit same-name players from the players table")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--country-history", type=Path, default=DEFAULT_COUNTRY_HISTORY_PATH)
    parser.add_argument("--update", action="store_true", help="Write discovered entries into the output file")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = audit_same_name_players(
        db_path=args.db_path,
        output_path=args.output,
        country_history_path=args.country_history,
        update=args.update,
    )
    print("Same-name player audit:")
    print(f"  Existing entries:   {summary['existing_entries']}")
    print(f"  Discovered entries: {summary['discovered_entries']}")
    print(f"  Added entries:      {summary['added_entries']}")
    print(f"  Total entries:      {summary['total_entries']}")
    print(f"  Updated file:       {bool(summary['updated'])}")


if __name__ == "__main__":
    sys.exit(main())
