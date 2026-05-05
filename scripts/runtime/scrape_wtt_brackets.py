#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只抓 WTT 事件的 brackets 数据。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wtt_scrape_shared import DEFAULT_LIVE_EVENT_DATA_DIR, DEFAULT_SUB_EVENTS, scrape_brackets_only


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
    args = ap.parse_args()

    event_dir = Path(args.live_event_data_root) / str(args.event_id)
    print(f"Scrape WTT brackets {args.event_id} -> {event_dir}")
    summary = scrape_brackets_only(args.event_id, args.sub_events, event_dir)
    print()
    print(f"Done: {len(summary['files'])} files, {len(summary['errors'])} errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
