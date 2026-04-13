#!/usr/bin/env python3
"""
翻译脚本：将 ranking JSON 文件翻译成中文

使用前请在项目根目录创建 .env 文件并配置 API Key:
    MINIMAX_API_KEY=your_api_key_here

使用方法:
    python scripts/translate_rankings.py --file data/women_singles_top50.json
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


def translate_ranking_data(data: dict, translator: Translator) -> dict:
    """翻译排名数据为中文"""
    result = data.copy()
    
    # 翻译每个排名条目
    if 'rankings' in result and result['rankings']:
        for player in result['rankings']:
            # 翻译姓名
            if player.get('name'):
                player['name_zh'] = translator.translate(
                    player['name'], category='players', use_api=True
                )
            
            # 翻译国家代码
            if player.get('country_code'):
                player['country_code_zh'] = translator.translate(
                    player['country_code'], category='locations', use_api=True
                )
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='翻译 ranking 数据为中文',
        epilog='请确保项目根目录的 .env 文件已配置 MINIMAX_API_KEY'
    )
    parser.add_argument('--file', type=str, required=True, help='要翻译的 ranking JSON 文件')
    args = parser.parse_args()
    
    input_path = Path(args.file)
    if not input_path.exists():
        logger.error(f"文件不存在: {input_path}")
        return 1
    
    # 输出文件名添加 _cn 后缀
    output_path = input_path.with_suffix('').with_name(
        input_path.stem + "_cn"
    ).with_suffix('.json')
    
    translator = Translator()
    stats_before = translator.get_stats()
    logger.info(f"词典统计: {stats_before}")
    
    try:
        logger.info(f"读取: {input_path}")
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        translated = translate_ranking_data(data, translator)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(translated, f, ensure_ascii=False, indent=2)
        
        logger.info(f"已保存: {output_path}")
        
    except Exception as e:
        logger.error(f"翻译失败: {e}")
        return 1
    
    stats_after = translator.get_stats()
    new_entries = stats_after['total'] - stats_before['total']
    logger.info(f"新增词典词条: {new_entries}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
