#!/usr/bin/env python3
"""
ITTF TOP 50运动员比赛记录爬虫
手动模式 - 需要用户在浏览器中完成登录和数据获取
"""

import os
import json
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = Path('/Users/wangsili/.openclaw/workspace/agents/daily-shasha/ittf_rankings/data')
PLAYERS_FILE = DATA_DIR / 'women_singles_top100.json'
OUTPUT_DIR = DATA_DIR / 'matches_complete'

YEARS = [2025, 2026]

def load_players():
    with open(PLAYERS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('rankings', [])[:50]

def main():
    players = load_players()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"加载了 {len(players)} 名运动员")
    logger.info(f"目标年份: {YEARS}")
    logger.info(f"数据将保存到: {OUTPUT_DIR}")
    
    # 打印前10个运动员供确认
    logger.info("\n前10名运动员:")
    for i, p in enumerate(players[:10]):
        logger.info(f"  {i+1}. {p.get('english_name', '')} ({p.get('country_code', '')})")

    logger.info("\n请在浏览器中手动执行以下操作:")
    logger.info("1. 打开 https://results.ittf.link/index.php/matches/players-matches-per-event")
    logger.info("2. 使用账号 flyingdolphin 登录")
    logger.info("3. 对每个运动员进行搜索并获取赛事列表")
    logger.info("4. 点击每个赛事获取详细比赛数据")
    logger.info("5. 将获取的数据保存到对应的JSON文件")

if __name__ == "__main__":
    main()
