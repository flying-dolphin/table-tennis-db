#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
events_calendar ↔ events 同步。

两步：
1) 对 events_calendar.event_id IS NULL 的行，尝试从 href 中正则提取 eventId
   （形如 https://www.worldtabletennis.com/...?eventId=N
        或 https://www.ittf.com/tournament/N/...）
   提取成功则回填。

2) 对 events_calendar.event_id 已设置但 events 表无对应行的"孤儿"日历项，
   从 events_calendar 字段在 events 表里 seed 一条 lifecycle_status='upcoming'
   的最小 event 行。这样未来赛事就能在 events 表里被签表/赛程数据挂载。

幂等：可重复执行。

用法:
    python backfill_events_calendar_event_id.py
    python backfill_events_calendar_event_id.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import config

    DEFAULT_DB_PATH = Path(config.DB_PATH)
except ImportError:
    DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "db" / "ittf.db"


HREF_EVENT_ID_RE = re.compile(r"(?:[?&]eventId=|/tournament/)(\d+)")


def extract_event_id_from_href(href: str | None) -> int | None:
    if not href:
        return None
    m = HREF_EVENT_ID_RE.search(href)
    return int(m.group(1)) if m else None


# ── Step 1: 从 href 回填 event_id ────────────────────────────────────────────


def backfill_event_id_from_href(cursor: sqlite3.Cursor, *, dry_run: bool) -> dict:
    rows = cursor.execute(
        """
        SELECT calendar_id, name, href
        FROM events_calendar
        WHERE event_id IS NULL AND href IS NOT NULL AND href <> ''
        """
    ).fetchall()

    matched: list[tuple[int, int, str]] = []
    for calendar_id, name, href in rows:
        ev_id = extract_event_id_from_href(href)
        if ev_id is not None:
            matched.append((calendar_id, ev_id, name))

    if not dry_run:
        cursor.executemany(
            "UPDATE events_calendar SET event_id = ? WHERE calendar_id = ?",
            [(ev_id, cid) for cid, ev_id, _ in matched],
        )

    return {"scanned": len(rows), "recovered": len(matched), "samples": matched[:5]}


# ── Step 2: 从 calendar seed events 行 ──────────────────────────────────────


def seed_missing_events(cursor: sqlite3.Cursor, *, dry_run: bool) -> dict:
    rows = cursor.execute(
        """
        SELECT
            ec.event_id,
            ec.year,
            ec.name,
            ec.name_zh,
            ec.event_type,
            ec.event_kind,
            ec.event_category_id,
            cat.category_id        AS category_code,
            cat.category_name_zh   AS category_name_zh,
            ec.start_date,
            ec.end_date,
            ec.location,
            ec.href,
            ec.scraped_at
        FROM events_calendar ec
        LEFT JOIN events e ON e.event_id = ec.event_id
        LEFT JOIN event_categories cat ON cat.id = ec.event_category_id
        WHERE ec.event_id IS NOT NULL AND (e.event_id IS NULL OR e.scraped_at IS NULL)
        """
    ).fetchall()

    if not dry_run:
        cursor.executemany(
            """
            INSERT INTO events (
                event_id, year, name, name_zh, event_type_name, event_kind,
                event_category_id, category_code, category_name_zh,
                total_matches, start_date, end_date, location, href,
                scraped_at, lifecycle_status
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?,
                0, ?, ?, ?, ?,
                ?, 'upcoming'
            )
            ON CONFLICT(event_id) DO UPDATE SET
                scraped_at = excluded.scraped_at
            WHERE events.scraped_at IS NULL
            """,
            rows,
        )

    return {"seeded": len(rows), "samples": [(r[0], r[2], r[9], r[10]) for r in rows[:5]]}


# ── 入口 ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill events_calendar.event_id and seed events.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    try:
        print("=== Step 1: 从 href 回填 events_calendar.event_id ===")
        s1 = backfill_event_id_from_href(cursor, dry_run=args.dry_run)
        print(f"  scanned (null event_id with href): {s1['scanned']}")
        print(f"  recovered: {s1['recovered']}")
        for cid, ev_id, name in s1["samples"]:
            print(f"    calendar_id={cid} -> event_id={ev_id}  {name!r}")

        print("\n=== Step 2: seed 缺失的 events 行（lifecycle_status='upcoming'）===")
        s2 = seed_missing_events(cursor, dry_run=args.dry_run)
        print(f"  seeded: {s2['seeded']}")
        for ev_id, name, start, end in s2["samples"]:
            print(f"    event_id={ev_id} {start}~{end} {name!r}")

        if args.dry_run:
            conn.rollback()
            print("\n[dry-run] no changes committed.")
        else:
            conn.commit()
            print("\n✅ Committed.")

        # 简要快照
        cursor.execute("SELECT lifecycle_status, COUNT(*) FROM events GROUP BY lifecycle_status")
        print("\nevents.lifecycle_status:", list(cursor.fetchall()))

        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
