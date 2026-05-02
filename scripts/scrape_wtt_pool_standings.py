#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture WTT team-event pool standings via the Stage Groups page.

This script is intentionally standalone and does not affect the existing
scrape/import pipeline. It opens the public groups-stage page in a headless
browser, listens for poolstandings network responses, and saves both the raw
response wrapper and a normalized standings snapshot for MTEAM/WTEAM.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.browser_runtime import close_browser_page, open_browser_page

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "wtt_pool_standings_analysis"
GROUPS_URL_TEMPLATE = (
    "https://www.worldtabletennis.com/teamseventInfo"
    "?selectedTab={stage_label}&eventId={event_id}"
)
TARGET_CODES = ("MTEAM", "WTEAM")


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def normalize_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def athlete_name(athlete: dict[str, Any]) -> str:
    desc = athlete.get("Description") or {}
    given = (desc.get("GivenName") or "").strip()
    family = (desc.get("FamilyName") or "").strip()
    return f"{given} {family}".strip()


def normalize_team_row(row: dict[str, Any]) -> dict[str, Any]:
    competitor = row.get("Competitor") or {}
    composition = competitor.get("Composition") or {}
    athletes = composition.get("Athlete") or []

    return {
        "group": row.get("Group"),
        "organization": competitor.get("Organization"),
        "competitor_code": competitor.get("Code"),
        "team_name": ((competitor.get("Description") or {}).get("TeamName")),
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
                "organization": ((athlete.get("Description") or {}).get("Organization")),
                "gender": ((athlete.get("Description") or {}).get("Gender")),
                "birth_date": ((athlete.get("Description") or {}).get("BirthDate")),
                "name": athlete_name(athlete),
            }
            for athlete in athletes
        ],
        "extended_results": ((row.get("ExtendedResults") or {}).get("ExtendedResult")) or [],
    }


def build_standings_snapshot(wrapper: dict[str, Any]) -> dict[str, Any]:
    payload = normalize_payload(wrapper.get("MessagePayload"))
    competition = (payload or {}).get("Competition") or {}
    results = competition.get("Result") or []
    normalized_rows = [normalize_team_row(row) for row in results]

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in normalized_rows:
        groups.setdefault(row["group"] or "", []).append(row)

    for rows in groups.values():
        rows.sort(key=lambda item: (str(item.get("rank") or ""), item.get("organization") or ""))

    extended_infos = competition.get("ExtendedInfos") or {}
    return {
        "competition_meta": {
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
        },
        "rows": normalized_rows,
        "groups": groups,
    }


def capture_pool_standings(page: Any, event_id: int) -> dict[str, dict[str, Any]]:
    captures: dict[str, dict[str, Any]] = {}

    def on_response(resp: Any) -> None:
        try:
            url = resp.url
            if f"/websitecacheddata/{event_id}/poolstandings/" not in url:
                return
            status = int(resp.status)
            if status != 200:
                return
            payload = resp.json()
            if not isinstance(payload, list) or not payload:
                return

            wrapper = payload[0]
            team_code = None
            if "/MTEAM.json" in url:
                team_code = "MTEAM"
            elif "/WTEAM.json" in url:
                team_code = "WTEAM"
            if team_code not in TARGET_CODES:
                return

            captures[team_code] = {
                "requested_url": url,
                "status": status,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "wrapper": wrapper,
                "normalized": build_standings_snapshot(wrapper),
            }
            logger.info("Captured %s standings from %s", team_code, url)
        except Exception as exc:
            logger.warning("Failed to process pool standings response: %s", exc)

    page.on("response", on_response)
    return captures


def click_team_tab(page: Any, label: str) -> bool:
    try:
        locator = page.get_by_role("button", name=label).first
        if locator.count() and locator.is_visible():
            locator.click(timeout=5000)
            return True
    except Exception:
        pass

    try:
        locator = page.get_by_text(label, exact=True).first
        if locator.count() and locator.is_visible():
            locator.click(timeout=5000)
            return True
    except Exception:
        pass

    return False


