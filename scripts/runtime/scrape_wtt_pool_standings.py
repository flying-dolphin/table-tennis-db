#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture WTT team-event pool standings for all groups (Stage 1A + 1B).

The page-level standings data comes from the cached frontdoor endpoint:
`websitecacheddata/{event_id}/poolstandings/{team_code}.json`.
Each team file contains multiple wrappers (per-group intermediates plus an
official aggregate). Per (gender, group) we keep the row from the wrapper with
the newest `(LocalDate, LocalTime)` timestamp so the freshest intermediate wins
over a stale aggregate.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sys
import time
import urllib.error
import urllib.request
import zlib
from urllib.parse import quote
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import brotli

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"
API_BASE = "https://liveeventsapi.worldtabletennis.com/api/cms"
WTT_CACHEDDATA_BASE = "https://wtt-web-frontdoor-withoutcache-cqakg0andqf5hchn.a01.azurefd.net/websitecacheddata"
TARGET_CODES = ("MTEAM", "WTEAM")

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


def canonical_stage_label(stage_label: str) -> str:
    normalized = stage_label.strip()
    if "groups" in normalized.lower():
        return "Groups"
    return normalized


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def normalize_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def decode_response_body(body: bytes, content_encoding: str | None) -> str:
    encoding = (content_encoding or "").lower().strip()
    if encoding == "br":
        body = brotli.decompress(body)
    elif encoding == "gzip":
        body = gzip.decompress(body)
    elif encoding == "deflate":
        body = zlib.decompress(body)
    elif encoding not in ("", "identity"):
        raise ValueError(f"unsupported content encoding: {content_encoding}")
    return body.decode("utf-8")


def loads_response_json(body: bytes, content_encoding: str | None) -> Any:
    return json.loads(decode_response_body(body, content_encoding))


