#!/usr/bin/env python3
"""Scrape ITTF rankings from results.ittf.link and optionally refresh profiles."""

from __future__ import annotations

import argparse
import html
import json
import logging
import random
import re
import sqlite3
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from bs4 import BeautifulSoup

from lib.anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep, move_mouse_to_locator
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.browser_session import ensure_logged_in
from lib.capture import save_json
from lib.checkpoint import CheckpointStore, utc_now_iso
from lib.name_normalizer import normalize_player_name
from lib.navigation_runtime import verify_cdp_session_or_prompt
from lib.page_ops import _retry_after_seconds, click_next_page_if_any, guarded_goto

from db.config import DB_PATH
from scrape_events import select_browser_profiles
from scrape_profiles import scrape_player_profile
from merge_ranking_ids import (
    load_player_name_aliases,
    merge_rankings_with_results_ids,
    normalize_key_name_variants,
)

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


def extract_results_reported_total(page_html: str) -> int | None:
    soup = BeautifulSoup(page_html, "html.parser")
    pagination_text = " ".join(
        node.get_text(" ", strip=True)
        for node in soup.select(".list-footer, .pagination, .fabrikNav")
    )
    text = pagination_text or soup.get_text(" ", strip=True)
    match = re.search(r"\bTotal\s*:?\s*([\d,]+)\b", text, re.IGNORECASE)
    if not match:
        return None
    return parse_int(match.group(1), default=0) or None


def extract_results_pagination_info(page_html: str) -> tuple[int, int, int] | None:
    soup = BeautifulSoup(page_html, "html.parser")
    pagination_text = " ".join(
        node.get_text(" ", strip=True)
        for node in soup.select(".list-footer, .pagination, .fabrikNav")
    )
    match = re.search(
        r"\bPage\s+(\d+)\s+of\s+(\d+)\s+Total\s*:?\s*([\d,]+)\b",
        pagination_text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return (
        parse_int(match.group(1)),
        parse_int(match.group(2)),
        parse_int(match.group(3)),
    )


def validate_live_page_against_partial(
    live_rows: list[dict[str, Any]],
    saved_rows: list[dict[str, Any]],
    *,
    current_page: int,
    page_size: int,
) -> tuple[bool | None, str]:
    """Compare a live results page with the corresponding saved row slice."""
    if current_page <= 0 or page_size <= 0:
        return False, "invalid pagination state"
    offset = (current_page - 1) * page_size
    overlap = min(len(live_rows), max(0, len(saved_rows) - offset))
    if overlap <= 0:
        return None, f"current page offset {offset} has no overlap with {len(saved_rows)} saved rows"

    for relative_index in range(overlap):
        saved = saved_rows[offset + relative_index]
        live = live_rows[relative_index]
        saved_id = str(saved.get("player_id") or "")
        live_id = str(live.get("player_id") or "")
        if not saved_id or saved_id != live_id:
            return False, (
                f"player mismatch at saved row {offset + relative_index + 1}: "
                f"saved={saved_id or '?'} live={live_id or '?'}"
            )
    return True, f"validated {overlap} overlapping rows at offset {offset}"


def select_results_display_100(
    page: Any,
    *,
    timeout_sec: float = 20.0,
    poll_sec: float = 0.25,
) -> bool:
    selectors = [
        "select#limit58",
        ".limit select[id^='limit']",
        "select[id^='limit']",
        ".limit select.inputbox.form-select",
    ]
    locator = None
    selected_by = ""
    for selector in selectors:
        candidate = page.locator(selector).first
        try:
            if candidate.count() == 0 or not candidate.is_visible():
                continue
            locator = candidate
            selected_by = selector
            break
        except Exception as exc:
            logger.warning("Failed to inspect Display # selector %s: %s", selector, exc)

    if locator is None:
        logger.warning("Results ranking Display # select element not found; using current page size")
        return False

    try:
        current_value = (locator.input_value() or "").strip()
        if current_value != "100":
            locator.select_option("100")
            logger.info("Selected results ranking Display # = 100 via selector: %s", selected_by)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
        else:
            logger.info("Results ranking Display # already 100 via selector: %s", selected_by)
    except Exception as exc:
        logger.warning("Failed to select results ranking Display # = 100: %s", exc)
        return False

    deadline = time.monotonic() + max(0.0, timeout_sec)
    while True:
        risk = detect_risk(page)
        if risk:
            retry_after = 300.0 if "too many requests" in risk.lower() else None
            raise RiskControlTriggered(
                risk,
                status=429 if retry_after is not None else None,
                retry_after_sec=retry_after,
            )
        try:
            selected_value = (locator.input_value() or "").strip()
            page_html = page.content()
            pagination = extract_results_pagination_info(page_html)
            rows = parse_results_ranking_html(page_html, 100)
            if pagination is not None:
                current_page, total_pages, total_records = pagination
                expected_rows = min(100, max(0, total_records - ((current_page - 1) * 100)))
                expected_pages = max(1, (total_records + 99) // 100)
                if (
                    selected_value == "100"
                    and total_pages == expected_pages
                    and len(rows) == expected_rows
                ):
                    logger.info(
                        "Verified results ranking Display # = 100: rows=%d pages=%d total=%d",
                        len(rows),
                        total_pages,
                        total_records,
                    )
                    return True
        except Exception as exc:
            logger.debug("Waiting for results ranking Display # = 100: %s", exc)

        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, poll_sec))

    logger.warning("Display # = 100 did not produce a verified 100-row results ranking page; using actual page state")
    return False


