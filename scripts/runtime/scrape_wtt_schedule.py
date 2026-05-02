#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只抓 WTT 事件的赛程/签表基础数据。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scrape_wtt_event import (
    DEFAULT_LIVE_EVENT_DATA_DIR,
    DEFAULT_SUB_EVENTS,
    print_stage1a_groups,
    scrape_schedule_bundle,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-id", type=int, required=True)
    ap.add_argument(
        "--sub-events",
        nargs="+",
        default=DEFAULT_SUB_EVENTS,
        help="WTT sub-event codes（5 字符），默认 MTEAM WTEAM",
    )
    ap.add_argument(
        "--live-event-data-root",
        default=str(DEFAULT_LIVE_EVENT_DATA_DIR),
        help="进行中赛事数据根目录",
    )
    ap.add_argument("--print-stage1a", nargs="*", type=int, default=None)
    args = ap.parse_args()

    event_dir = Path(args.live_event_data_root) / str(args.event_id)
    print(f"Scrape WTT schedule {args.event_id} -> {event_dir}")
    summary = scrape_schedule_bundle(args.event_id, args.sub_events, event_dir)
    print()
    print(f"Done: {len(summary['files'])} files, {len(summary['errors'])} errors")

    if args.print_stage1a is not None:
        groups = args.print_stage1a or [1, 2]
        print_stage1a_groups(event_dir, groups)

    return 0


if __name__ == "__main__":
    sys.exit(main())
