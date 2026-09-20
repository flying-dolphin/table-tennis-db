#!/usr/bin/env python3
"""Capture and normalize Asian Games table-tennis result details."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.asian_games_2026.common import (
    EVENT_ID,
    NORMALIZED_ROOT,
    RAW_ROOT,
    SOURCE_TIME_ZONE,
    DISPLAY_TIME_ZONE,
    STATE_ROOT,
    api_path,
    atomic_write_json,
    convert_source_timestamp,
    fetch_json,
    normalize_status,
    round_meta,
    sub_event_code,
)

TEAM_EVENTS = {"MT", "WT", "XT"}
DEFAULT_DETAIL_STATUSES = {"RUNNING", "LIVE", "UNOFFICIAL", "OFFICIAL", "FINISHED"}


def select_detail_units(rows: list[dict[str, Any]], *, all_linked: bool = False) -> list[dict[str, Any]]:
    selected = []
    for row in rows:
        status = str(row.get("Status") or "").upper()
        if row.get("isH2H") is not True or row.get("ShowLink") is not True or not row.get("Key"):
            continue
        if all_linked or status in DEFAULT_DETAIL_STATUSES:
            selected.append(row)
    return selected


def _player(value: dict[str, Any], *, order: int) -> dict[str, Any]:
    return {
        "source_id": str(value.get("Reg") or "") or None,
        "name": str(value.get("Name") or value.get("NameS") or "").strip(),
        "country": str(value.get("Org") or "").strip() or None,
        "order": int(value.get("Order") or order),
    }


def _winner_side(competitors: list[dict[str, Any]]) -> str | None:
    for index, competitor in enumerate(competitors[:2]):
        if str(competitor.get("WLT") or "").upper() == "W" or competitor.get("Winner") is True:
            return "A" if index == 0 else "B"
    return None


def _score(competitors: list[dict[str, Any]], results: dict[str, Any]) -> str | None:
    if len(competitors) >= 2:
        home = str(competitors[0].get("Result") or "").strip()
        away = str(competitors[1].get("Result") or "").strip()
        if home or away:
            return f"{home or '0'}-{away or '0'}"
    return str(results.get("ResDetail") or "").strip() or None


def _games(results: dict[str, Any]) -> list[dict[str, Any]]:
    current_period = int(results.get("CurrentPeriod") or 0)
    games = []
    for period in results.get("Periods") or []:
        if not isinstance(period, dict):
            continue
        order = int(period.get("Order") or len(games) + 1)
        home = str(period.get("ResHome") or "").strip()
        away = str(period.get("ResAway") or "").strip()
        if order > current_period and (not home or home == "0") and (not away or away == "0"):
            continue
        games.append({"player": int(home or 0), "opponent": int(away or 0)})
    return games


def _match_sides(competitors: list[dict[str, Any]], winner_side: str | None) -> list[dict[str, Any]]:
    output = []
    for index, competitor in enumerate(competitors[:2], start=1):
        members = [item for item in competitor.get("Members") or [] if isinstance(item, dict)]
        if members:
            players = [_player(item, order=order) for order, item in enumerate(members, start=1)]
        else:
            players = [_player(competitor, order=1)] if competitor.get("Name") else []
        output.append(
            {
                "side_no": index,
                "team_code": str(competitor.get("Org") or "").strip() or None,
                "is_winner": winner_side == ("A" if index == 1 else "B"),
                "players": players,
            }
        )
    return output


def _base(info: dict[str, Any]) -> dict[str, Any]:
    timestamp = convert_source_timestamp(str(info["DateTimeRaw"]))
    stage_code, round_code, group_code = round_meta(
        str(info.get("PhaseDesc") or ""),
        phase_code=str(info.get("Phase") or "") or None,
    )
    return {
        "external_match_code": str(info.get("Key") or info.get("ResCode") or ""),
        "sub_event_type_code": sub_event_code(str(info.get("EventDesc") or "")),
        "stage_label": str(info.get("PhaseDescA") or info.get("PhaseDesc") or "") or None,
        "stage_code": stage_code,
        "round_label": str(info.get("PhaseDesc") or "") or None,
        "round_code": round_code,
        "group_code": group_code,
        "session_label": str(info.get("UnitDescA") or info.get("UnitDesc") or "") or None,
        "scheduled_local_at": timestamp.source_local,
        "scheduled_utc_at": timestamp.utc,
        "scheduled_beijing_at": timestamp.beijing,
        "table_no": str(info.get("LocDesc") or "") or None,
        "status": normalize_status(str(info.get("Status") or "")),
        "source_status": str(info.get("Status") or "") or None,
    }


def normalize_match_unit(unit: dict[str, Any], *, parent_code: str | None = None) -> dict[str, Any]:
    info = unit.get("Info") or {}
    competitors = [item for item in unit.get("Competitors") or [] if isinstance(item, dict)]
    results = unit.get("Results") or {}
    winner_side = _winner_side(competitors)
    output = {
        "kind": "match",
        **_base(info),
        "parent_external_match_code": parent_code,
        "match_score": _score(competitors, results),
        "games": _games(results),
        "winner_side": winner_side,
        "winner_name": next((c.get("Name") for c in competitors if str(c.get("WLT") or "").upper() == "W"), None),
        "sides": _match_sides(competitors, winner_side),
        "raw_source_payload": unit,
    }
    return output


def normalize_detail(detail: dict[str, Any]) -> dict[str, Any]:
    info = detail.get("Info") or {}
    event_code = sub_event_code(str(info.get("EventDesc") or ""))
    if event_code not in TEAM_EVENTS:
        return normalize_match_unit(detail)

    competitors = [item for item in detail.get("Competitors") or [] if isinstance(item, dict)]
    results = detail.get("Results") or {}
    winner_side = _winner_side(competitors)
    output = {
        "kind": "team_tie",
        **_base(info),
        "match_score": _score(competitors, results),
        "winner_side": winner_side,
        "winner_team_code": next((c.get("Org") for c in competitors if str(c.get("WLT") or "").upper() == "W"), None),
        "sides": [],
        "rubbers": [],
        "raw_source_payload": detail,
    }
    for index, competitor in enumerate(competitors[:2], start=1):
        roster = [item for item in competitor.get("Members") or [] if isinstance(item, dict)]
        output["sides"].append(
            {
                "side_no": index,
                "team_code": str(competitor.get("Org") or "").strip() or None,
                "team_name": str(competitor.get("Name") or competitor.get("OrgDesc") or "").strip() or None,
                "is_winner": winner_side == ("A" if index == 1 else "B"),
                "nominated_players": [_player(item, order=order) for order, item in enumerate(roster, start=1)],
            }
        )
    parent_code = output["external_match_code"]
    output["rubbers"] = [
        normalize_match_unit(unit, parent_code=parent_code)
        for unit in detail.get("SubUnits") or []
        if isinstance(unit, dict) and unit.get("Info")
    ]
    return output


def _daily_as_detail(row: dict[str, Any]) -> dict[str, Any]:
    competitors = [row.get("Home"), row.get("Away")]
    return {
        "Info": row,
        "Results": {"Periods": row.get("Periods") or []},
        "Competitors": [item for item in competitors if isinstance(item, dict)],
        "SubUnits": [],
    }


def build_snapshot(rows_by_date: dict[str, list[dict[str, Any]]], details: dict[str, dict[str, Any]]) -> dict[str, Any]:
    units: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rows in rows_by_date.values():
        for row in rows:
            if row.get("isH2H") is not True or not row.get("Key"):
                continue
            key = str(row["Key"])
            if key in seen:
                continue
            seen.add(key)
            units.append(normalize_detail(details.get(key) or _daily_as_detail(row)))
    for key, detail in details.items():
        if key not in seen:
            units.append(normalize_detail(detail))
    return {
        "event_id": EVENT_ID,
        "source_time_zone": SOURCE_TIME_ZONE,
        "display_time_zone": DISPLAY_TIME_ZONE,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "schedule_dates": sorted(rows_by_date),
        "team_ties": [item for item in units if item["kind"] == "team_tie"],
        "matches": [item for item in units if item["kind"] == "match"],
    }


def load_schedule_raw(raw_root: Path) -> dict[str, list[dict[str, Any]]]:
    rows_by_date = {}
    for path in sorted((raw_root / "schedule").glob("????-??-??.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows_by_date[path.stem] = [item for item in payload if isinstance(item, dict)]
    if not rows_by_date:
        raise ValueError("no raw daily schedule files; run scrape_schedule first")
    return rows_by_date


def _cached_detail_status(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    info = payload.get("Info") if isinstance(payload, dict) else None
    return str(info.get("Status") or "").upper() if isinstance(info, dict) else None


def capture_details(rows_by_date: dict[str, list[dict[str, Any]]], *, raw_root: Path, all_linked: bool) -> dict[str, dict[str, Any]]:
    result_dir = raw_root / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    requested: dict[str, dict[str, Any]] = {}
    for rows in rows_by_date.values():
        for row in select_detail_units(rows, all_linked=all_linked):
            requested[str(row["Key"])] = row
    for key in sorted(requested):
        cached_path = result_dir / f"{key}.json"
        source_status = str(requested[key].get("Status") or "").upper()
        # Running units must be refreshed. Official units are immutable in the
        # normal loop and are fetched once; the final --all-linked sweep forces
        # a reconciliation of every linked result.
        cached_status = _cached_detail_status(cached_path) if cached_path.exists() else None
        if (
            cached_path.exists()
            and source_status in {"OFFICIAL", "FINISHED"}
            and cached_status in {"OFFICIAL", "FINISHED"}
            and not all_linked
        ):
            continue
        payload = fetch_json(api_path(f"/results/{key}"))
        if not isinstance(payload, dict) or not payload.get("Info"):
            raise ValueError(f"invalid result detail for {key}")
        atomic_write_json(cached_path, payload)

    details: dict[str, dict[str, Any]] = {}
    for path in result_dir.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("Info"), dict):
            key = str(payload["Info"].get("Key") or path.stem)
            details[key] = payload
    return details


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="抓取亚运会乒乓球比赛详情")
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--output", type=Path, default=NORMALIZED_ROOT / "current_matches.json")
    parser.add_argument("--all-linked", action="store_true", help="抓取所有已有详情链接的比赛，用于最终核对")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        rows_by_date = load_schedule_raw(args.raw_root)
        details = capture_details(rows_by_date, raw_root=args.raw_root, all_linked=args.all_linked)
        snapshot = build_snapshot(rows_by_date, details)
        atomic_write_json(args.output, snapshot)
        atomic_write_json(
            STATE_ROOT / "latest_scrape.json",
            {
                "scraped_at": snapshot["scraped_at"],
                "team_ties": len(snapshot["team_ties"]),
                "matches": len(snapshot["matches"]),
                "result_details": len(details),
            },
        )
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"比赛详情抓取失败：{exc}", file=sys.stderr)
        return 1
    print(f"已标准化 {len(snapshot['team_ties'])} 场团体赛、{len(snapshot['matches'])} 场单项赛")
    return 0


if __name__ == "__main__":
    sys.exit(main())
