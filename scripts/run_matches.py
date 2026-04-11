#!/usr/bin/env python3
"""
ITTF Matches 数据抓取主入口

自动完成以下流程:
1. 根据排名列表抓取每个运动员的比赛数据
2. 保存原始数据到 data/matches_complete/orig/
3. 自动翻译并保存中文数据到 data/matches_complete/cn/

用法:
    python scripts/run_matches.py
    python scripts/run_matches.py --players-file data/women_singles_top50.json --top-n 30
    python scripts/run_matches.py --from-date 2025-01-01
    python scripts/run_matches.py --player-name "SUN Yingsha" --player-country CHN
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from scrape_matches import build_parser, run


def main() -> None:
    """主入口函数"""
    parser = build_parser()
    
    # 更新帮助信息
    parser.description = "ITTF Matches 数据抓取主入口 (自动翻译为中文)"
    parser.epilog = """
示例:
    # 抓取前30名运动员的比赛数据
    python run_matches.py --players-file data/women_singles_top50.json --top-n 30
    
    # 从指定日期开始抓取
    python run_matches.py --from-date 2025-01-01 --top-n 20
    
    # 抓取指定运动员
    python run_matches.py --player-name "SUN Yingsha" --player-country CHN
    
    # 强制重新抓取（忽略检查点）
    python run_matches.py --force --top-n 10
    
    # 使用 CDP 模式连接已有 Chrome
    python run_matches.py --cdp-port 9222 --top-n 10

输出:
    - data/matches_complete/orig/     # 原始比赛数据
    - data/matches_complete/cn/       # 中文翻译版
    - data/raw_event_payloads/        # 原始事件数据
    - data/checkpoints/               # 检查点文件
"""
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("ITTF Matches 数据抓取")
    print("=" * 60)
    print(f"运动员列表: {args.players_file}")
    print(f"抓取数量: 前 {args.top_n} 名")
    print(f"起始日期: {args.from_date}")
    print(f"输出目录: data/matches_complete/")
    print("=" * 60)
    
    rc = run(args)
    
    if rc == 0:
        print("\n✓ 抓取完成!")
        print(f"  - 原始数据: data/matches_complete/orig/")
        print(f"  - 中文数据: data/matches_complete/cn/")
        print(f"  - 原始事件: data/raw_event_payloads/")
    elif rc == 3:
        print("\n⚠ 触发风控，已停止")
        print("  请稍后再试，或更换 IP/账号")
    elif rc == 4:
        print("\n✗ 抓取出错")
    else:
        print(f"\n✗ 抓取失败 (退出码: {rc})")
    
    sys.exit(rc)


if __name__ == "__main__":
    main()
