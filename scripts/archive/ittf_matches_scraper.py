#!/usr/bin/env python3
"""
ITTF TOP 50运动员比赛记录爬虫

功能：
- 获取女子单打排名前50的运动员列表
- 获取每位运动员的比赛记录
- 提取比赛详情（对手、比分、结果）

使用方法：
    python ittf_matches_scraper.py              # 运行一次抓取
    python ittf_matches_scraper.py --player-id 131163 --player-name "SUN Yingsha"
"""

import os
import json
import re
import time
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 路径配置
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
PLAYERS_FILE = DATA_DIR / "top50_players.json"
MATCHES_DIR = DATA_DIR / "matches"

# ITTF官网URL
ITTF_BASE_URL = "https://results.ittf.link"
RANKINGS_URL = f"{ITTF_BASE_URL}/ittf-rankings/ittf-ranking-women-singles"
PLAYER_PROFILE_URL = f"{ITTF_BASE_URL}/index.php/player-profile/list/60"

# 时间范围
YEAR_START = 2024
YEAR_END = 2026


def get_headers():
    """获取请求头"""
    return {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }


def fetch_page(url, params=None):
    """获取网页内容"""
    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"请求失败: {url} - {e}")
        return None


def parse_rankings_page(html):
    """解析排名页面，获取TOP 50运动员列表"""
    soup = BeautifulSoup(html, 'html.parser')
    players = []
    
    table = soup.find('table')
    if not table:
        logger.error("未找到排名表格")
        return players
    
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 5:
            name_cell = cells[4] if len(cells) > 4 else None
            if name_cell:
                name_link = name_cell.find('a')
                if name_link:
                    name = name_link.get_text(strip=True)
                    href = name_link.get('href', '')
                    
                    player_id = None
                    if 'player_id_raw' in href:
                        match = re.search(r'player_id_raw=(\d+)', href)
                        if match:
                            player_id = match.group(1)
                    
                    if name and player_id:
                        assoc = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                        points = cells[3].get_text(strip=True) if len(cells) > 3 else "0"
                        
                        players.append({
                            'name': name,
                            'player_id': player_id,
                            'association': assoc,
                            'points': points,
                        })
        
        if len(players) >= 50:
            break
    
    return players


def parse_player_profile(html, player_id, player_name):
    """解析球员Profile页面，提取比赛记录"""
    soup = BeautifulSoup(html, 'html.parser')
    
    player_info = {
        'player_id': player_id,
        'name': player_name,
        'recent_matches': [],
        'wtt_results': [],
        'ittf_results': []
    }
    
    # 规范化函数
    def normalize_text(text):
        return text.replace('\xa0', ' ')
    
    # 解析近期比赛
    for p in soup.find_all('p'):
        text = normalize_text(p.get_text())
        
        if 'Recent Singles Matches:' in text:
            player_info['recent_matches'] = parse_recent_matches(text, player_name)
        
        # WTT赛事
        if 'Results in Singles Matches in WTT Events' in text:
            player_info['wtt_results'] = parse_tournament_results(text, player_name)
        
        # ITTF赛事
        if 'Results in Singles Matches in ITTF Individual Events' in text:
            player_info['ittf_results'] = parse_tournament_results(text, player_name)
    
    return player_info


def parse_recent_matches(text, player_name):
    """解析近期比赛记录"""
    matches = []
    
    # 按 "Result:" 分割
    parts = text.split('Result:')
    
    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        
        match_info = {}
        
        # 提取对手
        opponent_match = re.search(r'vs\s+(.+?)\s+\(([A-Z]{3})\)', part)
        if opponent_match:
            match_info['opponent'] = opponent_match.group(1).strip()
            match_info['opponent_country'] = opponent_match.group(2)
        else:
            continue
        
        # 提取比分
        score_match = re.search(r'(\d+)\s*-\s*(\d+)\s*\(([\d:\s]+)\)', part)
        if score_match:
            match_info['score'] = f"{score_match.group(1)}-{score_match.group(2)}"
            games_text = score_match.group(3)
            games = []
            for g in games_text.split():
                if ':' in g:
                    parts = g.split(':')
                    games.append((int(parts[0]), int(parts[1])))
            match_info['games'] = games
        else:
            match_info['score'] = ""
            match_info['games'] = []
        
        # 提取结果
        result_match = re.search(r'(WON|LOST)', part)
        match_info['result'] = result_match.group(1) if result_match else ''
        
        # 提取阶段
        for stage in ['Final', 'SemiFinal', 'QuarterFinal', 'R16', 'R32', 'R64', 'Qualification']:
            if stage in part:
                match_info['stage'] = stage
                break
        else:
            match_info['stage'] = ''
        
        # 提取赛事名 - 在对手之前
        event_match = re.search(r'(ITTF[^\n]+?)(?:\d{4}|' + player_name.replace(' ', r'\s*') + r')', part)
        if event_match:
            match_info['event'] = event_match.group(1).strip()
        else:
            match_info['event'] = ''
        
        matches.append(match_info)
    
    return matches