def validate_scraped_results_count(
    rankings: list[dict[str, Any]],
    top_n: int,
    reported_total: int | None,
) -> None:
    if reported_total is None:
        return
    expected = min(top_n, reported_total)
    if len(rankings) < expected:
        raise RuntimeError(
            f"results ranking scrape incomplete: parsed {len(rankings)} rows, "
            f"page reported {reported_total} (expected {expected})"
        )


def validate_results_rows(rankings: list[Any], *, require_order: bool = True) -> tuple[bool, str]:
    seen_ids: set[str] = set()
    previous_rank = 0
    for index, row in enumerate(rankings, start=1):
        if not isinstance(row, dict):
            return False, f"row {index} is invalid"
        rank = parse_int(row.get("rank"))
        player_id = str(row.get("player_id") or "")
        profile_url = str(row.get("profile_url") or "")
        if rank <= 0 or (require_order and rank < previous_rank):
            return False, f"ranks are not ordered at row {index}"
        if not row.get("name") or not player_id or not profile_url:
            return False, f"row {index} lacks required fields"
        if player_id in seen_ids:
            return False, f"has duplicate player ID {player_id}"
        if extract_player_id_from_href(profile_url) != player_id:
            return False, f"player ID/profile URL mismatch at row {index}"
        seen_ids.add(player_id)
        previous_rank = rank
    return True, f"validated {len(rankings)} rows"


