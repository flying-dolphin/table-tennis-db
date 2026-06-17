#!/usr/bin/env python3
"""Scrape ITTF rankings from results.ittf.link and optionally refresh profiles."""

from __future__ import annotations

import argparse
import html
import json
import logging
import random
import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from lib.anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.browser_session import ensure_logged_in
from lib.capture import save_json
from lib.checkpoint import CheckpointStore, utc_now_iso
from lib.name_normalizer import normalize_player_name
from lib.navigation_runtime import verify_cdp_session_or_prompt
from lib.page_ops import click_next_page_if_any, guarded_goto

from scrape_events import select_browser_profiles
from scrape_profiles import scrape_player_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_results_rankings")

BASE_URL = "https://results.ittf.link"
RANKING_URLS = {
    "women": f"{BASE_URL}/index.php/ittf-rankings/ittf-ranking-women-singles",
    "men": f"{BASE_URL}/index.php/ittf-rankings/ittf-ranking-men-singles",
}


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_int(value: str | int | None, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    cleaned = re.sub(r"[^\d+-]", "", str(value or ""))
    if cleaned in {"", "+", "-"}:
        return default
    try:
        return int(cleaned)
    except ValueError:
        return default


def absolutize_results_url(href: str | None) -> str | None:
    if not href:
        return None
    decoded = html.unescape(href.strip()).replace("\\/", "/")
    return urllib.parse.urljoin(BASE_URL + "/", decoded)


def extract_player_id_from_href(href: str | None) -> str | None:
    if not href:
        return None
    match = re.search(r"(?:vw_profiles___)?player_id_raw=(\d+)", html.unescape(href))
    return match.group(1) if match else None


def _parse_dom_rows(soup: BeautifulSoup, top_n: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    table = soup.select_one("table#list_58_com_fabrik_58") or soup.select_one("table")
    if table is None:
        return rows

    for tr in table.select("tbody tr"):
        cells = tr.select("td")
        if len(cells) < 8:
            continue
        rank = parse_int(cells[1].get_text(" ", strip=True), default=-1)
        if rank <= 0:
            continue

        name_link = cells[4].select_one("a")
        href = name_link.get("href") if name_link else ""
        profile_url = absolutize_results_url(href)
        name = normalize_player_name(cells[4].get_text(" ", strip=True))
        flag = cells[5].select_one("img")
        country_code = normalize_space(flag.get("title") if flag else "")

        rows.append(
            {
                "rank": rank,
                "name": name,
                "english_name": name,
                "points": parse_int(cells[3].get_text(" ", strip=True)),
                "country": normalize_space(cells[6].get_text(" ", strip=True)),
                "country_code": country_code,
                "continent": normalize_space(cells[7].get_text(" ", strip=True)),
                "player_id": extract_player_id_from_href(href),
                "profile_url": profile_url,
            }
        )
        if len(rows) >= top_n:
            break
    return rows


def _extract_json_field(block: str, field: str) -> str:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)"', block, re.DOTALL)
    if not match:
        return ""
    return html.unescape(match.group(1).replace("\\/", "/").replace('\\"', '"'))


def _extract_json_int(block: str, field: str) -> int:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*(-?\d+)', block)
    return int(match.group(1)) if match else 0


def _parse_embedded_fabrik_rows(page_html: str, top_n: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    blocks = re.findall(r'\{"data":\{.*?\}\s*(?=,\s*"cursor"|\}\s*,\s*\{"data"|\]\])', page_html, re.DOTALL)
    if not blocks:
        blocks = re.findall(r'\{"data":\{.*?\}\}', page_html, re.DOTALL)

    for block in blocks:
        if "fab_rank_ws___Name" not in block:
            continue
        rank = _extract_json_int(block, "fab_rank_ws___Position_raw") or _extract_json_int(block, "fab_rank_ws___Num")
        if rank <= 0:
            continue

        name_html = _extract_json_field(block, "fab_rank_ws___Name")
        name_soup = BeautifulSoup(name_html, "html.parser")
        link = name_soup.select_one("a")
        href = link.get("href") if link else ""
        raw_name = _extract_json_field(block, "fab_rank_ws___Name_raw") or name_soup.get_text(" ", strip=True)
        flag_html = _extract_json_field(block, "fab_rank_ws___Flag")
        flag_soup = BeautifulSoup(flag_html, "html.parser")
        flag = flag_soup.select_one("img")
        country_code = _extract_json_field(block, "fab_rank_ws___Country_raw") or normalize_space(flag.get("title") if flag else "")
        player_id = extract_player_id_from_href(href) or str(_extract_json_int(block, "fab_rank_ws___PID_raw") or "")

        name = normalize_player_name(normalize_space(raw_name))
        rows.append(
            {
                "rank": rank,
                "name": name,
                "english_name": name,
                "points": _extract_json_int(block, "fab_rank_ws___Points_raw") or parse_int(_extract_json_field(block, "fab_rank_ws___Points")),
                "country": _extract_json_field(block, "fab_rank_ws___Country"),
                "country_code": country_code,
                "continent": _extract_json_field(block, "fab_rank_ws___ITTF_raw") or _extract_json_field(block, "fab_rank_ws___ITTF"),
                "player_id": player_id or None,
                "profile_url": absolutize_results_url(href),
            }
        )
        if len(rows) >= top_n:
            break
    return rows


def parse_results_ranking_html(page_html: str, top_n: int) -> list[dict[str, Any]]:
    soup = BeautifulSoup(page_html, "html.parser")
    rows = _parse_dom_rows(soup, top_n)
    if rows:
        return rows[:top_n]
    return _parse_embedded_fabrik_rows(page_html, top_n)[:top_n]


def build_output_payload(rankings: list[dict[str, Any]], category: str, source_url: str, pages_scraped: int) -> dict[str, Any]:
    return {
        "category": category,
        "source": "results.ittf.link",
        "source_url": source_url,
        "scraped_at": utc_now_iso(),
        "pages_scraped": pages_scraped,
        "total_players": len(rankings),
        "rankings": rankings,
    }


def find_completed_results_output(checkpoint: CheckpointStore, category: str, top_n: int) -> Path | None:
    prefix = f"results-ranking|{category}|top:{top_n}|"
    candidates: list[tuple[str, Path]] = []
    for key, value in checkpoint.data.get("completed", {}).items():
        if not key.startswith(prefix):
            continue
        if isinstance(value, str):
            continue
        if not isinstance(value, dict):
            continue
        output_file = value.get("meta", {}).get("output_file")
        if not output_file:
            continue
        path = Path(output_file)
        if path.exists():
            candidates.append((str(value.get("at", "")), path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def load_results_rankings_snapshot(path: Path, category: str, top_n: int) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rankings = data.get("rankings", [])
    if not isinstance(rankings, list):
        raise ValueError(f"results snapshot has invalid rankings list: {path}")
    if data.get("category") and data.get("category") != category:
        raise ValueError(f"results snapshot category mismatch: {path}")
    return rankings[:top_n]


def scrape_results_rankings(page: Any, category: str, top_n: int, delay_cfg: DelayConfig, output_file: Path) -> list[dict[str, Any]]:
    rankings: list[dict[str, Any]] = []
    source_url = RANKING_URLS[category]
    pages_scraped = 0
    seen_player_ids: set[str] = set()

    while len(rankings) < top_n:
        risk = detect_risk(page)
        if risk:
            save_json(output_file, build_output_payload(rankings, category, source_url, pages_scraped))
            raise RiskControlTriggered(risk)

        page_rows = parse_results_ranking_html(page.content(), top_n - len(rankings))
        pages_scraped += 1
        if not page_rows:
            break

        for row in page_rows:
            player_id = str(row.get("player_id") or "")
            if player_id and player_id in seen_player_ids:
                continue
            if player_id:
                seen_player_ids.add(player_id)
            rankings.append(row)
            if len(rankings) >= top_n:
                break

        save_json(output_file, build_output_payload(rankings, category, source_url, pages_scraped))
        if len(rankings) >= top_n:
            break
        human_sleep(delay_cfg.min_request_sec, delay_cfg.max_request_sec, "before next results ranking page")
        if not click_next_page_if_any(page):
            break

    return rankings[:top_n]


def refresh_profiles(
    page: Any,
    rankings: list[dict[str, Any]],
    args: argparse.Namespace,
    delay_cfg: DelayConfig,
    checkpoint: CheckpointStore,
) -> int:
    profile_dir = Path(args.profile_dir)
    profile_orig_dir = profile_dir / "orig"
    profile_orig_dir.mkdir(parents=True, exist_ok=True)
    avatar_dir = Path(args.avatar_dir)
    avatar_dir.mkdir(parents=True, exist_ok=True)

    refreshed = 0
    for idx, player in enumerate(rankings, 1):
        if not player.get("profile_url") or not player.get("player_id"):
            continue
        logger.info("[%d/%d] Refresh profile: %s (%s)", idx, len(rankings), player.get("name"), player.get("player_id"))
        profile_data, scraped_now = scrape_player_profile(
            page,
            str(player["profile_url"]),
            player,
            delay_cfg,
            profile_orig_dir,
            avatar_dir,
            checkpoint=checkpoint,
            category=args.category,
            force=bool(args.force),
        )
        if profile_data is None:
            raise RuntimeError(f"profile scrape failed for {player.get('name')} ({player.get('player_id')})")
        if scraped_now:
            refreshed += 1
            if idx < len(rankings):
                human_sleep(delay_cfg.min_player_gap_sec, delay_cfg.max_player_gap_sec, "between profile refreshes")
    return refreshed


def run(args: argparse.Namespace) -> int:
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        logger.error("patchright is required. Install with: pip install patchright && python -m patchright install chromium")
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = Path(args.output) if args.output else output_dir / f"results_{args.category}_top{args.top}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    checkpoint = CheckpointStore(Path(args.checkpoint))
    if args.force:
        checkpoint.reset()
    resume_output = None
    if getattr(args, "resume", False) and not args.force:
        resume_output = find_completed_results_output(checkpoint, args.category, args.top)
        if resume_output is not None:
            output_file = resume_output
            logger.info("Resuming from completed results ranking snapshot: %s", resume_output)
            if args.ranking_only:
                return 0

    delay_cfg = DelayConfig(
        min_request_sec=args.min_delay,
        max_request_sec=args.max_delay,
        min_player_gap_sec=args.min_player_gap,
        max_player_gap_sec=args.max_player_gap,
    )

    with sync_playwright() as p:
        profile = random.choice(select_browser_profiles())
        viewport = random.choice(profile["viewport_choices"])
        dpr = random.choice(profile["dpr_choices"])
        context_kwargs: dict[str, Any] = {
            "viewport": viewport,
            "locale": "en-US",
            "timezone_id": "Asia/Shanghai",
            "user_agent": profile["user_agent"],
            "device_scale_factor": dpr,
            "color_scheme": "light",
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "sec-ch-ua": profile["sec_ch_ua"],
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": profile["sec_ch_ua_platform"],
            },
        }
        storage_state = Path(args.storage_state)
        if storage_state.exists():
            context_kwargs["storage_state"] = str(storage_state)

        via_cdp, browser, _context, page = open_browser_page(
            p,
            use_cdp=True,
            cdp_port=args.cdp_port,
            cdp_only=bool(args.cdp_only),
            launch_kwargs={"headless": args.headless, "slow_mo": args.slow_mo},
            context_kwargs=context_kwargs,
            log_prefix="results-rankings",
        )

        try:
            target_url = RANKING_URLS[args.category]
            if via_cdp:
                verify_cdp_session_or_prompt(page, target_url, delay_cfg)
            else:
                ensure_logged_in(page, target_url, delay_cfg, storage_state, args.init_session)
                if args.init_session:
                    close_browser_page(via_cdp, browser, page)
                    return 0

            if resume_output is not None:
                rankings = load_results_rankings_snapshot(resume_output, args.category, args.top)
            else:
                guarded_goto(page, target_url, delay_cfg, f"open results ranking: {args.category}")
                try:
                    page.locator("table").first.wait_for(timeout=15000)
                except Exception:
                    logger.warning("ranking table did not appear before timeout")

                rankings = scrape_results_rankings(page, args.category, args.top, delay_cfg, output_file)
            if not rankings:
                logger.error("Parsed 0 results ranking rows")
                close_browser_page(via_cdp, browser, page)
                return 5

            if resume_output is None:
                checkpoint.mark_done(
                    f"results-ranking|{args.category}|top:{args.top}|{output_file.name}",
                    meta={"output_file": str(output_file), "total_players": len(rankings)},
                )
                logger.info("Saved results ranking snapshot: %s", output_file)

            if not args.ranking_only:
                refreshed = refresh_profiles(page, rankings, args, delay_cfg, checkpoint)
                logger.info("Profile refresh complete: %d scraped now", refreshed)
        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            close_browser_page(via_cdp, browser, page)
            return 4
        except Exception as exc:
            logger.error("Results ranking scrape failed: %s", exc)
            close_browser_page(via_cdp, browser, page)
            return 4

        close_browser_page(via_cdp, browser, page)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape results.ittf.link ranking with player IDs")
    parser.add_argument("--category", choices=sorted(RANKING_URLS.keys()), default="women")
    parser.add_argument("--top", type=int, default=1000)
    parser.add_argument("--output-dir", default="data/rankings/id_snapshots")
    parser.add_argument("--output", default=None)
    parser.add_argument("--checkpoint", default="data/rankings/checkpoint_results_rankings.json")
    parser.add_argument("--storage-state", default="data/session/ittf_results_storage_state.json")
    parser.add_argument("--profile-dir", default="data/player_profiles")
    parser.add_argument("--avatar-dir", default="data/player_avatars")
    parser.add_argument("--ranking-only", action="store_true", help="Only scrape ranking snapshot; skip profile refresh")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Reuse a completed results ranking snapshot from checkpoint and continue profiles")
    parser.add_argument("--init-session", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--cdp-only", action="store_true")
    parser.add_argument("--min-delay", type=float, default=2.0)
    parser.add_argument("--max-delay", type=float, default=5.0)
    parser.add_argument("--min-player-gap", type=float, default=2.0)
    parser.add_argument("--max-player-gap", type=float, default=5.0)
    return parser


def main() -> None:
    parser = build_parser()
    rc = run(parser.parse_args())
    sys.exit(rc)


if __name__ == "__main__":
    main()
