#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入赛事完整日程（按日纲要）。

数据源：data/event_schedule/{event_id}.json
JSON 字段（中文键）：
    "日期": "4月28日"            # 月日，年份从 events 表补
    "时间": ["10:00", "17:00"]   # [start, end] HH:MM
    "赛事": ["男团/女团 第1轮", "男团/女团 32强赛", ...]
    "球台数": 12
    "场馆": "铜盒竞技场"

写入 event_session_schedule 表，UNIQUE(event_id, day_index)。

赛事文本解析规则：
    "<sub_events> [<stage>] <round>[ + <round>...]"
    sub_events: "男团/女团" → [MT, WT]；"男单" → [MS]
    stage 关键字：种子排位赛 / 预选赛 / 附加赛 / 排位赛
    round 关键字：决赛 / 铜牌赛 / 半决赛 / 四分之一决赛 / N强赛 / 第N轮

无 stage 关键字且 round 是 R1/R2/R3 时，按团体赛小组阶段当作 MAIN_STAGE1。
其它情况 stage 默认 MAIN_DRAW。

用法:
    python import_session_schedule.py
    python import_session_schedule.py --event 3216
    python import_session_schedule.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = RUNTIME_ROOT / "data" / "db" / "ittf.db"
DEFAULT_SCHEDULE_DIR = RUNTIME_ROOT / "data" / "event_schedule"


# ── 解析字典 ─────────────────────────────────────────────────────────────────


SUB_EVENT_ZH = {
    "男团": "MT",
    "女团": "WT",
    "混团": "XT",
    "男单": "MS",
    "女单": "WS",
    "男双": "MD",
    "女双": "WD",
    "混双": "XD",
}

# 顺序敏感：种子排位赛 必须在 排位赛 前
STAGE_KEYWORDS = [
    ("种子排位赛", "SEEDING_GROUPS"),
    ("预选赛", "PRELIMINARY"),
    ("附加赛", "CONSOLATION"),
    ("排位赛", "POSITION_DRAW"),
]

ROUND_ZH = {
    "决赛": "F",
    "铜牌赛": "BR",
    "半决赛": "SF",
    "四分之一决赛": "QF",
    "256强赛": "R256",
    "128强赛": "R128",
    "64强赛": "R64",
    "48强赛": "R48",
    "32强赛": "R32",
    "24强赛": "R24",
    "16强赛": "R16",
    "8强赛": "R8",
    "第1轮": "R1",
    "第2轮": "R2",
    "第3轮": "R3",
    "第4轮": "R4",
    "第5轮": "R5",
}


DATE_RE = re.compile(r"^(\d{1,2})\s*月\s*(\d{1,2})\s*日$")


# ── 解析函数 ─────────────────────────────────────────────────────────────────


def parse_local_date(raw: str, base_year: int, prev_date: date | None) -> date:
    """'4月28日' + base_year → date；若小于 prev_date，年份 +1（跨年事件）。"""
    m = DATE_RE.match(raw.strip())
    if not m:
        raise ValueError(f"日期格式无法解析: {raw!r}")
    month = int(m.group(1))
    day = int(m.group(2))
    candidate = date(base_year, month, day)
    if prev_date is not None and candidate < prev_date:
        candidate = date(base_year + 1, month, day)
    return candidate


def parse_time_window(times: list[str] | None) -> tuple[str | None, str | None]:
    if not times:
        return None, None
    start = times[0].strip() if len(times) >= 1 else None
    end = times[1].strip() if len(times) >= 2 else None
    return start or None, end or None


def parse_event_segment(segment: str) -> list[dict]:
    """解析一条赛事字符串 → list of {sub_event_code, stage_code, round_code}。"""
    s = segment.strip()
    if not s:
        return []

    # 分离 sub_events 与剩余
    sub_part, _, rest = s.partition(" ")
    if not rest:
        sub_part, rest = s, ""

    sub_event_codes: list[str] = []
    for token in sub_part.split("/"):
        token = token.strip()
        if token in SUB_EVENT_ZH:
            sub_event_codes.append(SUB_EVENT_ZH[token])
    if not sub_event_codes:
        # sub_event 无法识别 → 返回空
        return []

    # 剥 stage 关键字
    stage_code: str | None = None
    rest_stripped = rest.strip()
    for kw, code in STAGE_KEYWORDS:
        if kw in rest_stripped:
            stage_code = code
            rest_stripped = rest_stripped.replace(kw, " ").strip()
            break

    # 拆 round（按 + 或 中文加号）
    round_tokens = [t.strip() for t in re.split(r"\s*[+＋]\s*", rest_stripped) if t.strip()]
    round_codes: list[str] = []
    for tok in round_tokens:
        if tok in ROUND_ZH:
            round_codes.append(ROUND_ZH[tok])

    # 默认 stage
    if stage_code is None:
        if round_codes and all(rc in ("R1", "R2", "R3", "R4", "R5") for rc in round_codes):
            stage_code = "MAIN_STAGE1"
        else:
            stage_code = "MAIN_DRAW"

    if not round_codes:
        # 仅 stage（如 "男团/女团 预选赛"）—— round 留空（用 UNKNOWN）
        round_codes = ["UNKNOWN"]

    out = []
    for sub_code in sub_event_codes:
        for round_code in round_codes:
            out.append({
                "sub_event_code": sub_code,
                "stage_code": stage_code,
                "round_code": round_code,
            })
    return out


# ── DB 写入 ─────────────────────────────────────────────────────────────────


def get_event(cursor: sqlite3.Cursor, event_id: int) -> dict | None:
    row = cursor.execute(
        "SELECT event_id, year, name, start_date, end_date FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "event_id": row[0],
        "year": row[1],
        "name": row[2],
        "start_date": row[3],
        "end_date": row[4],
    }


