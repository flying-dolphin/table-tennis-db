#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refresh WTT upcoming/in-progress event schedules.

Task C.1 orchestration:
  1. Select events with lifecycle_status in ('draw_published', 'in_progress').
  2. Scrape WTT event data into data/live_event_data/{event_id}/.
  3. Re-import GetEventSchedule.json via scripts/runtime/import_wtt_event.py.
  4. Capture/import Stage Groups pool standings into event_group_standings.

This script intentionally does not promote rows to historical tables and does
not parse detailed score cards yet.
"""

from __future__ import annotations

import argparse
import io
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

try:
    from db import config

    PROJECT_ROOT = Path(config.PROJECT_ROOT)
    DEFAULT_DB_PATH = Path(config.DB_PATH)
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"

SCRIPT_ROOT = Path(__file__).resolve().parent
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"
SCRAPE_SCRIPT = SCRIPT_ROOT / "scrape_wtt_event.py"
IMPORT_SCRIPT = SCRIPT_ROOT / "import_wtt_event.py"
POOL_STANDINGS_SCRAPE_SCRIPT = SCRIPT_ROOT / "scrape_wtt_pool_standings.py"
POOL_STANDINGS_IMPORT_SCRIPT = SCRIPT_ROOT / "import_wtt_pool_standings.py"


@dataclass
class EventRow:
    event_id: int
    name: str
    lifecycle_status: str
    start_date: str | None
    end_date: str | None


@dataclass
class EventResult:
    event_id: int
    name: str
    scrape_ok: bool | None
    import_ok: bool | None
    matches: int | None = None
    error: str | None = None


def get_events(
    db_path: Path,
    *,
    event_id: int | None,
    limit: int | None,
) -> list[EventRow]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        if event_id is not None:
            rows = cursor.execute(
                """
                SELECT event_id, name, lifecycle_status, start_date, end_date
                FROM events
                WHERE event_id = ?
                """,
                (event_id,),
            ).fetchall()
        else:
            sql = """
                SELECT event_id, name, lifecycle_status, start_date, end_date
                FROM events
                WHERE lifecycle_status IN ('draw_published', 'in_progress')
                ORDER BY
                    CASE lifecycle_status
                        WHEN 'in_progress' THEN 0
                        WHEN 'draw_published' THEN 1
                        ELSE 2
                    END,
                    start_date IS NULL,
                    start_date,
                    event_id
            """
            if limit is not None:
                sql += " LIMIT ?"
                rows = cursor.execute(sql, (limit,)).fetchall()
            else:
                rows = cursor.execute(sql).fetchall()

        return [
            EventRow(
                event_id=int(row[0]),
                name=row[1],
                lifecycle_status=row[2],
                start_date=row[3],
                end_date=row[4],
            )
            for row in rows
        ]
    finally:
        conn.close()


def count_schedule_matches(db_path: Path, event_id: int) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(1) FROM event_schedule_matches WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        return int(row[0])
    finally:
        conn.close()


def run_command(cmd: list[str], *, cwd: Path, verbose: bool) -> subprocess.CompletedProcess[str]:
    if verbose:
        print("  $ " + " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=None if verbose else subprocess.PIPE,
        stderr=None if verbose else subprocess.PIPE,
        check=False,
    )


def stage_slug(stage_label: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in stage_label).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "unknown_stage"


def scrape_event(
    event: EventRow,
    *,
    live_event_data_root: Path,
    sub_events: list[str],
    verbose: bool,
) -> tuple[bool, str | None]:
    cmd = [
        sys.executable,
        str(SCRAPE_SCRIPT),
        "--event-id",
        str(event.event_id),
        "--live-event-data-root",
        str(live_event_data_root),
        "--sub-events",
        *sub_events,
    ]
    completed = run_command(cmd, cwd=PROJECT_ROOT, verbose=verbose)
    if completed.returncode == 0:
        return True, None
    return False, (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"


def import_event(
    event: EventRow,
    *,
    db_path: Path,
    live_event_data_root: Path,
    dry_run: bool,
    verbose: bool,
) -> tuple[bool, str | None]:
    cmd = [
        sys.executable,
        str(IMPORT_SCRIPT),
        "--event",
        str(event.event_id),
        "--db",
        str(db_path),
        "--live-event-data-root",
        str(live_event_data_root),
    ]
    if dry_run:
        cmd.append("--dry-run")
    if verbose:
        cmd.append("--verbose")

    completed = run_command(cmd, cwd=PROJECT_ROOT, verbose=verbose)
    if completed.returncode == 0:
        return True, None
    return False, (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"


def scrape_pool_standings(
    event: EventRow,
    *,
    live_event_data_root: Path,
    stage_label: str,
    verbose: bool,
) -> tuple[bool, Path | None, str | None]:
    output_dir = live_event_data_root / str(event.event_id) / "group_standings" / stage_slug(stage_label)
    cmd = [
        sys.executable,
        str(POOL_STANDINGS_SCRAPE_SCRIPT),
        "--event-id",
        str(event.event_id),
        "--stage-label",
        stage_label,
        "--live-event-data-root",
        str(live_event_data_root),
    ]
    if verbose:
        cmd.append("--verbose")

    completed = run_command(cmd, cwd=PROJECT_ROOT, verbose=verbose)
    if completed.returncode != 0:
        return False, None, (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"
    if output_dir.exists():
        return True, output_dir, None
    return False, None, f"pool standings scrape completed but produced no output dir: {output_dir}"


def import_pool_standings(
    *,
    db_path: Path,
    input_dir: Path,
    verbose: bool,
) -> tuple[bool, str | None]:
    cmd = [
        sys.executable,
        str(POOL_STANDINGS_IMPORT_SCRIPT),
        "--input-dir",
        str(input_dir),
        "--db-path",
        str(db_path),
    ]
    completed = run_command(cmd, cwd=PROJECT_ROOT, verbose=verbose)
    if completed.returncode == 0:
        return True, None
    return False, (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"


def refresh_event(
    event: EventRow,
    *,
    db_path: Path,
    live_event_data_root: Path,
    sub_events: list[str],
    standings_stages: list[str],
    skip_scrape: bool,
    dry_run: bool,
    verbose: bool,
) -> EventResult:
    print(f"\n=== {event.event_id} {event.name} [{event.lifecycle_status}] ===")

    if dry_run:
        print("  dry-run: scrape/import commands will not change persisted data")

    scrape_ok: bool | None = None
    if skip_scrape:
        print("  scrape: skipped")
    elif dry_run:
        print("  scrape: dry-run skipped")
        scrape_ok = None
    else:
        print("  scrape: running")
        scrape_ok, err = scrape_event(event, live_event_data_root=live_event_data_root, sub_events=sub_events, verbose=verbose)
        if not scrape_ok:
            print("  scrape: failed")
            return EventResult(event.event_id, event.name, scrape_ok, None, error=err)
        print("  scrape: ok")

    print("  import: running")
    import_ok, err = import_event(
        event,
        db_path=db_path,
        live_event_data_root=live_event_data_root,
        dry_run=dry_run,
        verbose=verbose,
    )
    if not import_ok:
        print("  import: failed")
        return EventResult(event.event_id, event.name, scrape_ok, import_ok, error=err)

    matches = None if dry_run else count_schedule_matches(db_path, event.event_id)
    print(f"  import: ok" + (f" ({matches} matches)" if matches is not None else ""))

    if skip_scrape:
        print("  standings: skipped (skip-scrape)")
    elif dry_run:
        print("  standings: skipped (dry-run)")
    else:
        for stage_label in standings_stages:
            print(f"  standings [{stage_label}]: running")
            standings_scrape_ok, input_dir, scrape_err = scrape_pool_standings(
                event,
                live_event_data_root=live_event_data_root,
                stage_label=stage_label,
                verbose=verbose,
            )
            if not standings_scrape_ok or input_dir is None:
                print(f"  standings [{stage_label}]: scrape failed")
                if scrape_err:
                    first_line = scrape_err.splitlines()[0]
                    print(f"    warning: {first_line}")
                continue

            standings_import_ok, import_err = import_pool_standings(
                db_path=db_path,
                input_dir=input_dir,
                verbose=verbose,
            )
            if not standings_import_ok:
                print(f"  standings [{stage_label}]: import failed")
                if import_err:
                    first_line = import_err.splitlines()[0]
                    print(f"    warning: {first_line}")
                continue

            print(f"  standings [{stage_label}]: ok")
    return EventResult(event.event_id, event.name, scrape_ok, import_ok, matches=matches)


def print_summary(results: list[EventResult]) -> None:
    scraped_ok = sum(1 for r in results if r.scrape_ok is True)
    scraped_failed = sum(1 for r in results if r.scrape_ok is False)
    imported_ok = sum(1 for r in results if r.import_ok is True)
    imported_failed = sum(1 for r in results if r.import_ok is False)

    print("\n=== Summary ===")
    print(f"events: {len(results)}")
    print(f"scraped: {scraped_ok} ok, {scraped_failed} failed")
    print(f"imported: {imported_ok} ok, {imported_failed} failed")

    failures = [r for r in results if r.error]
    if failures:
        print("\nFailures:")
        for result in failures:
            first_line = (result.error or "").splitlines()[0]
            print(f"  {result.event_id}: {first_line}")

    imported = [r for r in results if r.import_ok and r.matches is not None]
    if imported:
        print("\nImported matches:")
        for result in imported:
            print(f"  {result.event_id}: {result.matches}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily refresh for WTT upcoming event schedules.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--live-event-data-root", type=Path, default=DEFAULT_LIVE_EVENT_DATA_DIR)
    parser.add_argument("--raw-root", dest="legacy_live_event_data_root", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--standings-root", dest="legacy_standings_root", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--event", type=int, default=None, help="Refresh one event_id only.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-scrape", action="store_true", help="Reuse existing data/live_event_data JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Do not scrape; run import in dry-run mode.")
    parser.add_argument(
        "--sub-events",
        nargs="+",
        default=["MTEAM", "WTEAM"],
        help="WTT bracket document sub-events for scrape_wtt_event.py.",
    )
    parser.add_argument(
        "--standings-stages",
        nargs="+",
        default=["Stage 1B(Groups)", "Stage 1A(Groups)"],
        help="Stage Groups tabs to capture/import as official pool standings.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    live_event_data_root = args.legacy_live_event_data_root or args.live_event_data_root

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1
    if not SCRAPE_SCRIPT.exists():
        print(f"Scrape script not found: {SCRAPE_SCRIPT}", file=sys.stderr)
        return 1
    if not IMPORT_SCRIPT.exists():
        print(f"Import script not found: {IMPORT_SCRIPT}", file=sys.stderr)
        return 1
    if not POOL_STANDINGS_SCRAPE_SCRIPT.exists():
        print(f"Pool standings scrape script not found: {POOL_STANDINGS_SCRAPE_SCRIPT}", file=sys.stderr)
        return 1
    if not POOL_STANDINGS_IMPORT_SCRIPT.exists():
        print(f"Pool standings import script not found: {POOL_STANDINGS_IMPORT_SCRIPT}", file=sys.stderr)
        return 1

    events = get_events(args.db, event_id=args.event, limit=args.limit)
    if not events:
        print("No events to refresh.")
        return 0

    print(f"Refreshing {len(events)} event(s).")
    results: list[EventResult] = []
    for event in events:
        result = refresh_event(
            event,
            db_path=args.db,
            live_event_data_root=live_event_data_root,
            sub_events=args.sub_events,
            standings_stages=args.standings_stages,
            skip_scrape=args.skip_scrape,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        results.append(result)

    print_summary(results)
    return 1 if any(r.error for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
