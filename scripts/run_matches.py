#!/usr/bin/env python3
"""
ITTF Matches 数据抓取主入口

自动完成以下流程:
1. 根据排名列表抓取每个运动员的比赛数据
2. 保存原始数据到 data/matches_complete/orig/

用法:
    python scripts/run_matches.py
    python scripts/run_matches.py --players-file data/women_singles_top50.json --top-n 30
    python scripts/run_matches.py --players-file data/women_singles_top100.json --top-n 51-100
    python scripts/run_matches.py --from-date 2025-01-01
    python scripts/run_matches.py --player-name "SUN Yingsha" --player-country CHN
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from scrape_matches import build_parser as build_scrape_parser, run as run_scrape
from translate_matches import run as run_translate


def format_top_spec(raw: object) -> str:
    text = str(raw).strip()
    if "-" in text:
        return f"第 {text} 名"
    return f"前 {text} 名"


def main() -> None:
    """主入口函数"""
    parser = build_scrape_parser()
    
    # 更新帮助信息
    parser.description = "ITTF Matches 完整流程主入口"
    parser.epilog = """
示例:
    # 抓取并翻译前30名运动员的比赛数据
    python run_matches.py --players-file data/women_singles_top50.json --top-n 30

    # 抓取第51到100名运动员的比赛数据
    python run_matches.py --players-file data/women_singles_top100.json --top-n 51-100
    
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
    - data/matches_complete/cn/       # 中文比赛数据
    - data/raw_event_payloads/        # 原始事件数据
    - data/checkpoints/               # 检查点文件
"""
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("ITTF Matches 完整流程")
    print("=" * 60)
    print(f"运动员列表: {args.players_file}")
    print(f"抓取范围: {format_top_spec(args.top_n)}")
    print(f"起始日期: {args.from_date}")
    print("阶段: scrape -> translate")
    print("=" * 60)
    
    rc = run_scrape(args)
    if rc == 0:
        translate_args = argparse.Namespace(
            file=None,
            orig_dir=str(Path(args.output_dir) / "orig"),
            cn_dir=str(Path(args.output_dir) / "cn"),
            checkpoint="data/matches_complete/checkpoint_translate_matches.json",
            force=bool(args.force),
            rebuild_checkpoint=bool(args.rebuild_checkpoint),
        )
        rc = run_translate(translate_args)
    
    if rc == 0:
        print("\n✓ 完整流程完成!")
        print(f"  - 原始数据: data/matches_complete/orig/")
        print(f"  - 中文数据: data/matches_complete/cn/")
        print(f"  - 原始事件: data/raw_event_payloads/")
    elif rc == 3:
        print("\n⚠ 触发风控，已停止")
        print("  请稍后再试，或更换 IP/账号")
    elif rc == 4:
        print("\n✗ 流程出错")
    else:
        print(f"\n✗ 抓取失败 (退出码: {rc})")
    
    sys.exit(rc)


if __name__ == "__main__":
    main()