def repair_cp936_mojibake(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        repaired = value.encode("cp936").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value

    def cjk_count(text: str) -> int:
        return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")

    if cjk_count(value) == 0 or cjk_count(repaired) >= cjk_count(value):
        return value
    return repaired


def athlete_name(athlete: dict[str, Any]) -> str:
    desc = athlete.get("Description") or {}
    given = (repair_cp936_mojibake(desc.get("GivenName")) or "").strip()
    family = (repair_cp936_mojibake(desc.get("FamilyName")) or "").strip()
    return f"{given} {family}".strip()


def normalize_team_row(row: dict[str, Any]) -> dict[str, Any]:
    competitor = row.get("Competitor") or {}
    composition = competitor.get("Composition") or {}
    athletes = composition.get("Athlete") or []

    return {
        "group": row.get("Group"),
        "organization": competitor.get("Organization"),
        "competitor_code": competitor.get("Code"),
        "team_name": repair_cp936_mojibake(((competitor.get("Description") or {}).get("TeamName"))),
        "qualification_mark": row.get("QualificationMark"),
        "played": row.get("Played"),
        "won": row.get("Won"),
        "lost": row.get("Lost"),
        "result": row.get("Result"),
        "rank": row.get("Rank"),
        "rank_equal": row.get("RankEqual"),
        "for": row.get("For"),
        "against": row.get("Against"),
        "diff": row.get("Diff"),
        "ratio": row.get("Ratio"),
        "games_played": row.get("GamesPlayed"),
        "games_won": row.get("GamesWon"),
        "games_lost": row.get("GamesLost"),
        "tie_ratio": row.get("TieRatio"),
        "result_type": row.get("ResultType"),
        "irm": row.get("Irm"),
        "players": [
            {
                "code": athlete.get("Code"),
                "order": athlete.get("Order"),
                "if_id": ((athlete.get("Description") or {}).get("IfId")),
                "organization": repair_cp936_mojibake(((athlete.get("Description") or {}).get("Organization"))),
                "gender": repair_cp936_mojibake(((athlete.get("Description") or {}).get("Gender"))),
                "birth_date": repair_cp936_mojibake(((athlete.get("Description") or {}).get("BirthDate"))),
                "name": athlete_name(athlete),
            }
            for athlete in athletes
        ],
        "extended_results": ((row.get("ExtendedResults") or {}).get("ExtendedResult")) or [],
    }


def fetch_pool_standings(event_id: int, retries: int = 4, backoff: float = 1.5) -> list[dict[str, Any]]:
    url = f"{API_BASE}/GetPoolStandings/{event_id}"
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=REQ_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 204:
                    return []
                body = resp.read()
                data = loads_response_json(body, resp.headers.get("Content-Encoding"))
                if not isinstance(data, list):
                    raise ValueError(f"unexpected response type: {type(data).__name__}")
                return data
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(backoff ** attempt)
                continue
            raise RuntimeError(f"failed after {retries} attempts: {last_err}") from last_err
    return []


def fetch_cached_pool_standings(event_id: int, team_code: str, retries: int = 4, backoff: float = 1.5) -> list[dict[str, Any]]:
    q = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    url = f"{WTT_CACHEDDATA_BASE}/{event_id}/poolstandings/{team_code}.json?q={quote(q)}"
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=REQ_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 204:
                    return []
                body = resp.read()
                data = loads_response_json(body, resp.headers.get("Content-Encoding"))
            if not isinstance(data, list):
                raise ValueError(f"unexpected response type: {type(data).__name__}")
            return data
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(backoff ** attempt)
                continue
            raise RuntimeError(f"failed after {retries} attempts: {last_err}") from last_err
    return []


def classify_team_code(document_code: str | None) -> str | None:
    if not document_code:
        return None
    code = document_code.strip()
    if code.startswith("TTEMTEAM"):
        return "MTEAM"
    if code.startswith("TTEWTEAM"):
        return "WTEAM"
    return None


def wrapper_timestamp_key(payload: dict[str, Any]) -> tuple[str, int]:
    """Sortable key — newer wrappers compare greater."""
    date = (payload.get("UtcDate") or payload.get("LocalDate") or "")
    raw_time = payload.get("UtcTime") or payload.get("LocalTime") or "0"
    try:
        time_val = int(str(raw_time))
    except (TypeError, ValueError):
        time_val = 0
    return (str(date), time_val)


def build_meta_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    extended_infos = (payload.get("Competition") or {}).get("ExtendedInfos") or {}
    return {
        "event_id": payload.get("EventId"),
        "competition_code": payload.get("CompetitionCode"),
        "document_code": payload.get("DocumentCode"),
        "document_type": payload.get("DocumentType"),
        "result_status": payload.get("ResultStatus"),
        "source": payload.get("Source"),
        "local_date": payload.get("LocalDate"),
        "local_time": payload.get("LocalTime"),
        "utc_date": payload.get("UtcDate"),
        "utc_time": payload.get("UtcTime"),
        "sport_description": extended_infos.get("SportDescription"),
        "venue_description": extended_infos.get("VenueDescription"),
        "progress": extended_infos.get("Progress"),
    }


def aggregate_by_team(wrappers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Merge wrappers into per-team-code snapshots covering every group seen.

    For each (team_code, group) we keep the row from the wrapper with the newest
    timestamp, so a fresh per-group intermediate overrides a stale aggregate row.
    """
    # Sort wrappers oldest -> newest so later writes win on ties.
    enriched: list[tuple[tuple[str, int], str, dict[str, Any]]] = []
    for wrapper in wrappers:
        payload = normalize_payload(wrapper.get("MessagePayload"))
        if not isinstance(payload, dict):
            continue
        team_code = classify_team_code(payload.get("DocumentCode"))
        if team_code not in TARGET_CODES:
            continue
        enriched.append((wrapper_timestamp_key(payload), team_code, payload))
    enriched.sort(key=lambda item: item[0])

    by_team: dict[str, dict[str, Any]] = {}
    for _key, team_code, payload in enriched:
        slot = by_team.setdefault(
            team_code,
            {
                "rows_by_group_org": {},  # (group, org) -> normalized row
                "group_sources": {},       # group -> {document_code, status, ...}
                "latest_meta": None,
                "latest_key": ("", 0),
                "wrapper_count": 0,
                "document_codes": [],
            },
        )
        slot["wrapper_count"] += 1
        doc_code = payload.get("DocumentCode")
        if doc_code and doc_code not in slot["document_codes"]:
            slot["document_codes"].append(doc_code)

        ts_key = wrapper_timestamp_key(payload)
        if ts_key >= slot["latest_key"]:
            slot["latest_key"] = ts_key
            slot["latest_meta"] = build_meta_from_payload(payload)

        results = (payload.get("Competition") or {}).get("Result") or []
        for raw_row in results:
            normalized = normalize_team_row(raw_row)
            group = normalized.get("group") or ""
            org = normalized.get("organization") or normalized.get("competitor_code") or ""
            slot["rows_by_group_org"][(group, org)] = normalized
            slot["group_sources"][group] = {
                "document_code": payload.get("DocumentCode"),
                "result_status": payload.get("ResultStatus"),
                "local_date": payload.get("LocalDate"),
                "local_time": payload.get("LocalTime"),
                "utc_date": payload.get("UtcDate"),
                "utc_time": payload.get("UtcTime"),
            }
    return by_team


def build_team_snapshot(slot: dict[str, Any]) -> dict[str, Any]:
    rows = list(slot["rows_by_group_org"].values())

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row.get("group") or "", []).append(row)

    def rank_sort_key(item: dict[str, Any]) -> tuple[int, str]:
        rank_raw = item.get("rank")
        try:
            rank_int = int(rank_raw) if rank_raw not in (None, "") else 9999
        except (TypeError, ValueError):
            rank_int = 9999
        return (rank_int, item.get("organization") or "")

    for grp_rows in groups.values():
        grp_rows.sort(key=rank_sort_key)

    rows_sorted = sorted(
        rows,
        key=lambda r: (r.get("group") or "", rank_sort_key(r)[0], r.get("organization") or ""),
    )

    return {
        "competition_meta": slot["latest_meta"] or {},
        "rows": rows_sorted,
        "groups": dict(sorted(groups.items())),
        "group_sources": dict(sorted(slot["group_sources"].items())),
        "source_document_codes": slot["document_codes"],
        "wrapper_count": slot["wrapper_count"],
    }


def write_outputs(event_dir: Path, snapshots: dict[str, dict[str, Any]], meta: dict[str, Any]) -> None:
    event_dir.mkdir(parents=True, exist_ok=True)
    (event_dir / "standings_capture_summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="",
    )
    for code, snapshot in sorted(snapshots.items()):
        (event_dir / f"{code}_standings.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="",
        )


def analyze_event(
    event_id: int,
    live_event_data_root: Path,
    *,
    stage_label: str,
) -> int:
    canonical_label = canonical_stage_label(stage_label)
    output_dir = live_event_data_root / str(event_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshots: dict[str, dict[str, Any]] = {}
    captured_urls: dict[str, str] = {}
    for team_code in TARGET_CODES:
        cached_url = f"{WTT_CACHEDDATA_BASE}/{event_id}/poolstandings/{team_code}.json"
        logger.info("Fetching %s", cached_url)
        try:
            wrappers = fetch_cached_pool_standings(event_id, team_code)
            source_url = cached_url
        except Exception as cached_exc:
            live_url = f"{API_BASE}/GetPoolStandings/{event_id}"
            logger.warning("Cached standings fetch failed for %s: %s; falling back to %s", team_code, cached_exc, live_url)
            try:
                wrappers = fetch_pool_standings(event_id)
                source_url = live_url
            except Exception as exc:
                logger.error("Failed to fetch pool standings for %s: %s", team_code, exc)
                return 2

        if not wrappers:
            logger.error("Pool standings response was empty for event %s team %s", event_id, team_code)
            return 1

        by_team = aggregate_by_team(wrappers)
        snapshot = build_team_snapshot(by_team[team_code]) if team_code in by_team else None
        if snapshot is None:
            logger.error("Missing pool standings snapshot for team %s (available: %s)", team_code, ", ".join(sorted(by_team.keys())) or "none")
            return 1
        snapshots[team_code] = snapshot
        captured_urls[team_code] = source_url

    missing = [code for code in TARGET_CODES if code not in snapshots]
    if missing:
        logger.error(
            "Missing pool standings for: %s (available: %s)",
            ", ".join(missing),
            ", ".join(sorted(snapshots.keys())) or "none",
        )
        return 1

    for code, snapshot in sorted(snapshots.items()):
        groups = snapshot.get("groups") or {}
        logger.info(
            "Captured %s standings: %d groups (%s) from %d wrapper(s)",
            code,
            len(groups),
            ", ".join(sorted(groups.keys())) or "-",
            snapshot.get("wrapper_count", 0),
        )

    meta = {
        "event_id": event_id,
        "stage_label": canonical_label,
        "api_url": f"{WTT_CACHEDDATA_BASE}/{event_id}/poolstandings/{{team_code}}.json",
        "output_dir": str(output_dir),
        "captured_codes": sorted(snapshots.keys()),
        "captured_urls": captured_urls,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "group_summary": {
            code: sorted((snapshot.get("groups") or {}).keys())
            for code, snapshot in sorted(snapshots.items())
        },
    }
    write_outputs(output_dir, snapshots, meta)
    logger.info("Saved pool standings analysis to %s", output_dir)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture WTT pool standings for all groups via the live API.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument(
        "--stage-label",
        default="Groups",
        help="Stored stage label is normalized to 'Groups'. Kept for orchestrator compatibility.",
    )
    parser.add_argument("--live-event-data-root", type=Path, default=DEFAULT_LIVE_EVENT_DATA_DIR)
    parser.add_argument("--verbose", action="store_true")
    # Browser-related flags retained as no-ops so the existing orchestrator (`scrape_current_event.py`)
    # can keep passing them without modification.
    parser.add_argument("--headless", action="store_true", default=True, help=argparse.SUPPRESS)
    parser.add_argument("--cdp-port", type=int, default=9222, help=argparse.SUPPRESS)
    parser.add_argument("--use-cdp", action="store_true", help=argparse.SUPPRESS)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.verbose)
    return analyze_event(
        args.event_id,
        args.live_event_data_root.resolve(),
        stage_label=str(args.stage_label),
    )


if __name__ == "__main__":
    sys.exit(main())