def upsert_session_rows(cursor: sqlite3.Cursor, event_id: int, sessions: list[dict]) -> int:
    cursor.execute("DELETE FROM event_session_schedule WHERE event_id = ?", (event_id,))
    cursor.executemany(
        """
        INSERT INTO event_session_schedule (
            event_id, day_index, local_date, start_local_time, end_local_time,
            venue_raw, table_count, raw_sub_events_text, parsed_rounds_json,
            updated_at
        ) VALUES (
            :event_id, :day_index, :local_date, :start_local_time, :end_local_time,
            :venue_raw, :table_count, :raw_sub_events_text, :parsed_rounds_json,
            datetime('now')
        )
        """,
        sessions,
    )
    return len(sessions)


def maybe_advance_lifecycle(cursor: sqlite3.Cursor, event_id: int) -> None:
    """日程入库后，若 event 仍是 'upcoming'，提升至 'draw_published'。"""
    cursor.execute(
        """
        UPDATE events
        SET lifecycle_status = 'draw_published'
        WHERE event_id = ? AND lifecycle_status = 'upcoming'
        """,
        (event_id,),
    )


# ── 主流程 ──────────────────────────────────────────────────────────────────


def import_one_file(
    cursor: sqlite3.Cursor, path: Path, *, dry_run: bool, verbose: bool
) -> dict:
    event_id = int(path.stem)
    event = get_event(cursor, event_id)
    if not event:
        return {"event_id": event_id, "error": "events 表无此 event_id（先跑 backfill_events_calendar_event_id.py 或手工 seed）"}

    with open(path, "r", encoding="utf-8") as f:
        raw_days = json.load(f)
    if not isinstance(raw_days, list):
        return {"event_id": event_id, "error": "JSON 顶层应为数组"}

    base_year = event["year"]
    sessions: list[dict] = []
    prev_date: date | None = None
    parse_errors: list[str] = []
    unmatched_segments: list[str] = []

    for idx, day in enumerate(raw_days, start=1):
        try:
            local_date = parse_local_date(day["日期"], base_year, prev_date)
        except (KeyError, ValueError) as e:
            parse_errors.append(f"day#{idx}: {e}")
            continue
        prev_date = local_date

        start_t, end_t = parse_time_window(day.get("时间"))
        venue_raw = (day.get("场馆") or "").strip() or None
        table_count = day.get("球台数")
        if isinstance(table_count, str):
            table_count = int(table_count) if table_count.isdigit() else None

        raw_segments: list[str] = day.get("赛事") or []
        parsed: list[dict] = []
        for seg in raw_segments:
            entries = parse_event_segment(seg)
            if not entries and seg.strip():
                unmatched_segments.append(seg)
            parsed.extend(entries)

        sessions.append({
            "event_id": event_id,
            "day_index": idx,
            "local_date": local_date.isoformat(),
            "start_local_time": start_t,
            "end_local_time": end_t,
            "venue_raw": venue_raw,
            "table_count": table_count,
            "raw_sub_events_text": " | ".join(raw_segments) if raw_segments else None,
            "parsed_rounds_json": json.dumps(parsed, ensure_ascii=False),
        })

    if not dry_run:
        upsert_session_rows(cursor, event_id, sessions)
        maybe_advance_lifecycle(cursor, event_id)

    if verbose:
        for s in sessions:
            print(f"    day#{s['day_index']:>2} {s['local_date']} {s['start_local_time']}-{s['end_local_time']} "
                  f"@{s['venue_raw']!r} tables={s['table_count']}")
            print(f"        parsed: {s['parsed_rounds_json']}")

    return {
        "event_id": event_id,
        "name": event["name"],
        "days": len(sessions),
        "parse_errors": parse_errors,
        "unmatched_segments": unmatched_segments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import event session schedule JSONs.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dir", type=Path, default=DEFAULT_SCHEDULE_DIR,
                        help="data/event_schedule/ 目录")
    parser.add_argument("--event", type=int, default=None,
                        help="只导入指定 event_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1
    if not args.dir.exists():
        print(f"Schedule dir not found: {args.dir}", file=sys.stderr)
        return 1

    if args.event is not None:
        files = [args.dir / f"{args.event}.json"]
    else:
        files = sorted(args.dir.glob("*.json"))

    files = [p for p in files if p.exists()]
    if not files:
        print(f"No JSON files found in {args.dir}")
        return 0

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    try:
        all_results = []
        for path in files:
            print(f"\n=== {path.name} ===")
            result = import_one_file(cursor, path, dry_run=args.dry_run, verbose=args.verbose)
            all_results.append(result)
            if "error" in result:
                print(f"  ❌ {result['error']}")
                continue
            print(f"  event_id={result['event_id']}  days={result['days']}  ({result['name']})")
            if result["parse_errors"]:
                print(f"  ⚠ {len(result['parse_errors'])} parse errors:")
                for err in result["parse_errors"][:5]:
                    print(f"      {err}")
            if result["unmatched_segments"]:
                print(f"  ⚠ {len(result['unmatched_segments'])} unmatched segments:")
                for seg in result["unmatched_segments"][:5]:
                    print(f"      {seg!r}")

        if args.dry_run:
            conn.rollback()
            print("\n[dry-run] no changes committed.")
        else:
            conn.commit()
            print("\n✅ Committed.")

        # 失败统计
        failed = [r for r in all_results if "error" in r]
        ok = [r for r in all_results if "error" not in r]
        print(f"\nSummary: {len(ok)} imported, {len(failed)} skipped (errors).")
        return 0 if not failed else 0  # non-zero would mask normal "no schedule yet" cases
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
