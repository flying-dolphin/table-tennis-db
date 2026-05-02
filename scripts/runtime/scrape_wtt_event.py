#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WTT 事件抓取：拉取 worldtabletennis.com 上某个 eventId 的公开赛程/签表/实时结果 JSON。

live 链路与 completed 链路分开处理：

  live:
  - websitestaticapifiles/{eventId}/{eventId}_livematchids.json
                                             → 前端 Live Matches 优先使用的静态缓存
  - GetLiveResult?EventId={eventId}          → Live Matches API 回退

  completed:
  - GetOfficialResult?EventId={eventId}&include_match_card=true&take=10
                                             → 最近完赛结果（当前仍保留旧逻辑，后续再替换为全量源）

其他赛程/签表基础端点：

  - GetEventDraws/{eventId}                  → 各 draw（Qualification/Stage 1/Main）起止时间
  - GetEventSchedule/{eventId}               → 全部 unit 级日程，含 Round/StartDate/StartList
  - GetBrackets/{eventId}/{documentCode}     → 每个 sub_event 的 bracket 结构（KO + group 元信息）

输出：
  data/live_event_data/{event_id}/schedule/
  data/live_event_data/{event_id}/match_results/

抓取过程使用纯 HTTP（urllib），不需要打开浏览器；偶尔遇到的 SSL EOF
会自动重试。日程接口涵盖所有 group / KO 比赛，故 Stage 1A Group 1/2
直接通过过滤 GetEventSchedule 的 Round=GP01/GP02 即可（见 --print-stage1a）。

后续 import 脚本可读取本目录的 raw JSON 写入 event_schedule_matches 等表。
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"

API_BASE = "https://liveeventsapi.worldtabletennis.com/api/cms"
LIVE_MATCH_STATIC_BASE = "https://wtt-web-frontdoor-withoutcache-cqakg0andqf5hchn.a01.azurefd.net"

DEFAULT_SUB_EVENTS = ["MTEAM", "WTEAM"]
OFFICIAL_RESULTS_PAGE_SIZE = 100

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
    """完整 42 字符 documentCode：TTE + SUB(5) + 34 个 '-' 占位。"""
    sub = (sub_event + "-----")[:5]
    return f"TTE{sub}{'-' * 34}"


def fetch_json(url: str, retries: int = 4, backoff: float = 1.5) -> bytes | None:
    """GET url 返回原始 bytes；遇到 SSL EOF / 临时网络错误自动重试。

    HTTP 204/404/500 等错误会以异常返回 None，不抛。
    """
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=REQ_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 204:
                    return None
                return resp.read()
        except urllib.error.HTTPError as e:
            return None
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff ** attempt)
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

    left_updated = (
        left.get("ActualEndDate")
        or left.get("ActualStartDate")
        or left.get("UpdatedAt")
        or left.get("StartDate")
        or ""
    )
    right_updated = (
        right.get("ActualEndDate")
        or right.get("ActualStartDate")
        or right.get("UpdatedAt")
        or right.get("StartDate")
        or ""
    )
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


def normalize_live_result_item(item: dict, schedule_unit_index: dict[str, dict]) -> dict:
    match_card = item.get("match_card") if isinstance(item.get("match_card"), dict) else {}
    payload = match_card or item
    code = normalize_match_code(item.get("documentCode") or match_card.get("documentCode") or item.get("Code"))
    schedule_unit = schedule_unit_index.get(code) or {}

    starts = (((schedule_unit.get("StartList") or {}).get("Start")) or [])
    schedule_sides = [build_side_from_schedule_start(start) for start in starts[:2] if isinstance(start, dict)]

    match_card_competitors = payload.get("competitiors") or payload.get("competitors") or []
    score = extract_match_score(payload) or extract_match_score(item)
    games = normalize_games(payload.get("resultsGameScores") or payload.get("gameScores") or item.get("resultsGameScores") or item.get("gameScores"))

    sides: list[dict] = []
    if schedule_sides:
        sides = schedule_sides
    elif isinstance(match_card_competitors, list):
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


