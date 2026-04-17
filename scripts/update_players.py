#!/usr/bin/env python3
"""
Update players list from matches data and scrape missing profiles from search page.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scrape_profiles_from_search import run as run_scrape_profiles_from_search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("update_players")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update players from matches and scrape missing profiles")
    parser.add_argument("--matches-dir", default="data/matches_complete/cn", help="Directory of match JSON files")
    parser.add_argument("--db-path", default="data/db/ittf.db", help="SQLite database path")
    parser.add_argument("--output", default="data/player_profiles/pending_from_matches.json", help="Output file for missing players")
    parser.add_argument("--dry-run", action="store_true", help="Only generate missing list, do not scrape profiles")

    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--cdp-only", action="store_true")
    parser.add_argument("--storage-state", default="data/session/ittf_storage_state.json")
    parser.add_argument("--init-session", action="store_true")

    parser.add_argument("--profile-dir", default="data/player_profiles")
    parser.add_argument("--avatar-dir", default="data/player_avatars")
    parser.add_argument("--profile-checkpoint", default="data/player_profiles/checkpoint_scrape_profiles_from_search.json")
    parser.add_argument("--rebuild-checkpoint", action="store_true")
    parser.add_argument("--force", action="store_true")

    parser.add_argument("--min-delay", type=float, default=5.0)
    parser.add_argument("--max-delay", type=float, default=10.0)
    parser.add_argument("--min-player-gap", type=float, default=5.0)
    parser.add_argument("--max-player-gap", type=float, default=10.0)
    return parser


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_key(value: str) -> str:
    return _normalize_space(value).lower()


def _strip_cn_country_suffix(name_zh: str) -> str:
    value = _normalize_space(name_zh)
    if not value:
        return ""
    value = re.sub(r"\s*[\(（][^()（）]+[\)）]\s*$", "", value).strip()
    return value


def _parse_en_player_token(token: str) -> tuple[str, str, str]:
    raw = _normalize_space(token)
    if not raw:
        return "", "", ""
    m = re.match(r"^(.*?)\s*\(([A-Z]{3})\)\s*$", raw)
    if not m:
        english_name = raw
        return english_name, "", english_name
    english_name = _normalize_space(m.group(1))
    country_code = m.group(2).upper()
    with_country = f"{english_name} ({country_code})"
    return english_name, country_code, with_country


def _iter_matches(payload: dict[str, Any]) -> list[dict[str, Any]]:
    years = payload.get("years")
    if not isinstance(years, dict):
        return []
    results: list[dict[str, Any]] = []
    for year_data in years.values():
        if not isinstance(year_data, dict):
            continue
        events = year_data.get("events", [])
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            matches = event.get("matches", [])
            if not isinstance(matches, list):
                continue
            for match in matches:
                if isinstance(match, dict):
                    results.append(match)
    return results


def _append_side_entries(
    names_en: list[str],
    names_zh: list[str],
    aggregates: dict[tuple[str, str], dict[str, Any]],
) -> None:
    for idx, token_en in enumerate(names_en):
        english_name, country_code, english_with_country = _parse_en_player_token(str(token_en))
        if not english_name:
            continue

        name_zh = ""
        if idx < len(names_zh):
            name_zh = _strip_cn_country_suffix(str(names_zh[idx]))
        if _normalize_key(name_zh) == _normalize_key(english_name):
            name_zh = ""

        key = (_normalize_key(english_name), country_code)
        item = aggregates.setdefault(
            key,
            {
                "english_name": english_name,
                "country_code": country_code,
                "english_with_country": english_with_country,
                "name_zh": "",
                "name_zh_variants": set(),
                "occurrences": 0,
            },
        )
        item["occurrences"] += 1
        if name_zh:
            item["name_zh_variants"].add(name_zh)
            if not item["name_zh"]:
                item["name_zh"] = name_zh


def collect_players_from_matches(matches_dir: Path) -> tuple[list[dict[str, Any]], int]:
    aggregates: dict[tuple[str, str], dict[str, Any]] = {}
    file_count = 0

    for json_file in sorted(matches_dir.glob("*.json")):
        file_count += 1
        try:
            payload = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skip invalid JSON %s: %s", json_file, exc)
            continue

        for match in _iter_matches(payload):
            side_a = match.get("side_a") if isinstance(match.get("side_a"), list) else []
            side_b = match.get("side_b") if isinstance(match.get("side_b"), list) else []
            side_a_zh = match.get("side_a_zh") if isinstance(match.get("side_a_zh"), list) else []
            side_b_zh = match.get("side_b_zh") if isinstance(match.get("side_b_zh"), list) else []

            _append_side_entries(side_a, side_a_zh, aggregates)
            _append_side_entries(side_b, side_b_zh, aggregates)

    players = []
    for item in aggregates.values():
        variants = sorted(item["name_zh_variants"])
        players.append(
            {
                "english_name": item["english_name"],
                "country_code": item["country_code"],
                "english_with_country": item["english_with_country"],
                "name_zh": item["name_zh"],
                "name_zh_variants": variants,
                "occurrences": item["occurrences"],
            }
        )

    players.sort(key=lambda x: (-int(x["occurrences"]), x["english_name"], x["country_code"]))
    return players, file_count


def load_existing_player_names(db_path: Path) -> set[str]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM players")
        rows = cur.fetchall()
        return {_normalize_key(str(row[0] or "")) for row in rows if row and row[0]}
    finally:
        conn.close()


def select_missing_players(
    all_players: list[dict[str, Any]],
    existing_name_keys: set[str],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in all_players:
        grouped[_normalize_key(str(item["english_name"]))].append(item)

    missing: list[dict[str, Any]] = []
    for english_key, variants in grouped.items():
        if english_key in existing_name_keys:
            continue

        variants_sorted = sorted(
            variants,
            key=lambda x: (
                -int(x["occurrences"]),
                0 if x["country_code"] else 1,
                x["country_code"],
            ),
        )
        chosen = variants_sorted[0]

        missing.append(
            {
                "english_name": chosen["english_name"],
                "country_code": chosen["country_code"],
                "english_with_country": chosen["english_with_country"],
                "name_zh": chosen["name_zh"],
                "occurrences": chosen["occurrences"],
                "country_variants": sorted({v["country_code"] for v in variants if v["country_code"]}),
                "name_zh_variants": sorted({z for v in variants for z in v.get("name_zh_variants", []) if z}),
            }
        )

    missing.sort(key=lambda x: x["english_name"])
    return missing


def write_missing_output(
    output_file: Path,
    matches_dir: Path,
    file_count: int,
    unique_players: int,
    missing_players: list[dict[str, Any]],
) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _utc_now_iso(),
        "matches_dir": str(matches_dir),
        "match_files_scanned": file_count,
        "unique_players_in_matches": unique_players,
        "missing_player_count": len(missing_players),
        "players": missing_players,
    }
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="")


def run(args: argparse.Namespace) -> int:
    matches_dir = Path(args.matches_dir)
    db_path = Path(args.db_path)
    output_file = Path(args.output)

    if not matches_dir.exists():
        logger.error("Matches directory not found: %s", matches_dir)
        return 2

    all_players, file_count = collect_players_from_matches(matches_dir)
    logger.info("Scanned %d files, collected %d unique players (name+country)", file_count, len(all_players))

    existing_name_keys = load_existing_player_names(db_path)
    logger.info("Loaded %d existing player names from DB", len(existing_name_keys))

    missing_players = select_missing_players(all_players, existing_name_keys)
    write_missing_output(output_file, matches_dir, file_count, len(all_players), missing_players)

    logger.info("Missing player names: %d", len(missing_players))
    logger.info("Missing list saved to: %s", output_file)

    if args.dry_run:
        preview = missing_players[:15]
        if preview:
            logger.info("Dry-run preview (first %d):", len(preview))
            for item in preview:
                logger.info("  - %s | country=%s | zh=%s", item["english_name"], item["country_code"] or "N/A", item["name_zh"] or "N/A")
        return 0

    if not missing_players and not args.init_session:
        logger.info("No missing players to scrape.")
        return 0

    scrape_args = argparse.Namespace(
        players_file=str(output_file),
        headless=args.headless,
        slow_mo=args.slow_mo,
        cdp_port=args.cdp_port,
        cdp_only=args.cdp_only,
        storage_state=args.storage_state,
        init_session=args.init_session,
        profile_dir=args.profile_dir,
        avatar_dir=args.avatar_dir,
        db_path=str(db_path),
        checkpoint=args.profile_checkpoint,
        force=args.force,
        rebuild_checkpoint=args.rebuild_checkpoint,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        min_player_gap=args.min_player_gap,
        max_player_gap=args.max_player_gap,
    )
    return run_scrape_profiles_from_search(scrape_args)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        code = run(args)
    except KeyboardInterrupt:
        logger.error("Interrupted by user.")
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
