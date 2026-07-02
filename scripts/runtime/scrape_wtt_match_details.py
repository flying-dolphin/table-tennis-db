#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch per-match WTT matchdata for missing completed and current live units."""

from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import brotli

from wtt_scrape_shared import (
    API_BASE,
    DEFAULT_LIVE_EVENT_DATA_DIR,
    LIVE_MATCH_STATIC_BASE,
    PROJECT_ROOT,
    build_schedule_unit_index,
    load_local_schedule_payload,
    normalize_live_result_item,
    normalize_match_code,
)

MATCHDATA_BASE = f"{LIVE_MATCH_STATIC_BASE}/matchdata"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"
MATCHDATA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.worldtabletennis.com",
    "Referer": "https://www.worldtabletennis.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
}
OFFICIAL_STATUSES = {"OFFICIAL"}
LIVE_STATUSES = {"LIVE", "INTERMEDIATE", "DISPLAYED"}
UPCOMING_WINDOW = timedelta(minutes=15)


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


def add_target(selected: list[MatchDetailTarget], seen: set[str], code: str | None, reason: str) -> None:
    normalized = normalize_match_code(code)
    if not normalized or normalized in seen:
        return
    selected.append(MatchDetailTarget(normalized, reason))
    seen.add(normalized)


def parse_schedule_start_utc(value: str | None, event_time_zone: str | None) -> datetime | None:
    if not value or not event_time_zone:
        return None
    try:
        tz = ZoneInfo(event_time_zone)
    except ZoneInfoNotFoundError:
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=tz).astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(timezone.utc)


def load_event_time_zone(db_path: Path, event_id: int) -> str | None:
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT time_zone FROM events WHERE event_id = ?", (event_id,)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass
    return (row[0] or "").strip() if row else None


