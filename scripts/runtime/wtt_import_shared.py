#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared WTT import helpers for current-event scripts."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"
DEFAULT_SCHEDULE_DIR = PROJECT_ROOT / "data" / "event_schedule"

SUB_EVENT_MAP = {
    "Men's Teams": "MT",
    "Women's Teams": "WT",
    "Mixed Teams": "XT",
    "Men's Singles": "MS",
    "Women's Singles": "WS",
    "Men's Doubles": "MD",
    "Women's Doubles": "WD",
    "Mixed Doubles": "XD",
}

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

STATUS_MAP = {
    "scheduled": "scheduled",
    "start list": "scheduled",
    "intermediate": "live",
    "live": "live",
    "official": "completed",
    "completed": "completed",
    "walkover": "walkover",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}


def normalize_external_match_code(value: str | None) -> str:
    return (value or "").replace(" ", "").rstrip("-").strip()


def parse_tie_score(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.search(r"(\d+)\s*-\s*(\d+)", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def bool_to_int(value: object) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


@dataclass(frozen=True)
class RoundInfo:
    stage_code: str
    round_code: str
    group_code: str | None


def normalize_round(raw_round: str | None) -> RoundInfo:
    raw = (raw_round or "").strip().upper()
    if raw.startswith("GP") and len(raw) >= 4 and raw[2:4].isdigit():
        group_no = int(raw[2:4])
        if 1 <= group_no <= 16:
            return RoundInfo("PRELIMINARY", f"G{group_no}", raw[:4])

    if raw == "RND1":
        return RoundInfo("PRELIMINARY", "R1", None)

    direct = {
        "R32-": "R32",
        "R32": "R32",
        "R16": "R16",
        "8FNL": "QF",
        "QFNL": "QF",
        "SFNL": "SF",
        "FNL-": "F",
        "FNL": "F",
    }
    if raw in direct:
        return RoundInfo("MAIN_DRAW", direct[raw], None)

    return RoundInfo("UNKNOWN", "UNKNOWN", None)


def normalize_status(raw_status: str | None) -> str:
    key = (raw_status or "").strip().lower()
    return STATUS_MAP.get(key, "scheduled")


def parse_local_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def infer_time_zone(event: dict) -> str | None:
    existing = (event.get("time_zone") or "").strip()
    if existing:
        return existing

    haystack = " ".join(str(event.get(k) or "") for k in ("name", "location", "href")).lower()
    if "london" in haystack or "united kingdom" in haystack or "england" in haystack:
        return "Europe/London"
    return None


def to_local_and_utc(raw_value: str | None, tz_name: str | None) -> tuple[str | None, str | None]:
    dt = parse_local_datetime(raw_value)
    if dt is None:
        return None, None

    if dt.tzinfo is None:
        local_iso = dt.isoformat(timespec="seconds")
        if not tz_name:
            return local_iso, None
        try:
            local_dt = dt.replace(tzinfo=ZoneInfo(tz_name))
        except ZoneInfoNotFoundError:
            return local_iso, None
    else:
        local_dt = dt
        local_iso = local_dt.isoformat(timespec="seconds")

    utc_iso = local_dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    return local_iso, utc_iso


def text_value(items: list[dict] | None) -> str | None:
    for item in items or []:
        if item.get("Language") == "ENG" and item.get("Value"):
            return item["Value"]
    for item in items or []:
        if item.get("Value"):
            return item["Value"]
    return None


def competitor_name(competitor: dict) -> str:
    desc = competitor.get("Description") or {}
    team_name = (desc.get("TeamName") or "").strip()
    if team_name:
        return team_name
    given = (desc.get("GivenName") or "").strip()
    family = (desc.get("FamilyName") or "").strip()
    name = " ".join(part for part in (family, given) if part)
    return name or (competitor.get("Code") or competitor.get("Organization") or "TBD")


def athlete_name(athlete: dict) -> str:
    desc = athlete.get("Description") or {}
    given = (desc.get("GivenName") or "").strip()
    family = (desc.get("FamilyName") or "").strip()
    return " ".join(part for part in (family, given) if part) or (athlete.get("Code") or "Unknown")


def load_units(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    units: list[dict] = []
    if isinstance(data, list):
        for entry in data:
            competition = entry.get("Competition") or {}
            units.extend(competition.get("Unit") or [])
    elif isinstance(data, dict):
        competition = data.get("Competition") or {}
        units.extend(competition.get("Unit") or [])
    return [u for u in units if isinstance(u, dict)]


def unit_status_priority(unit: dict, official_result_codes: set[str]) -> int:
    base_priority = {
        "completed": 40,
        "walkover": 40,
        "live": 30,
        "scheduled": 20,
        "cancelled": 10,
    }.get(normalize_status(unit.get("ScheduleStatus")), 0)
    code = normalize_external_match_code(unit.get("Code"))
    if code and code in official_result_codes:
        base_priority += 1
    return base_priority


def unit_completeness(unit: dict) -> int:
    starts = ((unit.get("StartList") or {}).get("Start") or [])
    athletes = 0
    team_codes = 0
    for start in starts[:2]:
        competitor = start.get("Competitor") or {}
        if competitor.get("Organization"):
            team_codes += 1
        athletes += len((((competitor.get("Composition") or {}).get("Athlete")) or []))

    return (
        (100 if unit.get("Result") else 0)
        + athletes * 5
        + team_codes * 3
        + (2 if unit.get("Location") else 0)
        + (1 if text_value(unit.get("ItemName")) or text_value(unit.get("ItemDescription")) else 0)
    )


def pick_preferred_unit(left: dict, right: dict, official_result_codes: set[str]) -> dict:
    status_diff = unit_status_priority(left, official_result_codes) - unit_status_priority(right, official_result_codes)
    if status_diff != 0:
        return left if status_diff > 0 else right
    completeness_diff = unit_completeness(left) - unit_completeness(right)
    if completeness_diff != 0:
        return left if completeness_diff > 0 else right
    left_updated = left.get("ActualEndDate") or left.get("ActualStartDate") or left.get("UpdatedAt") or left.get("StartDate") or ""
    right_updated = right.get("ActualEndDate") or right.get("ActualStartDate") or right.get("UpdatedAt") or right.get("StartDate") or ""
    if left_updated != right_updated:
        return left if left_updated > right_updated else right
    return left


def dedupe_units(units: list[dict], official_result_codes: set[str]) -> list[dict]:
    deduped: dict[str, dict] = {}
    ordered_no_code: list[dict] = []
    for unit in units:
        code = normalize_external_match_code(unit.get("Code"))
        if not code:
            ordered_no_code.append(unit)
            continue
        current = deduped.get(code)
        deduped[code] = unit if current is None else pick_preferred_unit(current, unit, official_result_codes)
    result = list(deduped.values()) + ordered_no_code
    result.sort(key=lambda u: (u.get("StartDate") or "", u.get("Code") or ""))
    return result


def get_event(cursor: sqlite3.Cursor, event_id: int) -> dict | None:
    row = cursor.execute(
        """
        SELECT event_id, year, name, location, start_date, end_date, time_zone, lifecycle_status
        FROM events
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "event_id": row[0],
        "year": row[1],
        "name": row[2],
        "location": row[3],
        "start_date": row[4],
        "end_date": row[5],
        "time_zone": row[6],
        "lifecycle_status": row[7],
    }


DATE_RE = re.compile(r"^(\d{1,2})\s*月\s*(\d{1,2})\s*日$")


def parse_local_date(raw: str, base_year: int, prev_date) -> datetime.date:
    m = DATE_RE.match(raw.strip())
    if not m:
        raise ValueError(f"日期格式无法解析: {raw!r}")
    month = int(m.group(1))
    day = int(m.group(2))
    candidate = datetime(base_year, month, day).date()
    if prev_date is not None and candidate < prev_date:
        candidate = datetime(base_year + 1, month, day).date()
    return candidate


def parse_time_window(times: list[str] | None) -> tuple[str | None, str | None]:
    if not times:
        return None, None
    start = times[0].strip() if len(times) >= 1 else None
    end = times[1].strip() if len(times) >= 2 else None
    return start or None, end or None


def parse_event_segment(segment: str) -> list[dict]:
    s = segment.strip()
    if not s:
        return []

    sub_part, _, rest = s.partition(" ")
    if not rest:
        sub_part, rest = s, ""

    sub_event_codes: list[str] = []
    for token in sub_part.split("/"):
        token = token.strip()
        if token in SUB_EVENT_ZH:
            sub_event_codes.append(SUB_EVENT_ZH[token])
    if not sub_event_codes:
        return []

    stage_code: str | None = None
    rest_stripped = rest.strip()
    for kw, code in STAGE_KEYWORDS:
        if kw in rest_stripped:
            stage_code = code
            rest_stripped = rest_stripped.replace(kw, " ").strip()
            break

    round_tokens = [t.strip() for t in re.split(r"\s*[+＋]\s*", rest_stripped) if t.strip()]
    round_codes: list[str] = []
    for tok in round_tokens:
        if tok in ROUND_ZH:
            round_codes.append(ROUND_ZH[tok])

    if stage_code is None:
        if round_codes and all(rc in ("R1", "R2", "R3", "R4", "R5") for rc in round_codes):
            stage_code = "MAIN_STAGE1"
        else:
            stage_code = "MAIN_DRAW"

    if not round_codes:
        round_codes = ["UNKNOWN"]

    out = []
    for sub_code in sub_event_codes:
        for round_code in round_codes:
            out.append({"sub_event_code": sub_code, "stage_code": stage_code, "round_code": round_code})
    return out


def load_player_ids(cursor: sqlite3.Cursor, if_ids: set[int]) -> dict[int, int]:
    if not if_ids:
        return {}
    placeholders = ",".join("?" for _ in if_ids)
    rows = cursor.execute(
        f"SELECT player_id FROM players WHERE player_id IN ({placeholders})",
        tuple(sorted(if_ids)),
    ).fetchall()
    return {int(row[0]): int(row[0]) for row in rows}
