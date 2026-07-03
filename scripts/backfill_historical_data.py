#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plan and orchestrate historical ITTF event/match/player backfills."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

BASE_URL = "https://results.ittf.link"
DEFAULT_EVENTS_DIR = Path("data/events_list/orig")
DEFAULT_EVENT_MATCHES_ORIG_DIR = Path("data/event_matches/orig")
DEFAULT_EVENT_MATCHES_PROBLEMATIC_DIR = Path("data/event_matches/problematic")
DEFAULT_DB_PATH = Path("data/db/ittf.db")
DEFAULT_PROFILE_SEARCH_CACHE = Path("data/player_profiles/profile_search_candidates.json")
DEFAULT_BACKFILL_DIR = Path("data/backfill/historical")
DEFAULT_EVENTS_CN_DIR = Path("data/events_list/cn")
DEFAULT_EVENT_MATCHES_CN_DIR = Path("data/event_matches/cn")
DEFAULT_PLAYER_PROFILES_DIR = Path("data/player_profiles")

PLAYER_TOKEN_RE = re.compile(r"^(.+?)\s*\(([A-Za-z]{3})\)$")


def normalize_name_key(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_event_id(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text if text.isdigit() else ""


def collect_existing_event_ids(*directories: Path) -> set[str]:
    existing: set[str] = set()
    for directory in directories:
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            event_id = ""
            try:
                payload = load_json(path)
                if isinstance(payload, dict):
                    event_id = parse_event_id(payload.get("event_id"))
            except Exception:
                event_id = ""
            if not event_id:
                match = re.search(r"_(\d+)\.json$", path.name)
                event_id = match.group(1) if match else ""
            if event_id:
                existing.add(event_id)
    return existing


def iter_event_rows(events_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not events_dir.exists():
        return rows
    for path in sorted(events_dir.glob("*.json")):
        try:
            payload = load_json(path)
        except Exception:
            continue
        events = payload.get("events", []) if isinstance(payload, dict) else []
        if isinstance(events, list):
            rows.extend(event for event in events if isinstance(event, dict))
    return rows


def build_event_match_url_plan(
    *,
    events_dir: Path = DEFAULT_EVENTS_DIR,
    output_dir: Path = DEFAULT_EVENT_MATCHES_ORIG_DIR,
    problematic_dir: Path = DEFAULT_EVENT_MATCHES_PROBLEMATIC_DIR,
) -> dict[str, Any]:
    existing_ids = collect_existing_event_ids(output_dir, problematic_dir)
    pending: list[dict[str, Any]] = []
    filtering_only_count = 0
    seen: set[str] = set()

    for event in iter_event_rows(events_dir):
        event_id = parse_event_id(event.get("event_id"))
        matches_href = str(event.get("matches_href") or "").strip()
        if not event_id or not matches_href or event_id in seen:
            continue
        seen.add(event_id)

        filtering_only = bool(event.get("filtering_only"))
        if filtering_only:
            filtering_only_count += 1
        if event_id in existing_ids:
            continue

        pending.append(
            {
                "event_id": event_id,
                "event_name": str(event.get("name") or event.get("event") or "").strip(),
                "filtering_only": filtering_only,
                "url": urljoin(BASE_URL, matches_href),
            }
        )

    return {
        "total_events": len(seen),
        "completed_count": len(existing_ids & seen),
        "pending_count": len(pending),
        "failed_count": 0,
        "filtering_only_count": filtering_only_count,
        "pending": pending,
    }


def extract_player_names_from_event_matches(event_matches_dir: Path) -> set[str]:
    names: set[str] = set()
    if not event_matches_dir.exists():
        return names
    for path in sorted(event_matches_dir.glob("*.json")):
        try:
            payload = load_json(path)
        except Exception:
            continue
        matches = payload.get("matches", []) if isinstance(payload, dict) else []
        if not isinstance(matches, list):
            continue
        for match in matches:
            if not isinstance(match, dict):
                continue
            for side_key in ("side_a", "side_b"):
                entries = match.get(side_key) or []
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    parsed = PLAYER_TOKEN_RE.match(str(entry).strip())
                    if parsed:
                        names.add(" ".join(parsed.group(1).split()))
    return names


def load_db_player_names(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT name FROM players WHERE name IS NOT NULL AND TRIM(name) <> ''").fetchall()
    finally:
        conn.close()
    return {" ".join(str(row[0]).split()) for row in rows if row and str(row[0]).strip()}


def load_profile_search_cache(cache_path: Path) -> dict[str, Any]:
    if not cache_path.exists():
        return {}
    try:
        payload = load_json(cache_path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_profile_search_plan(
    *,
    event_matches_dir: Path = DEFAULT_EVENT_MATCHES_ORIG_DIR,
    db_path: Path = DEFAULT_DB_PATH,
    cache_path: Path = DEFAULT_PROFILE_SEARCH_CACHE,
    refresh_names: list[str] | None = None,
) -> dict[str, Any]:
    names = extract_player_names_from_event_matches(event_matches_dir) | load_db_player_names(db_path)
    cache = load_profile_search_cache(cache_path)
    refresh_keys = {normalize_name_key(name) for name in (refresh_names or [])}

    pending: list[dict[str, str]] = []
    cached_count = 0
    for name in sorted(names, key=lambda item: item.lower()):
        key = normalize_name_key(name)
        if key in cache:
            cached_count += 1
        if key not in cache or key in refresh_keys:
            pending.append({"name": name, "name_key": key})

    return {
        "total_names": len(names),
        "cached_count": cached_count,
        "pending_count": len(pending),
        "failed_count": 0,
        "pending": pending,
    }


def write_event_match_urls(plan: dict[str, Any], output_file: Path) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [item["url"] for item in plan.get("pending", []) if item.get("url")]
    output_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="")
    return output_file


def write_profile_search_players(plan: dict[str, Any], output_file: Path) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    players = [
        {"english_name": item["name"], "country_code": "", "name_zh": ""}
        for item in plan.get("pending", [])
        if item.get("name")
    ]
    output_file.write_text(json.dumps({"players": players}, ensure_ascii=False, indent=2), encoding="utf-8", newline="")
    return output_file


def run_command(cmd: list[str], *, dry_run: bool = False) -> int:
    print(" ".join(cmd))
    if dry_run:
        return 0
    return subprocess.run(cmd, check=False).returncode


def add_browser_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--cdp-port", type=int, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Historical ITTF data backfill helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="Print local backfill gap statistics")
    plan.add_argument("--events-dir", type=Path, default=DEFAULT_EVENTS_DIR)
    plan.add_argument("--event-matches-dir", type=Path, default=DEFAULT_EVENT_MATCHES_ORIG_DIR)
    plan.add_argument("--problematic-dir", type=Path, default=DEFAULT_EVENT_MATCHES_PROBLEMATIC_DIR)
    plan.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    plan.add_argument("--profile-cache", type=Path, default=DEFAULT_PROFILE_SEARCH_CACHE)
    plan.add_argument("--include-details", action="store_true", help="Include pending item details in JSON output")

    scrape_events = subparsers.add_parser("scrape-events", help="Scrape the full historical events list")
    scrape_events.add_argument("--from-date", default="1900-01-01")
    scrape_events.add_argument("--output-dir", type=Path, default=DEFAULT_EVENTS_DIR)
    scrape_events.add_argument("--force", action="store_true")
    add_browser_args(scrape_events)

    scrape_matches = subparsers.add_parser("scrape-matches", help="Scrape missing event match files")
    scrape_matches.add_argument("--events-dir", type=Path, default=DEFAULT_EVENTS_DIR)
    scrape_matches.add_argument("--output-dir", type=Path, default=DEFAULT_EVENT_MATCHES_ORIG_DIR)
    scrape_matches.add_argument("--problematic-dir", type=Path, default=DEFAULT_EVENT_MATCHES_PROBLEMATIC_DIR)
    scrape_matches.add_argument("--batch-file", type=Path, default=DEFAULT_BACKFILL_DIR / "event_match_urls.txt")
    scrape_matches.add_argument("--filter", action="store_true", help="Skip filtering_only events during match scraping")
    scrape_matches.add_argument("--force", action="store_true")
    add_browser_args(scrape_matches)

    scrape_players = subparsers.add_parser("scrape-players", help="Scrape missing player profiles from match names")
    scrape_players.add_argument("--event-matches-dir", type=Path, default=DEFAULT_EVENT_MATCHES_ORIG_DIR)
    scrape_players.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    scrape_players.add_argument("--profile-cache", type=Path, default=DEFAULT_PROFILE_SEARCH_CACHE)
    scrape_players.add_argument("--players-file", type=Path, default=DEFAULT_BACKFILL_DIR / "profile_search_players.json")
    scrape_players.add_argument("--profile-dir", type=Path, default=DEFAULT_PLAYER_PROFILES_DIR)
    scrape_players.add_argument("--refresh-name", action="append", default=[])
    scrape_players.add_argument("--force", action="store_true")
    add_browser_args(scrape_players)

    translate = subparsers.add_parser("translate", help="Translate newly scraped events, matches, and profiles")
    translate.add_argument("--events-orig-dir", type=Path, default=DEFAULT_EVENTS_DIR)
    translate.add_argument("--events-cn-dir", type=Path, default=DEFAULT_EVENTS_CN_DIR)
    translate.add_argument("--matches-orig-dir", type=Path, default=DEFAULT_EVENT_MATCHES_ORIG_DIR)
    translate.add_argument("--matches-cn-dir", type=Path, default=DEFAULT_EVENT_MATCHES_CN_DIR)
    translate.add_argument("--profiles-orig-dir", type=Path, default=DEFAULT_PLAYER_PROFILES_DIR / "orig")
    translate.add_argument("--profiles-cn-dir", type=Path, default=DEFAULT_PLAYER_PROFILES_DIR / "cn")
    translate.add_argument("--career-best-rank-lte", type=int, default=50)
    translate.add_argument("--since", default=None)
    translate.add_argument("--dry-run", action="store_true")

    import_stage = subparsers.add_parser("import", help="Import translated historical data into SQLite")
    import_stage.add_argument("--event-file", type=Path, default=None)
    import_stage.add_argument("--event-id", nargs="+", default=[])
    import_stage.add_argument("--source-dir", type=Path, default=DEFAULT_EVENT_MATCHES_CN_DIR)
    import_stage.add_argument("--skip-same-name-player-matches", action="store_true")
    import_stage.add_argument("--dry-run", action="store_true")
    return parser


def run_plan(args: argparse.Namespace) -> int:
    event_urls = build_event_match_url_plan(
        events_dir=args.events_dir,
        output_dir=args.event_matches_dir,
        problematic_dir=args.problematic_dir,
    )
    profile_search = build_profile_search_plan(
        event_matches_dir=args.event_matches_dir,
        db_path=args.db_path,
        cache_path=args.profile_cache,
    )
    if not args.include_details:
        event_urls = {key: value for key, value in event_urls.items() if key != "pending"}
        profile_search = {key: value for key, value in profile_search.items() if key != "pending"}
    print(json.dumps({"event_matches": event_urls, "profile_search": profile_search}, ensure_ascii=False, indent=2))
    return 0


def run_scrape_events(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        "scripts/scrape_events.py",
        "--from-date",
        args.from_date,
        "--output-dir",
        str(args.output_dir),
    ]
    if args.headless:
        cmd.append("--headless")
    if args.cdp_port is not None:
        cmd += ["--cdp-port", str(args.cdp_port)]
    if args.force:
        cmd.append("--force")
    return run_command(cmd, dry_run=args.dry_run)


def run_scrape_matches(args: argparse.Namespace) -> int:
    plan = build_event_match_url_plan(
        events_dir=args.events_dir,
        output_dir=args.output_dir,
        problematic_dir=args.problematic_dir,
    )
    write_event_match_urls(plan, args.batch_file)
    print(
        "event_matches: "
        f"completed={plan['completed_count']} pending={plan['pending_count']} "
        f"failed={plan['failed_count']} filtering_only={plan['filtering_only_count']}"
    )
    if plan["pending_count"] == 0:
        return 0

    cmd = [
        sys.executable,
        "scripts/scrape_matches_from_events.py",
        "--urls-file",
        str(args.batch_file),
        "--output-dir",
        str(args.output_dir),
    ]
    if args.headless:
        cmd.append("--headless")
    if args.cdp_port is not None:
        cmd += ["--cdp-port", str(args.cdp_port)]
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    if args.filter:
        cmd.append("--filter")
    if args.force:
        cmd.append("--force")
    return run_command(cmd, dry_run=args.dry_run)


def run_scrape_players(args: argparse.Namespace) -> int:
    plan = build_profile_search_plan(
        event_matches_dir=args.event_matches_dir,
        db_path=args.db_path,
        cache_path=args.profile_cache,
        refresh_names=args.refresh_name,
    )
    write_profile_search_players(plan, args.players_file)
    print(
        "profile_search: "
        f"cached={plan['cached_count']} pending={plan['pending_count']} failed={plan['failed_count']}"
    )
    if plan["pending_count"] == 0:
        return 0

    cmd = [
        sys.executable,
        "scripts/scrape_profiles_from_search.py",
        "--players-file",
        str(args.players_file),
        "--profile-dir",
        str(args.profile_dir),
        "--db-path",
        str(args.db_path),
    ]
    if args.headless:
        cmd.append("--headless")
    if args.cdp_port is not None:
        cmd += ["--cdp-port", str(args.cdp_port)]
    if args.limit:
        print("[WARN] scrape-players --limit only limits generated players file in future; current file contains all pending names")
    if args.force:
        cmd.append("--force")
    return run_command(cmd, dry_run=args.dry_run)


def run_translate(args: argparse.Namespace) -> int:
    commands = [
        [
            sys.executable,
            "scripts/translate_events.py",
            "--orig-dir",
            str(args.events_orig_dir),
            "--cn-dir",
            str(args.events_cn_dir),
        ],
        [
            sys.executable,
            "scripts/translate_matches.py",
            "--orig-dir",
            str(args.matches_orig_dir),
            "--cn-dir",
            str(args.matches_cn_dir),
        ],
        [
            sys.executable,
            "scripts/translate_profiles.py",
            "--orig-dir",
            str(args.profiles_orig_dir),
            "--cn-dir",
            str(args.profiles_cn_dir),
            "--career-best-rank-lte",
            str(args.career_best_rank_lte),
        ],
    ]
    if args.since:
        for cmd in commands:
            cmd += ["--since", args.since]

    for cmd in commands:
        rc = run_command(cmd, dry_run=args.dry_run)
        if rc != 0:
            return rc
    return 0


def run_import(args: argparse.Namespace) -> int:
    if bool(args.event_file) == bool(args.event_id):
        print("Exactly one of --event-file or --event-id is required")
        return 2
    cmd = ["scripts/run_import_wtt_events.sh", "--source-dir", str(args.source_dir)]
    if args.event_file:
        cmd += ["--event-file", str(args.event_file)]
    else:
        cmd += ["--event-id", *[str(event_id) for event_id in args.event_id]]
    if args.skip_same_name_player_matches:
        cmd.append("--skip-same-name-player-matches")
    return run_command(cmd, dry_run=args.dry_run)


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "plan":
        return run_plan(args)
    if args.command == "scrape-events":
        return run_scrape_events(args)
    if args.command == "scrape-matches":
        return run_scrape_matches(args)
    if args.command == "scrape-players":
        return run_scrape_players(args)
    if args.command == "translate":
        return run_translate(args)
    if args.command == "import":
        return run_import(args)
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
