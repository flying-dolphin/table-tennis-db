#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WTT 事件抓取：拉取 worldtabletennis.com 上某个 eventId 的全部公开赛程/签表 JSON。

调用 liveeventsapi.worldtabletennis.com 暴露的几个 CMS 端点：

  - GetEventDraws/{eventId}                  → 各 draw（Qualification/Stage 1/Main）起止时间
  - GetEventSchedule/{eventId}               → 全部 unit 级日程，含 Round/StartDate/StartList
  - GetBrackets/{eventId}/{documentCode}     → 每个 sub_event 的 bracket 结构（KO + group 元信息）
  - GetOfficialResult?EventId={eventId}&include_match_card=true&take=10
                                             → 最近完赛结果（每日刷新增量用）

输出：data/wtt_raw/{event_id}/...

抓取过程使用纯 HTTP（urllib），不需要打开浏览器；偶尔遇到的 SSL EOF
会自动重试。日程接口涵盖所有 group / KO 比赛，故 Stage 1A Group 1/2
直接通过过滤 GetEventSchedule 的 Round=GP01/GP02 即可（见 --print-stage1a）。

后续 import 脚本可读取本目录的 raw JSON 写入 event_schedule_matches 等表。
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

RUNTIME_ROOT = Path(__file__).resolve().parents[1]

API_BASE = "https://liveeventsapi.worldtabletennis.com/api/cms"

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


def scrape_event(event_id: int, sub_events: list[str], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"event_id": event_id, "files": [], "errors": []}

    targets: list[tuple[str, str, str]] = [
        ("event_draws", f"{API_BASE}/GetEventDraws/{event_id}", "GetEventDraws.json"),
        ("event_schedule", f"{API_BASE}/GetEventSchedule/{event_id}", "GetEventSchedule.json"),
        (
            "live_results",
            f"{API_BASE}/GetLiveResult?EventId={event_id}",
            "GetLiveResult.json",
        ),
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
        size = save_json(out_dir / fname, body)
        print(f"  [{kind}] ✓ {size:,} B -> {fname}")
        summary["files"].append({"kind": kind, "file": fname, "size": size})

    official_results = fetch_all_official_results(event_id)
    official_payload = json.dumps(official_results, ensure_ascii=False, indent=2).encode("utf-8")
    official_size = save_json(out_dir / "GetOfficialResult.json", official_payload)
    summary["files"].append(
        {
            "kind": "official_results",
            "file": "GetOfficialResult.json",
            "size": official_size,
            "count": len(official_results),
        }
    )

    recent_payload = json.dumps(official_results[:10], ensure_ascii=False, indent=2).encode("utf-8")
    recent_size = save_json(out_dir / "GetOfficialResult_take10.json", recent_payload)
    summary["files"].append(
        {
            "kind": "official_results_recent",
            "file": "GetOfficialResult_take10.json",
            "size": recent_size,
            "count": min(len(official_results), 10),
        }
    )

    summary["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (out_dir / "_scrape_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def print_stage1a_groups(out_dir: Path, groups: list[int]) -> None:
    """读取已抓取的 GetEventSchedule.json，打印 Stage 1A 指定 Group 概览。"""
    sch_path = out_dir / "GetEventSchedule.json"
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
    ap.add_argument("--out-root", default=str(RUNTIME_ROOT / "data" / "wtt_raw"),
                    help="raw JSON 落地根目录")
    ap.add_argument("--out-dir", default=None,
                    help="指定本次抓取输出目录；设置后优先于 --out-root")
    ap.add_argument("--print-stage1a", nargs="*", type=int, default=None,
                    help="抓完后打印 Stage 1A 指定 Group 列表，例如 --print-stage1a 1 2")
    args = ap.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else Path(args.out_root) / str(args.event_id)
    print(f"Scrape WTT event {args.event_id} -> {out_dir}")
    summary = scrape_event(args.event_id, args.sub_events, out_dir)
    print()
    print(f"Done: {len(summary['files'])} files, {len(summary['errors'])} errors")

    if args.print_stage1a is not None:
        groups = args.print_stage1a or [1, 2]
        print_stage1a_groups(out_dir, groups)

    return 0


if __name__ == "__main__":
    sys.exit(main())
