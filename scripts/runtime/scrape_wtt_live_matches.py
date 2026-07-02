from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import brotli

from wtt_scrape_shared import (
    DEFAULT_LIVE_EVENT_DATA_DIR,
    build_schedule_unit_index,
    load_local_schedule_payload,
    normalize_match_code,
    parse_score_pair,
)

CDN_BASE = "https://wtt-web-frontdoor-withoutcache-cqakg0andqf5hchn.a01.azurefd.net"
CDN_HEADERS = {
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
}


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


def fetch_cdn_json(path: str, retries: int = 2) -> Any:
    url = f"{CDN_BASE}{path}"
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=CDN_HEADERS)
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


def fetch_live_events_index() -> list[dict[str, Any]]:
    payload = fetch_cdn_json(
        "/websitestaticapifiles/general/wtt_live_results_event_id.json"
    )
    if isinstance(payload, list):
        return payload
    return []


def fetch_live_match_ids(event_id: int) -> list[dict[str, Any]]:
    payload = fetch_cdn_json(
        f"/websitestaticapifiles/{event_id}/{event_id}_livematchids.json?EventId={event_id}"
    )
    if isinstance(payload, list):
        return payload
    return []


def fetch_take_10_official(event_id: int) -> list[dict[str, Any]]:
    payload = fetch_cdn_json(
        f"/websitestaticapifiles/{event_id}/{event_id}_take_10_official_results.json"
    )
    if isinstance(payload, list):
        return payload
    return []


def full_document_code(value: str | None) -> str:
    normalized = normalize_match_code(value)
    return normalized + ("-" * max(0, 42 - len(normalized)))


def fetch_matchdata_card(event_id: int, match_code: str) -> dict[str, Any] | None:
    doc_code = full_document_code(match_code)
    path = f"/matchdata/{event_id}/{doc_code}.json?q={time.strftime('%Y-%m-%d')}"
    payload = fetch_cdn_json(path)
    if isinstance(payload, dict):
        return payload
    return None


def sub_event_code_from_name(name: str | None) -> str | None:
    mapping = {
        "Men's Singles": "MS",
        "Women's Singles": "WS",
        "Men's Doubles": "MD",
        "Women's Doubles": "WD",
        "Mixed Doubles": "XD",
        "Men's Teams": "MT",
        "Women's Teams": "WT",
        "Mixed Teams": "XT",
        "Men Singles": "MS",
        "Women Singles": "WS",
        "Men Doubles": "MD",
        "Women Doubles": "WD",
        "Mixed Doubles": "XD",
    }
    if not name:
        return None
    return mapping.get(name.strip())


def round_code_from_description(desc: str | None) -> str | None:
    if not desc:
        return None
    raw = desc.strip()
    if re.search(r"Preliminary Round", raw, re.IGNORECASE):
        return "RND1"
    if re.search(r"Quarterfinal", raw, re.IGNORECASE):
        return "QFNL"
    if re.search(r"Semifinal", raw, re.IGNORECASE):
        return "SFNL"
    if re.search(r"\bFinal\b", raw, re.IGNORECASE) and "Quarterfinal" not in raw and "Semifinal" not in raw:
        return "FNL"
    m = re.search(r"Round of\s+(\d+)", raw, re.IGNORECASE)
    if m:
        size = int(m.group(1))
        if size == 16:
            return "8FNL"
        if size == 32:
            return "R32-"
        if size == 64:
            return "R64-"
        if size == 128:
            return "R128"
    m = re.search(r"Group\s+(\d+)", raw, re.IGNORECASE)
    if m:
        return f"GP{int(m.group(1)):02d}"
    return None


def build_sides_from_competitors(card: dict[str, Any]) -> list[dict[str, Any]]:
    competitors = card.get("competitiors") or card.get("competitors") or []
    sides: list[dict[str, Any]] = []
    for competitor in competitors[:2]:
        if not isinstance(competitor, dict):
            continue
        name = (
            competitor.get("competitiorName")
            or competitor.get("competitorName")
            or ""
        )
        org = (
            competitor.get("competitiorOrg")
            or competitor.get("competitorOrg")
            or ""
        )
        sides.append(
            {
                "competitor_code": competitor.get("competitiorCode") or competitor.get("competitorCode"),
                "organization": org,
                "display_name": name,
                "players": [],
            }
        )
    return sides