def load_db_match_detail_targets(db_path: Path, event_id: int) -> list[MatchDetailTarget]:
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            """
            SELECT external_match_code, status, match_score, games
            FROM current_event_matches
            WHERE event_id = ?
              AND external_match_code IS NOT NULL
              AND trim(external_match_code) != ''
              AND (
                status IN ('scheduled', 'live')
                OR (
                  status IN ('completed', 'walkover')
                  AND (
                    match_score IS NULL OR trim(match_score) = ''
                    OR games IS NULL OR trim(games) = '' OR trim(games) = '[]'
                  )
                )
              )
            ORDER BY external_match_code
            """,
            (event_id,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass

    targets: list[MatchDetailTarget] = []
    for code, status, _match_score, _games in rows:
        normalized_status = (status or "").strip().lower()
        if normalized_status == "live":
            reason = "db_live"
        elif normalized_status in {"completed", "walkover"}:
            reason = "db_completed_missing_score"
        else:
            reason = "db_scheduled"
        normalized = normalize_match_code(code)
        if normalized:
            targets.append(MatchDetailTarget(normalized, reason))
    return targets


def select_match_detail_codes(
    schedule_payload: Any,
    official_results: Any,
    live_payload: Any,
    *,
    now_utc: datetime | None = None,
    event_time_zone: str | None = None,
    db_codes: list[MatchDetailTarget] | None = None,
) -> list[MatchDetailTarget]:
    schedule_units = build_schedule_unit_index(schedule_payload)
    known_official_codes = official_result_codes(official_results)
    selected: list[MatchDetailTarget] = []
    seen: set[str] = set()
    now_utc = now_utc or datetime.now(timezone.utc)

    for code, unit in sorted(schedule_units.items(), key=lambda item: (item[1].get("StartDate") or "", item[0])):
        start_utc = parse_schedule_start_utc(unit.get("StartDate"), event_time_zone)
        if start_utc and now_utc <= start_utc <= now_utc + UPCOMING_WINDOW:
            add_target(selected, seen, code, "upcoming")
            continue
        if (unit.get("ScheduleStatus") or "").strip().lower() != "official":
            continue
        if code in known_official_codes:
            continue
        add_target(selected, seen, code, "missing_official")

    for code in live_result_codes(live_payload):
        add_target(selected, seen, code, "live")

    for target in db_codes or []:
        add_target(selected, seen, target.match_code, target.reason)

    return selected


def fetch_match_card(event_id: int, match_code: str) -> tuple[str, dict[str, Any] | None, str | None]:
    doc_code = full_document_code(match_code)
    url = f"{MATCHDATA_BASE}/{event_id}/{doc_code}.json?q={time.strftime('%Y-%m-%d')}"
    payload = fetch_matchdata_json(url)
    if isinstance(payload, dict):
        return url, payload, "static_matchdata"
    official_url = (
        f"{API_BASE}/GetOfficialResult?EventId={event_id}"
        f"&DocumentCode={doc_code}&include_match_card=true"
    )
    official_payload = fetch_matchdata_json(official_url)
    card = extract_official_match_card(official_payload)
    return official_url, card, "official_query" if card is not None else None


def extract_official_match_card(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, list):
        if not payload:
            return None
        first = payload[0]
        if not isinstance(first, dict):
            return None
        card = first.get("match_card")
        return card if isinstance(card, dict) else first
    if isinstance(payload, dict):
        card = payload.get("match_card")
        return card if isinstance(card, dict) else payload
    return None


def decode_response_body(response: Any, body: bytes) -> bytes:
    encoding = ""
    try:
        encoding = response.headers.get("Content-Encoding", "")
    except AttributeError:
        encoding = ""
    if encoding.lower() == "br":
        return brotli.decompress(body)
    if encoding.lower() == "gzip" or body[:2] == b"\x1f\x8b":
        return gzip.decompress(body)
    return body


def fetch_matchdata_json(url: str, retries: int = 2) -> Any:
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=MATCHDATA_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 204:
                    return None
                body = decode_response_body(resp, resp.read())
                if body.startswith(b"\xef\xbb\xbf"):
                    body = body[3:]
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


def scrape_match_details_only(event_id: int, event_dir: Path, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    event_dir.mkdir(parents=True, exist_ok=True)
    schedule_payload = load_local_schedule_payload(event_dir)
    official_payload = load_json_or_default(event_dir / "GetOfficialResult.json", [])
    live_payload = load_json_or_default(event_dir / "GetLiveResult.json", {"matches": []})
    event_time_zone = load_event_time_zone(db_path, event_id)
    db_targets = load_db_match_detail_targets(db_path, event_id)
    targets = select_match_detail_codes(
        schedule_payload,
        official_payload,
        live_payload,
        event_time_zone=event_time_zone,
        db_codes=db_targets,
    )

    cards: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    source_counts = {"static_matchdata": 0, "official_query": 0}
    for target in targets:
        url, card, source_kind = fetch_match_card(event_id, target.match_code)
        if source_kind in source_counts:
            source_counts[source_kind] += 1
        sources.append(
            {
                "match_code": target.match_code,
                "reason": target.reason,
                "url": url,
                "source": source_kind,
                "ok": card is not None,
            }
        )
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
        "source_counts": source_counts,
        "db_targets": len(db_targets),
        "event_time_zone": event_time_zone,
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


def print_fetch_errors(errors: list[dict[str, Any]]) -> None:
    if not errors:
        return
    print(f"  WARNING: {len(errors)} match detail target(s) could not be fetched")
    for error in errors:
        print(
            "    "
            f"match_code={error.get('match_code') or '-'} "
            f"reason={error.get('reason') or '-'} "
            f"url={error.get('url') or '-'}"
        )


def has_useful_match_detail_output(summary: dict[str, Any]) -> bool:
    if summary.get("fetched", 0) > 0:
        return True
    merge = summary.get("merge") if isinstance(summary.get("merge"), dict) else {}
    return any((merge.get(key) or 0) > 0 for key in ("official_added", "live_added", "live_updated"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch per-match WTT matchdata for missing completed and live matches.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--live-event-data-root", type=Path, default=DEFAULT_LIVE_EVENT_DATA_DIR)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    event_dir = args.live_event_data_root.resolve() / str(args.event_id)
    print(f"Scrape WTT match details {args.event_id} -> {event_dir}")
    summary = scrape_match_details_only(args.event_id, event_dir, args.db_path.resolve())
    print(
        f"  [match_details] targets={summary['targets']} fetched={summary['fetched']} "
        f"static={summary['source_counts']['static_matchdata']} "
        f"official_query={summary['source_counts']['official_query']} "
        f"official_added={summary['merge']['official_added']} live_added={summary['merge']['live_added']} "
        f"live_updated={summary['merge']['live_updated']}"
    )
    print_fetch_errors(summary["errors"])
    print()
    print(f"Done: {len(summary['files'])} file(s), {len(summary['errors'])} error(s)")
    return 0 if not summary["errors"] or has_useful_match_detail_output(summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
