#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import WTT event schedule JSON into upcoming-event tables.

Input:
    data/wtt_raw/{event_id}/GetEventSchedule.json

Output:
    event_draw_entries
    event_draw_entry_players
    event_schedule_matches
    event_schedule_match_sides
    event_schedule_match_side_players

The import is incremental per event_id: only rows present in the latest raw
payload are inserted or updated, and older rows are preserved.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import config

    PROJECT_ROOT = Path(config.PROJECT_ROOT)
    DEFAULT_DB_PATH = Path(config.DB_PATH)
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"

DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "wtt_raw"
DEFAULT_MAPPING_PATH = PROJECT_ROOT / "data" / "stage_round_mapping.json"

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


@dataclass(frozen=True)
class RoundInfo:
    stage_code: str
    round_code: str
    group_code: str | None


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    rows = cursor.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def ensure_import_schema(cursor: sqlite3.Cursor, mapping: dict) -> None:
    """Apply small forward-compatible schema additions needed by this import."""
    additions = [
        ("event_schedule_matches", "external_match_code", "TEXT"),
        ("event_schedule_matches", "raw_schedule_status", "TEXT"),
        ("event_schedule_match_sides", "seed", "INTEGER"),
        ("event_schedule_match_sides", "qualifier", "INTEGER"),
    ]
    for table, column, ddl_type in additions:
        if not column_exists(cursor, table, column):
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_schedule_matches_external_code
            ON event_schedule_matches(event_id, external_match_code)
        """
    )

    cursor.executemany(
        """
        INSERT INTO stage_codes (code, name, name_zh, sort_order)
        VALUES (:code, :name, :name_zh, :sort_order)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            name_zh = excluded.name_zh,
            sort_order = excluded.sort_order
        """,
        mapping.get("stage_codes", []),
    )
    cursor.executemany(
        """
        INSERT INTO round_codes (code, name, name_zh, kind, sort_order)
        VALUES (:code, :name, :name_zh, :kind, :sort_order)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            name_zh = excluded.name_zh,
            kind = excluded.kind,
            sort_order = excluded.sort_order
        """,
        mapping.get("round_codes", []),
    )


def load_mapping(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def load_official_result_codes(raw_root: Path, event_id: int) -> set[str]:
    event_dir = raw_root / str(event_id)
    for filename in ("GetOfficialResult.json", "GetOfficialResult_take10.json"):
        path = event_dir / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return set()

        codes: set[str] = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            match_card = item.get("match_card") or {}
            code = normalize_external_match_code(item.get("documentCode") or match_card.get("documentCode"))
            if code:
                codes.add(code)
        return codes
    return set()


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


def unit_status_priority(unit: dict, official_result_codes: set[str]) -> int:
    code = normalize_external_match_code(unit.get("Code"))
    if code and code in official_result_codes:
        return 5
    return {
        "completed": 4,
        "walkover": 4,
        "live": 3,
        "scheduled": 2,
        "cancelled": 1,
    }.get(normalize_status(unit.get("ScheduleStatus")), 0)


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

    left_updated = left.get("UpdatedAt") or left.get("StartDate") or ""
    right_updated = right.get("UpdatedAt") or right.get("StartDate") or ""
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


def infer_time_zone(event: dict) -> str | None:
    existing = (event.get("time_zone") or "").strip()
    if existing:
        return existing

    haystack = " ".join(
        str(event.get(k) or "") for k in ("name", "location", "href")
    ).lower()
    if "london" in haystack or "united kingdom" in haystack or "england" in haystack:
        return "Europe/London"
    return None


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
    return name or (competitor.get("Code") or "TBD")


def athlete_name(athlete: dict) -> str:
    desc = athlete.get("Description") or {}
    given = (desc.get("GivenName") or "").strip()
    family = (desc.get("FamilyName") or "").strip()
    return " ".join(part for part in (family, given) if part) or (athlete.get("Code") or "Unknown")


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


def load_player_ids(cursor: sqlite3.Cursor, if_ids: set[int]) -> dict[int, int]:
    if not if_ids:
        return {}
    placeholders = ",".join("?" for _ in if_ids)
    rows = cursor.execute(
        f"SELECT player_id FROM players WHERE player_id IN ({placeholders})",
        tuple(sorted(if_ids)),
    ).fetchall()
    return {int(row[0]): int(row[0]) for row in rows}


def load_existing_entry_ids(cursor: sqlite3.Cursor, event_id: int) -> dict[tuple[str, str, str], int]:
    rows = cursor.execute(
        """
        SELECT entry_id, sub_event_type_code, stage_code, team_code
        FROM event_draw_entries
        WHERE event_id = ?
          AND team_code IS NOT NULL
        """,
        (event_id,),
    ).fetchall()
    return {
        (str(row[1]), str(row[2]), str(row[3])): int(row[0])
        for row in rows
    }


def next_slot_index(cursor: sqlite3.Cursor, event_id: int, sub_event_type_code: str, stage_code: str) -> int:
    row = cursor.execute(
        """
        SELECT COALESCE(MAX(slot_index), 0)
        FROM event_draw_entries
        WHERE event_id = ?
          AND sub_event_type_code = ?
          AND stage_code = ?
        """,
        (event_id, sub_event_type_code, stage_code),
    ).fetchone()
    return int(row[0] or 0) + 1


def replace_entry_players(
    cursor: sqlite3.Cursor,
    entry_id: int,
    players: list[dict],
    player_ids: dict[int, int],
) -> None:
    cursor.execute("DELETE FROM event_draw_entry_players WHERE entry_id = ?", (entry_id,))
    for player_order, player in enumerate(sorted(players, key=lambda p: p["order"]), start=1):
        if_id = player.get("if_id")
        cursor.execute(
            """
            INSERT INTO event_draw_entry_players (
                entry_id, player_order, player_id, player_name, player_country
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                player_order,
                player_ids.get(if_id) if if_id is not None else None,
                player["name"],
                player["country"],
            ),
        )


