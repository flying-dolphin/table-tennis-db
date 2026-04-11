#!/usr/bin/env python3
"""
翻译脚本：将 player_profiles/orig 中的数据翻译成中文，保存到 cn 目录

使用前请在项目根目录创建 .env 文件并配置 API Key:
    MINIMAX_API_KEY=your_api_key_here

使用方法:
    python scripts/translate_profiles.py              # 翻译所有文件
    python scripts/translate_profiles.py --file player_xxx.json
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
ORIG_DIR = PROJECT_ROOT / "data" / "player_profiles" / "orig"
CN_DIR = PROJECT_ROOT / "data" / "player_profiles" / "cn"

# 固定术语映射
STATIC_TERMS = {
    'Female': '女', 'Male': '男',
    'Right': '右手', 'Left': '左手',
    'ShakeHand': '横拍', 'Penhold': '直拍',
    'WON': '胜', 'LOST': '负', 'DRAW': '平',
}


def translate_profile_data(data: dict, translator: Translator) -> dict:
    """翻译运动员档案为中文"""
    result = data.copy()
    
    # 翻译姓名
    if result.get('name'):
        result['name_zh'] = translator.translate(
            result['name'], category='players', use_api=True
        )
    
    # 翻译国家
    if result.get('country_code'):
        result['country_code_zh'] = translator.translate(
            result['country_code'], category='countries', use_api=True
        )
    
    # 翻译性别
    if result.get('gender'):
        result['gender_zh'] = STATIC_TERMS.get(result['gender'], result['gender'])
    
    # 翻译打法风格
    if result.get('style'):
        style = result['style']
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
        result['style_zh'] = ''.join(parts) if parts else style
    
    # 翻译持拍手
    if result.get('playing_hand'):
        result['playing_hand_zh'] = STATIC_TERMS.get(
            result['playing_hand'], result['playing_hand']
        )
    
    # 翻译握拍
    if result.get('grip'):
        result['grip_zh'] = STATIC_TERMS.get(result['grip'], result['grip'])
    
    # 翻译近期比赛
    if 'recent_matches' in result and result['recent_matches']:
        for match in result['recent_matches']:
            # 赛事
            if match.get('event'):
                match['event_zh'] = translator.translate(
                    match['event'], category='events', use_api=True
                )
            
            # 对手
            if match.get('opponent'):
                match['opponent_zh'] = translator.translate(
                    match['opponent'], category='players', use_api=True
                )
            
            # 对手国家
            if match.get('opponent_country'):
                match['opponent_country_zh'] = translator.translate(
                    match['opponent_country'], category='countries', use_api=True
                )
            
            # 阶段
            if match.get('stage'):
                parts = match['stage'].split(' - ')
                translated = []
                for part in parts:
                    part = part.strip()
                    if part.startswith('WS'):
                        translated.append('女子单打' + part[2:].strip())
                    elif part.startswith('MS'):
                        translated.append('男子单打' + part[2:].strip())
                    elif part.startswith('XD'):
                        translated.append('混合双打' + part[2:].strip())
                    elif part.startswith('WD'):
                        translated.append('女子双打' + part[2:].strip())
                    elif part.startswith('MD'):
                        translated.append('男子双打' + part[2:].strip())
                    else:
                        translated.append(translator.translate(part, category='terms', use_api=True))
                match['stage_zh'] = ' - '.join(translated)
            
            # 结果
            if match.get('result'):
                match['result_zh'] = STATIC_TERMS.get(match['result'], match['result'])
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='翻译 profiles 数据为中文',
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
        files = list(ORIG_DIR.glob('player_*.json'))
    
    logger.info(f"找到 {len(files)} 个文件待翻译")
    
    success = 0
    for file_path in files:
        try:
            logger.info(f"处理: {file_path.name}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            translated = translate_profile_data(data, translator)
            
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
    import sys
    sys.exit(main())