def parse_tournament_results(text, player_name):
    """解析赛事结果"""
    results = []
    
    # 按年份分割
    year_blocks = re.split(r'(\d{4})\s*-', text)
    
    for i in range(1, len(year_blocks), 2):
        year = int(year_blocks[i])
        block = year_blocks[i + 1] if i + 1 < len(year_blocks) else ''
        
        if year < YEAR_START or year > YEAR_END:
            continue
        
        # 分割成单条记录
        lines = block.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            result = parse_single_tournament_result(line, year, player_name)
            if result:
                results.append(result)
    
    return results


def parse_single_tournament_result(line, year, player_name):
    """解析单条赛事结果"""
    result = {
        'year': year,
        'event': '',
        'stage': '',
        'winner': '',
        'winner_country': ''
    }
    
    # 提取赛事名
    event_match = re.search(r'-\s*(.+?)\s+WS', line)
    if event_match:
        result['event'] = event_match.group(1).strip()
    
    # 提取阶段
    for stage in ['Final', 'SemiFinal', 'QuarterFinal', 'R16', 'R32', 'R64']:
        if stage in line:
            result['stage'] = stage
            break
    
    # 提取冠军
    winner_match = re.search(r'Winner:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\((\w+)\)', line)
    if winner_match:
        result['winner'] = winner_match.group(1)
        result['winner_country'] = winner_match.group(2)
    
    return result if result['event'] else None


def scrape_player_matches(player):
    """抓取单个球员的比赛记录"""
    player_id = player['player_id']
    player_name = player['name']
    
    logger.info(f"正在抓取: {player_name} ({player_id})")
    
    url = f"{PLAYER_PROFILE_URL}?resetfilters=1&vw_profiles___player_id_raw={player_id}&vw_profiles___Name_raw={quote(player_name)}"
    html = fetch_page(url)
    
    if not html:
        logger.error(f"无法获取 {player_name} 的页面")
        return None
    
    player_data = parse_player_profile(html, player_id, player_name)
    player_data['association'] = player.get('association', '')
    
    return player_data


def save_player_data(player_data):
    """保存球员数据到文件"""
    MATCHES_DIR.mkdir(parents=True, exist_ok=True)
    
    safe_name = player_data['name'].replace(' ', '_')
    filepath = MATCHES_DIR / f"{safe_name}_{player_data['player_id']}.json"
    
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        json.dump(player_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"已保存: {filepath}")


def scrape_top50():
    """抓取TOP 50运动员数据"""
    logger.info("=" * 60)
    logger.info("开始抓取ITTF女子单打TOP 50运动员比赛记录")
    logger.info("=" * 60)
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MATCHES_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info("正在获取排名页面...")
    html = fetch_page(RANKINGS_URL)
    
    if not html:
        logger.error("无法获取排名页面")
        return
    
    players = parse_rankings_page(html)
    logger.info(f"获取到 {len(players)} 名运动员")
    
    if not players:
        return
    
    with open(PLAYERS_FILE, 'w', encoding='utf-8', newline='') as f:
        json.dump(players, f, ensure_ascii=False, indent=2)
    
    # 逐个抓取
    for i, player in enumerate(players[:50], 1):
        logger.info(f"\n[{i}/50] {player['name']} ({player['association']})")
        
        try:
            player_data = scrape_player_matches(player)
            
            if player_data:
                save_player_data(player_data)
                
                recent = len(player_data.get('recent_matches', []))
                wtt = len(player_data.get('wtt_results', []))
                ittf = len(player_data.get('ittf_results', []))
                
                logger.info(f"  ✓ 近期: {recent}场 | WTT: {wtt}场 | ITTF: {ittf}场")
            
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"处理 {player['name']} 时出错: {e}")
            continue
    
    logger.info("\n" + "=" * 60)
    logger.info("抓取完成!")
    logger.info(f"数据保存在: {MATCHES_DIR}")
    logger.info("=" * 60)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='ITTF TOP 50运动员比赛记录爬虫')
    parser.add_argument('--player-id', type=str, help='指定球员ID')
    parser.add_argument('--player-name', type=str, help='指定球员名字')
    args = parser.parse_args()
    
    if args.player_id:
        player = {'player_id': args.player_id, 'name': args.player_name or 'Unknown'}
        data = scrape_player_matches(player)
        if data:
            save_player_data(data)
            print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        scrape_top50()


if __name__ == "__main__":
    main()
