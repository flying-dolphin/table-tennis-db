#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""当前赛事导入总入口。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"
DEFAULT_EVENT_SCHEDULE_DIR = PROJECT_ROOT / "data" / "event_schedule"
SCRIPT_DIR = Path(__file__).resolve().parent


def run_step(cmd: list[str]) -> int:
    print(f"> {' '.join(cmd)}")
    completed = subprocess.run(cmd)
    return int(completed.returncode)


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
            str(SCRIPT_DIR / "import_current_event_schedule.py"),
            "--event-id",
            str(args.event_id),
            *db_args,
            *live_args,
        ]
        rc = run_step(cmd)
        if rc != 0:
            return rc

    if "standings" in args.sources:
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
