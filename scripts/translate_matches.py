#!/usr/bin/env python3
"""
翻译脚本：将 matches_complete/orig 中的数据翻译成中文，保存到 cn 目录

使用前请在项目根目录创建 .env 文件并配置 API Key:
    MINIMAX_API_KEY=your_api_key_here

使用方法:
    python scripts/translate_matches.py              # 翻译所有文件
    python scripts/translate_matches.py --file SUN_Yingsha.json  # 仅翻译指定文件
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))

from lib.translator import Translator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
ORIG_DIR = PROJECT_ROOT / "data" / "matches_complete" / "orig"
CN_DIR = PROJECT_ROOT / "data" / "matches_complete" / "cn"


def translate_matches_data(data: dict, translator: Translator) -> dict:
    """翻译比赛数据为中文"""
    result = data.copy()
    
    # 翻译运动员姓名
    if result.get('player_name'):
        result['player_name_zh'] = translator.translate(
            result['player_name'], category='players', use_api=True
        )
    
    # 翻译国家代码
    if result.get('country_code'):
        result['country_code_zh'] = translator.translate(
            result['country_code'], category='countries', use_api=True
        )
    
    # 翻译每年的赛事数据
    if 'years' in result:
        for year, year_data in result['years'].items():
            if 'events' not in year_data:
                continue
                
            for event in year_data['events']:
                # 翻译赛事名称
                if event.get('event_name'):
                    event['event_name_zh'] = translator.translate(
                        event['event_name'], category='events', use_api=True
                    )
                
                # 翻译赛事类型
                if event.get('event_type'):
                    event['event_type_zh'] = translator.translate(
                        event['event_type'], category='events', use_api=True
                    )
                
                # 翻译比赛数据
                if 'matches' in event:
                    for match in event['matches']:
                        # 翻译阶段
                        if match.get('stage'):
                            match['stage_zh'] = translator.translate(
                                match['stage'], category='terms', use_api=True
                            )
                        
                        # 翻译轮次
                        if match.get('round'):
                            original = match['round']
                            if original.startswith('R') and original[1:].isdigit():
                                match['round_zh'] = f"第{original[1:]}轮"
                            else:
                                match['round_zh'] = translator.translate(
                                    original, category='terms', use_api=True
                                )
                        
                        # 翻译子赛事类型
                        if match.get('sub_event'):
                            sub_event_map = {
                                'WS': '女子单打', 'MS': '男子单打',
                                'WD': '女子双打', 'MD': '男子双打',
                                'XD': '混合双打', 'XT': '混合团体',
                                'WT': '女子团体', 'MT': '男子团体',
                            }
                            match['sub_event_zh'] = sub_event_map.get(
                                match['sub_event'], match['sub_event']
                            )
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='翻译 matches 数据为中文',
        epilog='请确保项目根目录的 .env 文件已配置 MINIMAX_API_KEY'
    )
    parser.add_argument('--file', type=str, help='仅翻译指定文件')
    args = parser.parse_args()
    
    if not ORIG_DIR.exists():
        logger.error(f"原始数据目录不存在: {ORIG_DIR}")
        logger.error("请先运行抓取脚本获取原始数据")
        return 1
    
    CN_DIR.mkdir(parents=True, exist_ok=True)
    
    translator = Translator()
    stats_before = translator.get_stats()
    logger.info(f"词典统计: {stats_before}")
    
    # 获取要处理的文件
    if args.file:
        files = [ORIG_DIR / args.file]
    else:
        files = list(ORIG_DIR.glob('*.json'))
    
    logger.info(f"找到 {len(files)} 个文件待翻译")
    
    success = 0
    for file_path in files:
        try:
            logger.info(f"处理: {file_path.name}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            translated = translate_matches_data(data, translator)
            
            output_path = CN_DIR / file_path.name
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(translated, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已保存: {output_path}")
            success += 1
            
        except Exception as e:
            logger.error(f"翻译失败 {file_path.name}: {e}")
    
    stats_after = translator.get_stats()
    new_entries = stats_after['total'] - stats_before['total']
    
    logger.info(f"\n翻译完成: {success}/{len(files)} 个文件")
    logger.info(f"新增词典词条: {new_entries}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
