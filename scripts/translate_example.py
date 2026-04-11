#!/usr/bin/env python3
"""
翻译模块使用示例

演示如何使用 lib/translator 模块翻译：
1. 运动员人名
2. 赛事名称
3. 术语
4. 完整文档

使用方法：
    python translate_example.py
    python translate_example.py --api-key YOUR_KEY
    python translate_example.py --batch-test
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

# 添加项目根目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent))

from lib.translator import Translator, quick_translate

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def demo_basic_translation(api_key: str | None = None):
    """基础翻译演示 - 查词典"""
    print("\n" + "=" * 60)
    print("演示1: 基础翻译（优先查词典）")
    print("=" * 60)
    
    translator = Translator(api_key=api_key)
    
    # 这些应该在词典中有预定义
    test_names = [
        ("Ma Long", "players"),
        ("Sun Yingsha", "players"),
        ("Harimoto Tomokazu", "players"),
        ("World Championships", "events"),
        ("Round of 16", "terms"),
        ("CHN", "countries"),
    ]
    
    print("\n从词典翻译（无需API调用）:\n")
    for text, category in test_names:
        result = translator.translate(text, category=category, use_api=False)
        source = "词典" if result != text else "未命中"
        print(f"  [{category:12s}] {text:20s} -> {result:20s} ({source})")
    
    # 显示词典统计
    stats = translator.get_stats()
    print(f"\n词典统计: {stats}")


def demo_api_translation(api_key: str | None = None):
    """API翻译演示 - 新词汇"""
    if not api_key:
        print("\n未提供API Key，跳过API翻译演示")
        return
    
    print("\n" + "=" * 60)
    print("演示2: API翻译（词典未命中的新词汇）")
    print("=" * 60)
    
    translator = Translator(api_key=api_key)
    
    # 一些可能不在词典中的名字
    new_names = [
        ("Alexis Lebrun", "players"),
        ("Truls Moregard", "players"),
    ]
    
    print("\n新词汇翻译（需要API调用）:\n")
    for text, category in new_names:
        # 第一次调用会走API
        result = translator.translate(text, category=category, use_api=True)
        print(f"  [{category:12s}] {text:20s} -> {result}")
    
    # 再次翻译同一名称（应该从缓存/词典中读取）
    print("\n再次翻译（应从缓存读取）:\n")
    for text, category in new_names:
        result = translator.translate(text, category=category, use_api=True)
        print(f"  [{category:12s}] {text:20s} -> {result}")
    
    # 显示更新后的词典统计
    stats = translator.get_stats()
    print(f"\n词典统计: {stats}")


def demo_batch_translation(api_key: str | None = None):
    """批量翻译演示"""
    print("\n" + "=" * 60)
    print("演示3: 批量翻译")
    print("=" * 60)
    
    translator = Translator(api_key=api_key)
    
    # 批量翻译运动员名
    players = ["Ma Long", "Fan Zhendong", "Sun Yingsha", "Test Player XYZ"]
    results = translator.translate_batch(players, category="players", use_api=False)
    
    print("\n批量翻译运动员:\n")
    for original, translated in results.items():
        source = "词典" if translated != original else "未命中"
        print(f"  {original:20s} -> {translated:20s} ({source})")
    
    # 批量翻译术语
    terms = ["Round of 32", "Quarterfinal", "Main Draw", "Unknown Term"]
    results = translator.translate_batch(terms, category="terms", use_api=False)
    
    print("\n批量翻译术语:\n")
    for original, translated in results.items():
        source = "词典" if translated != original else "未命中"
        print(f"  {original:20s} -> {translated:20s} ({source})")


def demo_document_translation(api_key: str | None = None):
    """文档翻译演示"""
    if not api_key:
        print("\n未提供API Key，跳过文档翻译演示")
        return
    
    print("\n" + "=" * 60)
    print("演示4: 文档翻译")
    print("=" * 60)
    
    translator = Translator(api_key=api_key)
    
    # 示例规则片段
    sample_doc = """
# ITTF World Ranking Regulations

## 1. General Principles
The ITTF World Ranking system is designed to reflect the relative strength of players.

## 2. Ranking Points
Players earn points based on their performance in ITTF events:
- World Championships: 2000 points for winner
- Grand Smash: 2000 points for winner
- World Cup: 1500 points for winner

## 3. Seeding
The seeding for events is based on the latest World Ranking.
    """
    
    print("\n原文片段:\n")
    print(sample_doc[:500] + "...")
    
    print("\n翻译中...")
    translated = translator.translate_document(sample_doc, doc_type="regulations")
    
    print("\n翻译结果:\n")
    print(translated[:500] + "...")


def demo_profile_translation(api_key: str | None = None):
    """运动员Profile翻译演示"""
    print("\n" + "=" * 60)
    print("演示5: 运动员Profile字段翻译")
    print("=" * 60)
    
    translator = Translator(api_key=api_key)
    
    # 模拟profile数据
    profile_fields = {
        "players": ["Player Name", "Date of Birth", "Playing Style", "Grip"],
        "terms": ["World Ranking", "Career Titles", "Wins/Losses", "Win Rate"],
        "countries": ["China", "Japan", "Germany"],
    }
    
    print("\nProfile字段翻译:\n")
    for category, fields in profile_fields.items():
        print(f"\n  [{category}]:")
        for field in fields:
            result = translator.translate(field, category=category, use_api=False)
            print(f"    {field:20s} -> {result}")


def demo_event_translation(api_key: str | None = None):
    """赛事翻译演示"""
    print("\n" + "=" * 60)
    print("演示6: 赛事名称翻译")
    print("=" * 60)
    
    translator = Translator(api_key=api_key)
    
    # 赛事名称列表
    events = [
        "World Championships",
        "Grand Smash",
        "World Cup",
        "Star Contenders",
        "Youth Contenders",
        "Some Unknown Event 2024",
    ]
    
    print("\n赛事名称翻译:\n")
    for event in events:
        result = translator.translate(event, category="events", use_api=False)
        source = "词典" if result != event else "未命中(可调用API)"
        print(f"  {event:30s} -> {result:30s} ({source})")


def main():
    parser = argparse.ArgumentParser(
        description='翻译模块使用示例',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    %(prog)s                           # 运行所有演示（不使用API）
    %(prog)s --api-key YOUR_KEY        # 运行所有演示（包括API翻译）
    %(prog)s --basic                   # 仅运行基础翻译演示
    %(prog)s --batch-test              # 运行批量翻译测试
        """
    )
    parser.add_argument('--api-key', type=str, default=os.environ.get('MINIMAX_API_KEY'),
                        help='MiniMax API密钥')
    parser.add_argument('--basic', action='store_true',
                        help='仅运行基础翻译演示')
    parser.add_argument('--batch-test', action='store_true',
                        help='运行批量翻译测试')
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("ITTF 翻译模块使用示例")
    print("=" * 60)
    
    if args.batch_test:
        demo_batch_translation(args.api_key)
    elif args.basic:
        demo_basic_translation(args.api_key)
    else:
        # 运行所有演示
        demo_basic_translation(args.api_key)
        demo_api_translation(args.api_key)
        demo_batch_translation(args.api_key)
        demo_profile_translation(args.api_key)
        demo_event_translation(args.api_key)
        demo_document_translation(args.api_key)
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
