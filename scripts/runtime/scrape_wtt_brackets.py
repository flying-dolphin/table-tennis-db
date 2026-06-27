#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只抓 WTT 事件的 brackets 数据。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wtt_scrape_shared import (
    DEFAULT_LIVE_EVENT_DATA_DIR,
    discover_event_sub_events,
    resolve_bracket_sub_events,
    scrape_brackets_only,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-id", type=int, required=True)
    ap.add_argument(
        "--sub-events",
        nargs="+",
        default=None,
        help="WTT bracket sub-event codes; omitted means derive from data/event_schedule/{event_id}.json",
    )
    ap.add_argument(
        "--live-event-data-root",
        default=str(DEFAULT_LIVE_EVENT_DATA_DIR),
        help="进行中赛事数据根目录",
    )
    args = ap.parse_args()

    event_dir = Path(args.live_event_data_root) / str(args.event_id)
    print(f"Scrape WTT brackets {args.event_id} -> {event_dir}")
    sub_events = args.sub_events
    if sub_events is None:
        discovered = discover_event_sub_events(args.event_id)
        sub_events = resolve_bracket_sub_events(discovered)
        if not sub_events:
            source = discovered.source_path
            reason = "missing" if not discovered.source_exists else "no supported sub-events"
            print(f"Skip brackets: {reason} in {source}")
    summary = scrape_brackets_only(args.event_id, sub_events, event_dir)
    print()
    print(f"Done: {len(summary['files'])} files, {len(summary['errors'])} errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