def load_local_schedule_payload(event_dir: Path):
    schedule_path = event_dir / "schedule" / "GetEventSchedule.json"
    if not schedule_path.exists():
        return None
    try:
        return json.loads(schedule_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


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
    for source_name, payload in (
        ("static_live_matches", static_payload),
        ("api_live_result", api_payload),
    ):
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

    normalized = sorted(
        merged_by_code.values(),
        key=lambda item: (item.get("scheduled_start") or "", item.get("match_code") or ""),
    )
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


def fetch_all_official_results(event_id: int) -> list[dict]:
    results: list[dict] = []
    seen_keys: set[str] = set()
    skip = 0

    while True:
        url = (
            f"{API_BASE}/GetOfficialResult?EventId={event_id}"
            f"&include_match_card=true&take={OFFICIAL_RESULTS_PAGE_SIZE}&skip={skip}"
        )
        page = fetch_json_value(url)
        if page is None:
            break
        if not isinstance(page, list) or not page:
            break

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

        if len(page) < OFFICIAL_RESULTS_PAGE_SIZE or new_count == 0:
            break
        skip += OFFICIAL_RESULTS_PAGE_SIZE

    return results


def scrape_schedule_bundle(
    event_id: int,
    sub_events: list[str],
    event_dir: Path,
) -> dict:
    schedule_dir = event_dir / "schedule"
    schedule_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"event_id": event_id, "files": [], "errors": []}

    targets: list[tuple[str, str, str]] = [
        ("event_draws", f"{API_BASE}/GetEventDraws/{event_id}", "GetEventDraws.json"),
        ("event_schedule", f"{API_BASE}/GetEventSchedule/{event_id}", "GetEventSchedule.json"),
    ]
    for sub in sub_events:
        dc = doc_code_for_sub(sub)
        targets.append((
            f"brackets_{sub}",
            f"{API_BASE}/GetBrackets/{event_id}/{dc}",
            f"GetBrackets_{sub}.json",
        ))

    for kind, url, fname in targets:
        body = fetch_json(url)
        if body is None:
            print(f"  [{kind}] ✗ no data ({url})")
            summary["errors"].append({"kind": kind, "url": url})
            continue
        size = save_json(schedule_dir / fname, body)
        print(f"  [{kind}] ✓ {size:,} B -> {fname}")
        summary["files"].append({"kind": kind, "file": fname, "size": size})

    summary["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (event_dir / "_scrape_summary_schedule.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


def scrape_live_matches(
    event_id: int,
    event_dir: Path,
    *,
    schedule_payload=None,
) -> dict:
    match_results_dir = event_dir / "match_results"
    match_results_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"event_id": event_id, "files": [], "errors": []}

    if schedule_payload is None:
        schedule_payload = load_local_schedule_payload(event_dir)

    live_summary, live_matches, live_raw_sources = build_live_results_snapshot(event_id, schedule_payload)
    live_summary["schedule_cache_used"] = bool(schedule_payload)
    if not schedule_payload:
        live_summary["schedule_cache_note"] = "local GetEventSchedule.json missing; sides may be incomplete"

    live_raw_payload = json.dumps(live_raw_sources[0], ensure_ascii=False, indent=2).encode("utf-8")
    live_raw_size = save_json(match_results_dir / "GetLiveResult_sources.json", live_raw_payload)
    summary["files"].append(
        {
            "kind": "live_results_sources",
            "file": "GetLiveResult_sources.json",
            "size": live_raw_size,
            "count": live_summary["matches"],
        }
    )
    normalized_live_payload = json.dumps(
        {
            "summary": live_summary,
            "matches": live_matches,
        },
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    normalized_live_size = save_json(match_results_dir / "GetLiveResult.json", normalized_live_payload)
    summary["files"].append(
        {
            "kind": "live_results_normalized",
            "file": "GetLiveResult.json",
            "size": normalized_live_size,
            "count": live_summary["matches"],
            "detail_rich_count": live_summary["detail_rich_matches"],
        }
    )
    print(
        "  [live_results] ✓ "
        f"{live_summary['matches']} matches "
        f"({live_summary['detail_rich_matches']} with score+games+players)"
    )

    summary["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (event_dir / "_scrape_summary_live.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


def scrape_completed_matches(event_id: int, event_dir: Path) -> dict:
    match_results_dir = event_dir / "match_results"
    match_results_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"event_id": event_id, "files": [], "errors": []}

    official_results = fetch_all_official_results(event_id)
    official_payload = json.dumps(official_results, ensure_ascii=False, indent=2).encode("utf-8")
    official_size = save_json(match_results_dir / "GetOfficialResult.json", official_payload)
    summary["files"].append(
        {
            "kind": "official_results",
            "file": "GetOfficialResult.json",
            "size": official_size,
            "count": len(official_results),
        }
    )

    recent_payload = json.dumps(official_results[:10], ensure_ascii=False, indent=2).encode("utf-8")
    recent_size = save_json(match_results_dir / "GetOfficialResult_take10.json", recent_payload)
    summary["files"].append(
        {
            "kind": "official_results_recent",
            "file": "GetOfficialResult_take10.json",
            "size": recent_size,
            "count": min(len(official_results), 10),
        }
    )
    print(f"  [official_results] ✓ {len(official_results)} matches")

    summary["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (event_dir / "_scrape_summary_completed.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


def scrape_event(
    event_id: int,
    sub_events: list[str],
    event_dir: Path,
    *,
    result_sources: set[str],
) -> dict:
    summary: dict = {"event_id": event_id, "files": [], "errors": []}

    schedule_summary = scrape_schedule_bundle(event_id, sub_events, event_dir)
    summary["files"].extend(schedule_summary["files"])
    summary["errors"].extend(schedule_summary["errors"])

    schedule_payload = load_local_schedule_payload(event_dir)

    if "live" in result_sources:
        live_summary = scrape_live_matches(event_id, event_dir, schedule_payload=schedule_payload)
        summary["files"].extend(live_summary["files"])
        summary["errors"].extend(live_summary["errors"])
    else:
        print("  [live_results] - skipped")

    if "completed" in result_sources:
        completed_summary = scrape_completed_matches(event_id, event_dir)
        summary["files"].extend(completed_summary["files"])
        summary["errors"].extend(completed_summary["errors"])
    else:
        print("  [official_results] - skipped")

    summary["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (event_dir / "_scrape_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


def print_stage1a_groups(event_dir: Path, groups: list[int]) -> None:
    """读取已抓取的 GetEventSchedule.json，打印 Stage 1A 指定 Group 概览。"""
    sch_path = event_dir / "schedule" / "GetEventSchedule.json"
    if not sch_path.exists():
        print(f"  (skip) {sch_path} missing")
        return
    data = json.loads(sch_path.read_text(encoding="utf-8"))
    units: list[dict] = []
    for entry in data:
        units.extend(entry.get("Competition", {}).get("Unit", []))

    target_rounds = {f"GP{g:02d}" for g in groups}
    matched = [u for u in units if u.get("Round") in target_rounds]
    matched.sort(key=lambda u: (u.get("Round"), u.get("SubEvent"), u.get("StartDate") or "", u.get("Code") or ""))

    print()
    print(f"Stage 1A view (rounds {sorted(target_rounds)}): {len(matched)} matches")
    print("-" * 100)
    for u in matched:
        starts = u.get("StartList", {}).get("Start", []) or []

        def org(t):
            return ((t or {}).get("Competitor") or {}).get("Organization") or "TBD"

        sides = " vs ".join(org(t) for t in starts[:2]) if starts else "-"
        name = (u.get("ItemName", [{}])[0].get("Value") or "")
        print(
            f"  {u.get('SubEvent','?'):14} {u.get('Round')} "
            f"{(u.get('StartDate') or '')[:16]} T={u.get('Location','-'):4} "
            f"{sides:18}  {name}"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-id", type=int, required=True)
    ap.add_argument("--sub-events", nargs="+", default=DEFAULT_SUB_EVENTS,
                    help="WTT sub-event codes（5 字符），默认 MTEAM WTEAM")
    ap.add_argument("--live-event-data-root", default=str(DEFAULT_LIVE_EVENT_DATA_DIR),
                    help="进行中赛事数据根目录")
    ap.add_argument("--out-root", dest="live_event_data_root_legacy", default=None,
                    help=argparse.SUPPRESS)
    ap.add_argument(
        "--result-sources",
        nargs="+",
        choices=("live", "completed"),
        default=["live", "completed"],
        help="结果数据源：live / completed；默认同时抓两者",
    )
    ap.add_argument("--print-stage1a", nargs="*", type=int, default=None,
                    help="抓完后打印 Stage 1A 指定 Group 列表，例如 --print-stage1a 1 2")
    args = ap.parse_args()

    root = Path(args.live_event_data_root_legacy or args.live_event_data_root)
    event_dir = root / str(args.event_id)
    print(f"Scrape WTT event {args.event_id} -> {event_dir}")
    summary = scrape_event(
        args.event_id,
        args.sub_events,
        event_dir,
        result_sources=set(args.result_sources),
    )
    print()
    print(f"Done: {len(summary['files'])} files, {len(summary['errors'])} errors")

    if args.print_stage1a is not None:
        groups = args.print_stage1a or [1, 2]
        print_stage1a_groups(event_dir, groups)

    return 0


if __name__ == "__main__":
    sys.exit(main())