def replace_match_sides(
    cursor: sqlite3.Cursor,
    schedule_match_id: int,
    sub_event: str,
    round_info: RoundInfo,
    starts: list[dict],
    entry_ids: dict[tuple[str, str, str], int],
    player_ids: dict[int, int],
) -> tuple[int, int]:
    cursor.execute(
        """
        DELETE FROM event_schedule_match_side_players
        WHERE schedule_side_id IN (
            SELECT schedule_side_id
            FROM event_schedule_match_sides
            WHERE schedule_match_id = ?
        )
        """,
        (schedule_match_id,),
    )
    cursor.execute("DELETE FROM event_schedule_match_sides WHERE schedule_match_id = ?", (schedule_match_id,))

    side_count = 0
    side_player_count = 0
    for side_no, start in enumerate(starts[:2], start=1):
        competitor = start.get("Competitor") or {}
        comp_code = (competitor.get("Code") or "").strip()
        entry_id = entry_ids.get((sub_event, round_info.stage_code, comp_code))
        placeholder = None if comp_code else competitor_name(competitor)

        cursor.execute(
            """
            INSERT INTO event_schedule_match_sides (
                schedule_match_id, side_no, entry_id, placeholder_text,
                team_code, seed, qualifier, is_winner
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                schedule_match_id,
                side_no,
                entry_id,
                placeholder,
                competitor.get("Organization"),
                int_or_none(competitor.get("Seed")),
                bool_to_int(competitor.get("Qualifier")),
            ),
        )
        schedule_side_id = int(cursor.lastrowid)
        side_count += 1

        athletes = (((competitor.get("Composition") or {}).get("Athlete")) or [])
        for player_order, athlete in enumerate(athletes, start=1):
            desc = athlete.get("Description") or {}
            if_id = int_or_none(desc.get("IfId") or athlete.get("Code"))
            cursor.execute(
                """
                INSERT INTO event_schedule_match_side_players (
                    schedule_side_id, player_order, player_id, player_name, player_country
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    schedule_side_id,
                    player_order,
                    player_ids.get(if_id) if if_id is not None else None,
                    athlete_name(athlete),
                    desc.get("Organization") or competitor.get("Organization"),
                ),
            )
            side_player_count += 1

    return side_count, side_player_count