def is_results_snapshot_complete(
    snapshot_path: Path | str,
    weekly_path: Path | str,
    top_n: int,
    reported_total: int | None = None,
) -> tuple[bool, str]:
    try:
        snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        weekly = json.loads(Path(weekly_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"snapshot validation failed: {exc}"

    rankings = snapshot.get("rankings")
    weekly_rankings = weekly.get("rankings")
    if not isinstance(rankings, list) or not isinstance(weekly_rankings, list):
        return False, "snapshot validation failed: rankings must be lists"

    weekly_total = parse_int(weekly.get("total_players"), default=len(weekly_rankings))
    expected = min(top_n, weekly_total or len(weekly_rankings))
    if reported_total is not None:
        expected = max(expected, min(top_n, reported_total))
    site_total = parse_int(snapshot.get("site_total_players"), default=len(rankings))
    if site_total < expected:
        return False, f"results snapshot incomplete: site rows {site_total}, expected {expected} from weekly/page total"
    if len(rankings) < site_total:
        return False, f"results snapshot invalid: contains {len(rankings)} rows but metadata reports {site_total} site rows"
    rows_valid, rows_reason = validate_results_rows(rankings, require_order=False)
    if not rows_valid:
        return False, f"results snapshot invalid: {rows_reason}"
    return True, f"results snapshot complete: site rows {site_total}, expected {expected}"


def find_db_profile_candidates(db_path: Path | str, weekly: dict[str, Any]) -> list[dict[str, Any]]:
    country_code = str(weekly.get("country_code") or weekly.get("country") or "").upper()
    weekly_names = normalize_key_name_variants(str(weekly.get("english_name") or weekly.get("name") or ""))
    if not country_code or not weekly_names:
        return []

    path = Path(db_path).resolve()
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                p.player_id,
                p.name AS player_name,
                pp.name AS profile_name,
                pp.english_name,
                p.country_code,
                pp.profile_url
            FROM players AS p
            JOIN player_profiles AS pp
              ON CAST(pp.player_id AS INTEGER) = p.player_id
            WHERE UPPER(p.country_code) = ?
              AND pp.profile_url IS NOT NULL
              AND TRIM(pp.profile_url) <> ''
            ORDER BY p.player_id
            """,
            (country_code,),
        ).fetchall()
    finally:
        connection.close()

    candidates: list[dict[str, Any]] = []
    for row in rows:
        candidate_names = {
            str(row["player_name"] or ""),
            str(row["profile_name"] or ""),
            str(row["english_name"] or ""),
        }
        if not any(normalize_key_name_variants(name) & weekly_names for name in candidate_names if name):
            continue
        english_name = normalize_player_name(
            normalize_space(str(row["english_name"] or row["profile_name"] or row["player_name"] or ""))
        )
        candidates.append(
            {
                "player_id": str(row["player_id"]),
                "name": english_name,
                "english_name": english_name,
                "country_code": str(row["country_code"] or "").upper(),
                "profile_url": str(row["profile_url"]),
            }
        )
    return candidates


def recover_missing_players_from_db(
    weekly_rows: list[dict[str, Any]],
    results_rows: list[dict[str, Any]],
    db_path: Path | str,
    profile_loader: Callable[[dict[str, Any]], dict[str, Any] | None],
    aliases: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not Path(db_path).is_file():
        logger.warning("Database fallback skipped; database not found: %s", db_path)
        return []

    merged_rows, _unresolved = merge_rankings_with_results_ids(weekly_rows, results_rows, aliases=aliases)
    used_player_ids = {
        str(row["player_id"])
        for row in merged_rows
        if row.get("player_id")
    }
    profile_cache: dict[str, dict[str, Any] | None] = {}
    recovered: list[dict[str, Any]] = []

    for weekly, merged in zip(weekly_rows, merged_rows):
        if merged.get("player_id"):
            continue

        verified: list[dict[str, Any]] = []
        try:
            db_candidates = find_db_profile_candidates(db_path, weekly)
        except sqlite3.Error as exc:
            logger.warning("Database fallback query failed: %s", exc)
            return recovered
        for candidate in db_candidates:
            player_id = str(candidate.get("player_id") or "")
            if not player_id or player_id in used_player_ids:
                continue
            profile_input = {
                **candidate,
                "rank": weekly.get("rank"),
                "points": weekly.get("points"),
                "change": weekly.get("change", weekly.get("rank_change")),
                "country": weekly.get("country") or weekly.get("country_code"),
            }
            if player_id not in profile_cache:
                try:
                    profile_cache[player_id] = profile_loader(profile_input)
                except Exception as exc:
                    logger.warning(
                        "Database fallback profile load failed for %s (%s): %s",
                        profile_input.get("name"),
                        player_id,
                        exc,
                    )
                    profile_cache[player_id] = None
            profile = profile_cache[player_id]
            if profile is None:
                continue
            if parse_int(profile.get("current_rank")) == parse_int(weekly.get("rank")):
                verified.append(candidate)

        if len(verified) != 1:
            continue

        candidate = verified[0]
        player_id = str(candidate["player_id"])
        used_player_ids.add(player_id)
        name = str(weekly.get("english_name") or weekly.get("name") or candidate.get("english_name") or "")
        country_code = str(weekly.get("country_code") or weekly.get("country") or "").upper()
        recovered.append(
            {
                "rank": parse_int(weekly.get("rank")),
                "name": name,
                "english_name": name,
                "points": parse_int(weekly.get("points")),
                "country": weekly.get("country") or country_code,
                "country_code": country_code,
                "player_id": player_id,
                "profile_url": candidate.get("profile_url"),
                "id_resolution_hint": "db_profile_rank",
            }
        )

    return recovered


def recover_missing_profiles_with_browser(
    page: Any,
    results_rows: list[dict[str, Any]],
    args: argparse.Namespace,
    delay_cfg: DelayConfig,
    checkpoint: CheckpointStore,
) -> list[dict[str, Any]]:
    weekly_file = getattr(args, "weekly_file", None)
    db_path = getattr(args, "db_path", None)
    if not weekly_file or not db_path:
        return []

    weekly_path = Path(weekly_file)
    if not weekly_path.is_file():
        logger.warning("Database fallback skipped; weekly ranking file not found: %s", weekly_path)
        return []
    try:
        weekly_payload = json.loads(weekly_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Database fallback skipped; weekly ranking file is unreadable: %s", exc)
        return []
    weekly_rows = weekly_payload.get("rankings") or []
    if not isinstance(weekly_rows, list):
        logger.warning("Database fallback skipped; weekly rankings is not a list: %s", weekly_path)
        return []

    aliases = load_player_name_aliases(getattr(args, "aliases", None))
    profile_orig_dir = Path(args.profile_dir) / "orig"
    profile_orig_dir.mkdir(parents=True, exist_ok=True)
    avatar_dir = Path(args.avatar_dir)
    avatar_dir.mkdir(parents=True, exist_ok=True)

    def load_profile(candidate: dict[str, Any]) -> dict[str, Any] | None:
        profile_data, _scraped_now = scrape_player_profile(
            page,
            str(candidate["profile_url"]),
            candidate,
            delay_cfg,
            profile_orig_dir,
            avatar_dir,
            checkpoint=checkpoint,
            category=args.category,
            resume=bool(getattr(args, "resume", False)),
        )
        return profile_data

    recovered = recover_missing_players_from_db(
        weekly_rows,
        results_rows,
        db_path,
        profile_loader=load_profile,
        aliases=aliases,
    )
    logger.info("Database/profile-rank fallback recovered %d players", len(recovered))
    return recovered


def build_output_payload(
    rankings: list[dict[str, Any]],
    category: str,
    source_url: str,
    pages_scraped: int,
    site_total_players: int | None = None,
    db_profile_recovered: int = 0,
    source_reported_total: int | None = None,
    next_page_url: str | None = None,
    page_size: int | None = None,
    page_checkpoints: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "source": "results.ittf.link",
        "source_url": source_url,
        "scraped_at": utc_now_iso(),
        "pages_scraped": pages_scraped,
        "total_players": len(rankings),
        "site_total_players": len(rankings) if site_total_players is None else site_total_players,
        "db_profile_recovered": db_profile_recovered,
        "source_reported_total": source_reported_total,
        "next_page_url": next_page_url,
        "page_size": page_size,
        "page_checkpoints": page_checkpoints or {},
        "rankings": rankings,
    }


def build_results_checkpoint_meta(output_file: Path | str, payload: dict[str, Any]) -> dict[str, Any]:
    rankings = payload.get("rankings") or []
    return {
        "output_file": str(output_file),
        "total_players": len(rankings),
        "site_total_players": parse_int(payload.get("site_total_players"), default=len(rankings)),
        "pages_scraped": parse_int(payload.get("pages_scraped")),
        "page_size": parse_int(payload.get("page_size")) or None,
        "page_checkpoints": dict(payload.get("page_checkpoints") or {}),
        "next_page_url": payload.get("next_page_url"),
    }


def add_risk_cooldown_meta(
    meta: dict[str, Any],
    exc: RiskControlTriggered,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Add a server-directed cooldown to a failed checkpoint."""
    result = dict(meta)
    if exc.status is not None:
        result["http_status"] = exc.status
    if exc.retry_after_sec is None:
        return result
    current = now or datetime.now(timezone.utc)
    retry_after = max(0.0, float(exc.retry_after_sec))
    result["retry_after_sec"] = retry_after
    result["resume_not_before"] = (current + timedelta(seconds=retry_after)).isoformat()
    return result


def results_resume_wait_seconds(
    checkpoint: CheckpointStore,
    checkpoint_key: str,
    *,
    now: datetime | None = None,
) -> float:
    failed = checkpoint.data.get("failed", {}).get(checkpoint_key)
    if not isinstance(failed, dict):
        return 0.0
    meta = failed.get("meta")
    if not isinstance(meta, dict) or not meta.get("resume_not_before"):
        return 0.0
    try:
        resume_at = datetime.fromisoformat(str(meta["resume_not_before"]))
        if resume_at.tzinfo is None:
            resume_at = resume_at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return 0.0
    current = now or datetime.now(timezone.utc)
    return max(0.0, (resume_at - current).total_seconds())


def build_results_resume_url(page_html: str, source_url: str, offset: int) -> str | None:
    soup = BeautifulSoup(page_html, "html.parser")
    link = soup.select_one("a[rel='next'][href], a[title='End'][href]")
    if link is None:
        return None
    href = urllib.parse.urljoin(source_url, html.unescape(str(link.get("href") or "")))
    if not href:
        return None
    parsed = urllib.parse.urlsplit(href)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    limit_keys = [key for key, _value in query if re.fullmatch(r"limitstart\d+", key)]
    if not limit_keys:
        return None
    limit_key = limit_keys[0]
    updated_query = [(key, str(offset) if key == limit_key else value) for key, value in query]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(updated_query), parsed.fragment)
    )