def normalize_cdn_match(
    card: dict[str, Any],
    source_status: str,
    schedule_unit_index: dict[str, dict],
) -> dict[str, Any]:
    code = normalize_match_code(card.get("documentCode"))
    schedule_unit = schedule_unit_index.get(code) if schedule_unit_index else None

    score = (
        card.get("resultOverallScores")
        or card.get("overallScores")
        or None
    )
    games_raw = card.get("resultsGameScores") or card.get("gameScores") or ""
    games = [g.strip() for g in games_raw.split(",") if g.strip()] if isinstance(games_raw, str) else (games_raw if isinstance(games_raw, list) else [])

    sides = build_sides_from_competitors(card)

    winner_side = None
    parsed = parse_score_pair(score)
    if parsed and len(sides) >= 2:
        if parsed[0] > parsed[1]:
            winner_side = "A"
        elif parsed[1] > parsed[0]:
            winner_side = "B"

    sub_event_name = card.get("subEventName")
    sub_event = sub_event_code_from_name(sub_event_name) or (schedule_unit.get("SubEvent") if schedule_unit else None)

    table_no = card.get("tableName") or card.get("tableNumber") or (schedule_unit.get("Location") if schedule_unit else None)

    scheduled_start = None
    match_dt = card.get("matchDateTime") or {}
    if isinstance(match_dt, dict):
        scheduled_start = match_dt.get("startDateUTC") or match_dt.get("startDateLocal")

    session_label = None
    if schedule_unit:
        from wtt_scrape_shared import text_value
        session_label = text_value(schedule_unit.get("ItemName")) or text_value(schedule_unit.get("ItemDescription"))
    if not session_label:
        session_label = card.get("subEventDescription")

    round_code = schedule_unit.get("Round") if schedule_unit else None
    if not round_code:
        round_code = round_code_from_description(card.get("subEventDescription"))

    return {
        "match_code": code,
        "source_status": source_status,
        "sub_event": sub_event,
        "sub_event_name": sub_event_name,
        "round": round_code,
        "scheduled_start": scheduled_start,
        "table_no": table_no,
        "session_label": session_label,
        "score": score,
        "games": games,
        "winner_side": winner_side,
        "sides": sides,
        "individual_matches": [],
        "raw_match_card": card,
    }


def scrape_event_matches(
    event_id: int,
    *,
    include_official: bool = False,
    schedule_payload: Any = None,
) -> list[dict[str, Any]]:
    schedule_unit_index = build_schedule_unit_index(schedule_payload) if schedule_payload else {}

    matches: list[dict[str, Any]] = []
    seen_codes: set[str] = set()

    live_ids = fetch_live_match_ids(event_id)
    for entry in live_ids:
        code = normalize_match_code(entry.get("documentCode"))
        if not code or code in seen_codes:
            continue
        sub_type = entry.get("subEventType")

        card = fetch_matchdata_card(event_id, code)
        if card is None:
            continue

        status = (card.get("resultStatus") or "").strip().upper() or "LIVE"

        normalized = normalize_cdn_match(card, status, schedule_unit_index)
        if normalized["match_code"]:
            seen_codes.add(normalized["match_code"])
            matches.append(normalized)

    if include_official:
        official_items = fetch_take_10_official(event_id)
        for item in official_items:
            match_card = item.get("match_card") if isinstance(item.get("match_card"), dict) else {}
            payload = match_card or item
            code = normalize_match_code(
                item.get("documentCode") or match_card.get("documentCode")
            )
            if not code or code in seen_codes:
                continue

            status = (payload.get("resultStatus") or item.get("fullResults") or "OFFICIAL").strip().upper()
            normalized = normalize_cdn_match(payload, status, schedule_unit_index)
            if schedule_unit_index:
                unit = schedule_unit_index.get(normalized.get("match_code"))
                if unit:
                    if not normalized.get("sub_event"):
                        normalized["sub_event"] = unit.get("SubEvent")
                    if not normalized.get("round"):
                        normalized["round"] = unit.get("Round")

            if normalized.get("match_code"):
                seen_codes.add(normalized["match_code"])
                matches.append(normalized)

    matches.sort(
        key=lambda m: (
            m.get("source_status") or "",
            m.get("table_no") or "",
            m.get("match_code") or "",
        )
    )
    return matches


