#!/usr/bin/env python3
"""Capture the official Asian Games table-tennis schedule.

The public schedule is authored in Asia/Tokyo.  The two compatibility outputs
use Beijing wall-clock time, matching the rest of this project's UI/data files.
Official decoded responses are retained under ``data/asian_games/2026/raw``.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.asian_games_2026.common import (
    DISPLAY_SCHEDULE_PATH,
    EVENT_SCHEDULE_PATH,
    RAW_ROOT,
    api_path,
    atomic_write_json,
    convert_source_timestamp,
    fetch_json,
    round_meta,
    sub_event_code,
    translate_phase,
)


def parse_schedule_days(payload: Any) -> list[str]:
    if not isinstance(payload, list):
        raise ValueError("schedule/days response is not an array")
    days: list[str] = []
    for item in payload:
        raw = item.get("raw") if isinstance(item, dict) else None
        if not isinstance(raw, str):
            continue
        datetime.strptime(raw, "%Y-%m-%d")
        if raw not in days:
            days.append(raw)
    if not days:
        raise ValueError("official API returned no table-tennis competition days")
    return days


def fetch_schedule(*, raw_root: Path = RAW_ROOT) -> dict[str, list[dict[str, Any]]]:
    days_payload = fetch_json(api_path("/schedule/days"))
    atomic_write_json(raw_root / "schedule" / "days.json", days_payload)
    rows_by_date: dict[str, list[dict[str, Any]]] = {}
    for day in parse_schedule_days(days_payload):
        payload = fetch_json(api_path(f"/schedule/daily/{day}"))
        if not isinstance(payload, list):
            raise ValueError(f"daily schedule response for {day} is not an array")
        atomic_write_json(raw_root / "schedule" / f"{day}.json", payload)
        rows_by_date[day] = [item for item in payload if isinstance(item, dict)]
    return rows_by_date


def _parsed_round(event_desc: str, phase_desc: str) -> dict[str, str] | None:
    event_code = sub_event_code(event_desc)
    stage_code, round_code, _ = round_meta(phase_desc)
    if event_code == "UNKNOWN":
        return None
    return {
        "sub_event_code": event_code,
        "stage_code": stage_code,
        "round_code": round_code,
    }


def build_schedule(rows_by_date: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    slots: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
    for rows in rows_by_date.values():
        for row in sorted(rows, key=lambda value: str(value.get("DateTimeRaw") or "")):
            if row.get("isH2H") is not True:
                continue
            raw_datetime = str(row.get("DateTimeRaw") or "").strip()
            event_desc = str(row.get("EventDesc") or "").strip()
            phase_desc = str(row.get("PhaseDesc") or "").strip()
            venue = str(row.get("VenueDesc") or "").strip()
            if not raw_datetime or not event_desc or not phase_desc:
                continue
            # Group on the source instant before converting its presentation.
            converted = convert_source_timestamp(raw_datetime)
            key = (converted.utc, venue)
            slot = slots.setdefault(
                key,
                {
                    "beijing": converted.beijing,
                    "events": [],
                    "parsed": [],
                    "parsed_keys": set(),
                },
            )
            event_zh = translate_phase(event_desc, phase_desc)
            if event_zh not in slot["events"]:
                slot["events"].append(event_zh)
            parsed = _parsed_round(event_desc, phase_desc)
            if parsed:
                parsed_key = tuple(parsed.values())
                if parsed_key not in slot["parsed_keys"]:
                    slot["parsed_keys"].add(parsed_key)
                    slot["parsed"].append(parsed)

    output: list[dict[str, Any]] = []
    for (_, venue), slot in sorted(slots.items(), key=lambda item: item[0]):
        beijing = datetime.fromisoformat(slot["beijing"])
        output.append(
            {
                "日期": f"{beijing.month}月{beijing.day}日",
                "场次": "",
                "时间": beijing.strftime("%H:%M"),
                "赛事": slot["events"],
                "球台": "",
                "场馆": venue,
                "_parsed": slot["parsed"],
            }
        )
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="抓取 2026 亚运会乒乓球赛程")
    parser.add_argument("--output", type=Path, default=DISPLAY_SCHEDULE_PATH)
    parser.add_argument("--event-schedule-output", type=Path, default=EVENT_SCHEDULE_PATH)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        schedule = build_schedule(fetch_schedule(raw_root=args.raw_root))
        if not schedule:
            raise ValueError("no competition schedule rows were found")
        atomic_write_json(args.output, schedule)
        atomic_write_json(args.event_schedule_output, schedule)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"赛程抓取失败：{exc}", file=sys.stderr)
        return 1
    print(f"已写入 {args.output} 和 {args.event_schedule_output}（{len(schedule)} 个时段）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