def extract_results_page_urls(page_html: str, source_url: str) -> dict[int, str]:
    soup = BeautifulSoup(page_html, "html.parser")
    urls: dict[int, str] = {0: source_url}
    for link in soup.select(".pagination a[href]"):
        href = urllib.parse.urljoin(source_url, html.unescape(str(link.get("href") or "")))
        parsed = urllib.parse.urlsplit(href)
        for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            if not re.fullmatch(r"limitstart\d+", key):
                continue
            offset = parse_int(value, default=-1)
            if offset >= 0:
                urls[offset] = href
            break
    return urls


def extract_results_page_offset(url: str) -> int:
    for key, value in urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query, keep_blank_values=True):
        if re.fullmatch(r"limitstart\d+", key):
            return max(0, parse_int(value))
    return 0


def click_results_page_offset(
    page: Any,
    *,
    offset: int,
    page_size: int,
    delay_cfg: DelayConfig,
    timeout_sec: float = 20.0,
    poll_sec: float = 0.25,
) -> bool:
    links = page.locator(".pagination a[href]")
    target = None
    for index in range(links.count()):
        candidate = links.nth(index)
        try:
            href = urllib.parse.urljoin(page.url, html.unescape(candidate.get_attribute("href") or ""))
            if extract_results_page_offset(href) != offset or not candidate.is_visible():
                continue
            target = candidate
            break
        except Exception:
            continue
    if target is None:
        return False

    risk_response: Any = None

    def observe_response(response: Any) -> None:
        nonlocal risk_response
        try:
            status = int(response.status)
            response_offset = extract_results_page_offset(str(response.url))
        except (TypeError, ValueError):
            return
        if status in {403, 429, 503} and response_offset == offset:
            risk_response = response

    page.on("response", observe_response)
    try:
        human_sleep(delay_cfg.min_request_sec, delay_cfg.max_request_sec, f"before clicking results offset {offset}")
        target.scroll_into_view_if_needed()
        move_mouse_to_locator(page, target)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
    finally:
        try:
            page.remove_listener("response", observe_response)
        except Exception:
            pass

    if risk_response is not None:
        status = int(risk_response.status)
        headers = getattr(risk_response, "headers", {}) or {}
        retry_after = _retry_after_seconds(headers.get("retry-after"), 0)
        reason = getattr(risk_response, "status_text", "") or ""
        raise RiskControlTriggered(
            f"HTTP {status}{f' {reason}' if reason else ''} after clicking results offset {offset}",
            status=status,
            retry_after_sec=retry_after if status in {429, 503} else None,
        )

    expected_page = (offset // page_size) + 1
    deadline = time.monotonic() + max(0.0, timeout_sec)
    while True:
        risk = detect_risk(page)
        if risk:
            retry_after = 300.0 if "too many requests" in risk.lower() else None
            raise RiskControlTriggered(
                risk,
                status=429 if retry_after is not None else None,
                retry_after_sec=retry_after,
            )
        pagination = extract_results_pagination_info(page.content())
        if pagination is not None and pagination[0] == expected_page:
            logger.info("Clicked results pagination offset %d; active page=%d", offset, expected_page)
            return True
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, poll_sec))
    raise RuntimeError(
        f"results pagination click did not reach offset {offset} (expected page {expected_page})"
    )


