#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 agent-browser 抓取 WTT 团体赛页面的全量已完结比赛数据。

适用于带 LOAD MORE 按钮的团体赛页面（如 ITTF 世乒赛团体赛）。

抓取内容：
  - 对战双方国家代码
  - 团体赛总比分（如 3-1）
  - 每一盘（单打/双打）的双方球员全名、盘比分、每局局分

依赖：agent-browser（npm i -g agent-browser）
输出：data/live_event_data/{event_id}/match_results/wtt_matches_browser.json

用法示例：
  python scrape_wtt_matches.py --event-id 3216
  python scrape_wtt_matches.py --event-id 3216 --max-load-more 60
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_EVENT_DATA_DIR = PROJECT_ROOT / "data" / "live_event_data"

WTT_TEAMS_URL = (
    "https://www.worldtabletennis.com/teamseventInfo"
    "?selectedTab=Results&innerselectedTab=Completed&eventId={event_id}"
)

# JavaScript: click LOAD MORE button if present, return 'clicked' or 'not_found'
_JS_CLICK_LOAD_MORE = (
    "(function(){"
    "var btn=Array.from(document.querySelectorAll('.generic_btn'))"
    ".find(function(el){return el.textContent.trim()==='LOAD MORE';});"
    "if(btn){btn.scrollIntoView();btn.click();return 'clicked';}"
    "return 'not_found';"
    "})()"
)

# JavaScript: accept cookie consent dialog if present
_JS_ACCEPT_COOKIES = (
    "(function(){"
    "var btn=Array.from(document.querySelectorAll('button'))"
    ".find(function(b){return b.textContent.includes('Accept All');});"
    "if(btn){btn.click();return 'accepted';}"
    "return 'no_dialog';"
    "})()"
)

# JavaScript: extract all match data from loaded cards
_JS_EXTRACT_MATCHES = """
(function() {
  var cards = document.querySelectorAll('app-teams-match-card');
  var allMatches = [];

  cards.forEach(function(card) {
    var matCard = card.querySelector('.example-card');
    if (!matCard) return;

    var categoryEl = matCard.querySelector('[title^="Men"], [title^="Women"]');
    var category = categoryEl ? categoryEl.getAttribute('title').trim() : '';

    var matchInfoEl = matCard.querySelector('.low_bot_indicator');
    var matchInfo = matchInfoEl ? matchInfoEl.textContent.trim() : '';

    var flagSpans = matCard.querySelectorAll('app-country-flag span[title]');
    var team1 = flagSpans[0] ? flagSpans[0].getAttribute('title') : '';
    var team2 = flagSpans[1] ? flagSpans[1].getAttribute('title') : '';

    var score1El = matCard.querySelector('.custom_card_span1 .small_score_span');
    var score2El = matCard.querySelector('.custom_card_span2 .small_score_span');
    var score1 = score1El ? score1El.textContent.trim() : '';
    var score2 = score2El ? score2El.textContent.trim() : '';

    var tableEl = matCard.querySelector('.col-5 span');
    var table = tableEl ? tableEl.textContent.trim() : '';

    var games = [];
    var gameRows = card.querySelectorAll('.results_expander_holder > .ng-star-inserted');
    gameRows.forEach(function(row) {
      var playerEls = row.querySelectorAll('span[title]');
      if (playerEls.length < 2) return;

      var p1 = playerEls[0].getAttribute('title');
      var p2 = playerEls[1].getAttribute('title');

      // Middle div (text-align: center) holds the game score "3 - 1"
      var divs = row.querySelectorAll('div');
      var gameScore = '';
      for (var i = 0; i < divs.length; i++) {
        if (divs[i].style.textAlign === 'center') {
          gameScore = divs[i].textContent.trim().replace(/\\s+/g, ' ');
          break;
        }
      }

      var setScoreEl = row.querySelector('.fw400');
      var setScores = setScoreEl ? setScoreEl.textContent.trim() : '';

      games.push({ player1: p1, player2: p2, gameScore: gameScore, setScores: setScores });
    });

    allMatches.push({
      category: category,
      matchInfo: matchInfo,
      team1: team1,
      score: score1 + '-' + score2,
      team2: team2,
      table: table,
      games: games,
    });
  });

  return JSON.stringify(allMatches);
})()
"""


# On Windows, npm-installed CLIs are .cmd wrappers; shutil.which resolves them.
_AGENT_BROWSER = shutil.which("agent-browser") or "agent-browser"
# shell=True is needed on Windows when the resolved path is a .cmd file.
_SHELL = sys.platform == "win32"


def _run(args: list[str], *, timeout: int = 30) -> str:
    cmd = [_AGENT_BROWSER] + args
    result = subprocess.run(
        cmd if not _SHELL else subprocess.list2cmdline(cmd),
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        shell=_SHELL,
    )
    return result.stdout.strip()


