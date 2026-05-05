#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 agent-browser 抓取 WTT 团体赛页面的全量已完结比赛数据。

适用于带 LOAD MORE 按钮的团体赛页面（如 ITTF 世乒赛团体赛）。

抓取内容：
  - 对战双方国家代码
  - 团体赛总比分（如 3-1）
  - 每一盘（单打/双打）的双方球员全名、盘比分、每局局分

依赖：agent-browser（npm i -g agent-browser）
输出：data/live_event_data/{event_id}/completed_matches.json

用法示例：
  python scrape_wtt_matches.py --event-id 3216
  python scrape_wtt_matches.py --event-id 3216 --max-load-more 60
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )


def _log(msg: str) -> None:
    """Print with timestamp + immediate flush so we can see real-time progress."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

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

# JavaScript: extract all match data from loaded cards.
#
# Forfeit/retirement marker handling:
#   WTT marks abandoned matches with one of: WO (walk over / no-show), INJ
#   (injury), DNS (did not start), DSQ (disqualified), RET (retired mid-match).
#   In the Angular bundle, the displayed numeric score has the marker stripped
#   via .replace("WO","").replace("INJ","")...trim(), and the marker is then
#   rendered separately as <span class="walk_over">{{isWalKOverType}}</span>.
#   So we cannot rely on the numeric .small_score_span alone — we must read
#   the parent score span's full textContent and pull the marker out by regex.
#
#   We do NOT use `games.length == 0` or `score == "0"` as a forfeit signal.
#   RET / INJ in particular can occur mid-match where games is non-empty and
#   the team score is non-zero (e.g. "3-1 RET"). The regex-on-textContent
#   approach captures the marker regardless of game count or score value.
_JS_EXTRACT_MATCHES = """
(function() {
  var MARKER_RE = /\\b(WO|INJ|DNS|DSQ|RET)\\b/;

  function _findMarker(text) {
    var m = text ? MARKER_RE.exec(text) : null;
    return m ? m[1] : '';
  }

  // Parse a score span (.custom_card_span1/2) into {num, marker}.
  // num is the numeric score with the marker stripped; marker is '' if absent.
  function _parseScoreSpan(spanEl) {
    if (!spanEl) return {num: '', marker: ''};
    var numEl = spanEl.querySelector('.small_score_span');
    var num = (numEl ? numEl.textContent : '').trim();
    var fullText = (spanEl.textContent || '').trim();
    var marker = _findMarker(fullText);
    if (marker) num = num.replace(marker, '').trim();
    return {num: num, marker: marker};
  }

  function _formatSide(parsed) {
    return parsed.marker ? (parsed.num || '0') + ' ' + parsed.marker : parsed.num;
  }

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

    var s1 = _parseScoreSpan(matCard.querySelector('.custom_card_span1'));
    var s2 = _parseScoreSpan(matCard.querySelector('.custom_card_span2'));
    // The marker indicator span sits inside whichever side forfeited.
    var forfeitSide = s1.marker ? 'team1' : (s2.marker ? 'team2' : '');
    var forfeitMarker = s1.marker || s2.marker || '';

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

      // Mid-match retirement: a single game can end in RET/INJ even though
      // the team score and games array look "normal". Capture explicitly so
      // downstream code doesn't have to parse the gameScore/setScores text.
      var gameMarker = _findMarker(gameScore) || _findMarker(setScores);

      games.push({
        player1: p1,
        player2: p2,
        gameScore: gameScore,
        setScores: setScores,
        forfeit_marker: gameMarker,
      });
    });

    allMatches.push({
      category: category,
      matchInfo: matchInfo,
      team1: team1,
      score: _formatSide(s1) + '-' + _formatSide(s2),
      team2: team2,
      table: table,
      forfeit_marker: forfeitMarker,
      forfeit_side: forfeitSide,
      games: games,
    });
  });

  return JSON.stringify(allMatches);
})()
"""


# On Windows, npm-installed CLIs are .cmd wrappers; shutil.which resolves them.
_AGENT_BROWSER = shutil.which("agent-browser") or "agent-browser"
_IS_WIN = sys.platform == "win32"


def _win_quote(arg: str) -> str:
    """Wrap arg in double quotes for cmd.exe if it contains shell-special chars."""
    if any(c in arg for c in '&|<>^()'):
        return '"' + arg.replace('"', '""') + '"'
    return arg


# Track the currently-running child so a Ctrl+C handler can kill its whole tree.
# Without this, subprocess.run's blocking communicate() on Windows swallows SIGINT —
# the user presses Ctrl+C and nothing happens because Python is stuck in native ReadFile.
_current_proc: subprocess.Popen | None = None
_proc_lock = threading.Lock()


def _kill_proc_tree(pid: int) -> None:
    """Force-kill a process and all its descendants. Best effort, never raises."""
    if _IS_WIN:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5,
            )
        except Exception as e:
            _log(f"  [kill] taskkill pid={pid} failed: {e}")
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception as e:
            _log(f"  [kill] killpg pid={pid} failed: {e}")


def _sigint_handler(signum, frame):
    _log("[!!] SIGINT — killing agent-browser process tree and exiting")
    with _proc_lock:
        proc = _current_proc
    if proc and proc.poll() is None:
        _kill_proc_tree(proc.pid)
    # Restore default so a second Ctrl+C terminates Python immediately.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    raise KeyboardInterrupt


def _spawn(cmd, *, input_text: str | None = None, timeout: int = 30, shell: bool = False):
    """subprocess.run replacement that:
      - drains stdout/stderr in background threads (avoids pipe-fill deadlock for MB-sized output)
      - polls in a short-sleep loop (so Windows Ctrl+C / KeyboardInterrupt can interrupt)
      - kills the whole process tree on timeout or interrupt
    """
    global _current_proc
    popen_kwargs = {
        "stdin": subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "shell": shell,
    }
    if _IS_WIN:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        cmd,
        **popen_kwargs,
    )
    with _proc_lock:
        _current_proc = proc

    out_buf: list[bytes] = []
    err_buf: list[bytes] = []

    def _drain(stream, buf):
        try:
            for chunk in iter(lambda: stream.read(8192), b""):
                buf.append(chunk)
        except Exception:
            pass

    threads = [
        threading.Thread(target=_drain, args=(proc.stdout, out_buf), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, err_buf), daemon=True),
    ]
    for t in threads:
        t.start()

    if input_text is not None:
        try:
            proc.stdin.write(input_text.encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass

    deadline = time.monotonic() + timeout
    try:
        while proc.poll() is None:
            if time.monotonic() > deadline:
                _log(f"  [spawn!] timeout {timeout}s reached, killing pid={proc.pid}")
                _kill_proc_tree(proc.pid)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
                raise subprocess.TimeoutExpired(cmd, timeout)
            time.sleep(0.2)  # short sleep keeps Ctrl+C responsive
    except KeyboardInterrupt:
        _log(f"  [spawn!] interrupted, killing pid={proc.pid}")
        _kill_proc_tree(proc.pid)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        raise
    finally:
        with _proc_lock:
            _current_proc = None
        for t in threads:
            t.join(timeout=1)

    stdout = b"".join(out_buf).decode("utf-8", errors="replace")
    stderr = b"".join(err_buf).decode("utf-8", errors="replace")
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


signal.signal(signal.SIGINT, _sigint_handler)


def _run(args: list[str], *, timeout: int = 30) -> str:
    if _IS_WIN:
        parts = [_win_quote(_AGENT_BROWSER)] + [_win_quote(a) for a in args]
        cmd: str | list[str] = " ".join(parts)
    else:
        cmd = [_AGENT_BROWSER] + args
    label = " ".join(args)[:80]
    _log(f"  [run>] {label}  (timeout={timeout}s)")
    t0 = time.monotonic()
    result = _spawn(cmd, timeout=timeout, shell=_IS_WIN)
    dt = time.monotonic() - t0
    out = result.stdout.strip()
    _log(
        f"  [run<] {label}  rc={result.returncode}  {dt:.1f}s  "
        f"stdout={len(out)}B stderr={len(result.stderr)}B"
    )
    if result.returncode != 0 and result.stderr:
        _log(f"  [run<] stderr: {result.stderr.strip()[:300]}")
    return out


def _eval(js: str, *, timeout: int = 30) -> str:
    if _IS_WIN:
        cmd: str | list[str] = " ".join(
            [_win_quote(_AGENT_BROWSER), "eval", "--stdin"]
        )
    else:
        cmd = [_AGENT_BROWSER, "eval", "--stdin"]
    js_preview = js.strip().splitlines()[0][:60] if js.strip() else ""
    _log(f"  [eval>] {js_preview!r}  (timeout={timeout}s, js={len(js)}B)")
    t0 = time.monotonic()
    result = _spawn(cmd, input_text=js, timeout=timeout, shell=_IS_WIN)
    dt = time.monotonic() - t0
    out = result.stdout.strip()
    _log(
        f"  [eval<] rc={result.returncode}  {dt:.1f}s  "
        f"stdout={len(out)}B stderr={len(result.stderr)}B"
    )
    if result.returncode != 0 and result.stderr:
        _log(f"  [eval<] stderr: {result.stderr.strip()[:300]}")
    return out


def _card_count() -> int:
    raw = _eval("document.querySelectorAll('app-teams-match-card').length")
    try:
        return int(raw.strip('"'))
    except (ValueError, AttributeError):
        _log(f"  [card_count] parse fail, raw={raw!r}")
        return 0


def scrape_matches(
    event_id: int,
    event_dir: Path,
    *,
    max_load_more: int = 50,
) -> dict:
    url = WTT_TEAMS_URL.format(event_id=event_id)
    summary: dict = {"event_id": event_id, "files": [], "errors": []}

    _log(f"  [browser] open {url}")
    _run(["open", url], timeout=60)
    _log("  [browser] wait networkidle...")
    _run(["wait", "--load", "networkidle"], timeout=45)

    # Accept cookie dialog (appears before Angular content renders)
    _log("  [browser] checking cookie dialog...")
    out = _eval(_JS_ACCEPT_COOKIES)
    if "accepted" in out:
        _log("  [browser] Cookie dialog accepted")

    # Angular renders match cards asynchronously after networkidle.
    # Wait for the CSS selector to appear (up to 30 s).
    _log("  [browser] wait for app-teams-match-card...")
    _run(["wait", "app-teams-match-card"], timeout=35)
    _run(["wait", "1000"], timeout=5)

    # Click LOAD MORE until exhausted or count stops growing
    prev_count = _card_count()
    _log(f"  [load_more] Initial: {prev_count} cards")

    for i in range(1, max_load_more + 1):
        _log(f"  [load_more] click #{i}...")
        result = _eval(_JS_CLICK_LOAD_MORE)
        if "not_found" in result:
            _log(f"  [load_more] Done after {i - 1} click(s) — button gone")
            break
        _log(f"  [load_more] sleeping 3s before recount...")
        time.sleep(3)
        count = _card_count()
        _log(f"  [load_more] Click {i}: {count} cards (prev={prev_count})")
        if count == prev_count:
            _log("  [load_more] Count unchanged, stopping")
            break
        prev_count = count
    else:
        _log(f"  [load_more] Reached limit ({max_load_more} clicks)")

    # Extract all match data
    _log("  [extract] Extracting match data from DOM...")
    raw = _eval(_JS_EXTRACT_MATCHES, timeout=60)
    _log(f"  [extract] raw payload {len(raw):,}B")

    try:
        # agent-browser wraps string return values in JSON quotes
        data = json.loads(raw)
        if isinstance(data, str):
            data = json.loads(data)
    except json.JSONDecodeError as e:
        _log(f"  [extract] ✗ JSON parse failed: {e}")
        summary["errors"].append({"kind": "json_parse", "error": str(e)})
        return summary

    if not isinstance(data, list):
        _log(f"  [extract] ✗ Unexpected type: {type(data)}")
        summary["errors"].append({"kind": "unexpected_type", "type": str(type(data))})
        return summary

    matches_with_games = sum(1 for m in data if m.get("games"))
    _log(f"  [extract] {len(data)} matches ({matches_with_games} with game detail)")

    event_dir.mkdir(parents=True, exist_ok=True)
    out_path = event_dir / "completed_matches.json"

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
    _log(f"  [save] ✓ {out_path.relative_to(PROJECT_ROOT)} ({size:,} B)")

    summary["files"].append({
        "kind": "completed_matches",
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
    _log(f"Scrape WTT teams event {args.event_id} (browser) -> {event_dir}")

    try:
        summary = scrape_matches(args.event_id, event_dir, max_load_more=args.max_load_more)
    finally:
        _log("  [browser] close")
        try:
            _run(["close"], timeout=15)
        except subprocess.TimeoutExpired:
            _log("  [browser] close TIMED OUT — agent-browser may be orphaned")

    print()
    _log(f"Done: {len(summary['files'])} file(s), {len(summary['errors'])} error(s)")
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
