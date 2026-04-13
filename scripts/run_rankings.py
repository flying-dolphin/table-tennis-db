#!/usr/bin/env python3
"""
ITTF 排名数据抓取主入口

从 https://www.ittf.com/rankings/ 抓取 Women's Singles 排名数据，
包括每个运动员的 points breakdown 明细。

用法:
    python scripts/run_rankings.py
    python scripts/run_rankings.py --top 100
    python scripts/run_rankings.py --top 10 --headless
    python scripts/run_rankings.py --force    # 忽略 checkpoint 重新抓取
"""

from __future__ import annotations

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from scrape_rankings import build_parser, run


def main() -> None:
    """主入口函数"""
    parser = build_parser()

    parser.description = "ITTF 排名数据抓取主入口 (Women's Singles)"
    parser.epilog = """
示例:
    # 抓取 Women's Singles 前100名排名 + points breakdown
    python run_rankings.py --top 100

    # 无头模式，只抓前10名（测试用）
    python run_rankings.py --top 10 --headless

    # 忽略 checkpoint，强制重新抓取
    python run_rankings.py --force

    # 指定输出目录
    python run_rankings.py --output-dir data/rankings/orig

输出:
    - data/rankings/orig/women_singles_top{N}_week{W}.json
"""

    args = parser.parse_args()

    print("=" * 60)
    print("ITTF 排名数据抓取 (Women's Singles)")
    print("=" * 60)
    print(f"数量: 前 {args.top} 名")
    print(f"输出: {args.output_dir}/")
    print(f"Checkpoint: {args.checkpoint}")
    print(f"强制重抓: {'是' if args.force else '否'}")
    print("=" * 60)

    rc = run(args)

    if rc == 0:
        print(f"\n✓ 抓取完成! 数据已保存到 {args.output_dir}/")
    else:
        print(f"\n✗ 抓取失败 (退出码: {rc})")

    sys.exit(rc)


if __name__ == "__main__":
    main()
