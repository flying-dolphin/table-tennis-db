#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导入当前赛事完整日程到 current_event_session_schedule。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import wtt_import_shared as legacy

DEFAULT_DB_PATH = legacy.DEFAULT_DB_PATH
DEFAULT_SCHEDULE_DIR = legacy.DEFAULT_SCHEDULE_DIR


def upsert_session_rows(cursor: sqlite3.Cursor, event_id: int, sessions: list[dict]) -> int:
    cursor.execute("DELETE FROM current_event_session_schedule WHERE event_id = ?", (event_id,))
    cursor.executemany(
        """
        INSERT INTO current_event_session_schedule (
            event_id, day_index, session_index, local_date,
            session_title, start_time, morning_session_start, afternoon_session_start,
            venue_raw, table_count, table_label, raw_sub_events_text, parsed_rounds_json,
            updated_at
        ) VALUES (
            :event_id, :day_index, :session_index, :local_date,
            :session_title, :start_time, :morning_session_start, :afternoon_session_start,
            :venue_raw, :table_count, :table_label, :raw_sub_events_text, :parsed_rounds_json,
            datetime('now')
        )
        """,
        sessions,
    )
    return len(sessions)


def import_one_file(
    cursor: sqlite3.Cursor, path: Path, *, dry_run: bool, verbose: bool
) -> dict:
    event_id = int(path.stem)
    event = legacy.get_event(cursor, event_id)
    if not event:
        return {"event_id": event_id, "error": "events 表无此 event_id"}

    raw_days = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_days, list):
        return {"event_id": event_id, "error": "JSON 顶层应为数组"}

    base_year = event["year"]
    sessions: list[dict] = []
    prev_date = None
    last_date = None
    day_index = 0
    parse_errors: list[str] = []
    unmatched_segments: list[str] = []

    for idx, day in enumerate(raw_days, start=1):
        try:
            local_date = legacy.parse_local_date(day["日期"], base_year, prev_date)
        except (KeyError, ValueError) as exc:
            parse_errors.append(f"row#{idx}: {exc}")
            continue
        prev_date = local_date
        # day_index 按不同日期递增；per-session 时同一天多行共享同一 day_index
        if local_date != last_date:
            day_index += 1
            last_date = local_date

        venue_raw = (day.get("场馆") or "").strip() or None
        raw_segments: list[str] = day.get("赛事") or []

        # parsed_rounds_json：优先用 scrape 产出的机器可读 _parsed（英文解析，最可靠），
        # 否则回退到对中文 赛事 文案的解析（旧的 per-day 文件，如 3216.json）。
        parsed_field = day.get("_parsed")
        if isinstance(parsed_field, list):
            parsed = parsed_field
        else:
            parsed = []
            for seg in raw_segments:
                entries = legacy.parse_event_segment(seg)
                if not entries and seg.strip():
                    unmatched_segments.append(seg)
                parsed.extend(entries)

        # per-session：时间是单字符串 / 含 场次 / 含 _parsed；per-day：时间是 [首场, 末场] 列表
        is_per_session = (
            "场次" in day
            or isinstance(parsed_field, list)
            or isinstance(day.get("时间"), str)
        )
        if is_per_session:
            start_time = (day.get("时间") or "").strip() or None
            session_title = (day.get("场次") or "").strip() or None
            table_label = (day.get("球台") or "").strip() or None
            # 把 start_time 同时写进 morning_session_start，使 cron 生成器无需改造即可工作
            morning_start = start_time
            afternoon_start = None
            table_count = None
        else:
            morning_start, afternoon_start = legacy.parse_time_window(day.get("时间"))
            session_title = None
            start_time = None
            table_label = None
            table_count = day.get("球台数")
            if isinstance(table_count, str):
                table_count = int(table_count) if table_count.isdigit() else None

        sessions.append(
            {
                "event_id": event_id,
                "day_index": day_index,
                "session_index": idx,
                "local_date": local_date.isoformat(),
                "session_title": session_title,
                "start_time": start_time,
                "morning_session_start": morning_start,
                "afternoon_session_start": afternoon_start,
                "venue_raw": venue_raw,
                "table_count": table_count,
                "table_label": table_label,
                "raw_sub_events_text": " | ".join(raw_segments) if raw_segments else None,
                "parsed_rounds_json": json.dumps(parsed, ensure_ascii=False),
            }
        )

    if not dry_run:
        upsert_session_rows(cursor, event_id, sessions)

    if verbose:
        for session in sessions:
            time_repr = session["start_time"] or (
                f"{session['morning_session_start']}-{session['afternoon_session_start']}"
            )
            print(
                f"    #{session['session_index']:>2} day{session['day_index']:>2} {session['local_date']} "
                f"{session['session_title'] or ''} {time_repr} "
                f"@{session['venue_raw']!r} tables={session['table_label'] or session['table_count']}"
            )

    return {
        "event_id": event_id,
        "name": event["name"],
        "days": len(sessions),
        "parse_errors": parse_errors,
        "unmatched_segments": unmatched_segments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import current-event session schedule JSONs.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dir", type=Path, default=DEFAULT_SCHEDULE_DIR, help="data/event_schedule/ 目录")
    parser.add_argument("--event", type=int, default=None, help="只导入指定 event_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.dir.exists():
        print(f"目录不存在: {args.dir}", file=sys.stderr)
        return 1

    files = [args.dir / f"{args.event}.json"] if args.event else sorted(args.dir.glob("*.json"))
    files = [path for path in files if path.exists()]
    if not files:
        print("未找到可导入的 schedule 文件", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        reports = []
        for path in files:
            report = import_one_file(cursor, path, dry_run=args.dry_run, verbose=args.verbose)
            reports.append(report)
            if report.get("error"):
                print(f"[{report['event_id']}] ERROR: {report['error']}")
            else:
                print(f"[{report['event_id']}] {report['name']} -> {report['days']} days")
                if report["parse_errors"]:
                    print(f"    parse_errors: {len(report['parse_errors'])}")
                if report["unmatched_segments"]:
                    print(f"    unmatched_segments: {len(report['unmatched_segments'])}")

        if args.dry_run:
            conn.rollback()
            print("dry-run: rolled back")
        else:
            conn.commit()
            print(f"committed to {args.db}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
