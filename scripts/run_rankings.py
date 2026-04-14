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

import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from scrape_rankings import build_parser as build_scrape_parser, run as run_scrape
from translate_rankings import run as run_translate


def main() -> None:
    """主入口函数"""
    parser = build_scrape_parser()

    parser.description = "ITTF 排名数据完整流程主入口 (Women's Singles)"
    parser.epilog = """
示例:
    # 抓取并翻译 Women's Singles 前100名排名 + points breakdown
    python run_rankings.py --top 100

    # 无头模式，只抓前10名（测试用）
    python run_rankings.py --top 10 --headless

    # 忽略 checkpoint，强制重新抓取
    python run_rankings.py --force

    # 使用 CDP 模式连接已有 Chrome
    python run_rankings.py --cdp-port 9222 --top 100

    # 指定输出目录
    python run_rankings.py --output-dir data/rankings/orig

输出:
    - data/rankings/orig/women_singles_top{N}_week{W}.json
    - data/rankings/cn/women_singles_top{N}_week{W}.json
"""

    args = parser.parse_args()

    print("=" * 60)
    print("ITTF 排名数据完整流程 (Women's Singles)")
    print("=" * 60)
    print(f"数量: 前 {args.top} 名")
    print(f"输出: {args.output_dir}/")
    print(f"CDP 端口: {args.cdp_port}")
    print(f"Checkpoint: {args.checkpoint}")
    print(f"强制重抓: {'是' if args.force else '否'}")
    print("阶段: scrape -> translate")
    print("=" * 60)

    rc = run_scrape(args)
    if rc == 0:
        translate_args = argparse.Namespace(
            file=None,
            orig_dir=str(Path(args.output_dir)),
            cn_dir="data/rankings/cn",
            dict_path=str(Path("scripts/data/translation_dict_v2.json")),
            force=bool(args.force),
        )
        rc = run_translate(translate_args)

    if rc == 0:
        print(f"\n✓ 完整流程完成!")
        print(f"  - 原始数据: {args.output_dir}/")
        print("  - 中文数据: data/rankings/cn/")
    else:
        print(f"\n✗ 流程失败 (退出码: {rc})")

    sys.exit(rc)


if __name__ == "__main__":
    main()