def collect_entries(units: list[dict]) -> dict[tuple[str, str, str], dict]:
    entries: dict[tuple[str, str, str], dict] = {}
    for unit in units:
        sub_event = SUB_EVENT_MAP.get((unit.get("SubEvent") or "").strip())
        if not sub_event:
            continue
        round_info = normalize_round(unit.get("Round"))
        starts = ((unit.get("StartList") or {}).get("Start") or [])
        for start in starts:
            competitor = start.get("Competitor") or {}
            code = (competitor.get("Code") or "").strip()
            if not code:
                continue
            key = (sub_event, round_info.stage_code, code)
            if key not in entries:
                entries[key] = {
                    "sub_event_type_code": sub_event,
                    "stage_code": round_info.stage_code,
                    "competitor_code": code,
                    "team_code": competitor.get("Organization"),
                    "seed": int_or_none(competitor.get("Seed")),
                    "players": [],
                }

            athletes = (((competitor.get("Composition") or {}).get("Athlete")) or [])
            existing_codes = {
                p["if_id"] for p in entries[key]["players"] if p.get("if_id") is not None
            }
            for athlete in athletes:
                desc = athlete.get("Description") or {}
                if_id = int_or_none(desc.get("IfId") or athlete.get("Code"))
                if if_id is not None and if_id in existing_codes:
                    continue
                entries[key]["players"].append({
                    "if_id": if_id,
                    "order": int_or_none(athlete.get("Order")) or len(entries[key]["players"]) + 1,
                    "name": athlete_name(athlete),
                    "country": desc.get("Organization") or competitor.get("Organization"),
                })
                if if_id is not None:
                    existing_codes.add(if_id)
    return entries


def insert_entries(
    cursor: sqlite3.Cursor,
    event_id: int,
    entries: dict[tuple[str, str, str], dict],
    player_ids: dict[int, int],
) -> dict[tuple[str, str, str], int]:
    entry_ids = load_existing_entry_ids(cursor, event_id)
    sorted_items = sorted(entries.items(), key=lambda item: item[0])

    for key, entry in sorted_items:
        entry_id = entry_ids.get(key)
        if entry_id is None:
            slot_index = next_slot_index(cursor, event_id, entry["sub_event_type_code"], entry["stage_code"])
            cursor.execute(
                """
                INSERT INTO event_draw_entries (
                    event_id, sub_event_type_code, stage_code, slot_index,
                    seed, group_code, team_code, placeholder_text
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL)
                """,
                (
                    event_id,
                    entry["sub_event_type_code"],
                    entry["stage_code"],
                    slot_index,
                    entry["seed"],
                    entry["team_code"],
                ),
            )
            entry_id = int(cursor.lastrowid)
            entry_ids[key] = entry_id
        else:
            cursor.execute(
                """
                UPDATE event_draw_entries
                SET seed = ?, team_code = ?, placeholder_text = NULL
                WHERE entry_id = ?
                """,
                (
                    entry["seed"],
                    entry["team_code"],
                    entry_id,
                ),
            )

        replace_entry_players(cursor, entry_id, entry["players"], player_ids)

    return entry_ids


