#!/usr/bin/env python3
"""
ITTF TOP 50运动员比赛记录爬虫 - 使用浏览器自动化

功能：
- 使用Playwright浏览器自动化
- 登录ITTF账号
- 搜索TOP 50运动员的比赛记录
- 获取2024-2026年的详细比赛数据

使用方法：
    python ittf_matches_browser.py              # 运行一次抓取
    python ittf_matches_browser.py --headless   # 无头模式运行
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path

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
PLAYERS_FILE = DATA_DIR / "women_singles_top100.json"
MATCHES_DIR = DATA_DIR / "matches_full"
STATE_FILE = SCRIPT_DIR / ".ittf_matches_browser_state.json"

# ITTF官网URL
ITTF_BASE_URL = "https://results.ittf.link"
SEARCH_URL = f"{ITTF_BASE_URL}/index.php/matches/players-matches-per-event"

# 时间范围
YEAR_START = 2024
YEAR_END = 2026


def load_players():
    """加载运动员列表"""
    if not PLAYERS_FILE.exists():
        logger.error(f"找不到运动员列表文件: {PLAYERS_FILE}")
        return []
    
    with open(PLAYERS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data.get('rankings', [])[:50]


def load_state():
    """加载状态"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'processed': [], 'current_index': 0}


def save_state(state):
    """保存状态"""
    with open(STATE_FILE, 'w', newline='') as f:
        json.dump(state, f, indent=2)


def get_match_details_from_page(browser_page):
    """从当前页面提取比赛详情"""
    matches = []
    
    try:
        # 等待表格加载
        page_text = browser_page.text
        
        if 'No records' in page_text or 'Total: 0' in page_text:
            return matches
        
        # 提取表格行
        table = browser_page.query_selector('table')
        if not table:
            return matches
        
        rows = table.query_selector_all('tbody tr')
        
        for row in rows:
            cells = row.query_selector_all('td')
            if len(cells) < 6:
                continue
            
            # 提取数据
            cell_texts = [cell.text_content().strip() for cell in cells]
            
            # 检查是否是数据行
            if 'Total:' in cell_texts[0]:
                continue
            
            match_info = {
                'year': '',
                'event': '',
                'player_a': '',
                'player_b': '',
                'player_x': '',
                'player_y': '',
                'sub_event': '',
                'stage': '',
                'round': '',
                'result': '',
                'games': [],
                'winner': ''
            }
            
            # 解析表格列
            for i, text in enumerate(cell_texts):
                if i == 0 and text:
                    match_info['year'] = text
                elif i == 1 and text:
                    match_info['event'] = text
            
            # 解析比赛详情 - 检查是否是单打或双打
            if 'WS' in cell_texts or 'MS' in cell_texts:
                # 单打
                for i, text in enumerate(cell_texts):
                    if text in ['WS', 'MS']:
                        match_info['sub_event'] = text
                        if i+1 < len(cell_texts):
                            match_info['stage'] = cell_texts[i+1]
                        if i+2 < len(cell_texts):
                            match_info['round'] = cell_texts[i+2]
                        if i+3 < len(cell_texts):
                            match_info['result'] = cell_texts[i+3]
                        if i+4 < len(cell_texts):
                            games_text = cell_texts[i+4]
                            # 解析比分
                            match_info['games'] = parse_games(games_text)
                        if i+5 < len(cell_texts):
                            match_info['winner'] = cell_texts[i+5]
                        break
            else:
                # 双打或其他
                for i, text in enumerate(cell_texts):
                    if text in ['WD', 'MD', 'XD']:
                        match_info['sub_event'] = text
                        if i+1 < len(cell_texts):
                            match_info['stage'] = cell_texts[i+1]
                        if i+2 < len(cell_texts):
                            match_info['round'] = cell_texts[i+2]
                        if i+3 < len(cell_texts):
                            match_info['result'] = cell_texts[i+3]
                        if i+4 < len(cell_texts):
                            games_text = cell_texts[i+4]
                            match_info['games'] = parse_games(games_text)
                        if i+5 < len(cell_texts):
                            match_info['winner'] = cell_texts[i+5]
                        break
            
            matches.append(match_info)
    
    except Exception as e:
        logger.error(f"提取比赛详情失败: {e}")
    
    return matches


def parse_games(games_text):
    """解析比分文本"""
    games = []
    try:
        # 格式: "11:7 8:11 8:11 11:8 8:11"
        parts = games_text.split()
        for part in parts:
            if ':' in part:
                score = part.split(':')
                games.append((int(score[0]), int(score[1])))
    except:
        pass
    return games


