#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""当前赛事抓取总入口。"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from wtt_scrape_shared import DEFAULT_LIVE_EVENT_DATA_DIR, discover_event_sub_events, resolve_standings_team_codes

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-id", type=int, required=True)
    ap.add_argument(
        "--sources",
        nargs="+",
        choices=("schedule", "brackets", "live", "completed", "match_details", "standings"),
        default=["schedule", "brackets", "live", "completed", "match_details", "standings"],
        help="抓取源列表，默认全部执行",
    )
    ap.add_argument(
        "--sub-events",
        nargs="+",
        default=None,
        help="brackets 使用的 sub-event codes；不传则从 data/event_schedule/{event_id}.json 推导",
    )
    ap.add_argument(
        "--live-event-data-root",
        default=str(DEFAULT_LIVE_EVENT_DATA_DIR),
        help="进行中赛事数据根目录",
    )
    ap.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite DB path for DB-backed scrape sources")
    ap.add_argument("--stage-label", default="Groups", help="standings 页签名称，默认 Groups")
    ap.add_argument("--cdp-port", type=int, default=9222)
    ap.add_argument("--use-cdp", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--with-debug-files", action="store_true", help="live 抓取时输出调试文件")
    ap.add_argument("--include-official", action=argparse.BooleanOptionalAction, default=True, help="live 时同时获取最近完成的比赛")
    args = ap.parse_args()

    base = [
        sys.executable,
    ]
    root_args = [
        "--event-id",
        str(args.event_id),
        "--live-event-data-root",
        str(Path(args.live_event_data_root)),
    ]
    browser_args: list[str] = []
    if args.use_cdp or args.cdp_port:
        browser_args.append("--use-cdp")
    if args.headless:
        browser_args.append("--headless")
    if args.verbose:
        browser_args.append("--verbose")
    if args.cdp_port:
        browser_args.extend(["--cdp-port", str(args.cdp_port)])

    for source in args.sources:
        if source == "schedule":
            cmd = base + [str(SCRIPT_DIR / "scrape_wtt_schedule.py")] + root_args
        elif source == "brackets":
            cmd = base + [str(SCRIPT_DIR / "scrape_wtt_brackets.py")] + root_args
            if args.sub_events:
                cmd += ["--sub-events", *args.sub_events]
        elif source == "live":
            live_args = list(root_args)
            if args.include_official:
                live_args.append("--include-official")
            cmd = base + [str(SCRIPT_DIR / "scrape_wtt_live_matches.py")] + live_args + browser_args
            if args.with_debug_files:
                cmd.append("--with-debug-files")
        elif source == "completed":
            cmd = base + [str(SCRIPT_DIR / "scrape_wtt_official_results.py")] + root_args
        elif source == "match_details":
            cmd = base + [str(SCRIPT_DIR / "scrape_wtt_match_details.py")] + root_args + ["--db-path", str(args.db_path)]
        else:
            discovered = discover_event_sub_events(args.event_id)
            team_codes = resolve_standings_team_codes(discovered)
            cmd = (
                base
                + [str(SCRIPT_DIR / "scrape_wtt_pool_standings.py")]
                + root_args
                + ["--stage-label", args.stage_label]
                + ["--team-codes", *team_codes]
                + browser_args
            )
        rc = run_step(cmd)
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":
    sys.exit(main())
