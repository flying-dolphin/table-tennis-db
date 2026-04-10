#!/usr/bin/env python3
"""
ITTF TOP 50运动员比赛记录爬虫 - 简化稳定版
"""

import os
import sys
import json
import time
import logging
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
OUTPUT_DIR = DATA_DIR / "matches_complete"

# URL
BASE_URL = "https://results.ittf.link"
SEARCH_URL = f"{BASE_URL}/index.php/matches/players-matches-per-event"

# 时间范围
YEARS = [2025, 2026]


def load_players():
    """加载运动员列表"""
    if not PLAYERS_FILE.exists():
        logger.error(f"找不到文件: {PLAYERS_FILE}")
        return []
    
    with open(PLAYERS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data.get('rankings', [])[:50]


def parse_match_details(page_text):
    """解析页面中的比赛详情"""
    matches = []
    
    lines = page_text.split('\n')
    current_match = None
    
    for line in lines:
        line = line.strip()
        
        # 检测子赛事类型
        if any(x in line for x in ['WS', 'MS', 'WD', 'MD', 'XD']):
            if current_match:
                matches.append(current_match)
            
            current_match = {
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
            
            for se in ['WS', 'MS', 'WD', 'MD', 'XD']:
                if se in line:
                    current_match['sub_event'] = se
                    parts = line.split(se)
                    if len(parts) > 1:
                        rest = parts[1].strip()
                        for stage in ['Main Draw', 'Qualification', 'Qualifying']:
                            if stage in rest:
                                current_match['stage'] = stage
                                rest = rest.replace(stage, '').strip()
                                break
                        
                        import re
                        score_match = re.search(r'(\d+)\s*-\s*(\d+)', rest)
                        if score_match:
                            current_match['result'] = f"{score_match.group(1)} - {score_match.group(2)}"
                        
                        games = re.findall(r'(\d+):(\d+)', rest)
                        if games:
                            current_match['games'] = [f"{g[0]}:{g[1]}" for g in games]
                        
                        if 'Winner:' in rest:
                            winner_part = rest.split('Winner:')[-1].strip()
                            current_match['winner'] = winner_part[:50]
                    break
    
    if current_match:
        matches.append(current_match)
    
    return matches


def scrape_player_matches(page, player_name, country_code, player_id, year):
    """抓取单个运动员在指定年份的比赛记录"""
    result = {
        'year': year,
        'events': []
    }
    
    search_key = f"{player_name} ({country_code})"
    
    try:
        # 1. 导航到搜索页面
        page.goto(SEARCH_URL)
        page.wait_for_load_state('networkidle', timeout=15000)
        time.sleep(0.5)
        
        # 2. 等待并点击Matches菜单展开
        try:
            matches_menu = page.locator('button:has-text("Matches")')
            if matches_menu.count() > 0:
                matches_menu.click()
                time.sleep(0.3)
                page.locator('a:has-text("Players Matches per Event")').click()
                page.wait_for_load_state('networkidle', timeout=10000)
        except:
            pass
        
        # 3. 输入运动员名字 - 使用更精确的选择器
        try:
            # 找到搜索框 (不是登录框) - 查找页面上真正用于搜索的输入框
            search_inputs = page.locator('main input[type="text"], .content input[type="text"]')
            search_box = search_inputs.first
            
            # 确保这是搜索框而不是登录框
            parent_form = search_box.locator('xpath=ancestor::form')
            if parent_form.count() > 0:
                form_html = parent_form.first.inner_html()
                if 'username' in form_html.lower() or 'password' in form_html.lower():
                    # 这是登录表单，尝试找其他搜索框
                    all_inputs = page.locator('input[type="text"]').all()
                    for inp in all_inputs:
                        inp_html = inp.locator('xpath=ancestor::form[not(contains(@action, "login"))]').inner_html()
                        if inp_html and 'player' in inp_html.lower():
                            search_box = inp
                            break
            
            search_box.click()
            time.sleep(0.2)
            
            # 清空并输入名字
            search_box.fill('')
            for char in player_name[:8]:
                search_box.type(char)
                time.sleep(0.03)
            time.sleep(1)
            
            # 点击自动完成选项
            try:
                item = page.wait_for_selector(
                    f'li:has-text("{player_name}"):has-text("{country_code}")',
                    timeout=3000
                )
                if item:
                    item.click()
                    time.sleep(0.5)
            except:
                pass
        except Exception as e:
            logger.warning(f"  搜索框问题: {e}")
        
        # 4. 选择年份
        try:
            selects = page.locator('select')
            for sel in selects.all():
                opt_text = sel.text_content() or ''
                if '2025' in opt_text or '2024' in opt_text:
                    sel.select_option(str(year))
                    time.sleep(0.2)
                    break
        except:
            pass
        
        # 5. 点击Go按钮
        try:
            page.locator('button:has-text("Go")').click()
            page.wait_for_load_state('networkidle', timeout=10000)
            time.sleep(0.5)
        except:
            pass
        
        # 6. 检查结果
        page_text = page.content()
        
        if 'Total: 0' in page_text or 'No records' in page_text:
            logger.warning(f"  没有找到比赛记录")
            return result
        
        # 7. 提取赛事列表
        table = page.locator('table').first
        rows = table.locator('tbody tr').all()
        
        event_count = 0
        for row in rows:
            cells = row.locator('td').all()
            if len(cells) < 6:
                continue
            
            cell_texts = [cell.text_content().strip() for cell in cells]
            
            if not cell_texts[0].isdigit():
                continue
            
            match_count = int(cell_texts[0])
            event_name = cell_texts[1]
            event_type = cell_texts[2] if len(cell_texts) > 2 else ''
            event_year = cell_texts[3] if len(cell_texts) > 3 else ''
            
            # 获取链接
            match_link = cells[0].locator('a')
            href = None
            if match_link.count() > 0:
                href = match_link.get_attribute('href')
            
            event_data = {
                'match_count': match_count,
                'event_name': event_name,
                'event_type': event_type,
                'year': event_year,
                'matches': []
            }
            
            if href:
                detail_url = BASE_URL + href if href.startswith('/') else href
                page.goto(detail_url)
                page.wait_for_load_state('networkidle', timeout=10000)
                time.sleep(0.3)
                
                detail_text = page.content()
                matches = parse_match_details(detail_text)
                event_data['matches'] = matches
            
            result['events'].append(event_data)
            event_count += 1
        
        logger.info(f"  ✓ {year}年: {event_count}个赛事")
        
    except Exception as e:
        logger.error(f"  ✗ 出错: {e}")
    
    return result


def run_scraper(username, password, headless=True):
    """运行爬虫"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("请安装: pip install playwright && playwright install chromium")
        return
    
    players = load_players()
    if not players:
        return
    
    logger.info(f"运动员数量: {len(players)}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={'width': 1280, 'height': 720})
        page = context.new_page()
        
        # 确保登录
        logger.info("正在访问网站...")
        page.goto(SEARCH_URL, timeout=30000)
        page.wait_for_load_state('networkidle', timeout=15000)
        time.sleep(2)
        
        # 检查登录状态
        try:
            # 使用第一个可见的表单进行登录
            forms = page.locator('form').all()
            for form in forms:
                if form.is_visible():
                    try:
                        username_input = form.locator('input[name="username"]')
                        if username_input.count() > 0 and username_input.is_visible():
                            logger.info("需要登录...")
                            form.locator('input[name="username"]').fill(username)
                            form.locator('input[name="password"]').fill(password)
                            form.locator('button[type="submit"]').click()
                            page.wait_for_load_state('networkidle', timeout=15000)
                            time.sleep(2)
                            logger.info("登录完成")
                            break
                    except:
                        pass
        except Exception as e:
            logger.warning(f"登录检查: {e}")
        
        logger.info("开始抓取数据...")
        
        for i, player in enumerate(players):
            rank = player.get('rank', i+1)
            player_name = player.get('english_name', '')
            country_code = player.get('country_code', '')
            player_id = player.get('player_id', '')
            
            if not player_name:
                continue
            
            logger.info(f"\n[{i+1}/{len(players)}] {player_name} ({country_code})")
            
            player_data = {
                'player_id': player_id,
                'player_name': player_name,
                'country_code': country_code,
                'rank': rank,
                'years': {}
            }
            
            for year in YEARS:
                year_data = scrape_player_matches(page, player_name, country_code, player_id, year)
                if year_data['events']:
                    player_data['years'][year] = year_data['events']
                time.sleep(0.5)
            
            if player_data['years']:
                safe_name = player_name.replace(' ', '_')
                output_file = OUTPUT_DIR / f"{safe_name}_{rank}.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(player_data, f, ensure_ascii=False, indent=2)
                logger.info(f"  → 已保存")
            
            time.sleep(1)
        
        browser.close()
    
    logger.info("\n" + "=" * 60)
    logger.info(f"抓取完成!")
    logger.info(f"数据目录: {OUTPUT_DIR}")
    logger.info("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--username', default='flyingdolphin')
    parser.add_argument('-p', '--password', default='Ss001104$')
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args()
    
    run_scraper(args.username, args.password, args.headless)
