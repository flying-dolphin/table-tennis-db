#!/usr/bin/env python3
"""
ITTF player profile scraper.

Scrapes player profiles from results.ittf.link ranking pages.
Uses the ranking table as input source to get player list,
then scrapes individual profile pages for detailed data.

注意：这个脚本有个bug，无法获取country code！待废弃
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from lib.anti_bot import DelayConfig, RiskControlTriggered, human_sleep
from lib.browser_runtime import close_browser_page, open_browser_page
from lib.capture import save_json, sanitize_filename
from lib.checkpoint import CheckpointStore
from lib.career_best import normalize_career_best_month
from lib.name_normalizer import normalize_player_name
from lib.navigation_runtime import open_page_with_verification
from lib.page_ops import click_next_page_if_any, guarded_goto
from lib.dict_translator import DictTranslator
from lib.country_codes import country_name_for_code, normalize_country_name, normalize_profile_country

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_profile_scraper")


class IncompleteProfileError(RuntimeError):
    """The requested page loaded, but did not contain a complete player profile."""


def validate_scraped_profile(profile_data: dict[str, Any], expected_player_id: Any) -> None:
    actual_player_id = profile_data.get("player_id")
    if str(actual_player_id or "") != str(expected_player_id or ""):
        raise IncompleteProfileError(
            f"profile player_id mismatch: expected {expected_player_id}, got {actual_player_id}"
        )

    missing_fields = [field for field in ("gender",) if not str(profile_data.get(field) or "").strip()]
    if missing_fields:
        raise IncompleteProfileError(f"missing required fields: {', '.join(missing_fields)}")


BASE_URL = "https://results.ittf.link"
PUBLIC_RANKING_BASE = f"{BASE_URL}/index.php/ittf-rankings"
RANKING_URLS = {
    "women": f"{PUBLIC_RANKING_BASE}/ittf-ranking-women-singles",
    "men": f"{PUBLIC_RANKING_BASE}/ittf-ranking-men-singles",
    "women_doubles": f"{PUBLIC_RANKING_BASE}/ittf-ranking-women-doubles",
    "men_doubles": f"{PUBLIC_RANKING_BASE}/ittf-ranking-men-doubles",
    "mixed": f"{PUBLIC_RANKING_BASE}/ittf-ranking-mixed-doubles",
}
CATEGORY_META = {
    "women": "女子单打",
    "men": "男子单打",
    "women_doubles": "女子双打",
    "men_doubles": "男子双打",
    "mixed": "混合双打",
}

COUNTRY_NAMES = {
    "CHN": "中国", "JPN": "日本", "KOR": "韩国", "GER": "德国",
    "FRA": "法国", "USA": "美国", "HKG": "中国香港", "TPE": "中国台北",
    "MAC": "中国澳门", "SGP": "新加坡", "BRA": "巴西", "EGY": "埃及",
    "IND": "印度", "ROU": "罗马尼亚", "AUT": "奥地利", "NED": "荷兰",
    "SWE": "瑞典", "POL": "波兰", "ESP": "西班牙", "ITA": "意大利",
    "ENG": "英格兰", "WAL": "威尔士", "SCO": "苏格兰", "AUS": "澳大利亚",
    "NZL": "新西兰", "CAN": "加拿大", "MEX": "墨西哥", "ARG": "阿根廷",
    "PUR": "波多黎各", "DOM": "多米尼加", "CZE": "捷克", "RUS": "俄罗斯",
    "UKR": "乌克兰", "TUR": "土耳其", "IRI": "伊朗", "THA": "泰国",
    "VIE": "越南", "INA": "印度尼西亚", "MAS": "马来西亚", "PHI": "菲律宾",
    "PAK": "巴基斯坦", "KAZ": "哈萨克斯坦", "UZB": "乌兹别克斯坦",
    "SIN": "新加坡", "AIN": "中立运动员", "POR": "葡萄牙",
}
CONTINENT_NAMES = {
    "ASIA": "亚洲", "EUROPE": "欧洲", "AMERICA": "美洲", "AFRICA": "非洲", "OCEANIA": "大洋洲",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF player profile scraper")
    parser.add_argument("--category", choices=sorted(RANKING_URLS.keys()), default="women")
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP remote debugging port (default: 9222)")
    parser.add_argument("--cdp-only", action="store_true", help="Require connecting to an existing CDP Chrome; do not launch a new browser")
    parser.add_argument("--snapshot-dir", default="data/ranking_snapshots")
    parser.add_argument("--profile-dir", default="data/player_profiles")
    parser.add_argument("--avatar-dir", default="data/player_avatars")
    parser.add_argument("--output", default=None)
    parser.add_argument("--checkpoint", default="data/player_profiles/checkpoint_scrape_profiles.json", help="Scrape checkpoint file path")
    parser.add_argument("--player-id", type=str, default=None, help="Player ID (player_id_raw)")
    parser.add_argument("--player-name", type=str, default=None, help="Player name (URL encoded)")
    parser.add_argument("--player-file", type=str, default=None, help="Batch file (player_id,player_name per line)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint: skip already-scraped profiles")
    parser.add_argument("--rebuild-checkpoint", action="store_true", help="Rebuild checkpoint from existing orig/cn files")
    return parser


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_int(text: str, default: int = 0) -> int:
    cleaned = re.sub(r"[^\d+-]", "", text or "")
    if cleaned in {"", "+", "-"}:
        return default
    try:
        return int(cleaned)
    except ValueError:
        return default


def translate_country(code: str, fallback: str = "") -> str:
    if code in COUNTRY_NAMES:
        return COUNTRY_NAMES[code]
    return fallback or code


def translate_continent(code: str, fallback: str = "") -> str:
    if code in CONTINENT_NAMES:
        return CONTINENT_NAMES[code]
    return fallback or code


def extract_player_id_from_href(href: str | None) -> str | None:
    if not href:
        return None
    match = re.search(r"player_id_raw=(\d+)", href)
    if match:
        return match.group(1)
    return None


def parse_ranking_rows(page: Any, top_n: int, translator: DictTranslator | None = None, translate_names: bool = True) -> list[dict[str, Any]]:
    """Parse ranking rows from the ranking list page, following pagination if needed."""
    rankings: list[dict[str, Any]] = []
    while len(rankings) < top_n:
        target_table = page.locator("table#list_58_com_fabrik_58")
        if target_table.count() == 0:
            target_table = page.locator("table")
        if target_table.count() == 0:
            break

        rows = target_table.first.locator("tbody tr")
        row_count = rows.count()

        rows_added = 0
        for idx in range(row_count):
            if len(rankings) >= top_n:
                break

            row = rows.nth(idx)
            cells = row.locator("td")
            cell_count = cells.count()
            if cell_count < 8:
                continue

            cell_texts = [normalize_space(cells.nth(i).inner_text()) for i in range(cell_count)]
            rank = parse_int(cell_texts[1] if len(cell_texts) > 1 else "", default=-1)
            if rank <= 0:
                continue

            expected_rank = len(rankings) + 1
            if rank != expected_rank:
                raise RuntimeError(
                    f"Ranking pagination mismatch on {page.url}: expected position {expected_rank}, got {rank}. "
                    "Next page navigation is likely broken."
                )

            change = parse_int(cell_texts[2] if len(cell_texts) > 2 else "0")
            points = parse_int(cell_texts[3] if len(cell_texts) > 3 else "0")
            english_name = normalize_player_name(normalize_space(cell_texts[4] if len(cell_texts) > 4 else ""))
            country_code = ""
            try:
                flag_img = cells.nth(5).locator("img").first
                if flag_img.count() > 0:
                    country_code = normalize_space(flag_img.get_attribute("title") or "")
            except Exception:
                country_code = ""

            association = normalize_space(cell_texts[6] if len(cell_texts) > 6 else "")
            continent_raw = normalize_space(cell_texts[7] if len(cell_texts) > 7 else "")

            href = None
            try:
                name_link = cells.nth(4).locator("a").first
                if name_link.count() > 0:
                    href = name_link.get_attribute("href")
            except Exception:
                href = None

            profile_url = None
            if href:
                profile_url = BASE_URL + href if href.startswith("/") else href
                profile_url = profile_url.replace("/../", "/")

            # 根据 translate_names 参数决定是否翻译
            if translate_names:
                # 翻译模式：查词典转换
                display_name = english_name
                if translator:
                    translated = translator.translate(english_name, 'players')
                    if translated != english_name:  # 词典命中
                        display_name = translated
                country_name = translate_country(country_code, association)
                continent_name = translate_continent(continent_raw, continent_raw)
            else:
                # 无翻译模式：保持原始英文
                display_name = english_name
                country_name = country_name_for_code(country_code) or association or country_code
                continent_name = continent_raw

            player = {
                "rank": rank,
                "name": display_name,
                "english_name": english_name,
                "points": points,
                "change": change,
                "country": country_name,
                "country_code": country_code,
                "continent": continent_name,
                "player_id": extract_player_id_from_href(href),
                "profile_url": profile_url,
            }
            rankings.append(player)
            rows_added += 1

        if len(rankings) >= top_n:
            break
        if rows_added == 0:
            break
        if not click_next_page_if_any(page):
            break

    return rankings


def extract_update_meta(page: Any, category: str) -> tuple[str, str]:
    html = page.content()

    week = ""
    week_match = re.search(r'fab_rank_ws___Week":(\d+)', html)
    if week_match:
        week_num = int(week_match.group(1))
        year = datetime.now().year
        week = f"{year}年第{week_num}周"

    update_date = ""
    date_match = re.search(r'(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})', html)
    if date_match:
        update_date = date_match.group(1)
    else:
        update_date = datetime.now().strftime("%Y年%m月%d日")

    return week, update_date


def build_output(rankings: list[dict[str, Any]], category: str, week: str, update_date: str) -> dict[str, Any]:
    return {
        "update_date": update_date,
        "week": week,
        "category": CATEGORY_META[category],
        "category_key": category,
        "total_players": len(rankings),
        "rankings": rankings,
    }


def scrape_player_profile(
    page: Any,
    profile_url: str,
    player_info: dict[str, Any],
    delay_cfg: DelayConfig,
    profile_orig_dir: Path,
    avatar_dir: Path,
    checkpoint: CheckpointStore | None = None,
    category: str | None = None,
    resume: bool = False,
    country_rev_map: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Scrape player profile page and save to JSON (orig only) and DB."""
    if not profile_url:
        return None, False

    player_id = player_info.get("player_id")
    if not player_id:
        return None, False

    # Stable checkpoint keys (per-player, scoped by category).
    cat = category or ""
    ck_base = f"profile|{cat}|player:{player_id}"
    ck_scrape = f"{ck_base}|scrape"
    safe_name = sanitize_filename(player_info.get("english_name", player_info.get("name", player_id)))
    json_filename = f"player_{player_id}_{safe_name}.json"
    orig_path = profile_orig_dir / json_filename

    # Only skip when --resume is active and checkpoint says done and file exists.
    if resume and checkpoint is not None and checkpoint.is_done(ck_scrape) and orig_path.exists():
        try:
            profile_data = json.loads(orig_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Checkpoint done but orig JSON unreadable, will rescrape: %s (%s)", orig_path, exc)
            profile_data = None

        if profile_data is None:
            # Fall through to web scraping.
            pass
        else:
            logger.info("Skipping profile scrape (checkpoint): %s", player_id)
            return profile_data or None, False

    try:
        profile_data = None
        for attempt in range(2):
            current_url = str(getattr(page, "url", "") or "")
            referer = current_url if current_url.startswith(BASE_URL) else None
            guarded_goto(
                page,
                profile_url,
                delay_cfg,
                f"open profile: {player_info.get('name', player_id)}",
                referer=referer,
                retries=0,
                retry_risk_responses=False,
            )

            page.wait_for_load_state("networkidle", timeout=10000)
            profile_data = extract_profile_info(page, player_info, profile_url, country_rev_map)
            try:
                validate_scraped_profile(profile_data, player_id)
                break
            except IncompleteProfileError:
                if attempt == 1:
                    raise
                logger.warning("Incomplete profile for %s; retrying once", player_id)

        assert profile_data is not None
        avatar_meta = download_player_avatar(page, player_info, avatar_dir)
        if avatar_meta:
            profile_data.update(avatar_meta)

        # Save original (English) profile to orig directory
        save_json(orig_path, profile_data)
        logger.info("Saved original profile: %s", orig_path)
        if checkpoint is not None:
            checkpoint.mark_done(ck_scrape, meta={"orig_path": str(orig_path), "profile_url": profile_url})

        return profile_data, True

    except RiskControlTriggered as exc:
        logger.warning("Risk control while scraping profile %s: %s", player_id, exc)
        if checkpoint is not None:
            meta: dict[str, Any] = {"profile_url": profile_url}
            if exc.status is not None:
                meta["http_status"] = exc.status
            if exc.retry_after_sec is not None:
                retry_after = max(0.0, float(exc.retry_after_sec))
                meta["retry_after_sec"] = retry_after
                meta["resume_not_before"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=retry_after)
                ).isoformat()
            checkpoint.mark_failed(ck_scrape, str(exc), meta=meta)
        raise
    except Exception as exc:
        logger.warning("Failed to scrape profile for %s: %s", player_id, exc)
        if checkpoint is not None:
            checkpoint.mark_failed(ck_scrape, str(exc), meta={"profile_url": profile_url})
        return None, False