def insert_matches(
    cursor: sqlite3.Cursor,
    event_id: int,
    units: list[dict],
    entry_ids: dict[tuple[str, str, str], int],
    player_ids: dict[int, int],
    tz_name: str | None,
    official_result_codes: set[str],
) -> dict:
    existing_match_ids = {
        normalize_external_match_code(row[0]): int(row[1])
        for row in cursor.execute(
            """
            SELECT external_match_code, schedule_match_id
            FROM event_schedule_matches
            WHERE event_id = ?
              AND external_match_code IS NOT NULL
            """,
            (event_id,),
        ).fetchall()
        if normalize_external_match_code(row[0])
    }
    match_count = 0
    side_count = 0
    side_player_count = 0
    skipped: list[str] = []

    for unit in sorted(units, key=lambda u: (u.get("StartDate") or "", u.get("Code") or "")):
        sub_event = SUB_EVENT_MAP.get((unit.get("SubEvent") or "").strip())
        if not sub_event:
            skipped.append(f"unknown sub_event={unit.get('SubEvent')!r} code={unit.get('Code')!r}")
            continue

        round_info = normalize_round(unit.get("Round"))
        local_at, utc_at = to_local_and_utc(unit.get("StartDate"), tz_name)
        raw_status = unit.get("ScheduleStatus")
        code = normalize_external_match_code(unit.get("Code"))
        status = "completed" if code and code in official_result_codes else normalize_status(raw_status)
        table_no = unit.get("Location")
        session_label = text_value(unit.get("ItemName")) or text_value(unit.get("ItemDescription"))

        schedule_match_id = existing_match_ids.get(code) if code else None
        if schedule_match_id is None:
            cursor.execute(
                """
                INSERT INTO event_schedule_matches (
                    event_id, sub_event_type_code, stage_code, round_code, group_code,
                    external_match_code, scheduled_local_at, scheduled_utc_at, table_no,
                    session_label, venue_id, status, raw_schedule_status, match_score,
                    games, winner_side, promoted_match_id, last_synced_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, NULL, NULL, NULL,
                    datetime('now')
                )
                """,
                (
                    event_id,
                    sub_event,
                    round_info.stage_code,
                    round_info.round_code,
                    round_info.group_code,
                    unit.get("Code"),
                    local_at,
                    utc_at,
                    table_no,
                    session_label,
                    status,
                    raw_status,
                ),
            )
            schedule_match_id = int(cursor.lastrowid)
            if code:
                existing_match_ids[code] = schedule_match_id
        else:
            cursor.execute(
                """
                UPDATE event_schedule_matches
                SET sub_event_type_code = ?,
                    stage_code = ?,
                    round_code = ?,
                    group_code = ?,
                    external_match_code = ?,
                    scheduled_local_at = ?,
                    scheduled_utc_at = ?,
                    table_no = ?,
                    session_label = ?,
                    status = ?,
                    raw_schedule_status = ?,
                    last_synced_at = datetime('now')
                WHERE schedule_match_id = ?
                """,
                (
                    sub_event,
                    round_info.stage_code,
                    round_info.round_code,
                    round_info.group_code,
                    unit.get("Code"),
                    local_at,
                    utc_at,
                    table_no,
                    session_label,
                    status,
                    raw_status,
                    schedule_match_id,
                ),
            )
        match_count += 1

        starts = ((unit.get("StartList") or {}).get("Start") or [])
        inserted_sides, inserted_side_players = replace_match_sides(
            cursor,
            schedule_match_id,
            sub_event,
            round_info,
            starts,
            entry_ids,
            player_ids,
        )
        side_count += inserted_sides
        side_player_count += inserted_side_players

    return {
        "matches": match_count,
        "sides": side_count,
        "side_players": side_player_count,
        "skipped": skipped,
    }


def collect_player_if_ids(entries: dict[tuple[str, str, str], dict]) -> set[int]:
    ids: set[int] = set()
    for entry in entries.values():
        for player in entry["players"]:
            if player.get("if_id") is not None:
                ids.add(player["if_id"])
    return ids


def snapshot_raw_files(raw_root: Path, event_id: int) -> Path:
    event_dir = raw_root / str(event_id)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = event_dir / "snapshots" / timestamp
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for path in event_dir.glob("*.json"):
        shutil.copy2(path, snapshot_dir / path.name)
    return snapshot_dir


