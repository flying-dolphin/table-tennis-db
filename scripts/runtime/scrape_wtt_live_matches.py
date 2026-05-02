#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scrape WTT live team-match details from the rendered Live Matches page DOM.

This script is the browser-based live pipeline. It does not fetch schedule data
from the network, but it can read a local `schedule/GetEventSchedule.json`
cache to map DOM cards back to schedule match codes for downstream importing.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.browser_runtime import close_browser_page, open_browser_page
from scrape_wtt_event import DEFAULT_LIVE_EVENT_DATA_DIR, build_schedule_unit_index, load_local_schedule_payload

logger = logging.getLogger(__name__)

LIVE_URL_TEMPLATE = (
    "https://www.worldtabletennis.com/teamseventInfo"
    "?selectedTab=Results&innerselectedTab=Live%20Matches&eventId={event_id}"
)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def parse_score_pair(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.search(r"(\d+)\s*-\s*(\d+)", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def infer_winner_side(score: str | None) -> str | None:
    parsed = parse_score_pair(score)
    if not parsed:
        return None
    if parsed[0] > parsed[1]:
        return "A"
    if parsed[1] > parsed[0]:
        return "B"
    return None


def parse_round_code(title: str | None) -> str | None:
    raw = (title or "").strip()
    group_match = re.search(r"Group\s+(\d+)", raw, flags=re.IGNORECASE)
    if group_match:
        return f"GP{int(group_match.group(1)):02d}"
    if "Preliminary Round" in raw:
        return "RND1"
    return None


def parse_match_no(match_label: str | None) -> int | None:
    match = re.search(r"Match\s+(\d+)", match_label or "", flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def flatten_schedule_units(schedule_payload: Any) -> list[dict[str, Any]]:
    return list(build_schedule_unit_index(schedule_payload).values())


def parse_scheduled_label(value: str | None) -> str | None:
    raw = (value or "").strip()
    if "|" not in raw:
        return raw or None
    return raw.split("|", 1)[1].strip() or None


def location_label(unit: dict[str, Any]) -> str | None:
    venue_desc = unit.get("VenueDescription") or {}
    return (
        venue_desc.get("LocationName")
        or venue_desc.get("VenueName")
        or unit.get("Location")
        or None
    )


def match_dom_card_to_schedule_unit(card: dict[str, Any], schedule_units: list[dict[str, Any]]) -> dict[str, Any] | None:
    side_orgs = tuple(
        side.get("organization")
        for side in (card.get("sides") or [])[:2]
        if isinstance(side, dict) and side.get("organization")
    )
    round_code = parse_round_code(card.get("sub_event"))
    match_no = parse_match_no(card.get("match_label"))
    table_no = (card.get("table_no") or "").strip().lower()
    sub_event = (card.get("sub_event_name") or "").strip().lower()

    candidates: list[tuple[int, dict[str, Any]]] = []
    for unit in schedule_units:
        starts = (((unit.get("StartList") or {}).get("Start")) or [])
        unit_orgs = tuple(
            ((start.get("Competitor") or {}).get("Organization") or "")
            for start in starts[:2]
            if isinstance(start, dict)
        )
        if len(unit_orgs) != 2 or unit_orgs != side_orgs:
            continue

        score = 0
        if round_code and (unit.get("Round") or "").strip().upper() == round_code:
            score += 6
        if sub_event and (unit.get("SubEvent") or "").strip().lower() == sub_event:
            score += 4
        if table_no and table_no in ((location_label(unit) or "").strip().lower()):
            score += 3

        item_name = " ".join(
            str(item.get("Value") or "")
            for item in (unit.get("ItemName") or [])
            if isinstance(item, dict)
        )
        if match_no is not None and re.search(rf"\bM\s*{match_no}\b", item_name, flags=re.IGNORECASE):
            score += 5

        start_date = (unit.get("StartDate") or "").strip()
        scheduled_label = (card.get("scheduled_label") or "").strip()
        if scheduled_label and scheduled_label in start_date:
            score += 1

        candidates.append((score, unit))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1].get("ActualEndDate") or item[1].get("ActualStartDate") or item[1].get("StartDate") or ""), reverse=True)
    best_score, best_unit = candidates[0]
    return best_unit if best_score > 0 else None


