#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared WTT scraping helpers for current-event scripts."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"
DEFAULT_SUB_EVENTS = ["MTEAM", "WTEAM"]
OFFICIAL_RESULTS_PAGE_SIZE = 100

API_BASE = "https://liveeventsapi.worldtabletennis.com/api/cms"
LIVE_MATCH_STATIC_BASE = "https://wtt-web-frontdoor-withoutcache-cqakg0andqf5hchn.a01.azurefd.net"

REQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.worldtabletennis.com",
    "Referer": "https://www.worldtabletennis.com/",
}


def doc_code_for_sub(sub_event: str) -> str:
    sub = (sub_event + "-----")[:5]
    return f"TTE{sub}{'-' * 34}"


def fetch_json(url: str, retries: int = 4, backoff: float = 1.5) -> bytes | None:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=REQ_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 204:
                    return None
                return resp.read()
        except urllib.error.HTTPError:
            return None
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(backoff**attempt)
            continue
    print(f"    ✗ {url} failed after {retries} attempts: {last_err}")
    return None


def save_json(out_path: Path, body: bytes) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(body)
    return len(body)


def fetch_json_value(url: str, retries: int = 4, backoff: float = 1.5):
    body = fetch_json(url, retries=retries, backoff=backoff)
    if body is None:
        return None
    return json.loads(body.decode("utf-8"))


def normalize_match_code(value: str | None) -> str:
    return (value or "").replace(" ", "").rstrip("-").strip()


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