def maybe_advance_lifecycle(cursor: sqlite3.Cursor, event_id: int) -> None:
    cursor.execute(
        """
        UPDATE events
        SET lifecycle_status = CASE
                WHEN start_date IS NOT NULL AND date('now') >= date(start_date)
                    THEN 'in_progress'
                WHEN lifecycle_status = 'upcoming'
                    THEN 'draw_published'
                ELSE lifecycle_status
            END,
            last_synced_at = datetime('now')
        WHERE event_id = ?
          AND lifecycle_status IN ('upcoming', 'draw_published', 'in_progress')
        """,
        (event_id,),
    )


def maybe_set_event_time_zone(cursor: sqlite3.Cursor, event_id: int, tz_name: str | None) -> None:
    if not tz_name:
        return
    cursor.execute(
        """
        UPDATE events
        SET time_zone = ?
        WHERE event_id = ?
          AND (time_zone IS NULL OR trim(time_zone) = '')
        """,
        (tz_name, event_id),
    )


def import_event(
    cursor: sqlite3.Cursor,
    event_id: int,
    raw_root: Path,
    mapping: dict,
    *,
    dry_run: bool,
) -> dict:
    event = get_event(cursor, event_id)
    if event is None:
        return {"event_id": event_id, "error": "events row not found"}

    schedule_path = raw_root / str(event_id) / "GetEventSchedule.json"
    if not schedule_path.exists():
        return {"event_id": event_id, "error": f"missing {schedule_path}"}

    ensure_import_schema(cursor, mapping)
    units = load_units(schedule_path)
    official_result_codes = load_official_result_codes(raw_root, event_id)
    deduped_units = dedupe_units(units, official_result_codes)
    entries = collect_entries(deduped_units)
    player_ids = load_player_ids(cursor, collect_player_if_ids(entries))
    tz_name = infer_time_zone(event)

    snapshot_dir = snapshot_raw_files(raw_root, event_id)
    entry_ids = insert_entries(cursor, event_id, entries, player_ids)
    match_stats = insert_matches(
        cursor,
        event_id,
        deduped_units,
        entry_ids,
        player_ids,
        tz_name,
        official_result_codes,
    )
    maybe_set_event_time_zone(cursor, event_id, tz_name)
    maybe_advance_lifecycle(cursor, event_id)

    if dry_run:
        cursor.connection.rollback()

    return {
        "event_id": event_id,
        "name": event["name"],
        "time_zone": tz_name,
        "snapshot_dir": str(snapshot_dir),
        "units": len(units),
        "deduped_units": len(deduped_units),
        "entries": len(entry_ids),
        "entry_players": sum(len(e["players"]) for e in entries.values()),
        "matched_players": len(player_ids),
        **match_stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import WTT event schedule JSON.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--event", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1
    if not args.mapping.exists():
        print(f"Mapping file not found: {args.mapping}", file=sys.stderr)
        return 1

    mapping = load_mapping(args.mapping)
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    try:
        result = import_event(
            cursor,
            args.event,
            args.raw_root,
            mapping,
            dry_run=args.dry_run,
        )
        if "error" in result:
            conn.rollback()
            print(f"Error: {result['error']}", file=sys.stderr)
            return 1

        if args.dry_run:
            print("[dry-run] no changes committed.")
        else:
            conn.commit()
            print("Committed.")

        print(
            f"event_id={result['event_id']} units={result['units']} deduped_units={result['deduped_units']} "
            f"entries={result['entries']} matches={result['matches']} "
            f"sides={result['sides']} side_players={result['side_players']}"
        )
        print(
            f"entry_players={result['entry_players']} matched_players={result['matched_players']} "
            f"time_zone={result['time_zone'] or 'UNKNOWN'}"
        )
        if result["skipped"]:
            print(f"Skipped {len(result['skipped'])} units:")
            for item in result["skipped"][:10]:
                print(f"  {item}")
        if args.verbose:
            print(f"Event: {result['name']}")

        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
