#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只抓 WTT 事件的 GetOfficialResult.json。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wtt_scrape_shared import (
    DEFAULT_LIVE_EVENT_DATA_DIR,
    OFFICIAL_RESULTS_PAGE_SIZE,
    scrape_official_results_only,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-id", type=int, required=True)
    ap.add_argument(
        "--live-event-data-root",
        default=str(DEFAULT_LIVE_EVENT_DATA_DIR),
        help="进行中赛事数据根目录",
    )
    ap.add_argument(
        "--page-size",
        type=int,
        default=OFFICIAL_RESULTS_PAGE_SIZE,
        help="每页请求条数，默认 100",
    )
    args = ap.parse_args()

    event_dir = Path(args.live_event_data_root) / str(args.event_id)
    print(f"Scrape WTT official results {args.event_id} -> {event_dir}")
    summary = scrape_official_results_only(
        args.event_id,
        event_dir,
        page_size=args.page_size,
    )
    print()
    print(f"Done: {len(summary['files'])} file(s), {len(summary['errors'])} error(s)")

    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