def run_browser_scraper(username, password, headless=True):
    """使用Playwright运行浏览器爬虫"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("请安装playwright: pip install playwright && playwright install")
        return
    
    players = load_players()
    if not players:
        logger.error("没有找到运动员列表")
        return
    
    logger.info(f"找到 {len(players)} 名运动员")
    
    state = load_state()
    processed = state.get('processed', [])
    
    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        
        # 1. 登录
        logger.info("正在登录...")
        page.goto(SEARCH_URL)
        page.wait_for_load_state('networkidle')
        
        # 如果看到登录表单，则登录
        if page.query_selector('input[name="username"]'):
            page.fill('input[name="username"]', username)
            page.fill('input[name="password"]', password)
            page.click('button:has-text("Log in")')
            page.wait_for_load_state('networkidle')
            time.sleep(2)
        
        logger.info("登录完成")
        
        # 2. 处理每个运动员
        for i, player in enumerate(players):
            player_name = player.get('english_name', '')
            country_code = player.get('country_code', '')
            search_key = f"{player_name} ({country_code})"
            
            if search_key in processed:
                logger.info(f"[{i+1}/{len(players)}] 跳过已处理的: {search_key}")
                continue
            
            logger.info(f"[{i+1}/{len(players)}] 处理: {search_key}")
            
            try:
                # 搜索运动员
                page.goto(SEARCH_URL)
                page.wait_for_load_state('networkidle')
                time.sleep(1)
                
                # 输入名字触发自动完成
                search_box = page.query_selector('input[type="text"], input[name*="player"]')
                if search_box:
                    search_box.click()
                    search_box.fill(player_name[:10])  # 输入前10个字符
                    time.sleep(1)
                    
                    # 等待并点击自动完成选项
                    try:
                        autocomplete_item = page.wait_for_selector(
                            f'li:has-text("{player_name}")',
                            timeout=3000
                        )
                        if autocomplete_item:
                            autocomplete_item.click()
                            time.sleep(0.5)
                    except:
                        # 尝试直接输入完整名字
                        search_box.fill(search_key)
                        time.sleep(1)
                
                # 选择年份 2024
                year_select = page.query_selector('select[name*="year"], select[name*="yr"]')
                if year_select:
                    year_select.select_option(str(YEAR_START))
                
                # 点击搜索
                page.click('button:has-text("Go")')
                page.wait_for_load_state('networkidle')
                time.sleep(1)
                
                # 获取赛事列表
                player_matches = {
                    'player_id': player.get('player_id', ''),
                    'name': player_name,
                    'country_code': country_code,
                    'year': YEAR_START,
                    'events': []
                }
                
                # 提取赛事数量
                page_text = page.text()
                if 'Total:' in page_text:
                    # 从表格中提取赛事
                    table = page.query_selector('table')
                    if table:
                        rows = table.query_selector_all('tbody tr')
                        for row in rows:
                            cells = row.query_selector_all('td')
                            if len(cells) >= 2:
                                match_count = cells[0].text_content().strip()
                                event_name = cells[1].text_content().strip()
                                event_type = cells[2].text_content().strip() if len(cells) > 2 else ''
                                year = cells[3].text_content().strip() if len(cells) > 3 else ''
                                
                                if match_count.isdigit() and event_name:
                                    player_matches['events'].append({
                                        'match_count': int(match_count),
                                        'event_name': event_name,
                                        'event_type': event_type,
                                        'year': year
                                    })
                
                # 保存初步结果
                if player_matches['events']:
                    safe_name = player_name.replace(' ', '_')
                    output_file = MATCHES_DIR / f"{safe_name}_{player.get('rank', 0)}_{YEAR_START}.json"
                    MATCHES_DIR.mkdir(parents=True, exist_ok=True)
                    
                    with open(output_file, 'w', encoding='utf-8', newline='') as f:
                        json.dump(player_matches, f, ensure_ascii=False, indent=2)
                    
                    logger.info(f"  ✓ 获取到 {len(player_matches['events'])} 个赛事")
                
                # 标记为已处理
                processed.append(search_key)
                state['processed'] = processed
                state['current_index'] = i + 1
                save_state(state)
                
                # 礼貌性延迟
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"处理 {search_key} 时出错: {e}")
                continue
        
        browser.close()
    
    logger.info("=" * 60)
    logger.info("抓取完成!")
    logger.info(f"数据保存在: {MATCHES_DIR}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='ITTF TOP 50运动员比赛记录爬虫')
    parser.add_argument('--username', '-u', default='flyingdolphin', help='ITTF账号')
    parser.add_argument('--password', '-p', default='Ss001104$', help='ITTF密码')
    parser.add_argument('--headless', action='store_true', help='无头模式运行')
    
    args = parser.parse_args()
    
    run_browser_scraper(args.username, args.password, args.headless)


if __name__ == "__main__":
    main()
