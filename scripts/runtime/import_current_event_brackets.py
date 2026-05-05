#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import GetBrackets_*.json into current_event_brackets."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"

SUB_EVENT_FILE_MAP = {
    "MTEAM": "MT",
    "WTEAM": "WT",
    "XTEAM": "XT",
    "MSING": "MS",
    "WSING": "WS",
    "MDOUB": "MD",
    "WDOUB": "WD",
    "XDOUB": "XD",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_score_pair(value: str | None) -> tuple[int, int] | None:
    if not value or "-" not in value:
        return None
    head = value.split("(", 1)[0].strip().replace(" ", "")
    parts = head.split("-", 1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0]), int(parts[1])


def infer_winner_side(item: dict[str, Any]) -> str | None:
    places = item.get("CompetitorPlace") or []
    if len(places) >= 1 and (places[0].get("Wlt") or "").upper() == "W":
        return "A"
    if len(places) >= 2 and (places[1].get("Wlt") or "").upper() == "W":
        return "B"
    parsed = parse_score_pair(item.get("Result"))
    if not parsed:
        return None
    if parsed[0] > parsed[1]:
        return "A"
    if parsed[1] > parsed[0]:
        return "B"
    return None


def normalize_round(raw_code: str | None) -> tuple[str | None, str | None, int | None]:
    raw = (raw_code or "").strip().upper()
    mapping = {
        "FNL-": ("MAIN_DRAW", "F", 10),
        "FNL": ("MAIN_DRAW", "F", 10),
        "SFNL": ("MAIN_DRAW", "SF", 20),
        "QFNL": ("MAIN_DRAW", "QF", 30),
        "8FNL": ("MAIN_DRAW", "R16", 40),
        "R32-": ("MAIN_DRAW", "R32", 50),
        "R32": ("MAIN_DRAW", "R32", 50),
        "R64-": ("MAIN_DRAW", "R64", 60),
        "R64": ("MAIN_DRAW", "R64", 60),
        "RND1": ("PRELIMINARY", "R1", 70),
    }
    if raw in mapping:
        return mapping[raw]
    if raw.startswith("GP") and raw[2:].isdigit():
        return ("MAIN_STAGE1", raw, 100 + int(raw[2:]))
    return (None, raw or None, None)


def infer_status(item: dict[str, Any], winner_side: str | None) -> str | None:
    if winner_side or (item.get("Result") or "").strip():
        return "completed"
    if item.get("Date") or item.get("Time"):
        return "scheduled"
    places = item.get("CompetitorPlace") or []
    if any((place.get("Competitor") or {}).get("Organization") for place in places if isinstance(place, dict)):
        return "scheduled"
    if any(((place.get("PreviousUnit") or {}).get("Unit")) for place in places if isinstance(place, dict)):
        return "scheduled"
    return None