def install_seen_marker(page: Any, event_id: int) -> None:
    page.add_init_script(
        f"""
        (() => {{
          window.__codexPoolStandingSeen = window.__codexPoolStandingSeen || {{}};
          const open = XMLHttpRequest.prototype.open;
          XMLHttpRequest.prototype.open = function(method, url, ...rest) {{
            try {{
              if (String(url).includes('/websitecacheddata/{event_id}/poolstandings/MTEAM.json')) {{
                window.__codexPoolStandingSeen.MTEAM = true;
              }}
              if (String(url).includes('/websitecacheddata/{event_id}/poolstandings/WTEAM.json')) {{
                window.__codexPoolStandingSeen.WTEAM = true;
              }}
            }} catch (err) {{}}
            return open.call(this, method, url, ...rest);
          }};
          const fetchRef = window.fetch;
          window.fetch = async (...args) => {{
            try {{
              const url = String(args[0] && args[0].url ? args[0].url : args[0]);
              if (url.includes('/websitecacheddata/{event_id}/poolstandings/MTEAM.json')) {{
                window.__codexPoolStandingSeen.MTEAM = true;
              }}
              if (url.includes('/websitecacheddata/{event_id}/poolstandings/WTEAM.json')) {{
                window.__codexPoolStandingSeen.WTEAM = true;
              }}
            }} catch (err) {{}}
            return fetchRef(...args);
          }};
        }})();
        """
    )


def write_outputs(run_dir: Path, captures: dict[str, dict[str, Any]], meta: dict[str, Any]) -> None:
    (run_dir / "capture_summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="",
    )

    for code, captured in sorted(captures.items()):
        (run_dir / f"{code}_raw_wrapper.json").write_text(
            json.dumps(captured["wrapper"], ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="",
        )
        (run_dir / f"{code}_standings.json").write_text(
            json.dumps(captured["normalized"], ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="",
        )


def analyze_event(
    event_id: int,
    output_root: Path,
    *,
    stage_label: str,
    headless: bool,
    cdp_port: int,
    use_cdp: bool,
) -> int:
    run_dir = output_root / str(event_id) / utc_now_compact()
    run_dir.mkdir(parents=True, exist_ok=True)
    url = GROUPS_URL_TEMPLATE.format(event_id=event_id, stage_label=stage_label)

    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("patchright/playwright not installed")
            return 2

    with sync_playwright() as p:
        via_cdp, browser, _, page = open_browser_page(
            p,
            use_cdp=use_cdp,
            cdp_port=cdp_port,
            cdp_only=False,
            launch_kwargs={"headless": headless},
            context_kwargs={"viewport": {"width": 1440, "height": 2000}, "locale": "en-US", "timezone_id": "Asia/Shanghai"},
            log_prefix="wtt-pool-standings",
        )

        captures = capture_pool_standings(page, event_id)
        try:
            logger.info("Opening %s", url)
            install_seen_marker(page, event_id)
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(6000)

            if "WTEAM" not in captures:
                if click_team_tab(page, "Women's Teams"):
                    logger.info("Switched to Women's Teams tab")
                    page.wait_for_timeout(5000)

            if "WTEAM" not in captures:
                page.wait_for_timeout(4000)

            missing = [code for code in TARGET_CODES if code not in captures]
            if missing:
                logger.error("Missing pool standings captures for: %s", ", ".join(missing))
                return 1

            meta = {
                "event_id": event_id,
                "stage_label": stage_label,
                "page_url": url,
                "captured_codes": sorted(captures.keys()),
                "captured_urls": {code: captures[code]["requested_url"] for code in sorted(captures)},
            }
            write_outputs(run_dir, captures, meta)
            logger.info("Saved pool standings analysis to %s", run_dir)
        finally:
            close_browser_page(via_cdp, browser, page)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture WTT pool standings via Stage Groups page.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--stage-label", default="Stage 1B(Groups)", help="Page tab label, e.g. 'Stage 1B(Groups)' or 'Stage 1A(Groups)'.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--use-cdp", action="store_true", help="Reuse existing Chrome via CDP instead of launching a fresh browser.")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.verbose)
    return analyze_event(
        args.event_id,
        args.output_root.resolve(),
        stage_label=str(args.stage_label),
        headless=bool(args.headless),
        cdp_port=args.cdp_port,
        use_cdp=bool(args.use_cdp),
    )


if __name__ == "__main__":
    sys.exit(main())
