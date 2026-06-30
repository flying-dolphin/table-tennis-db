#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch per-match WTT matchdata for missing completed and current live units."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import brotli

from wtt_scrape_shared import (
    DEFAULT_LIVE_EVENT_DATA_DIR,
    LIVE_MATCH_STATIC_BASE,
    build_schedule_unit_index,
    load_local_schedule_payload,
    normalize_live_result_item,
    normalize_match_code,
)

MATCHDATA_BASE = f"{LIVE_MATCH_STATIC_BASE}/matchdata"
MATCHDATA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.worldtabletennis.com",
    "Referer": "https://www.worldtabletennis.com/",
}
OFFICIAL_STATUSES = {"OFFICIAL"}
LIVE_STATUSES = {"LIVE", "INTERMEDIATE", "DISPLAYED"}


@dataclass(frozen=True)
class MatchDetailTarget:
    match_code: str
    reason: str


def full_document_code(value: str | None) -> str:
    normalized = normalize_match_code(value)
    return normalized + ("-" * max(0, 42 - len(normalized)))


def load_json_or_default(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def official_result_codes(payload: Any) -> set[str]:
    codes: set[str] = set()
    if not isinstance(payload, list):
        return codes
    for item in payload:
        if not isinstance(item, dict):
            continue
        match_card = item.get("match_card") if isinstance(item.get("match_card"), dict) else {}
        code = normalize_match_code(item.get("documentCode") or match_card.get("documentCode"))
        if code:
            codes.add(code)
    return codes


def live_result_codes(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    matches = payload.get("matches")
    if not isinstance(matches, list):
        return []
    codes: list[str] = []
    for item in matches:
        if not isinstance(item, dict):
            continue
        code = normalize_match_code(item.get("match_code") or item.get("documentCode"))
        if code:
            codes.append(code)
    return codes


def select_match_detail_codes(schedule_payload: Any, official_results: Any, live_payload: Any) -> list[MatchDetailTarget]:
    schedule_units = build_schedule_unit_index(schedule_payload)
    known_official_codes = official_result_codes(official_results)
    selected: list[MatchDetailTarget] = []
    seen: set[str] = set()

    for code, unit in sorted(schedule_units.items(), key=lambda item: (item[1].get("StartDate") or "", item[0])):
        if (unit.get("ScheduleStatus") or "").strip().lower() != "official":
            continue
        if code in known_official_codes or code in seen:
            continue
        selected.append(MatchDetailTarget(code, "missing_official"))
        seen.add(code)

    for code in live_result_codes(live_payload):
        if code in seen:
            continue
        selected.append(MatchDetailTarget(code, "live"))
        seen.add(code)

    return selected


def fetch_match_card(event_id: int, match_code: str) -> tuple[str, dict[str, Any] | None]:
    doc_code = full_document_code(match_code)
    url = f"{MATCHDATA_BASE}/{event_id}/{doc_code}.json?q={time.strftime('%Y-%m-%d')}"
    payload = fetch_matchdata_json(url)
    return url, payload if isinstance(payload, dict) else None


def decode_response_body(response: Any, body: bytes) -> bytes:
    encoding = ""
    try:
        encoding = response.headers.get("Content-Encoding", "")
    except AttributeError:
        encoding = ""
    if encoding.lower() == "br":
        return brotli.decompress(body)
    return body


def fetch_matchdata_json(url: str, retries: int = 2) -> Any:
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=MATCHDATA_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 204:
                    return None
                body = decode_response_body(resp, resp.read())
                return json.loads(body.decode("utf-8"))
        except Exception:
            if attempt >= retries:
                return None
            time.sleep(0.5 * attempt)
    return None


def official_result_item(event_id: int, match_card: dict[str, Any]) -> dict[str, Any]:
    return {
        "iD": None,
        "eventId": str(event_id),
        "documentCode": match_card.get("documentCode"),
        "messagePayload": None,
        "subEventType": match_card.get("subEventName"),
        "fullResults": match_card.get("resultStatus"),
        "extended_info": None,
        "match_card": match_card,
        "startDateLocal": ((match_card.get("matchDateTime") or {}).get("startDateLocal")),
    }


def live_result_item(match_card: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventId": match_card.get("eventId"),
        "documentCode": match_card.get("documentCode"),
        "status": match_card.get("resultStatus"),
        "match_card": match_card,
        "subEventType": match_card.get("subEventName"),
    }


def merge_match_cards(
    event_dir: Path,
    event_id: int,
    schedule_payload: Any,
    match_cards: list[dict[str, Any]],
) -> dict[str, int]:
    official_path = event_dir / "GetOfficialResult.json"
    live_path = event_dir / "GetLiveResult.json"
    official_payload = load_json_or_default(official_path, [])
    if not isinstance(official_payload, list):
        official_payload = []
    live_payload = load_json_or_default(live_path, {"summary": {"event_id": event_id}, "matches": []})
    if not isinstance(live_payload, dict):
        live_payload = {"summary": {"event_id": event_id}, "matches": []}
    if not isinstance(live_payload.get("matches"), list):
        live_payload["matches"] = []

    schedule_unit_index = build_schedule_unit_index(schedule_payload)
    existing_official = official_result_codes(official_payload)
    existing_live = {
        normalize_match_code(item.get("match_code"))
        for item in live_payload["matches"]
        if isinstance(item, dict) and normalize_match_code(item.get("match_code"))
    }

    official_added = 0
    live_added = 0
    live_updated = 0
    for match_card in match_cards:
        code = normalize_match_code(match_card.get("documentCode"))
        if not code:
            continue
        status = (match_card.get("resultStatus") or "").strip().upper()
        if status in OFFICIAL_STATUSES:
            if code in existing_official:
                continue
            official_payload.append(official_result_item(event_id, match_card))
            existing_official.add(code)
            official_added += 1
            continue

        if status in LIVE_STATUSES:
            normalized = normalize_live_result_item(live_result_item(match_card), schedule_unit_index)
            if code in existing_live:
                for idx, item in enumerate(live_payload["matches"]):
                    if isinstance(item, dict) and normalize_match_code(item.get("match_code")) == code:
                        live_payload["matches"][idx] = normalized
                        live_updated += 1
                        break
            else:
                live_payload["matches"].append(normalized)
                existing_live.add(code)
                live_added += 1

    official_path.write_text(json.dumps(official_payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="")
    live_payload["matches"].sort(key=lambda item: (item.get("scheduled_start") or "", item.get("match_code") or ""))
    summary = live_payload.get("summary") if isinstance(live_payload.get("summary"), dict) else {}
    summary["event_id"] = event_id
    summary["matches"] = len(live_payload["matches"])
    summary["detail_rich_matches"] = sum(1 for item in live_payload["matches"] if item.get("individual_matches"))
    live_payload["summary"] = summary
    live_path.write_text(json.dumps(live_payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="")

    return {"official_added": official_added, "live_added": live_added, "live_updated": live_updated}


def scrape_match_details_only(event_id: int, event_dir: Path) -> dict[str, Any]:
    event_dir.mkdir(parents=True, exist_ok=True)
    schedule_payload = load_local_schedule_payload(event_dir)
    official_payload = load_json_or_default(event_dir / "GetOfficialResult.json", [])
    live_payload = load_json_or_default(event_dir / "GetLiveResult.json", {"matches": []})
    targets = select_match_detail_codes(schedule_payload, official_payload, live_payload)

    cards: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for target in targets:
        url, card = fetch_match_card(event_id, target.match_code)
        sources.append({"match_code": target.match_code, "reason": target.reason, "url": url, "ok": card is not None})
        if card is None:
            errors.append({"match_code": target.match_code, "reason": target.reason, "url": url})
            continue
        cards.append(card)

    raw_path = event_dir / "GetPostMatchCenter.json"
    raw_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8", newline="")
    merge_report = merge_match_cards(event_dir, event_id, schedule_payload, cards)
    summary = {
        "event_id": event_id,
        "targets": len(targets),
        "fetched": len(cards),
        "files": [{"kind": "post_match_center", "file": raw_path.name, "size": raw_path.stat().st_size, "count": len(cards)}],
        "merge": merge_report,
        "sources": sources,
        "errors": errors,
    }
    (event_dir / "_scrape_summary_match_details.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch per-match WTT matchdata for missing completed and live matches.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--live-event-data-root", type=Path, default=DEFAULT_LIVE_EVENT_DATA_DIR)
    args = parser.parse_args()

    event_dir = args.live_event_data_root.resolve() / str(args.event_id)
    print(f"Scrape WTT match details {args.event_id} -> {event_dir}")
    summary = scrape_match_details_only(args.event_id, event_dir)
    print(
        f"  [match_details] targets={summary['targets']} fetched={summary['fetched']} "
        f"official_added={summary['merge']['official_added']} live_added={summary['merge']['live_added']} "
        f"live_updated={summary['merge']['live_updated']}"
    )
    print()
    print(f"Done: {len(summary['files'])} file(s), {len(summary['errors'])} error(s)")
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