def plan_missing_results_page_offsets(
    weekly_rows: list[dict[str, Any]],
    results_rows: list[dict[str, Any]],
    *,
    page_size: int,
    reported_total: int,
    aliases: list[dict[str, Any]] | None = None,
) -> list[int]:
    if page_size <= 0 or reported_total <= 0:
        return []
    merged_rows, _unresolved = merge_rankings_with_results_ids(
        weekly_rows,
        results_rows,
        aliases=aliases,
    )
    row_limit = min(len(weekly_rows), reported_total)
    offsets = {
        (index // page_size) * page_size
        for index, row in enumerate(merged_rows[:row_limit])
        if not row.get("player_id")
    }
    return sorted(offset for offset in offsets if offset < reported_total)


def recover_missing_results_pages(
    weekly_rows: list[dict[str, Any]],
    results_rows: list[dict[str, Any]],
    *,
    page_size: int,
    reported_total: int,
    fetch_page: Callable[[int], list[dict[str, Any]]],
    aliases: list[dict[str, Any]] | None = None,
    on_progress: Callable[[list[dict[str, Any]], dict[str, dict[str, Any]]], None] | None = None,
    completed_offsets: set[int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    recovered_by_id = {
        str(row.get("player_id")): dict(row)
        for row in results_rows
        if row.get("player_id")
    }
    page_checkpoints: dict[str, dict[str, Any]] = {}
    fetched_offsets: set[int] = set(completed_offsets or set())

    def fetch_and_merge(offset: int) -> None:
        page_rows = fetch_page(offset)
        expected_rows = min(page_size, max(0, reported_total - offset))
        if len(page_rows) != expected_rows:
            raise RuntimeError(
                f"results page offset {offset} incomplete: parsed {len(page_rows)} rows, "
                f"expected {expected_rows}"
            )
        rows_valid, rows_reason = validate_results_rows(page_rows)
        if not rows_valid:
            raise RuntimeError(f"results page offset {offset} invalid: {rows_reason}")
        for row in page_rows:
            recovered_by_id[str(row["player_id"])] = row
        fetched_offsets.add(offset)
        page_checkpoints[str(offset)] = {
            "status": "complete",
            "row_count": len(page_rows),
            "parsed_count": len(page_rows),
            "first_rank": parse_int(page_rows[0].get("rank")) if page_rows else None,
            "last_rank": parse_int(page_rows[-1].get("rank")) if page_rows else None,
        }
        if on_progress is not None:
            on_progress(current_rows(), dict(page_checkpoints))

    def current_rows() -> list[dict[str, Any]]:
        return sorted(
            recovered_by_id.values(),
            key=lambda row: (parse_int(row.get("rank")), str(row.get("name") or "")),
        )

    primary_offsets = plan_missing_results_page_offsets(
        weekly_rows,
        current_rows(),
        page_size=page_size,
        reported_total=reported_total,
        aliases=aliases,
    )
    for offset in primary_offsets:
        if offset not in fetched_offsets:
            fetch_and_merge(offset)

    remaining_offsets = plan_missing_results_page_offsets(
        weekly_rows,
        current_rows(),
        page_size=page_size,
        reported_total=reported_total,
        aliases=aliases,
    )
    adjacent_offsets: list[int] = []
    for offset in remaining_offsets:
        for neighbor in (offset - page_size, offset + page_size):
            if 0 <= neighbor < reported_total and neighbor not in fetched_offsets and neighbor not in adjacent_offsets:
                adjacent_offsets.append(neighbor)

    for offset in adjacent_offsets:
        fetch_and_merge(offset)
        if not plan_missing_results_page_offsets(
            weekly_rows,
            current_rows(),
            page_size=page_size,
            reported_total=reported_total,
            aliases=aliases,
        ):
            break

    return current_rows(), page_checkpoints


def validate_partial_results_snapshot(
    snapshot_path: Path | str,
    category: str,
    top_n: int,
) -> tuple[bool, str]:
    path = Path(snapshot_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"partial snapshot unreadable: {exc}"

    if payload.get("category") != category:
        return False, "partial snapshot category mismatch"
    rankings = payload.get("rankings")
    if not isinstance(rankings, list) or not rankings:
        return False, "partial snapshot has no ranking rows"
    reported_total = parse_int(payload.get("source_reported_total"))
    if reported_total <= len(rankings) or len(rankings) >= top_n:
        return False, "snapshot is not an incomplete ranking prefix"
    if parse_int(payload.get("pages_scraped")) <= 0:
        return False, "partial snapshot has no completed pages"
    if parse_int(rankings[0].get("rank")) != 1:
        return False, "partial snapshot is not a ranking prefix starting at rank 1"

    rows_valid, rows_reason = validate_results_rows(rankings)
    if not rows_valid:
        return False, f"partial snapshot {rows_reason}"
    return True, f"valid partial snapshot with {len(rankings)} rows"


def find_resumable_results_output(output_dir: Path | str, category: str, top_n: int) -> Path | None:
    directory = Path(output_dir)
    candidates: list[tuple[int, str, Path]] = []
    for path in directory.glob(f"results_{category}_top{top_n}_*.json"):
        valid, reason = validate_partial_results_snapshot(path, category, top_n)
        if valid:
            try:
                row_count = len(json.loads(path.read_text(encoding="utf-8")).get("rankings") or [])
            except (OSError, json.JSONDecodeError):
                continue
            candidates.append((row_count, path.name, path))
        else:
            logger.debug("Ignoring non-resumable results snapshot %s: %s", path, reason)
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][2]


def find_completed_results_output(
    checkpoint: CheckpointStore,
    category: str,
    top_n: int,
    weekly_file: Path | str | None = None,
) -> Path | None:
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
            if weekly_file is not None:
                complete, reason = is_results_snapshot_complete(path, weekly_file, top_n)
                if not complete:
                    logger.warning("Ignoring completed results checkpoint: %s (%s)", path, reason)
                    continue
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


def scrape_results_rankings(
    page: Any,
    category: str,
    top_n: int,
    delay_cfg: DelayConfig,
    output_file: Path,
    *,
    initial_rankings: list[dict[str, Any]] | None = None,
    initial_pages_scraped: int = 0,
    initial_reported_total: int | None = None,
    page_size: int | None = None,
    initial_page_checkpoints: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rankings: list[dict[str, Any]] = list(initial_rankings or [])
    source_url = RANKING_URLS[category]
    pages_scraped = initial_pages_scraped
    seen_player_ids: set[str] = {
        str(row.get("player_id")) for row in rankings if row.get("player_id")
    }
    reported_total = initial_reported_total
    page_checkpoints = dict(initial_page_checkpoints or {})

    while len(rankings) < top_n:
        risk = detect_risk(page)
        if risk:
            save_json(
                output_file,
                build_output_payload(
                    rankings,
                    category,
                    source_url,
                    pages_scraped,
                    source_reported_total=reported_total,
                ),
            )
            raise RiskControlTriggered(risk)

        page_html = page.content()
        page_reported_total = extract_results_reported_total(page_html)
        if reported_total is None:
            reported_total = page_reported_total
        elif page_reported_total is not None and page_reported_total != reported_total:
            raise RuntimeError(
                f"results ranking total changed during scrape: {reported_total} -> {page_reported_total}"
            )
        page_rows = parse_results_ranking_html(page_html, top_n - len(rankings))
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

        effective_page_size = page_size or len(page_rows)
        pagination = extract_results_pagination_info(page_html)
        page_offset = (
            (pagination[0] - 1) * effective_page_size
            if pagination is not None
            else extract_results_page_offset(str(page.url))
        )
        page_checkpoints[str(page_offset)] = {
            "status": "complete",
            "row_count": len(page_rows),
            "parsed_count": len(page_rows),
            "first_rank": parse_int(page_rows[0].get("rank")) if page_rows else None,
            "last_rank": parse_int(page_rows[-1].get("rank")) if page_rows else None,
        }

        expected_total = min(top_n, reported_total) if reported_total is not None else top_n
        reached_expected_total = len(rankings) >= expected_total
        next_page_url = None if reached_expected_total else build_results_resume_url(
            page_html,
            page.url,
            len(rankings),
        )
        save_json(
            output_file,
            build_output_payload(
                rankings,
                category,
                source_url,
                pages_scraped,
                source_reported_total=reported_total,
                next_page_url=next_page_url,
                page_size=effective_page_size,
                page_checkpoints=page_checkpoints,
            ),
        )
        if reached_expected_total:
            break
        human_sleep(delay_cfg.min_request_sec, delay_cfg.max_request_sec, "before next results ranking page")
        if not click_next_page_if_any(page, delay_cfg):
            break

    validate_scraped_results_count(rankings, top_n, reported_total)
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
            resume=bool(getattr(args, 'resume', False)),
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
    fresh_output_file = Path(args.output) if args.output else output_dir / f"results_{args.category}_top{args.top}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    output_file = fresh_output_file
    checkpoint = CheckpointStore(Path(args.checkpoint))
    if args.force:
        checkpoint.reset()
    resume_output = None
    partial_resume_output = None
    if getattr(args, "resume", False) and not args.force:
        resume_output = find_completed_results_output(
            checkpoint,
            args.category,
            args.top,
            weekly_file=getattr(args, "weekly_file", None),
        )
        if resume_output is not None:
            output_file = resume_output
            logger.info("Resuming from completed results ranking snapshot: %s", resume_output)
            if args.ranking_only:
                return 0
        else:
            partial_resume_output = find_resumable_results_output(
                output_dir,
                args.category,
                args.top,
            )
            if partial_resume_output is not None:
                output_file = partial_resume_output
                logger.info("Resuming incomplete results ranking snapshot: %s", partial_resume_output)

    checkpoint_key = f"results-ranking|{args.category}|top:{args.top}|{output_file.name}"

    if getattr(args, "resume", False) and not args.force:
        wait_seconds = results_resume_wait_seconds(checkpoint, checkpoint_key)
        if wait_seconds > 0:
            logger.error(
                "Results ranking cooldown is still active; retry --resume in %.0fs",
                wait_seconds,
            )
            return 4

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

            if resume_output is not None and getattr(args, "weekly_file", None):
                live_reported_total = extract_results_reported_total(page.content())
                complete, reason = is_results_snapshot_complete(
                    resume_output,
                    args.weekly_file,
                    args.top,
                    reported_total=live_reported_total,
                )
                if not complete:
                    logger.warning("Completed results snapshot is stale; scraping ranking list again: %s", reason)
                    resume_output = None
                    output_file = fresh_output_file
                    checkpoint_key = f"results-ranking|{args.category}|top:{args.top}|{output_file.name}"

            if resume_output is not None:
                rankings = load_results_rankings_snapshot(resume_output, args.category, args.top)
            else:
                try:
                    page.locator("table").first.wait_for(timeout=15000)
                except Exception:
                    logger.warning("ranking table did not appear before timeout")

                display_100_verified = select_results_display_100(page)

                partial_payload: dict[str, Any] | None = None
                targeted_rankings: list[dict[str, Any]] | None = None
                if partial_resume_output is not None:
                    partial_payload = json.loads(partial_resume_output.read_text(encoding="utf-8"))
                    live_html = page.content()
                    live_total = extract_results_reported_total(live_html)
                    live_page_rows = parse_results_ranking_html(live_html, args.top)
                    live_page_size = 100 if display_100_verified else len(live_page_rows)
                    saved_total = parse_int(partial_payload.get("source_reported_total"))
                    saved_rows = partial_payload.get("rankings") or []
                    live_pagination = extract_results_pagination_info(live_html)
                    snapshot_matches: bool | None = False
                    validation_reason = "invalid live pagination"
                    if live_page_size > 0 and live_pagination is not None:
                        snapshot_matches, validation_reason = validate_live_page_against_partial(
                            live_page_rows,
                            list(saved_rows),
                            current_page=live_pagination[0],
                            page_size=live_page_size,
                        )

                    if snapshot_matches is None and saved_rows:
                        anchor_offset = ((len(saved_rows) - 1) // live_page_size) * live_page_size
                        current_offset = (live_pagination[0] - 1) * live_page_size
                        if current_offset != anchor_offset:
                            logger.info(
                                "Current results page has no saved overlap; clicking validation anchor offset %d",
                                anchor_offset,
                            )
                            if not click_results_page_offset(
                                page,
                                offset=anchor_offset,
                                page_size=live_page_size,
                                delay_cfg=delay_cfg,
                            ):
                                raise RuntimeError(
                                    f"Cannot validate partial results snapshot: no pagination link for offset {anchor_offset}"
                                )
                            live_html = page.content()
                            live_total = extract_results_reported_total(live_html)
                            live_page_rows = parse_results_ranking_html(live_html, args.top)
                            live_pagination = extract_results_pagination_info(live_html)
                        if live_pagination is None:
                            snapshot_matches = False
                            validation_reason = "validation anchor lacks pagination metadata"
                        else:
                            snapshot_matches, validation_reason = validate_live_page_against_partial(
                                live_page_rows,
                                list(saved_rows),
                                current_page=live_pagination[0],
                                page_size=live_page_size,
                            )

                    if live_total != saved_total or snapshot_matches is not True or live_page_size <= 0:
                        logger.warning(
                            "Ignoring partial results snapshot because the live ranking changed: "
                            "saved_total=%s live_total=%s page_validation=%s page_size=%s",
                            saved_total,
                            live_total,
                            validation_reason,
                            live_page_size,
                        )
                        partial_resume_output = None
                        partial_payload = None
                        output_file = fresh_output_file
                        checkpoint_key = f"results-ranking|{args.category}|top:{args.top}|{output_file.name}"
                    else:
                        logger.info("Validated partial results snapshot: %s", validation_reason)
                        weekly_path = Path(str(getattr(args, "weekly_file", "") or ""))
                        if weekly_path.is_file():
                            weekly_payload = json.loads(weekly_path.read_text(encoding="utf-8"))
                            weekly_rows = weekly_payload.get("rankings") or []
                            if not isinstance(weekly_rows, list):
                                raise RuntimeError(f"weekly rankings is not a list: {weekly_path}")
                            aliases = load_player_name_aliases(getattr(args, "aliases", None))
                            planned_offsets = plan_missing_results_page_offsets(
                                weekly_rows,
                                list(saved_rows),
                                page_size=live_page_size,
                                reported_total=int(live_total or 0),
                                aliases=aliases,
                            )
                            logger.info(
                                "Targeted results resume: existing=%d missing_pages=%s page_size=%d",
                                len(saved_rows),
                                planned_offsets,
                                live_page_size,
                            )
                            page_urls = extract_results_page_urls(live_html, target_url)
                            existing_page_checkpoints = dict(partial_payload.get("page_checkpoints") or {})
                            completed_offsets = {
                                parse_int(offset)
                                for offset, value in existing_page_checkpoints.items()
                                if isinstance(value, dict) and value.get("status") == "complete"
                            }

                            def fetch_target_page(offset: int) -> list[dict[str, Any]]:
                                if offset == 0:
                                    target_html = live_html
                                else:
                                    page_url = page_urls.get(offset) or build_results_resume_url(
                                        live_html,
                                        target_url,
                                        offset,
                                    )
                                    if not page_url:
                                        raise RuntimeError(f"Cannot build results page URL for offset {offset}")
                                    logger.info("Fetching targeted results page offset %d: %s", offset, page_url)
                                    clicked = click_results_page_offset(
                                        page,
                                        offset=offset,
                                        page_size=live_page_size,
                                        delay_cfg=delay_cfg,
                                    )
                                    if not clicked:
                                        referer = page.url
                                        logger.warning(
                                            "No visible pagination link for offset %d; using one-shot URL fallback",
                                            offset,
                                        )
                                        guarded_goto(
                                            page,
                                            page_url,
                                            delay_cfg,
                                            f"fallback fetch targeted results page offset {offset}",
                                            referer=referer,
                                            retries=0,
                                            retry_risk_responses=False,
                                        )
                                    target_html = page.content()
                                target_total = extract_results_reported_total(target_html)
                                if target_total != live_total:
                                    raise RuntimeError(
                                        f"results total changed while fetching offset {offset}: "
                                        f"{live_total} -> {target_total}"
                                    )
                                return parse_results_ranking_html(target_html, live_page_size)

                            def save_targeted_progress(
                                rows: list[dict[str, Any]],
                                new_page_checkpoints: dict[str, dict[str, Any]],
                            ) -> None:
                                combined_checkpoints = {
                                    **existing_page_checkpoints,
                                    **new_page_checkpoints,
                                }
                                save_json(
                                    output_file,
                                    build_output_payload(
                                        rows,
                                        args.category,
                                        target_url,
                                        parse_int(partial_payload.get("pages_scraped"))
                                        + len(new_page_checkpoints),
                                        site_total_players=len(rows),
                                        source_reported_total=live_total,
                                        page_size=live_page_size,
                                        page_checkpoints=combined_checkpoints,
                                    ),
                                )

                            targeted_rankings, new_page_checkpoints = recover_missing_results_pages(
                                weekly_rows,
                                list(saved_rows),
                                page_size=live_page_size,
                                reported_total=int(live_total or 0),
                                fetch_page=fetch_target_page,
                                aliases=aliases,
                                on_progress=save_targeted_progress,
                                completed_offsets=completed_offsets,
                            )
                            save_targeted_progress(targeted_rankings, new_page_checkpoints)
                            validate_scraped_results_count(
                                targeted_rankings,
                                args.top,
                                live_total,
                            )
                        else:
                            resume_url = partial_payload.get("next_page_url") or build_results_resume_url(
                                live_html,
                                target_url,
                                len(saved_rows),
                            )
                            if not resume_url:
                                logger.warning("Ignoring partial results snapshot without a continuation URL")
                                partial_resume_output = None
                                partial_payload = None
                                output_file = fresh_output_file
                                checkpoint_key = f"results-ranking|{args.category}|top:{args.top}|{output_file.name}"
                            else:
                                logger.info(
                                    "Continuing results ranking at row offset %d: %s",
                                    len(saved_rows),
                                    resume_url,
                                )
                                guarded_goto(
                                    page,
                                    str(resume_url),
                                    delay_cfg,
                                    "resume results ranking page",
                                )

                if targeted_rankings is not None:
                    rankings = targeted_rankings
                elif partial_payload is not None:
                    rankings = scrape_results_rankings(
                        page,
                        args.category,
                        args.top,
                        delay_cfg,
                        output_file,
                        initial_rankings=list(partial_payload.get("rankings") or []),
                        initial_pages_scraped=parse_int(partial_payload.get("pages_scraped")),
                        initial_reported_total=parse_int(partial_payload.get("source_reported_total")) or None,
                        page_size=parse_int(partial_payload.get("page_size")) or None,
                        initial_page_checkpoints=dict(partial_payload.get("page_checkpoints") or {}),
                    )
                else:
                    fresh_html = page.content()
                    fresh_page_size = 100 if display_100_verified else len(
                        parse_results_ranking_html(fresh_html, args.top)
                    )
                    rankings = scrape_results_rankings(
                        page,
                        args.category,
                        args.top,
                        delay_cfg,
                        output_file,
                        page_size=fresh_page_size or None,
                    )
            if not rankings:
                logger.error("Parsed 0 results ranking rows")
                close_browser_page(via_cdp, browser, page)
                return 5

            if resume_output is None:
                completed_payload = json.loads(output_file.read_text(encoding="utf-8"))
                checkpoint.mark_done(
                    checkpoint_key,
                    meta=build_results_checkpoint_meta(output_file, completed_payload),
                )
                logger.info("Saved results ranking snapshot: %s", output_file)

            if not args.ranking_only:
                refreshed = refresh_profiles(page, rankings, args, delay_cfg, checkpoint)
                logger.info("Profile refresh complete: %d scraped now", refreshed)
                recovered = recover_missing_profiles_with_browser(
                    page,
                    rankings,
                    args,
                    delay_cfg,
                    checkpoint,
                )
                if recovered:
                    existing_payload = json.loads(output_file.read_text(encoding="utf-8"))
                    site_total_players = int(existing_payload.get("site_total_players") or len(rankings))
                    rankings.extend(recovered)
                    save_json(
                        output_file,
                        build_output_payload(
                            rankings,
                            args.category,
                            str(existing_payload.get("source_url") or target_url),
                            int(existing_payload.get("pages_scraped") or 0),
                            site_total_players=site_total_players,
                            db_profile_recovered=len(rankings) - site_total_players,
                            source_reported_total=parse_int(existing_payload.get("source_reported_total")) or None,
                            page_size=parse_int(existing_payload.get("page_size")) or None,
                            page_checkpoints=dict(existing_payload.get("page_checkpoints") or {}),
                        ),
                    )
                    augmented_payload = json.loads(output_file.read_text(encoding="utf-8"))
                    checkpoint.mark_done(
                        checkpoint_key,
                        meta={
                            **build_results_checkpoint_meta(output_file, augmented_payload),
                            "db_profile_recovered": len(rankings) - site_total_players,
                        },
                    )
                    logger.info("Saved augmented results ranking snapshot: %s", output_file)
        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            if output_file.exists():
                try:
                    failed_payload = json.loads(output_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    failed_payload = {}
                checkpoint.mark_failed(
                    checkpoint_key,
                    str(exc),
                    meta=add_risk_cooldown_meta(
                        build_results_checkpoint_meta(output_file, failed_payload),
                        exc,
                    ),
                )
            close_browser_page(via_cdp, browser, page)
            return 4
        except Exception as exc:
            logger.error("Results ranking scrape failed: %s", exc)
            if output_file.exists():
                try:
                    failed_payload = json.loads(output_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    failed_payload = {}
                checkpoint.mark_failed(
                    checkpoint_key,
                    str(exc),
                    meta=build_results_checkpoint_meta(output_file, failed_payload),
                )
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
    parser.add_argument("--weekly-file", default=None, help="Official weekly ranking JSON used for DB/profile fallback")
    parser.add_argument("--db-path", default=DB_PATH, help="SQLite database used for missing-player fallback")
    parser.add_argument("--aliases", default="scripts/data/player_name_aliases.json", help="Manual player name alias JSON")
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