def download_player_avatar(page: Any, player_info: dict[str, Any], avatar_dir: Path) -> dict[str, Any] | None:
    """Download player avatar image from profile page."""
    try:
        avatar_dir.mkdir(parents=True, exist_ok=True)
        candidates = page.locator("img")
        count = candidates.count()
        best_url = None
        for idx in range(count):
            try:
                src = candidates.nth(idx).get_attribute("src") or ""
                if not src:
                    continue
                src_lower = src.lower()
                if "headshot" in src_lower or ("wtt-media" in src_lower and any(ext in src_lower for ext in [".png", ".jpg", ".jpeg", ".webp"])):
                    best_url = src
                    break
            except Exception:
                continue
        if not best_url:
            return None

        parsed = urllib.parse.urlparse(best_url)
        ext = Path(parsed.path).suffix or ".png"
        safe_name = sanitize_filename(player_info.get("english_name", player_info.get("name", player_info.get("player_id", "unknown"))))
        file_path = avatar_dir / f"player_{player_info.get('player_id')}_{safe_name}{ext}"
        # URL-encode the path to handle spaces and special characters
        encoded_path = urllib.parse.quote(parsed.path, safe='/')
        encoded_url = urllib.parse.urlunparse((
            parsed.scheme, parsed.netloc, encoded_path, parsed.params, parsed.query, parsed.fragment
        ))
        req = urllib.request.Request(encoded_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read()
        file_path.write_bytes(content)
        return {
            "avatar_url": best_url,
            "avatar_file_path": str(file_path),
        }
    except Exception as exc:
        logger.warning("Failed to download avatar for %s: %s", player_info.get("player_id"), exc)
        return None


def extract_profile_info(page: Any, player_info: dict[str, Any], profile_url: str, country_rev_map: dict[str, str] | None = None) -> dict[str, Any]:
    """Extract detailed profile information from player page."""
    profile_data: dict[str, Any] = {
        "player_id": player_info.get("player_id"),
        "name": player_info.get("name", ""),
        "english_name": player_info.get("english_name", ""),
        "country": country_name_for_code(player_info.get("country_code")) or player_info.get("country", ""),
        "country_code": player_info.get("country_code", ""),
        "profile_url": profile_url,
        "rank": player_info.get("rank"),
        "points": player_info.get("points"),
        "rank_change": player_info.get("change"),
        "scraped_at": datetime.now().isoformat(),
    }

    try:
        main = page.locator("main") if page.locator("main").count() > 0 else page.locator("body")
        main_content = main.inner_text()

        stats_table = None
        tables = page.locator("main table") if page.locator("main table").count() > 0 else page.locator("table")
        for i in range(tables.count()):
            table = tables.nth(i)
            try:
                headers = [normalize_space(x) for x in table.locator("tr").first.locator("th,td").all_inner_texts()]
                if "Profile" in headers and "Career *" in headers and "Current Year *" in headers:
                    stats_table = table
                    break
            except Exception:
                continue

        profile_cell_raw_text = ""
        profile_cell_text = ""
        career_cell_text = ""
        current_year_cell_text = ""
        if stats_table is not None:
            rows = stats_table.locator("tr")
            for i in range(rows.count()):
                cells = rows.nth(i).locator("td")
                if cells.count() >= 5:
                    name_cell = normalize_space(cells.nth(1).inner_text())
                    if player_info.get("player_id") and player_info["player_id"] in name_cell:
                        profile_cell_raw_text = cells.nth(2).inner_text()
                        profile_cell_text = normalize_space(profile_cell_raw_text)
                        career_cell_text = normalize_space(cells.nth(3).inner_text())
                        current_year_cell_text = normalize_space(cells.nth(4).inner_text())
                        break
        if not profile_cell_raw_text:
            try:
                profile_cell = page.locator("td.vw_profiles___profile").first
                if profile_cell.count() > 0:
                    profile_cell_raw_text = profile_cell.inner_text()
                    profile_cell_text = normalize_space(profile_cell_raw_text)
            except Exception:
                profile_cell_raw_text = ""

        text_content = profile_cell_text or main_content

        profile_lines = [normalize_space(line) for line in profile_cell_raw_text.splitlines() if normalize_space(line)]
        if profile_lines:
            first_line = profile_lines[0]
            if re.fullmatch(r'[A-Z ]+', first_line):
                country_en = first_line.strip()
                profile_data["country"] = country_en
                profile_data["country_en"] = country_en
                if not profile_data.get("country_code") and country_rev_map:
                    code = country_rev_map.get(country_en)
                    if code:
                        profile_data["country_code"] = code
                    else:
                        player_id = profile_data.get("player_id", "?")
                        name = profile_data.get("name", "?")
                        raise ValueError(
                            f"Country '{country_en}' for player {player_id} ({name}) "
                            f"not found in country_code_map"
                        )

        gender_match = re.search(r'Gender:\s*(\w+)', text_content, re.IGNORECASE)
        if gender_match:
            profile_data["gender"] = gender_match.group(1).capitalize()

        birth_year_match = re.search(r'Birth Year:\s*(\d{4})', text_content, re.IGNORECASE)
        if birth_year_match:
            profile_data["birth_year"] = int(birth_year_match.group(1))

        age_match = re.search(r'Age:\s*(\d+)', text_content, re.IGNORECASE)
        if age_match:
            profile_data["age"] = int(age_match.group(1))

        style_match = re.search(r'Style:\s*(.+?)(?=\s*Ranking:|$)', text_content, re.IGNORECASE)
        if style_match:
            style_str = style_match.group(1).strip()
            profile_data["style"] = style_str
            if "right" in style_str.lower():
                profile_data["playing_hand"] = "Right"
            elif "left" in style_str.lower():
                profile_data["playing_hand"] = "Left"
            grip_match = re.search(r'\(([^)]+)\)', style_str)
            if grip_match:
                profile_data["grip"] = grip_match.group(1).strip()

        ranking_match = re.search(r'Ranking:\s*(\d+)\s*\|\s*Week:\s*(.+?)(?=\s*Career Best\*\*:|$)', text_content)
        if ranking_match:
            profile_data["current_rank"] = int(ranking_match.group(1))
            profile_data["ranking_week"] = ranking_match.group(2).strip()

        career_best_match = re.search(r'Career Best\*\*:\s*(\d+)\s*\|\s*(Week|Month):\s*([^\n]+)', text_content)
        if career_best_match:
            profile_data["career_best_rank"] = int(career_best_match.group(1))
            normalized = normalize_career_best_month(
                career_best_match.group(3).strip(),
                career_best_match.group(2).strip(),
            )
            if normalized.month:
                profile_data["career_best_month"] = normalized.month

        if career_cell_text:
            profile_data["career_stats"] = parse_stats_cell(career_cell_text, "career")
        if current_year_cell_text:
            profile_data["current_year_stats"] = parse_stats_cell(current_year_cell_text, "current_year")

        recent_matches = []
        recent_section_match = re.search(r'Recent Singles Matches:\s*(.+?)(?:Results in Singles Matches in WTT Events:|Results in Singles Matches in ITTF Individual Events:|$)', main_content, re.DOTALL)
        if recent_section_match:
            recent_text = normalize_space(recent_section_match.group(1))
            chunks = re.findall(r'(.+?Result:\s*(?:WON|LOST))(?=\s+(?:ITTF|WTT)\b|$)', recent_text)
            for chunk in chunks:
                chunk = chunk.strip()
                if ' vs ' not in chunk or 'Result:' not in chunk:
                    continue
                player_name = re.escape(player_info.get("english_name", "").strip())
                m = re.search(rf'^(.*?)\s+({player_name})\s+\(([A-Z]{{3}})\)\s+vs\s+([A-Z][A-Za-z\-\s]+)\s+\(([A-Z]{{3}})\)\s+(.*?)\s*\|\s*(.*?)\s*Result:\s*(WON|LOST)$', chunk)
                if not m:
                    m = re.search(r'^(.*?)\s+([A-Z][A-Za-z\-\s]+)\s+\(([A-Z]{3})\)\s+vs\s+([A-Z][A-Za-z\-\s]+)\s+\(([A-Z]{3})\)\s+(.*?)\s*\|\s*(.*?)\s*Result:\s*(WON|LOST)$', chunk)
                if not m:
                    continue
                recent_matches.append({
                    "event": normalize_space(m.group(1)),
                    "player": normalize_space(m.group(2)),
                    "player_country": m.group(3),
                    "opponent": normalize_space(m.group(4)),
                    "opponent_country": m.group(5),
                    "stage": normalize_space(m.group(6)),
                    "score": normalize_space(m.group(7)),
                    "result": m.group(8),
                })
        if recent_matches:
            profile_data["recent_matches"] = recent_matches

    except Exception as exc:
        logger.warning("Error extracting profile details: %s", exc)

    normalize_profile_country(profile_data)
    return profile_data


def parse_stats_cell(cell_text: str, prefix: str) -> dict[str, Any]:
    """Parse stats from a table cell text."""
    stats = {}
    
    # Events
    events_match = re.search(r'Events:\s*(\d+)', cell_text)
    if events_match:
        stats["events"] = int(events_match.group(1))
    
    # Matches
    matches_match = re.search(r'Matches:\s*(\d+)', cell_text)
    if matches_match:
        stats["matches"] = int(matches_match.group(1))
    
    # Wins
    wins_match = re.search(r'Wins:\s*(\d+)', cell_text)
    if wins_match:
        stats["wins"] = int(wins_match.group(1))
    
    # Loses
    loses_match = re.search(r'Loses:\s*(\d+)', cell_text)
    if loses_match:
        stats["loses"] = int(loses_match.group(1))
    
    # Games
    games_match = re.search(r'Games:\s*(\d+)\s*\(W:\s*(\d+)\s*,\s*L:\s*(\d+)\)', cell_text)
    if games_match:
        stats["games"] = int(games_match.group(1))
        stats["games_won"] = int(games_match.group(2))
        stats["games_lost"] = int(games_match.group(3))
    
    # Points
    points_match = re.search(r'Points:\s*(\d+)\s*\(W:\s*(\d+)\s*,\s*L:\s*(\d+)\)', cell_text)
    if points_match:
        stats["points_played"] = int(points_match.group(1))
        stats["points_won"] = int(points_match.group(2))
        stats["points_lost"] = int(points_match.group(3))
    
    # WTT Senior Titles
    wtt_match = re.search(r'WTT Senior Titles:\s*(\d+)', cell_text)
    if wtt_match:
        stats["wtt_senior_titles"] = int(wtt_match.group(1))
    
    # All Senior Titles
    all_titles_match = re.search(r'All Senior Titles:\s*(\d+)', cell_text)
    if all_titles_match:
        stats["all_senior_titles"] = int(all_titles_match.group(1))
    
    return stats


def _bootstrap_profiles_checkpoint_from_orig(
    checkpoint: CheckpointStore,
    category: str,
    profile_orig_dir: Path,
) -> None:
    """If checkpoint is missing/empty, infer completed players from existing orig files."""
    if checkpoint.path.exists() and checkpoint.has_any_completed():
        return

    if not profile_orig_dir.exists():
        return

    pat = re.compile(r"^player_(\d+)_.*\.json$", re.IGNORECASE)
    with checkpoint.bulk():
        for p in profile_orig_dir.glob("*.json"):
            m = pat.match(p.name)
            if not m:
                continue
            player_id = m.group(1)
            ck_base = f"profile|{category}|player:{player_id}"
            ck_scrape = f"{ck_base}|scrape"
            if not checkpoint.is_done(ck_scrape):
                checkpoint.mark_done(ck_scrape, meta={"bootstrapped_from": str(p)})


def load_player_file(player_file: str) -> list[dict[str, Any]]:
    """Load player_id,player_name from CSV-like file."""
    players = []
    path = Path(player_file)
    if not path.exists():
        raise FileNotFoundError(f"Player file not found: {player_file}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(",")
        if len(parts) >= 2:
            players.append({
                "player_id": parts[0].strip(),
                "player_name": parts[1].strip(),
            })
    return players


def run(args: argparse.Namespace) -> int:
    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    profile_dir = Path(args.profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建 orig 子目录
    profile_orig_dir = profile_dir / "orig"
    profile_orig_dir.mkdir(parents=True, exist_ok=True)

    avatar_dir = Path(args.avatar_dir)
    avatar_dir.mkdir(parents=True, exist_ok=True)

    output_path = Path(args.output) if args.output else Path(f"data/{args.category}_top{args.top}.json")
    checkpoint = CheckpointStore(Path(args.checkpoint))
    if getattr(args, "rebuild_checkpoint", False):
        checkpoint.reset()
    _bootstrap_profiles_checkpoint_from_orig(checkpoint, args.category, profile_orig_dir)

    delay_cfg = DelayConfig(
        min_request_sec=2.0,
        max_request_sec=5.0,
        min_player_gap_sec=2.0,
        max_player_gap_sec=5.0,
    )

    country_rev_map: dict[str, str] = {}
    country_map_path = Path(__file__).resolve().parent / "data" / "country_code_map.json"
    if country_map_path.exists():
        raw = json.loads(country_map_path.read_text(encoding="utf-8"))
        for code, entry in raw.items():
            en = normalize_country_name(entry.get("country_en", ""))
            if en:
                country_rev_map[en] = code

    player_id_arg = getattr(args, "player_id", None)
    player_name_arg = getattr(args, "player_name", None)
    player_file_arg = getattr(args, "player_file", None)
    direct_player_mode = bool(player_id_arg and player_name_arg)
    player_file_mode = bool(player_file_arg)

    if player_file_mode:
        players_from_file = load_player_file(player_file_arg)
        logger.info("Loaded %d players from file: %s", len(players_from_file), player_file_arg)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Please install Playwright first: pip install playwright && playwright install")
        return 2

    target_url = RANKING_URLS[args.category]

    with sync_playwright() as p:
        try:
            via_cdp, browser, context, page = open_browser_page(
                p,
                use_cdp=True,
                cdp_port=int(getattr(args, "cdp_port", 9222)),
                cdp_only=bool(getattr(args, "cdp_only", False)),
                launch_kwargs={"headless": args.headless, "slow_mo": args.slow_mo},
                context_kwargs={},
                log_prefix="profiles",
            )
        except RuntimeError as exc:
            logger.error("%s", exc)
            return 6

        try:
            if direct_player_mode:
                profile_url = f"{BASE_URL}/index.php/player-profile/list/60?resetfilters=1&vw_profiles___player_id_raw={player_id_arg}&vw_profiles___Name_raw={urllib.parse.quote(player_name_arg)}"
                player_info = {
                    "player_id": player_id_arg,
                    "name": player_name_arg,
                    "english_name": player_name_arg,
                    "profile_url": profile_url,
                }
                logger.info("Direct player mode: scraping %s (id=%s)", player_name_arg, player_id_arg)
                profile_data, scraped_now = scrape_player_profile(
                    page,
                    profile_url,
                    player_info,
                    delay_cfg,
                    profile_orig_dir,
                    avatar_dir,
                    checkpoint=checkpoint,
                    category=args.category,
                    resume=bool(args.resume),
                    country_rev_map=country_rev_map,
                )
                if profile_data is None:
                    logger.error("Profile scrape failed: %s", player_name_arg)
                    close_browser_page(via_cdp, browser, page)
                    return 4
                rankings = [player_info]
                week, update_date = "", ""
            elif player_file_mode:
                logger.info("Batch player-file mode: scraping %d players...", len(players_from_file))
                for idx, pf in enumerate(players_from_file):
                    pid = pf.get("player_id")
                    pname = pf.get("player_name")
                    profile_url = f"{BASE_URL}/index.php/player-profile/list/60?resetfilters=1&vw_profiles___player_id_raw={pid}&vw_profiles___Name_raw={urllib.parse.quote(pname)}"
                    player_info = {
                        "player_id": pid,
                        "name": pname,
                        "english_name": pname,
                        "profile_url": profile_url,
                    }
                    logger.info("[%d/%d] Batch scraping: %s (id=%s)", idx + 1, len(players_from_file), pname, pid)
                    profile_data, scraped_now = scrape_player_profile(
                        page,
                        profile_url,
                        player_info,
                        delay_cfg,
                        profile_orig_dir,
                        avatar_dir,
                        checkpoint=checkpoint,
                        category=args.category,
                        resume=bool(args.resume),
                        country_rev_map=country_rev_map,
                    )
                    if profile_data is None:
                        logger.error("Profile scrape failed: %s", pname)
                        close_browser_page(via_cdp, browser, page)
                        return 4
                    if scraped_now and idx < len(players_from_file) - 1:
                        human_sleep(delay_cfg.min_player_gap_sec, delay_cfg.max_player_gap_sec, "between player profiles")
                rankings = players_from_file
                week, update_date = "", ""
            else:
                open_page_with_verification(page, target_url, delay_cfg, f"open ranking page: {args.category}")

                table_count = page.locator("table").count()
                if table_count == 0:
                    logger.error("No table found on ranking page: %s", target_url)
                    close_browser_page(via_cdp, browser, page)
                    return 3

                html = page.content()
                snapshot_path = snapshot_dir / f"{args.category}.html"
                snapshot_path.write_text(html, encoding="utf-8", newline="")
                logger.info("Saved ranking snapshot: %s", snapshot_path)

                rankings = parse_ranking_rows(page, args.top, None, translate_names=False)
                if not rankings:
                    logger.error("Parsed 0 ranking rows from page: %s", target_url)
                    close_browser_page(via_cdp, browser, page)
                    return 5

                # Scrape player profiles (always enabled)
                logger.info("Starting profile scraping for %d players...", len(rankings))
                for idx, player in enumerate(rankings):
                    if player.get("profile_url"):
                        logger.info("[%d/%d] Scraping profile: %s", idx + 1, len(rankings), player.get("english_name", player.get("name")))
                        profile_data, scraped_now = scrape_player_profile(
                            page,
                            player.get("profile_url"),
                            player,
                            delay_cfg,
                            profile_orig_dir,
                            avatar_dir,
                            checkpoint=checkpoint,
                            category=args.category,
                            resume=bool(args.resume),
                            country_rev_map=country_rev_map,
                        )
                        if profile_data is None:
                            logger.error("Profile scrape failed: %s", player.get("english_name", player.get("name")))
                            close_browser_page(via_cdp, browser, page)
                            return 4
                        # Delay between players to avoid rate limiting
                        if scraped_now and idx < len(rankings) - 1:
                            human_sleep(delay_cfg.min_player_gap_sec, delay_cfg.max_player_gap_sec, "between player profiles")

                week, update_date = extract_update_meta(page, args.category)
            
            if not direct_player_mode and not player_file_mode:
                payload = build_output(rankings, args.category, week, update_date)
                save_json(output_path, payload)
                logger.info("Saved ranking JSON: %s", output_path)
        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            close_browser_page(via_cdp, browser, page)
            return 4

        close_browser_page(via_cdp, browser, page)

    logger.info("Ranking scrape completed: %s rows", len(rankings))
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = run(args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
