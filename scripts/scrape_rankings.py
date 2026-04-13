#!/usr/bin/env python3
"""
ITTF ranking scraper based on the shared Playwright utilities.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.anti_bot import DelayConfig, RiskControlTriggered, human_sleep
from lib.capture import save_json, sanitize_filename
from lib.page_ops import guarded_goto
from lib.translator import Translator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_ranking_scraper")

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
    parser = argparse.ArgumentParser(description="ITTF ranking scraper")
    parser.add_argument("--category", choices=sorted(RANKING_URLS.keys()), default="women")
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--snapshot-dir", default="data/ranking_snapshots")
    parser.add_argument("--profile-dir", default="data/player_profiles")
    parser.add_argument("--avatar-dir", default="data/player_avatars")
    parser.add_argument("--db-path", default="web/db/ittf_rankings.sqlite")
    parser.add_argument("--scrape-profiles", action="store_true", help="Scrape individual player profiles")
    parser.add_argument("--output", default=None)
    parser.add_argument("--no-translate", action="store_true", help="Skip translation, save only original data")
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


def parse_ranking_rows(page: Any, top_n: int, translator: Translator | None = None, translate_names: bool = True) -> list[dict[str, Any]]:
    rankings: list[dict[str, Any]] = []
    target_table = page.locator("table#list_58_com_fabrik_58")
    if target_table.count() == 0:
        target_table = page.locator("table")
    if target_table.count() == 0:
        return rankings

    rows = target_table.first.locator("tbody tr")
    row_count = rows.count()

    for idx in range(row_count):
        row = rows.nth(idx)
        cells = row.locator("td")
        cell_count = cells.count()
        if cell_count < 8:
            continue

        cell_texts = [normalize_space(cells.nth(i).inner_text()) for i in range(cell_count)]
        rank = parse_int(cell_texts[1] if len(cell_texts) > 1 else "", default=-1)
        if rank <= 0:
            continue

        change = parse_int(cell_texts[2] if len(cell_texts) > 2 else "0")
        points = parse_int(cell_texts[3] if len(cell_texts) > 3 else "0")
        english_name = normalize_space(cell_texts[4] if len(cell_texts) > 4 else "")
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
                translated = translator.translate(english_name, category='players', use_api=False)
                if translated != english_name:  # 词典命中
                    display_name = translated
            country_name = translate_country(country_code, association)
            continent_name = translate_continent(continent_raw, continent_raw)
        else:
            # 无翻译模式：保持原始英文
            display_name = english_name
            country_name = country_code or association
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

        if len(rankings) >= top_n:
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


def init_player_profiles_table(db_path: Path) -> None:
    """Initialize or migrate player_profiles table."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT UNIQUE NOT NULL,
            player_external_id TEXT,
            name TEXT NOT NULL,
            english_name TEXT,
            country TEXT,
            country_code TEXT,
            gender TEXT,
            birth_year INTEGER,
            age INTEGER,
            playing_hand TEXT,
            grip TEXT,
            current_rank INTEGER,
            ranking_week TEXT,
            career_best_rank INTEGER,
            career_best_week TEXT,
            career_stats JSON,
            current_year_stats JSON,
            recent_matches JSON,
            avatar_url TEXT,
            avatar_file_path TEXT,
            profile_data JSON,
            profile_url TEXT,
            json_file_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(player_profiles)")}
    required_cols = {
        "gender": "TEXT",
        "birth_year": "INTEGER",
        "age": "INTEGER",
        "current_rank": "INTEGER",
        "ranking_week": "TEXT",
        "career_best_rank": "INTEGER",
        "career_best_week": "TEXT",
        "career_stats": "JSON",
        "current_year_stats": "JSON",
        "recent_matches": "JSON",
        "avatar_url": "TEXT",
        "avatar_file_path": "TEXT",
    }
    for col, col_type in required_cols.items():
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE player_profiles ADD COLUMN {col} {col_type}")
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_player_profiles_player_id 
        ON player_profiles(player_id)
    """)
    conn.commit()
    conn.close()


def save_player_profile_to_db(
    db_path: Path,
    player_id: str,
    profile_data: dict[str, Any],
    json_file_path: str
) -> None:
    """Save player profile to SQLite database."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            INSERT INTO player_profiles (
                player_id, player_external_id, name, english_name, country,
                country_code, gender, birth_year, age, playing_hand, grip,
                current_rank, ranking_week, career_best_rank, career_best_week,
                career_stats, current_year_stats, recent_matches, avatar_url,
                avatar_file_path, profile_data, profile_url, json_file_path, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                name = excluded.name,
                english_name = excluded.english_name,
                country = excluded.country,
                country_code = excluded.country_code,
                gender = excluded.gender,
                birth_year = excluded.birth_year,
                age = excluded.age,
                playing_hand = excluded.playing_hand,
                grip = excluded.grip,
                current_rank = excluded.current_rank,
                ranking_week = excluded.ranking_week,
                career_best_rank = excluded.career_best_rank,
                career_best_week = excluded.career_best_week,
                career_stats = excluded.career_stats,
                current_year_stats = excluded.current_year_stats,
                recent_matches = excluded.recent_matches,
                avatar_url = excluded.avatar_url,
                avatar_file_path = excluded.avatar_file_path,
                profile_data = excluded.profile_data,
                profile_url = excluded.profile_url,
                json_file_path = excluded.json_file_path,
                updated_at = excluded.updated_at
        """, (
            player_id,
            profile_data.get("player_id"),
            profile_data.get("name", ""),
            profile_data.get("english_name", ""),
            profile_data.get("country", ""),
            profile_data.get("country_code", ""),
            profile_data.get("gender"),
            profile_data.get("birth_year"),
            profile_data.get("age"),
            profile_data.get("playing_hand"),
            profile_data.get("grip"),
            profile_data.get("current_rank"),
            profile_data.get("ranking_week"),
            profile_data.get("career_best_rank"),
            profile_data.get("career_best_week"),
            json.dumps(profile_data.get("career_stats"), ensure_ascii=False) if profile_data.get("career_stats") else None,
            json.dumps(profile_data.get("current_year_stats"), ensure_ascii=False) if profile_data.get("current_year_stats") else None,
            json.dumps(profile_data.get("recent_matches"), ensure_ascii=False) if profile_data.get("recent_matches") else None,
            profile_data.get("avatar_url"),
            profile_data.get("avatar_file_path"),
            json.dumps(profile_data, ensure_ascii=False),
            profile_data.get("profile_url"),
            json_file_path,
            datetime.now().isoformat()
        ))
        conn.commit()
    finally:
        conn.close()


def scrape_player_profile(
    page: Any,
    profile_url: str,
    player_info: dict[str, Any],
    delay_cfg: DelayConfig,
    profile_orig_dir: Path,
    profile_cn_dir: Path,
    avatar_dir: Path,
    db_path: Path,
    translator: Translator,
) -> dict[str, Any] | None:
    """Scrape player profile page and save to JSON (orig + cn) and DB."""
    if not profile_url:
        return None

    player_id = player_info.get("player_id")
    if not player_id:
        return None

    try:
        # Navigate to profile page
        guarded_goto(page, profile_url, delay_cfg, f"open profile: {player_info.get('name', player_id)}")

        # Wait for content to load
        page.wait_for_load_state("networkidle", timeout=10000)
        human_sleep(1.0, 2.0, "let profile page settle")

        # Extract profile information
        profile_data = extract_profile_info(page, player_info, profile_url)
        avatar_meta = download_player_avatar(page, player_info, avatar_dir)
        if avatar_meta:
            profile_data.update(avatar_meta)

        # Save original (English) profile to orig directory
        safe_name = sanitize_filename(player_info.get("english_name", player_info.get("name", player_id)))
        json_filename = f"player_{player_id}_{safe_name}.json"
        orig_path = profile_orig_dir / json_filename
        save_json(orig_path, profile_data)
        logger.info("Saved original profile: %s", orig_path)

        # Translate and save Chinese version to cn directory
        profile_cn = translate_profile_data(profile_data, translator)
        cn_path = profile_cn_dir / json_filename
        save_json(cn_path, profile_cn)
        logger.info("Saved Chinese profile: %s", cn_path)

        # Save to database (use original data)
        save_player_profile_to_db(db_path, player_id, profile_data, str(orig_path))
        logger.info("Saved player profile to DB: %s", player_id)

        return profile_data

    except Exception as exc:
        logger.warning("Failed to scrape profile for %s: %s", player_id, exc)
        return None


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


def extract_profile_info(page: Any, player_info: dict[str, Any], profile_url: str) -> dict[str, Any]:
    """Extract detailed profile information from player page."""
    profile_data: dict[str, Any] = {
        "player_id": player_info.get("player_id"),
        "name": player_info.get("name", ""),
        "english_name": player_info.get("english_name", ""),
        "country": player_info.get("country", ""),
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
                        profile_cell_text = normalize_space(cells.nth(2).inner_text())
                        career_cell_text = normalize_space(cells.nth(3).inner_text())
                        current_year_cell_text = normalize_space(cells.nth(4).inner_text())
                        break

        text_content = profile_cell_text or main_content

        profile_lines = [normalize_space(line) for line in profile_cell_text.splitlines() if normalize_space(line)]
        if profile_lines:
            first_line = profile_lines[0]
            if re.fullmatch(r'[A-Z ]+', first_line):
                profile_data["country_en"] = first_line.strip()

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

        career_best_match = re.search(r'Career Best\*\*:\s*(\d+)\s*\|\s*Week:\s*([^\n]+)', text_content)
        if career_best_match:
            profile_data["career_best_rank"] = int(career_best_match.group(1))
            profile_data["career_best_week"] = career_best_match.group(2).strip()

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


def translate_profile_data(profile_data: dict[str, Any], translator: Translator) -> dict[str, Any]:
    """翻译运动员档案数据为中文"""
    data = profile_data.copy()
    
    # 翻译运动员姓名
    if 'name' in data and data['name']:
        data['name_zh'] = translator.translate(data['name'], category='players', use_api=True)
    
    # 翻译国家代码
    if 'country_code' in data and data['country_code']:
        data['country_code_zh'] = translator.translate(data['country_code'], category='locations', use_api=True)
    
    # 翻译性别
    if 'gender' in data and data['gender']:
        gender_map = {'Female': '女', 'Male': '男'}
        data['gender_zh'] = gender_map.get(data['gender'], data['gender'])
    
    # 翻译打法风格
    if 'style' in data and data['style']:
        style = data['style']
        parts = []
        if 'right' in style.lower():
            parts.append('右手')
        elif 'left' in style.lower():
            parts.append('左手')
        if 'attack' in style.lower():
            parts.append('进攻型')
        elif 'defense' in style.lower():
            parts.append('防守型')
        elif 'all-round' in style.lower():
            parts.append('全面型')
        if 'shakehand' in style.lower():
            parts.append('(横拍)')
        elif 'penhold' in style.lower():
            parts.append('(直拍)')
        data['style_zh'] = ''.join(parts) if parts else style
    
    # 翻译持拍手
    if 'playing_hand' in data and data['playing_hand']:
        hand_map = {'Right': '右手', 'Left': '左手'}
        data['playing_hand_zh'] = hand_map.get(data['playing_hand'], data['playing_hand'])
    
    # 翻译握拍方式
    if 'grip' in data and data['grip']:
        grip_map = {'ShakeHand': '横拍', 'Penhold': '直拍'}
        data['grip_zh'] = grip_map.get(data['grip'], data['grip'])
    
    # 翻译近期比赛
    if 'recent_matches' in data and data['recent_matches']:
        for match in data['recent_matches']:
            # 翻译赛事名称
            if 'event' in match and match['event']:
                match['event_zh'] = translator.translate(match['event'], category='events', use_api=True)
            
            # 翻译对手姓名
            if 'opponent' in match and match['opponent']:
                match['opponent_zh'] = translator.translate(match['opponent'], category='players', use_api=True)
            
            # 翻译对手国家
            if 'opponent_country' in match and match['opponent_country']:
                match['opponent_country_zh'] = translator.translate(match['opponent_country'], category='locations', use_api=True)
            
            # 翻译比赛阶段
            if 'stage' in match and match['stage']:
                stage = match['stage']
                parts = stage.split(' - ')
                translated_parts = []
                for part in parts:
                    part = part.strip()
                    if part.startswith('WS'):
                        translated_parts.append('女子单打' + part[2:].strip())
                    elif part.startswith('MS'):
                        translated_parts.append('男子单打' + part[2:].strip())
                    elif part.startswith('XD'):
                        translated_parts.append('混合双打' + part[2:].strip())
                    elif part.startswith('WD'):
                        translated_parts.append('女子双打' + part[2:].strip())
                    elif part.startswith('MD'):
                        translated_parts.append('男子双打' + part[2:].strip())
                    else:
                        translated_parts.append(translator.translate(part, category='terms', use_api=True))
                match['stage_zh'] = ' - '.join(translated_parts)
            
            # 翻译结果
            if 'result' in match and match['result']:
                result_map = {'WON': '胜', 'LOST': '负', 'DRAW': '平'}
                match['result_zh'] = result_map.get(match['result'], match['result'])
    
    return data


def translate_ranking_data(ranking_data: dict[str, Any], translator: Translator) -> dict[str, Any]:
    """翻译排名数据为中文"""
    data = ranking_data.copy()
    
    # 翻译每个排名条目
    if 'rankings' in data and data['rankings']:
        for player in data['rankings']:
            # 翻译姓名
            if 'name' in player and player['name']:
                player['name_zh'] = translator.translate(player['name'], category='players', use_api=True)
            
            # 翻译国家代码（如果country是英文）
            if 'country_code' in player and player['country_code']:
                player['country_code_zh'] = translator.translate(player['country_code'], category='locations', use_api=True)
    
    return data


def run(args: argparse.Namespace) -> int:
    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    profile_dir = Path(args.profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建 orig 和 cn 子目录
    profile_orig_dir = profile_dir / "orig"
    profile_cn_dir = profile_dir / "cn"
    profile_orig_dir.mkdir(parents=True, exist_ok=True)
    profile_cn_dir.mkdir(parents=True, exist_ok=True)

    avatar_dir = Path(args.avatar_dir)
    avatar_dir.mkdir(parents=True, exist_ok=True)

    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_player_profiles_table(db_path)

    output_path = Path(args.output) if args.output else Path(f"data/{args.category}_top{args.top}.json")
    output_cn_path = output_path.with_suffix('').with_name(output_path.stem + "_cn").with_suffix('.json')
    
    # 初始化翻译器
    translator = Translator()

    delay_cfg = DelayConfig(
        min_request_sec=3.0,
        max_request_sec=8.0,
        min_player_gap_sec=5.0,
        max_player_gap_sec=10.0,
    )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Please install Playwright first: pip install playwright && playwright install")
        return 2

    target_url = RANKING_URLS[args.category]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slow_mo)
        context = browser.new_context()
        page = context.new_page()

        try:
            guarded_goto(page, target_url, delay_cfg, f"open ranking page: {args.category}")

            table_count = page.locator("table").count()
            if table_count == 0:
                logger.error("No table found on ranking page: %s", target_url)
                browser.close()
                return 3

            html = page.content()
            snapshot_path = snapshot_dir / f"{args.category}.html"
            snapshot_path.write_text(html, encoding="utf-8")
            logger.info("Saved ranking snapshot: %s", snapshot_path)

            rankings = parse_ranking_rows(page, args.top, translator, translate_names=not args.no_translate)
            if not rankings:
                logger.error("Parsed 0 ranking rows from page: %s", target_url)
                browser.close()
                return 5

            # Scrape player profiles if enabled
            if args.scrape_profiles:
                logger.info("Starting profile scraping for %d players...", len(rankings))
                for idx, player in enumerate(rankings):
                    if player.get("profile_url"):
                        logger.info("[%d/%d] Scraping profile: %s", idx + 1, len(rankings), player.get("english_name", player.get("name")))
                        scrape_player_profile(
                            page,
                            player.get("profile_url"),
                            player,
                            delay_cfg,
                            profile_orig_dir,
                            profile_cn_dir,
                            avatar_dir,
                            db_path,
                            translator,
                        )
                        # Delay between players to avoid rate limiting
                        if idx < len(rankings) - 1:
                            human_sleep(delay_cfg.min_player_gap_sec, delay_cfg.max_player_gap_sec, "between player profiles")

            week, update_date = extract_update_meta(page, args.category)
            payload = build_output(rankings, args.category, week, update_date)
            
            # Save original ranking
            save_json(output_path, payload)
            logger.info("Saved ranking JSON: %s", output_path)
            
            # Translate and save Chinese version (unless disabled)
            if not args.no_translate:
                payload_cn = translate_ranking_data(payload, translator)
                save_json(output_cn_path, payload_cn)
                logger.info("Saved Chinese ranking JSON: %s", output_cn_path)
            else:
                logger.info("Translation skipped ( --no-translate )")
        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            browser.close()
            return 4

        browser.close()

    logger.info("Ranking scrape completed: %s rows", len(rankings))
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = run(args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
