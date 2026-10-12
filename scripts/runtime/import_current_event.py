#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""当前赛事导入总入口。"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from wtt_scrape_shared import discover_event_sub_events, resolve_standings_team_codes

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"
DEFAULT_EVENT_SCHEDULE_DIR = PROJECT_ROOT / "data" / "event_schedule"
SCRIPT_DIR = Path(__file__).resolve().parent


def log_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_step(cmd: list[str]) -> int:
    rendered = " ".join(cmd)
    started = time.monotonic()
    print(f"[current-event] START {log_timestamp()} command={rendered}", flush=True)
    completed = subprocess.run(cmd)
    rc = int(completed.returncode)
    duration = time.monotonic() - started
    print(f"[current-event] END {log_timestamp()} rc={rc} duration={duration:.2f}s command={rendered}", flush=True)
    if rc != 0:
        print(f"[current-event] ERROR step failed rc={rc} command={rendered}", flush=True)
    return rc


def advance_event_lifecycle(db_path: Path, event_id: int, *, now: datetime | None = None) -> None:
    """Advance started events after import; only promote may mark them completed."""
    with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=rw", uri=True)) as conn, conn:
        row = conn.execute(
            "SELECT lifecycle_status, start_date, time_zone FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if not row or row[0] not in ("upcoming", "draw_published"):
            return
        try:
            start_date = date.fromisoformat((row[1] or "")[:10])
            event_tz = ZoneInfo((row[2] or "").strip())
        except (ValueError, ZoneInfoNotFoundError):
            print(f"[current-event] WARNING lifecycle unchanged event_id={event_id}: invalid start_date/time_zone", flush=True)
            return
        today = (now or datetime.now(timezone.utc)).astimezone(event_tz).date()
        if today < start_date:
            return
        updated = conn.execute(
            "UPDATE events SET lifecycle_status = 'in_progress' "
            "WHERE event_id = ? AND lifecycle_status IN ('upcoming', 'draw_published')",
            (event_id,),
        ).rowcount
        if updated:
            print(f"[current-event] lifecycle event_id={event_id}: {row[0]} -> in_progress (event-local date={today})", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import current event data into current_* tables.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=("session_schedule", "schedule", "standings", "brackets", "live", "completed", "team_ties", "matches"),
        default=["session_schedule", "schedule", "standings", "brackets", "live", "completed"],
        help="导入源列表，默认全部执行；team_ties/matches 为兼容别名，会执行 live 和 completed",
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--live-event-data-root", type=Path, default=DEFAULT_LIVE_EVENT_DATA_DIR)
    parser.add_argument("--event-schedule-dir", type=Path, default=DEFAULT_EVENT_SCHEDULE_DIR)
    args = parser.parse_args()

    py = sys.executable
    db_args = ["--db-path", str(args.db_path.resolve())]
    live_args = ["--live-event-data-root", str(args.live_event_data_root.resolve())]

    if "session_schedule" in args.sources:
        cmd = [
            py,
            str(SCRIPT_DIR / "import_current_event_session_schedule.py"),
            "--db",
            str(args.db_path.resolve()),
            "--dir",
            str(args.event_schedule_dir.resolve()),
            "--event",
            str(args.event_id),
        ]
        rc = run_step(cmd)
        if rc != 0:
            return rc

    if "schedule" in args.sources:
        cmd = [
            py,
            str(SCRIPT_DIR / "import_current_event_matches.py"),
            "--event-id",
            str(args.event_id),
            *db_args,
            *live_args,
        ]
        rc = run_step(cmd)
        if rc != 0:
            return rc

    if "standings" in args.sources:
        discovered = discover_event_sub_events(args.event_id)
        if discovered.source_exists and not resolve_standings_team_codes(discovered):
            print(f"Skip standings import: no team sub-events found in {discovered.source_path}")
        else:
            cmd = [
                py,
                str(SCRIPT_DIR / "import_current_event_group_standings.py"),
                "--db-path",
                str(args.db_path.resolve()),
                "--input-dir",
                str((args.live_event_data_root.resolve() / str(args.event_id))),
                "--event-id",
                str(args.event_id),
            ]
            rc = run_step(cmd)
            if rc != 0:
                return rc

    if "brackets" in args.sources:
        cmd = [
            py,
            str(SCRIPT_DIR / "import_current_event_brackets.py"),
            "--db-path",
            str(args.db_path.resolve()),
            "--input-dir",
            str((args.live_event_data_root.resolve() / str(args.event_id))),
            "--event-id",
            str(args.event_id),
        ]
        rc = run_step(cmd)
        if rc != 0:
            return rc

    sources = set(args.sources)
    if "team_ties" in sources or "matches" in sources:
        sources.update({"live", "completed"})

    if "live" in sources:
        cmd = [
            py,
            str(SCRIPT_DIR / "import_current_event_live.py"),
            "--event-id",
            str(args.event_id),
            *db_args,
            *live_args,
        ]
        rc = run_step(cmd)
        if rc != 0:
            return rc

    if "completed" in sources:
        cmd = [
            py,
            str(SCRIPT_DIR / "import_current_event_official_results.py"),
            "--event-id",
            str(args.event_id),
            *db_args,
            *live_args,
        ]
        rc = run_step(cmd)
        if rc != 0:
            return rc

    advance_event_lifecycle(args.db_path, args.event_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