def extract_side(place: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    competitor = place.get("Competitor") or {}
    description = competitor.get("Description") or {}
    previous_unit = place.get("PreviousUnit") or {}
    team_code = competitor.get("Organization")
    placeholder = None
    if not team_code:
        placeholder = (
            description.get("TeamName")
            or place.get("Code")
            or previous_unit.get("Unit")
            or None
        )
    return team_code, placeholder, previous_unit.get("Unit")


def load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_event_id(payload: dict[str, Any], explicit_event_id: int | None) -> int:
    if explicit_event_id is not None:
        return explicit_event_id
    event_id = payload.get("EventId")
    if isinstance(event_id, int):
        return event_id
    if isinstance(event_id, str) and event_id.isdigit():
        return int(event_id)
    raise ValueError("event_id is required")


def resolve_sub_event_type_code(path: Path) -> str:
    suffix = path.stem.replace("GetBrackets_", "").upper()
    sub_event_type_code = SUB_EVENT_FILE_MAP.get(suffix)
    if not sub_event_type_code:
        raise ValueError(f"unsupported brackets file name: {path.name}")
    return sub_event_type_code


def collect_rows(payload: dict[str, Any], *, event_id: int, sub_event_type_code: str) -> list[dict[str, Any]]:
    competition = payload.get("Competition") or {}
    brackets = competition.get("Bracket") or []
    collected_at = utc_now_iso()
    rows: list[dict[str, Any]] = []

    for bracket in brackets:
        draw_code = bracket.get("Code")
        groups = bracket.get("BracketItems") or []
        for group in groups:
            bracket_code = group.get("Code")
            stage_code, round_code, round_order = normalize_round(bracket_code)
            items = group.get("BracketItem") or []
            for item in items:
                places = item.get("CompetitorPlace") or []
                side_a = places[0] if len(places) >= 1 and isinstance(places[0], dict) else {}
                side_b = places[1] if len(places) >= 2 and isinstance(places[1], dict) else {}
                winner_side = infer_winner_side(item)
                side_a_team_code, side_a_placeholder, side_a_previous_unit = extract_side(side_a)
                side_b_team_code, side_b_placeholder, side_b_previous_unit = extract_side(side_b)
                rows.append(
                    {
                        "event_id": event_id,
                        "sub_event_type_code": sub_event_type_code,
                        "draw_code": draw_code,
                        "bracket_code": bracket_code,
                        "stage_code": stage_code,
                        "round_code": round_code,
                        "round_order": round_order,
                        "bracket_position": item.get("Position"),
                        "external_unit_code": item.get("Unit") or item.get("Code"),
                        "scheduled_date": item.get("Date"),
                        "scheduled_time": item.get("Time"),
                        "match_score": item.get("Result") or None,
                        "winner_side": winner_side,
                        "status": infer_status(item, winner_side),
                        "side_a_previous_unit": side_a_previous_unit,
                        "side_b_previous_unit": side_b_previous_unit,
                        "side_a_team_code": side_a_team_code,
                        "side_b_team_code": side_b_team_code,
                        "side_a_placeholder": side_a_placeholder,
                        "side_b_placeholder": side_b_placeholder,
                        "raw_source_payload": json.dumps(item, ensure_ascii=False),
                        "last_synced_at": collected_at,
                    }
                )
    return rows


def import_file(conn: sqlite3.Connection, path: Path, *, explicit_event_id: int | None) -> tuple[int, str, int]:
    payload = load_payload(path)
    event_id = resolve_event_id(payload, explicit_event_id)
    sub_event_type_code = resolve_sub_event_type_code(path)
    rows = collect_rows(payload, event_id=event_id, sub_event_type_code=sub_event_type_code)

    conn.execute(
        "DELETE FROM current_event_brackets WHERE event_id = ? AND sub_event_type_code = ?",
        (event_id, sub_event_type_code),
    )
    conn.executemany(
        """
        INSERT INTO current_event_brackets (
            event_id, sub_event_type_code, draw_code, bracket_code, stage_code, round_code,
            round_order, bracket_position, external_unit_code, scheduled_date, scheduled_time,
            match_score, winner_side, status, side_a_previous_unit, side_b_previous_unit,
            side_a_team_code, side_b_team_code, side_a_placeholder, side_b_placeholder,
            raw_source_payload, last_synced_at, created_at, updated_at
        ) VALUES (
            :event_id, :sub_event_type_code, :draw_code, :bracket_code, :stage_code, :round_code,
            :round_order, :bracket_position, :external_unit_code, :scheduled_date, :scheduled_time,
            :match_score, :winner_side, :status, :side_a_previous_unit, :side_b_previous_unit,
            :side_a_team_code, :side_b_team_code, :side_a_placeholder, :side_b_placeholder,
            :raw_source_payload, :last_synced_at, datetime('now'), datetime('now')
        )
        """,
        rows,
    )
    return event_id, sub_event_type_code, len(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import GetBrackets_*.json into current_event_brackets.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory containing GetBrackets_*.json")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--event-id", type=int)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_dir = args.input_dir.resolve()
    db_path = args.db_path.resolve()
    files = sorted(input_dir.glob("GetBrackets_*.json"))
    if not files:
        print(f"No GetBrackets_*.json files found in {input_dir}", file=sys.stderr)
        return 1

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN")
        reports: list[tuple[int, str, int]] = []
        for path in files:
            reports.append(import_file(conn, path, explicit_event_id=args.event_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for event_id, sub_event_type_code, count in reports:
        print(f"Imported {count} bracket rows for {event_id} / {sub_event_type_code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
