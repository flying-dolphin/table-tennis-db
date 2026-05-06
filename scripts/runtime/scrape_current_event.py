#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""当前赛事抓取总入口。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from wtt_scrape_shared import DEFAULT_LIVE_EVENT_DATA_DIR, DEFAULT_SUB_EVENTS

SCRIPT_DIR = Path(__file__).resolve().parent


def run_step(cmd: list[str]) -> int:
    print(f"> {' '.join(cmd)}")
    completed = subprocess.run(cmd)
    return int(completed.returncode)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-id", type=int, required=True)
    ap.add_argument(
        "--sources",
        nargs="+",
        choices=("schedule", "brackets", "live", "completed", "standings"),
        default=["schedule", "brackets", "live", "completed", "standings"],
        help="抓取源列表，默认全部执行",
    )
    ap.add_argument(
        "--sub-events",
        nargs="+",
        default=DEFAULT_SUB_EVENTS,
        help="schedule/brackets 使用的 sub-event codes，默认 MTEAM WTEAM",
    )
    ap.add_argument(
        "--live-event-data-root",
        default=str(DEFAULT_LIVE_EVENT_DATA_DIR),
        help="进行中赛事数据根目录",
    )
    ap.add_argument("--stage-label", default="Groups", help="standings 页签名称，默认 Groups")
    ap.add_argument("--cdp-port", type=int, default=9222)
    ap.add_argument("--use-cdp", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--with-debug-files", action="store_true", help="live 抓取时输出调试文件")
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
    if args.use_cdp:
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
            cmd = base + [str(SCRIPT_DIR / "scrape_wtt_brackets.py")] + root_args + ["--sub-events", *args.sub_events]
        elif source == "live":
            cmd = base + [str(SCRIPT_DIR / "scrape_wtt_live_matches.py")] + root_args + browser_args
            if args.with_debug_files:
                cmd.append("--with-debug-files")
        elif source == "completed":
            cmd = base + [str(SCRIPT_DIR / "scrape_wtt_official_results.py")] + root_args
        else:
            cmd = (
                base
                + [str(SCRIPT_DIR / "scrape_wtt_pool_standings.py")]
                + root_args
                + ["--stage-label", args.stage_label]
                + browser_args
            )
        rc = run_step(cmd)
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":
    sys.exit(main())