def parse_score_pair(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.search(r"(\d+)\s*-\s*(\d+)", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def normalize_games(value) -> list[str]:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return [part for part in parts if part]
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip())
            elif isinstance(item, dict):
                for key in ("value", "score", "gameScore", "result"):
                    raw = item.get(key)
                    if isinstance(raw, str) and raw.strip():
                        normalized.append(raw.strip())
                        break
        return normalized
    return []


def unit_status_priority(unit: dict) -> int:
    status = (unit.get("ScheduleStatus") or "").strip().lower()
    mapping = {
        "official": 60,
        "finished": 55,
        "completed": 55,
        "intermediate": 50,
        "in progress": 50,
        "live": 50,
        "start list": 40,
        "scheduled": 30,
    }
    return mapping.get(status, 0)


def unit_completeness(unit: dict) -> int:
    starts = (((unit.get("StartList") or {}).get("Start")) or [])
    athletes = 0
    organizations = 0
    for start in starts[:2]:
        competitor = (start or {}).get("Competitor") or {}
        if competitor.get("Organization"):
            organizations += 1
        athletes += len((((competitor.get("Composition") or {}).get("Athlete")) or []))

    return (
        athletes * 5
        + organizations * 3
        + (2 if unit.get("Location") else 0)
        + (2 if unit.get("ActualStartDate") else 0)
        + (2 if unit.get("ActualEndDate") else 0)
        + (1 if text_value(unit.get("ItemName")) or text_value(unit.get("ItemDescription")) else 0)
    )


def pick_preferred_unit(left: dict, right: dict) -> dict:
    status_diff = unit_status_priority(left) - unit_status_priority(right)
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


def build_schedule_unit_index(schedule_payload) -> dict[str, dict]:
    index: dict[str, dict] = {}
    if not isinstance(schedule_payload, list):
        return index

    for entry in schedule_payload:
        competition = (entry or {}).get("Competition") or {}
        for unit in competition.get("Unit") or []:
            if not isinstance(unit, dict):
                continue
            code = normalize_match_code(unit.get("Code"))
            if code:
                current = index.get(code)
                index[code] = unit if current is None else pick_preferred_unit(current, unit)
    return index


def build_side_from_schedule_start(start: dict) -> dict:
    competitor = start.get("Competitor") or {}
    athletes = (((competitor.get("Composition") or {}).get("Athlete")) or [])
    return {
        "competitor_code": competitor.get("Code"),
        "organization": competitor.get("Organization"),
        "seed": competitor.get("Seed"),
        "qualifier": competitor.get("Qualifier"),
        "display_name": competitor_name(competitor),
        "players": [
            {
                "code": athlete.get("Code"),
                "if_id": ((athlete.get("Description") or {}).get("IfId")),
                "organization": ((athlete.get("Description") or {}).get("Organization")),
                "gender": ((athlete.get("Description") or {}).get("Gender")),
                "birth_date": ((athlete.get("Description") or {}).get("BirthDate")),
                "name": athlete_name(athlete),
            }
            for athlete in athletes
        ],
    }


def load_local_schedule_payload(event_dir: Path):
    schedule_path = event_dir / "GetEventSchedule.json"
    if not schedule_path.exists():
        schedule_path = event_dir / "schedule" / "GetEventSchedule.json"
    if not schedule_path.exists():
        return None
    try:
        return json.loads(schedule_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def normalize_live_result_item(item: dict, schedule_unit_index: dict[str, dict]) -> dict:
    match_card = item.get("match_card") if isinstance(item.get("match_card"), dict) else {}
    payload = match_card or item
    code = normalize_match_code(item.get("documentCode") or match_card.get("documentCode") or item.get("Code"))
    schedule_unit = schedule_unit_index.get(code) or {}
    starts = (((schedule_unit.get("StartList") or {}).get("Start")) or [])
    schedule_sides = [build_side_from_schedule_start(start) for start in starts[:2] if isinstance(start, dict)]
    score = extract_match_score(payload) or extract_match_score(item)
    games = normalize_games(payload.get("resultsGameScores") or payload.get("gameScores") or item.get("resultsGameScores") or item.get("gameScores"))
    sides: list[dict] = schedule_sides
    if not sides:
        match_card_competitors = payload.get("competitiors") or payload.get("competitors") or []
        if isinstance(match_card_competitors, list):
            for competitor in match_card_competitors[:2]:
                if not isinstance(competitor, dict):
                    continue
                sides.append(
                    {
                        "competitor_code": competitor.get("competitiorCode") or competitor.get("competitorCode"),
                        "organization": competitor.get("competitiorOrg") or competitor.get("competitorOrg"),
                        "seed": competitor.get("seed"),
                        "qualifier": competitor.get("qualifier"),
                        "display_name": (
                            competitor.get("competitiorName")
                            or competitor.get("competitorName")
                            or competitor.get("competitiorOrg")
                            or competitor.get("competitorOrg")
                        ),
                        "players": [],
                    }
                )

    winner_side = None
    parsed_score = parse_score_pair(score)
    if parsed_score and len(sides) >= 2:
        if parsed_score[0] > parsed_score[1]:
            winner_side = "A"
        elif parsed_score[1] > parsed_score[0]:
            winner_side = "B"

    return {
        "match_code": code,
        "source_status": item.get("ScheduleStatus") or item.get("status") or schedule_unit.get("ScheduleStatus"),
        "sub_event": schedule_unit.get("SubEvent"),
        "round": schedule_unit.get("Round"),
        "scheduled_start": schedule_unit.get("StartDate"),
        "table_no": schedule_unit.get("Location"),
        "session_label": text_value(schedule_unit.get("ItemName")) or text_value(schedule_unit.get("ItemDescription")),
        "score": score,
        "games": games,
        "winner_side": winner_side,
        "sides": sides,
        "raw_result": item,
        "raw_match_card": match_card or None,
    }


def fetch_live_matches_static(event_id: int):
    url = f"{LIVE_MATCH_STATIC_BASE}/websitestaticapifiles/{event_id}/{event_id}_livematchids.json"
    return url, fetch_json_value(url)


def fetch_live_matches_api(event_id: int):
    url = f"{API_BASE}/GetLiveResult?EventId={event_id}"
    return url, fetch_json_value(url)


def fetch_all_official_results(event_id: int, page_size: int = OFFICIAL_RESULTS_PAGE_SIZE) -> tuple[dict, list[dict]]:
    results: list[dict] = []
    seen_keys: set[str] = set()
    skip = 0
    pages = 0

    while True:
        url = (
            f"{API_BASE}/GetOfficialResult?EventId={event_id}"
            f"&include_match_card=true&take={page_size}&skip={skip}"
        )
        page = fetch_json_value(url)
        if page is None:
            if pages == 0:
                return {"url": url, "ok": False, "count": 0, "pages": pages}, []
            break
        if not isinstance(page, list):
            if pages == 0:
                return {"url": url, "ok": False, "count": 0, "pages": pages}, []
            break
        if not page:
            break

        pages += 1
        new_count = 0
        for item in page:
            if not isinstance(item, dict):
                continue
            match_card = item.get("match_card") or {}
            key = json.dumps(
                {
                    "documentCode": item.get("documentCode") or match_card.get("documentCode"),
                    "resultOverallScores": match_card.get("resultOverallScores"),
                    "overallScores": match_card.get("overallScores"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            results.append(item)
            new_count += 1

        if len(page) < page_size or new_count == 0:
            break
        skip += page_size

    return {
        "url": (
            f"{API_BASE}/GetOfficialResult?EventId={event_id}"
            f"&include_match_card=true&take={page_size}"
        ),
        "ok": True,
        "count": len(results),
        "pages": pages,
    }, results


def build_live_results_snapshot(
    event_id: int,
    schedule_payload,
) -> tuple[dict, list[dict], list[dict]]:
    schedule_unit_index = build_schedule_unit_index(schedule_payload)
    static_url, static_payload = fetch_live_matches_static(event_id)
    api_url, api_payload = fetch_live_matches_api(event_id)

    raw_sources = {
        "static_live_matches": {
            "url": static_url,
            "ok": isinstance(static_payload, list),
            "count": len(static_payload) if isinstance(static_payload, list) else 0,
            "payload": static_payload,
        },
        "api_live_result": {
            "url": api_url,
            "ok": isinstance(api_payload, list),
            "count": len(api_payload) if isinstance(api_payload, list) else 0,
            "payload": api_payload,
        },
    }

    merged_by_code: dict[str, dict] = {}
    for source_name, payload in (("static_live_matches", static_payload), ("api_live_result", api_payload)):
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            normalized = normalize_live_result_item(item, schedule_unit_index)
            code = normalized["match_code"]
            if not code:
                continue

            current = merged_by_code.get(code)
            if current is None:
                normalized["sources"] = [source_name]
                merged_by_code[code] = normalized
                continue

            current["sources"] = sorted(set((current.get("sources") or []) + [source_name]))
            if not current.get("score") and normalized.get("score"):
                current["score"] = normalized["score"]
            if not current.get("games") and normalized.get("games"):
                current["games"] = normalized["games"]
            if (not current.get("raw_match_card")) and normalized.get("raw_match_card"):
                current["raw_match_card"] = normalized["raw_match_card"]
            if (not current.get("sides")) and normalized.get("sides"):
                current["sides"] = normalized["sides"]
            if (not current.get("source_status")) and normalized.get("source_status"):
                current["source_status"] = normalized["source_status"]
            if (not current.get("winner_side")) and normalized.get("winner_side"):
                current["winner_side"] = normalized["winner_side"]

    normalized = sorted(merged_by_code.values(), key=lambda item: (item.get("scheduled_start") or "", item.get("match_code") or ""))
    detail_rich = [
        item
        for item in normalized
        if item.get("score") and item.get("games") and any(side.get("players") for side in item.get("sides") or [])
    ]
    summary = {
        "event_id": event_id,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sources": {
            key: {
                "url": value["url"],
                "ok": value["ok"],
                "count": value["count"],
            }
            for key, value in raw_sources.items()
        },
        "matches": len(normalized),
        "detail_rich_matches": len(detail_rich),
    }
    return summary, normalized, [raw_sources]


def scrape_official_results_only(
    event_id: int,
    event_dir: Path,
    *,
    page_size: int = OFFICIAL_RESULTS_PAGE_SIZE,
) -> dict:
    event_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"event_id": event_id, "files": [], "errors": []}
    source_meta, official_results = fetch_all_official_results(event_id, page_size=page_size)

    if not source_meta.get("ok"):
        summary["errors"].append(
            {
                "kind": "official_results",
                "url": source_meta.get("url"),
                "message": "failed to fetch official results",
            }
        )
        _write_summary(event_dir / "_scrape_summary_official_results.json", summary)
        return summary

    payload = json.dumps(official_results, ensure_ascii=False, indent=2).encode("utf-8")
    size = save_json(event_dir / "GetOfficialResult.json", payload)
    summary["files"].append(
        {
            "kind": "official_results",
            "file": "GetOfficialResult.json",
            "size": size,
            "count": len(official_results),
            "pages": source_meta.get("pages", 0),
        }
    )
    summary["sources"] = {"official_results": source_meta}
    _write_summary(event_dir / "_scrape_summary_official_results.json", summary)
    return summary


def extract_match_score(payload: dict) -> str | None:
    for key in ("overallScores", "resultOverallScores", "result", "score", "finalScore"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    team_parent = payload.get("teamParentData") or {}
    extended_info = team_parent.get("extended_info") or {}
    final_result = extended_info.get("final_result") or []
    if final_result and isinstance(final_result[0], dict):
        value = (final_result[0].get("value") or "").strip()
        if value:
            return value
    return None


def _write_summary(summary_path: Path, summary: dict) -> None:
    summary["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def scrape_schedule_only(event_id: int, event_dir: Path) -> dict:
    event_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"event_id": event_id, "files": [], "errors": []}
    kind = "event_schedule"
    url = f"{API_BASE}/GetEventSchedule/{event_id}"
    fname = "GetEventSchedule.json"
    body = fetch_json(url)
    if body is None:
        summary["errors"].append({"kind": kind, "url": url})
    else:
        size = save_json(event_dir / fname, body)
        summary["files"].append({"kind": kind, "file": fname, "size": size})
    _write_summary(event_dir / "_scrape_summary_schedule.json", summary)
    return summary


def scrape_brackets_only(event_id: int, sub_events: list[str], event_dir: Path) -> dict:
    event_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"event_id": event_id, "files": [], "errors": []}
    for sub in sub_events:
        dc = doc_code_for_sub(sub)
        kind = f"brackets_{sub}"
        url = f"{API_BASE}/GetBrackets/{event_id}/{dc}"
        fname = f"GetBrackets_{sub}.json"
        body = fetch_json(url)
        if body is None:
            summary["errors"].append({"kind": kind, "url": url})
            continue
        size = save_json(event_dir / fname, body)
        summary["files"].append({"kind": kind, "file": fname, "size": size})
    _write_summary(event_dir / "_scrape_summary_brackets.json", summary)
    return summary


def print_stage1a_groups(event_dir: Path, groups: list[int]) -> None:
    path = event_dir / "GetEventSchedule.json"
    if not path.exists():
        print(f"missing schedule file: {path}")
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"invalid JSON: {path}")
        return
    units = build_schedule_unit_index(payload)
    for group in groups:
        code = f"GP{group:02d}"
        print(f"[{code}] {len([u for u in units.values() if (u.get('Round') or '').strip().upper() == code])} unit(s)")
