#!/usr/bin/env python3
"""
ITTF Rankings 数据抓取主入口

自动完成以下流程:
1. 抓取排名数据
2. 抓取运动员档案 (可选)
3. 保存原始数据到 orig 目录
4. 自动翻译并保存中文数据到 cn 目录

用法:
    python scripts/run_rankings.py
    python scripts/run_rankings.py --category women --top 50
    python scripts/run_rankings.py --scrape-profiles  # 同时抓取运动员档案
    python scripts/run_rankings.py --headless         # 无头模式
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from scrape_rankings import build_parser, run


def main() -> None:
    """主入口函数"""
    parser = build_parser()
    
    # 添加主入口特定的帮助信息
    parser.description = "ITTF Rankings 数据抓取主入口 (自动翻译为中文)"
    parser.epilog = """
示例:
    # 抓取女子单打前50名排名
    python run_rankings.py --category women --top 50
    
    # 抓取排名并获取运动员档案
    python run_rankings.py --category women --top 30 --scrape-profiles
    
    # 无头模式运行
    python run_rankings.py --headless --category men --top 50
    
    # 抓取所有类别
    python run_rankings.py --category women --top 50 --scrape-profiles
    python run_rankings.py --category men --top 50 --scrape-profiles

输出:
    - data/{category}_top{n}.json          # 原始排名数据
    - data/{category}_top{n}_cn.json       # 中文翻译版
    - data/player_profiles/orig/           # 原始运动员档案
    - data/player_profiles/cn/             # 中文翻译版档案
    - data/player_avatars/                 # 运动员头像
    - data/ranking_snapshots/              # HTML 快照
    - web/db/ittf_rankings.sqlite          # SQLite 数据库
"""
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("ITTF Rankings 数据抓取")
    print("=" * 60)
    print(f"类别: {args.category}")
    print(f"数量: 前 {args.top} 名")
    print(f"抓取档案: {'是' if args.scrape_profiles else '否'}")
    print(f"输出: data/{args.category}_top{args.top}.json")
    print("=" * 60)
    
    rc = run(args)
    
    if rc == 0:
        print("\n✓ 抓取完成!")
        print(f"  - 原始数据: data/{args.category}_top{args.top}.json")
        print(f"  - 中文数据: data/{args.category}_top{args.top}_cn.json")
        if args.scrape_profiles:
            print(f"  - 原始档案: data/player_profiles/orig/")
            print(f"  - 中文档案: data/player_profiles/cn/")
    else:
        print(f"\n✗ 抓取失败 (退出码: {rc})")
    
    sys.exit(rc)


if __name__ == "__main__":
    main()