def _eval(js: str, *, timeout: int = 30) -> str:
    cmd = [_AGENT_BROWSER, "eval", "--stdin"]
    result = subprocess.run(
        cmd if not _SHELL else subprocess.list2cmdline(cmd),
        input=js,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        shell=_SHELL,
    )
    return result.stdout.strip()


def _card_count() -> int:
    raw = _eval("document.querySelectorAll('app-teams-match-card').length")
    try:
        return int(raw.strip('"'))
    except (ValueError, AttributeError):
        return 0


def scrape_matches(
    event_id: int,
    event_dir: Path,
    *,
    max_load_more: int = 50,
) -> dict:
    url = WTT_TEAMS_URL.format(event_id=event_id)
    summary: dict = {"event_id": event_id, "files": [], "errors": []}

    print(f"  [browser] {url}")
    _run(["open", url])
    _run(["wait", "--load", "networkidle"], timeout=45)

    # Accept cookie dialog early (appears before Angular content renders)
    out = _eval(_JS_ACCEPT_COOKIES)
    if "accepted" in out:
        print("  [browser] Cookie dialog accepted")

    # Angular renders match cards asynchronously after networkidle;
    # wait up to 20 s for the first card or LOAD MORE to appear.
    _run(
        ["wait", "--fn",
         "document.querySelectorAll('app-teams-match-card').length > 0"
         " || !!Array.from(document.querySelectorAll('.generic_btn'))"
         ".find(function(el){return el.textContent.trim()==='LOAD MORE';})"],
        timeout=25,
    )
    _run(["wait", "1000"], timeout=5)

    # Click LOAD MORE until exhausted or count stops growing
    prev_count = _card_count()
    print(f"  [load_more] Initial: {prev_count} cards")

    for i in range(1, max_load_more + 1):
        result = _eval(_JS_CLICK_LOAD_MORE)
        if "not_found" in result:
            print(f"  [load_more] Done after {i - 1} click(s)")
            break
        time.sleep(3)
        count = _card_count()
        print(f"  [load_more] Click {i}: {count} cards")
        if count == prev_count:
            print("  [load_more] Count unchanged, stopping")
            break
        prev_count = count
    else:
        print(f"  [load_more] Reached limit ({max_load_more} clicks)")

    # Extract all match data
    print("  [extract] Extracting match data from DOM...")
    raw = _eval(_JS_EXTRACT_MATCHES, timeout=60)

    try:
        # agent-browser wraps string return values in JSON quotes
        data = json.loads(raw)
        if isinstance(data, str):
            data = json.loads(data)
    except json.JSONDecodeError as e:
        print(f"  [extract] ✗ JSON parse failed: {e}")
        summary["errors"].append({"kind": "json_parse", "error": str(e)})
        return summary

    if not isinstance(data, list):
        print(f"  [extract] ✗ Unexpected type: {type(data)}")
        summary["errors"].append({"kind": "unexpected_type", "type": str(type(data))})
        return summary

    matches_with_games = sum(1 for m in data if m.get("games"))
    print(f"  [extract] {len(data)} matches ({matches_with_games} with game detail)")

    out_dir = event_dir / "match_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "wtt_matches_browser.json"

    payload = {
        "event_id": event_id,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "url": url,
        "total_matches": len(data),
        "matches_with_game_detail": matches_with_games,
        "matches": data,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    size = out_path.stat().st_size
    print(f"  [save] ✓ {out_path.relative_to(PROJECT_ROOT)} ({size:,} B)")

    summary["files"].append({
        "kind": "wtt_matches_browser",
        "file": str(out_path),
        "size": size,
        "count": len(data),
    })
    summary["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(
        description="通过 agent-browser 抓取 WTT 团体赛全量已完结比赛数据"
    )
    ap.add_argument("--event-id", type=int, required=True, help="WTT 赛事 ID")
    ap.add_argument(
        "--live-event-data-root",
        default=str(DEFAULT_LIVE_EVENT_DATA_DIR),
        help="进行中赛事数据根目录（默认 data/live_event_data）",
    )
    ap.add_argument(
        "--max-load-more",
        type=int,
        default=50,
        help="最多点击 LOAD MORE 次数（默认 50）",
    )
    args = ap.parse_args()

    event_dir = Path(args.live_event_data_root) / str(args.event_id)
    print(f"Scrape WTT teams event {args.event_id} (browser) -> {event_dir}")

    try:
        summary = scrape_matches(args.event_id, event_dir, max_load_more=args.max_load_more)
    finally:
        _run(["close"])

    print()
    print(f"Done: {len(summary['files'])} file(s), {len(summary['errors'])} error(s)")
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