def build_side_players_from_individual_matches(individual_matches: list[dict[str, Any]], side_key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    players: list[dict[str, Any]] = []
    field = "player_a" if side_key == "A" else "player_b"
    for match in individual_matches:
        raw = (match.get(field) or "").strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        players.append({"name": raw})
    return players


def extract_live_cards(page: Any) -> list[dict[str, Any]]:
    script = """
() => {
  function text(el) {
    return ((el && (el.innerText || el.textContent)) || '').trim();
  }

  function parseIndividualMatches(card) {
    const holder = card.querySelector('.results_expander_holder');
    if (!holder) return [];
    const blocks = Array.from(holder.children)
      .filter(el => text(el))
      .map(el => text(el).replace(/\\s+/g, ' '));
    const out = [];
    const pattern = /^(.*?)\\s+(\\d+\\s*-\\s*\\d+)\\s+(.*?)\\s+((?:\\d+\\s*-\\s*\\d+(?:\\s*,\\s*|$))+)/;
    for (const block of blocks) {
      const match = block.match(pattern);
      if (!match) {
        out.push({ raw_text: block });
        continue;
      }
      out.push({
        player_a: match[1].trim(),
        match_score: match[2].replace(/\\s+/g, ''),
        player_b: match[3].trim(),
        games: match[4].split(',').map(x => x.trim()).filter(Boolean),
        raw_text: block,
      });
    }
    return out;
  }

  return Array.from(document.querySelectorAll('app-teams-match-card')).map((card, index) => {
    const title = text(card.querySelector('mat-card-title.card_head'));
    const schedule = text(card.querySelector('mat-card-title.card_head .row')) || '';
    const score = text(card.querySelector('.custom_card_div')) || null;
    const sideA = text(card.querySelector('.custom_card_span1.fl')) || null;
    const sideB = text(card.querySelector('.custom_card_span2.fr')) || null;
    const tableNo = text(card.querySelector('.col-5 span')) || text(card.querySelector('.col-5')) || null;
    const isLive = !!card.querySelector('.live_score_indicator');
    const details = parseIndividualMatches(card);
    return {
      index,
      raw_title: title,
      sub_event: title.replace(/\\s*LIVE\\s*/i, '').trim(),
      match_label: schedule.split('|')[0]?.trim() || schedule || null,
      scheduled_label: schedule.includes('|') ? schedule.split('|').slice(1).join('|').trim() : null,
      score,
      is_live: isLive,
      table_no: tableNo,
      sides: [
        { organization: sideA, display_name: sideA, players: [] },
        { organization: sideB, display_name: sideB, players: [] },
      ],
      individual_matches: details,
      raw_text: text(card),
    };
  }).filter(card => card.score || card.individual_matches.length > 0);
}
"""
    return page.evaluate(script)


def has_no_live_matches_banner(page: Any) -> bool:
    script = """
() => {
  const bodyText = (document.body && document.body.innerText) || '';
  return bodyText.includes('No live matches available currently.');
}
"""
    try:
        return bool(page.evaluate(script))
    except Exception:
        return False


def wait_for_live_content_or_empty(page: Any, timeout_ms: int) -> str:
    page.wait_for_selector("body", timeout=timeout_ms)
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        try:
            if page.locator("app-teams-match-card").count():
                return "cards"
        except Exception:
            pass

        try:
            if page.get_by_text("No live matches available currently.", exact=False).count():
                return "empty"
        except Exception:
            pass

        try:
            body_text = page.locator("body").inner_text(timeout=1000)
            normalized = re.sub(r"\s+", " ", body_text or "").strip()
            if "No live matches available currently." in normalized:
                return "empty"
            if "Live Matches" in normalized and "Completed" in normalized and "Results" in normalized:
                pass
        except Exception:
            pass

        page.wait_for_timeout(250)

    return "timeout"


def ensure_scores_visible(page: Any) -> None:
    try:
        toggle = page.get_by_text("Show Scores", exact=True).first
        if toggle.count() and toggle.is_visible():
            toggle.click(timeout=3000)
            page.wait_for_timeout(500)
    except Exception:
        pass


def expand_all_view_results(page: Any) -> None:
    headers = page.locator("mat-expansion-panel-header.custom_results_expansion_header")
    try:
        count = headers.count()
    except Exception:
        count = 0

    for idx in range(count):
        try:
            header = headers.nth(idx)
            if header.is_visible():
                header.click(timeout=3000)
                page.wait_for_timeout(150)
        except Exception:
            continue


def scrape_live_page(
    event_id: int,
    *,
    use_cdp: bool,
    cdp_port: int,
    headless: bool,
    timeout_ms: int,
) -> tuple[list[dict[str, Any]], str]:
    url = LIVE_URL_TEMPLATE.format(event_id=event_id)

    try:
        from patchright.sync_api import sync_playwright
    except Exception:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError("patchright/playwright not installed") from exc

    with sync_playwright() as p:
        via_cdp, browser, _, page = open_browser_page(
            p,
            use_cdp=use_cdp,
            cdp_port=cdp_port,
            cdp_only=False,
            launch_kwargs={"headless": headless},
            context_kwargs={"viewport": {"width": 1440, "height": 2000}},
            log_prefix="wtt-live-dom",
        )
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            state = wait_for_live_content_or_empty(page, timeout_ms)
            if state == "empty":
                return [], page.content()
            if state != "cards":
                raise TimeoutError("live page did not expose cards or empty-state banner in time")
            ensure_scores_visible(page)
            expand_all_view_results(page)
            page.wait_for_timeout(800)
            cards = extract_live_cards(page)
            return cards, page.content()
        finally:
            close_browser_page(via_cdp, browser, page)


def normalize_live_cards(
    cards: list[dict[str, Any]],
    schedule_payload: Any,
) -> list[dict[str, Any]]:
    schedule_units = flatten_schedule_units(schedule_payload)
    normalized: list[dict[str, Any]] = []

    for card in cards:
        if not isinstance(card, dict):
            continue
        score = (card.get("score") or "").strip() or None
        sides = card.get("sides") if isinstance(card.get("sides"), list) else []
        individual_matches = card.get("individual_matches") if isinstance(card.get("individual_matches"), list) else []
        schedule_unit = match_dom_card_to_schedule_unit(card, schedule_units)
        match_code = (schedule_unit.get("Code") or "").rstrip("-") if isinstance(schedule_unit, dict) else None

        for idx, side in enumerate(sides[:2]):
            if not isinstance(side, dict):
                continue
            side["players"] = build_side_players_from_individual_matches(individual_matches, "A" if idx == 0 else "B")

        normalized.append(
            {
                "match_code": match_code,
                "source_status": "Live" if card.get("is_live") else "Displayed",
                "sub_event": schedule_unit.get("SubEvent") if isinstance(schedule_unit, dict) else None,
                "sub_event_name": card.get("sub_event"),
                "round": schedule_unit.get("Round") if isinstance(schedule_unit, dict) else parse_round_code(card.get("sub_event")),
                "scheduled_start": schedule_unit.get("StartDate") if isinstance(schedule_unit, dict) else None,
                "scheduled_start_local": card.get("scheduled_label"),
                "table_no": card.get("table_no"),
                "session_label": card.get("match_label"),
                "score": score,
                "games": [m.get("match_score") for m in individual_matches if isinstance(m, dict) and m.get("match_score")],
                "winner_side": infer_winner_side(score),
                "sides": sides,
                "individual_matches": individual_matches,
                "raw_title": card.get("raw_title"),
                "raw_text": card.get("raw_text"),
            }
        )

    normalized.sort(key=lambda item: ((item.get("table_no") or ""), (item.get("match_code") or ""), (item.get("score") or "")))
    return normalized


def write_outputs(
    event_dir: Path,
    event_id: int,
    cards: list[dict[str, Any]],
    normalized: list[dict[str, Any]],
    page_html: str,
    *,
    schedule_cache_used: bool,
) -> dict[str, Any]:
    match_results_dir = event_dir / "match_results"
    match_results_dir.mkdir(parents=True, exist_ok=True)

    raw_payload = {
        "event_id": event_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "cards": cards,
    }
    raw_path = match_results_dir / "GetLiveResult_dom.json"
    raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="")

    summary = {
        "event_id": event_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "dom_live_page": {
                "url": LIVE_URL_TEMPLATE.format(event_id=event_id),
                "ok": True,
                "count": len(normalized),
            }
        },
        "matches": len(normalized),
        "detail_rich_matches": sum(1 for item in normalized if item.get("individual_matches")),
        "schedule_cache_used": schedule_cache_used,
    }
    normalized_payload = {"summary": summary, "matches": normalized}
    normalized_path = match_results_dir / "GetLiveResult.json"
    normalized_path.write_text(json.dumps(normalized_payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="")

    html_path = match_results_dir / "GetLiveResult_page.html"
    html_path.write_text(page_html, encoding="utf-8", newline="")

    script_summary = {
        "event_id": event_id,
        "files": [
            {"kind": "live_results_dom_raw", "file": raw_path.name, "size": raw_path.stat().st_size, "count": len(cards)},
            {"kind": "live_results_normalized", "file": normalized_path.name, "size": normalized_path.stat().st_size, "count": len(normalized)},
            {"kind": "live_results_page_html", "file": html_path.name, "size": html_path.stat().st_size},
        ],
        "errors": [],
        "fetched_at": summary["fetched_at"],
    }
    (event_dir / "_scrape_summary_live.json").write_text(
        json.dumps(script_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="",
    )
    return script_summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape WTT live team-match details from the rendered Live Matches page DOM.")
    ap.add_argument("--event-id", type=int, required=True)
    ap.add_argument(
        "--live-event-data-root",
        default=str(DEFAULT_LIVE_EVENT_DATA_DIR),
        help="进行中赛事数据根目录",
    )
    ap.add_argument("--cdp-port", type=int, default=9222)
    ap.add_argument("--use-cdp", action="store_true", help="Reuse existing Chrome via CDP.")
    ap.add_argument("--headless", action="store_true", help="Launch a headless browser when not using CDP.")
    ap.add_argument("--timeout-ms", type=int, default=30000)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    configure_logging(bool(args.verbose))

    event_dir = Path(args.live_event_data_root) / str(args.event_id)
    print(f"Scrape WTT live matches {args.event_id} -> {event_dir}")

    schedule_payload = load_local_schedule_payload(event_dir)
    try:
        cards, page_html = scrape_live_page(
            args.event_id,
            use_cdp=bool(args.use_cdp),
            cdp_port=args.cdp_port,
            headless=bool(args.headless),
            timeout_ms=int(args.timeout_ms),
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        print("Install with: pip install patchright && python -m patchright install chromium")
        return 1
    normalized = normalize_live_cards(cards, schedule_payload)
    summary = write_outputs(
        event_dir,
        args.event_id,
        cards,
        normalized,
        page_html,
        schedule_cache_used=bool(schedule_payload),
    )
    print(f"  [live_results_dom] ✓ {len(normalized)} matches ({sum(1 for item in normalized if item.get('individual_matches'))} with detailed boards)")
    print()
    print(f"Done: {len(summary['files'])} files, {len(summary['errors'])} errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