def write_outputs(
    event_dir: Path,
    event_id: int,
    matches: list[dict[str, Any]],
    *,
    schedule_cache_used: bool,
    with_debug_files: bool,
) -> dict[str, Any]:
    event_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "event_id": event_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "cdn_live_matches": {
                "url": f"{CDN_BASE}/websitestaticapifiles/general/wtt_live_results_event_id.json",
                "ok": True,
                "count": len(matches),
            }
        },
        "matches": len(matches),
        "detail_rich_matches": sum(
            1 for m in matches if m.get("score") and m.get("games")
        ),
        "schedule_cache_used": schedule_cache_used,
    }
    normalized_payload = {"summary": summary, "matches": matches}
    normalized_path = event_dir / "GetLiveResult.json"
    normalized_path.write_text(
        json.dumps(normalized_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="",
    )

    script_summary = {
        "event_id": event_id,
        "files": [
            {
                "kind": "live_results_normalized",
                "file": normalized_path.name,
                "size": normalized_path.stat().st_size,
                "count": len(matches),
            }
        ],
        "errors": [],
        "fetched_at": summary["fetched_at"],
    }

    if with_debug_files:
        raw_path = event_dir / "GetLiveResult_cdn_raw.json"
        raw_path.write_text(
            json.dumps(
                {
                    "event_id": event_id,
                    "fetched_at": summary["fetched_at"],
                    "matches": matches,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
            newline="",
        )
        script_summary["files"].append(
            {
                "kind": "live_results_cdn_raw",
                "file": raw_path.name,
                "size": raw_path.stat().st_size,
                "count": len(matches),
            }
        )

    (event_dir / "_scrape_summary_live.json").write_text(
        json.dumps(script_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="",
    )
    return script_summary


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Scrape WTT live matches via CDN JSON (no browser needed)."
    )
    ap.add_argument("--event-id", type=int, required=True)
    ap.add_argument(
        "--live-event-data-root",
        default=str(DEFAULT_LIVE_EVENT_DATA_DIR),
    )
    ap.add_argument("--include-official", action="store_true", help="Also fetch recently completed matches from take_10.")
    ap.add_argument("--with-debug-files", action="store_true")
    ap.add_argument("--timeout-ms", type=int, default=30000)
    ap.add_argument("--verbose", action="store_true")

    ap.add_argument("--use-cdp", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--cdp-port", type=int, default=9222, help=argparse.SUPPRESS)
    ap.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)

    args = ap.parse_args()

    event_dir = Path(args.live_event_data_root) / str(args.event_id)
    print(f"Scrape WTT live matches {args.event_id} -> {event_dir}")

    schedule_payload = load_local_schedule_payload(event_dir)
    schedule_cache_used = bool(schedule_payload)

    matches = scrape_event_matches(
        args.event_id,
        include_official=bool(args.include_official),
        schedule_payload=schedule_payload,
    )

    summary = write_outputs(
        event_dir,
        args.event_id,
        matches,
        schedule_cache_used=schedule_cache_used,
        with_debug_files=bool(args.with_debug_files),
    )

    print(
        f"  [cdn_live_matches] ✓ {len(matches)} matches "
        f"({sum(1 for m in matches if m.get('score') and m.get('games'))} with scores + games)"
    )
    print()
    print(f"Done: {len(summary['files'])} file(s), {len(summary['errors'])} error(s)")
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
