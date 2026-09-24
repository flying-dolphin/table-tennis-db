#!/usr/bin/env python3
"""Capture and normalize the official Asian Games individual and team brackets."""

from __future__ import annotations

import argparse
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.asian_games_2026.common import (
    EVENT_ID,
    NORMALIZED_ROOT,
    RAW_ROOT,
    api_path,
    atomic_write_json,
    convert_source_timestamp,
    fetch_json,
    normalize_status,
    phase_round_meta,
)


BRACKET_EVENTS = {
    "MT": "M.TEAM--------------",
    "WT": "W.TEAM--------------",
    "MS": "M.SINGLES-----------",
    "WS": "W.SINGLES-----------",
    "MD": "M.DOUBLES-----------",
    "WD": "W.DOUBLES-----------",
    "XD": "X.DOUBLES-----------",
}

def _phase_round(code: str) -> tuple[str, str, int]:
    metadata = phase_round_meta(code)
    if metadata is None or metadata[3] is None:
        raise ValueError(f"unsupported bracket phase: {code}")
    stage_code, round_code, _, round_order = metadata
    return stage_code, round_code, round_order


def _winner_side(match: dict[str, Any]) -> str | None:
    if (match.get("Home") or {}).get("Win") is True:
        return "A"
    if (match.get("Away") or {}).get("Win") is True:
        return "B"
    return None


def _match_score(match: dict[str, Any]) -> str | None:
    home = str((match.get("Home") or {}).get("Res") or "").strip()
    away = str((match.get("Away") or {}).get("Res") or "").strip()
    return f"{home or '0'}-{away or '0'}" if home or away else None


def _team_code(competitor: dict[str, Any]) -> str | None:
    return str(competitor.get("Org") or "").strip() or None


def _placeholder(competitor: dict[str, Any]) -> str | None:
    team_code = _team_code(competitor)
    if team_code == "BYE":
        return "BYE"
    if competitor.get("Name") or competitor.get("Members"):
        return None
    return "TBD"


def _scheduled_parts(value: str | None) -> tuple[str | None, str | None]:
    if not (value or "").strip():
        return None, None
    converted = convert_source_timestamp(str(value))
    date, time = converted.source_local.split("T", 1)
    return date, time


def normalize_bracket_payload(
    payload: list[dict[str, Any]], *, sub_event_type_code: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    phase_count = 0
    for draw in payload:
        if not isinstance(draw, dict):
            continue
        draw_code = "MAIN" if str(draw.get("Code") or "").upper() == "MAINDRAW" else str(draw.get("Code") or "MAIN")
        previous_matches: list[dict[str, Any]] = []
        for phase in draw.get("Phases") or []:
            if not isinstance(phase, dict):
                continue
            matches = [item for item in phase.get("Matches") or [] if isinstance(item, dict)]
            if not matches:
                continue
            phase_count += 1
            phase_code = str(phase.get("Code") or "")
            stage_code, round_code, round_order = _phase_round(phase_code)
            has_positional_feeders = len(previous_matches) == len(matches) * 2
            for index, match in enumerate(matches):
                info = match.get("Info") or {}
                external_unit_code = str(info.get("Key") or "").strip()
                if not external_unit_code:
                    raise ValueError(f"bracket match without key in {phase_code}")
                home = match.get("Home") if isinstance(match.get("Home"), dict) else {}
                away = match.get("Away") if isinstance(match.get("Away"), dict) else {}
                scheduled_date, scheduled_time = _scheduled_parts(info.get("DateTimeRaw"))
                previous_a = previous_b = None
                if has_positional_feeders:
                    previous_a = str((previous_matches[index * 2].get("Info") or {}).get("Key") or "") or None
                    previous_b = str((previous_matches[index * 2 + 1].get("Info") or {}).get("Key") or "") or None
                rows.append(
                    {
                        "event_id": EVENT_ID,
                        "sub_event_type_code": sub_event_type_code,
                        "draw_code": draw_code,
                        "bracket_code": phase_code,
                        "stage_code": stage_code,
                        "round_code": round_code,
                        "round_order": round_order,
                        "bracket_position": index + 1,
                        "external_unit_code": external_unit_code,
                        "scheduled_date": scheduled_date,
                        "scheduled_time": scheduled_time,
                        "match_score": _match_score(match),
                        "winner_side": _winner_side(match),
                        "status": normalize_status(info.get("Status")),
                        "side_a_previous_unit": previous_a,
                        "side_b_previous_unit": previous_b,
                        "side_a_team_code": _team_code(home),
                        "side_b_team_code": _team_code(away),
                        "side_a_placeholder": _placeholder(home),
                        "side_b_placeholder": _placeholder(away),
                        "raw_source_payload": match,
                    }
                )
            previous_matches = matches
    if phase_count == 0:
        raise ValueError(f"no bracket phases for {sub_event_type_code}")
    return rows


def capture_brackets(*, raw_root: Path) -> dict[str, Any]:
    raw_dir = raw_root / "brackets"
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for sub_event_type_code, official_code in BRACKET_EVENTS.items():
        payload = fetch_json(api_path(f"/brackets/{official_code}"))
        if not isinstance(payload, list):
            raise ValueError(f"invalid bracket payload for {sub_event_type_code}")
        atomic_write_json(raw_dir / f"{official_code}.json", payload)
        normalized = normalize_bracket_payload(payload, sub_event_type_code=sub_event_type_code)
        rows.extend(normalized)
        counts[sub_event_type_code] = len(normalized)
    return {
        "event_id": EVENT_ID,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sub_events": list(BRACKET_EVENTS),
        "counts": counts,
        "brackets": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="抓取亚运会乒乓球单项和团体签表")
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--output", type=Path, default=NORMALIZED_ROOT / "current_brackets.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        snapshot = capture_brackets(raw_root=args.raw_root)
        atomic_write_json(args.output, snapshot)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"签表抓取失败：{exc}", file=sys.stderr)
        return 1
    print("已标准化签表：" + ", ".join(f"{code}={count}" for code, count in snapshot["counts"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
