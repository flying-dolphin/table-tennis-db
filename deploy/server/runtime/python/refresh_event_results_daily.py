#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refresh WTT upcoming/in-progress event schedules.

Task C.1 orchestration:
  1. Select events with lifecycle_status in ('draw_published', 'in_progress').
  2. Scrape WTT raw JSON into data/wtt_raw/{event_id}/.
  3. Re-import GetEventSchedule.json via scripts/db/import_wtt_event.py.
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
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = RUNTIME_ROOT / "data" / "db" / "ittf.db"
DEFAULT_RAW_ROOT = RUNTIME_ROOT / "data" / "wtt_raw"
DEFAULT_STANDINGS_ROOT = RUNTIME_ROOT / "data" / "wtt_pool_standings_analysis"
DEFAULT_MAPPING_PATH = RUNTIME_ROOT / "data" / "stage_round_mapping.json"
SCRAPE_SCRIPT = PYTHON_ROOT / "scrape_wtt_event.py"
IMPORT_SCRIPT = PYTHON_ROOT / "import_wtt_event.py"
POOL_STANDINGS_SCRAPE_SCRIPT = PROJECT_ROOT / "scripts" / "scrape_wtt_pool_standings.py"
POOL_STANDINGS_IMPORT_SCRIPT = PROJECT_ROOT / "scripts" / "db" / "import_wtt_pool_standings.py"


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


def list_analysis_run_dirs(output_root: Path, event_id: int) -> dict[str, Path]:
    event_root = output_root / str(event_id)
    if not event_root.exists():
        return {}
    return {child.name: child for child in event_root.iterdir() if child.is_dir()}


def build_run_dir(raw_root: Path, event_id: int) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return raw_root / str(event_id) / "runs" / timestamp


def scrape_event(
    event: EventRow,
    *,
    run_dir: Path,
    sub_events: list[str],
    verbose: bool,
) -> tuple[bool, str | None]:
    cmd = [
        sys.executable,
        str(SCRAPE_SCRIPT),
        "--event-id",
        str(event.event_id),
        "--out-dir",
        str(run_dir),
        "--sub-events",
        *sub_events,
    ]
    completed = run_command(cmd, cwd=RUNTIME_ROOT, verbose=verbose)
    if completed.returncode == 0:
        return True, None
    return False, (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"


def import_event(
    event: EventRow,
    *,
    db_path: Path,
    raw_root: Path,
    mapping_path: Path,
    event_dir: Path | None,
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
        "--raw-root",
        str(raw_root),
        "--mapping",
        str(mapping_path),
    ]
    if event_dir is not None:
        cmd.extend(["--event-dir", str(event_dir)])
    if dry_run:
        cmd.append("--dry-run")
    if verbose:
        cmd.append("--verbose")

    completed = run_command(cmd, cwd=RUNTIME_ROOT, verbose=verbose)
    if completed.returncode == 0:
        return True, None
    return False, (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"


def scrape_pool_standings(
    event: EventRow,
    *,
    output_root: Path,
    stage_label: str,
    verbose: bool,
) -> tuple[bool, Path | None, str | None]:
    before = list_analysis_run_dirs(output_root, event.event_id)
    cmd = [
        sys.executable,
        str(POOL_STANDINGS_SCRAPE_SCRIPT),
        "--event-id",
        str(event.event_id),
        "--stage-label",
        stage_label,
        "--output-root",
        str(output_root),
    ]
    if verbose:
        cmd.append("--verbose")

    completed = run_command(cmd, cwd=PROJECT_ROOT, verbose=verbose)
    if completed.returncode != 0:
        return False, None, (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"

    after = list_analysis_run_dirs(output_root, event.event_id)
    new_names = sorted(set(after) - set(before))
    if new_names:
        return True, after[new_names[-1]], None
    if after:
        latest_name = sorted(after)[-1]
        return True, after[latest_name], None
    return False, None, "pool standings scrape completed but produced no output directory"


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
    raw_root: Path,
    standings_root: Path,
    mapping_path: Path,
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
    event_dir: Path | None = None
    if skip_scrape:
        print("  scrape: skipped")
    elif dry_run:
        print("  scrape: dry-run skipped")
        scrape_ok = None
    else:
        event_dir = build_run_dir(raw_root, event.event_id)
        print(f"  scrape dir: {event_dir}")
        print("  scrape: running")
        scrape_ok, err = scrape_event(event, run_dir=event_dir, sub_events=sub_events, verbose=verbose)
        if not scrape_ok:
            print("  scrape: failed")
            return EventResult(event.event_id, event.name, scrape_ok, None, error=err)
        print("  scrape: ok")

    print("  import: running")
    import_ok, err = import_event(
        event,
        db_path=db_path,
        raw_root=raw_root,
        mapping_path=mapping_path,
        event_dir=event_dir,
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
                output_root=standings_root,
                stage_label=stage_label,
                verbose=verbose,
            )
            if not standings_scrape_ok or input_dir is None:
                print(f"  standings [{stage_label}]: scrape failed")
                if scrape_err:
                    print(f"    warning: {scrape_err.splitlines()[0]}")
                continue

            standings_import_ok, import_err = import_pool_standings(
                db_path=db_path,
                input_dir=input_dir,
                verbose=verbose,
            )
            if not standings_import_ok:
                print(f"  standings [{stage_label}]: import failed")
                if import_err:
                    print(f"    warning: {import_err.splitlines()[0]}")
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
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--standings-root", type=Path, default=DEFAULT_STANDINGS_ROOT)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--event", type=int, default=None, help="Refresh one event_id only.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-scrape", action="store_true", help="Reuse existing data/wtt_raw JSON.")
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

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1
    if not SCRAPE_SCRIPT.exists():
        print(f"Scrape script not found: {SCRAPE_SCRIPT}", file=sys.stderr)
        return 1
    if not IMPORT_SCRIPT.exists():
        print(f"Import script not found: {IMPORT_SCRIPT}", file=sys.stderr)
        return 1
    if not args.mapping.exists():
        print(f"Mapping file not found: {args.mapping}", file=sys.stderr)
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
            raw_root=args.raw_root,
            standings_root=args.standings_root,
            mapping_path=args.mapping,
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
