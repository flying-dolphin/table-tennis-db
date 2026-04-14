#!/usr/bin/env python3
"""
ITTF 运动员档案抓取主入口

自动完成以下流程:
1. 从排名页获取运动员列表
2. 逐个抓取运动员详情档案
3. 保存原始数据到 orig 目录

用法:
    python scripts/run_profiles.py
    python scripts/run_profiles.py --category women --top 50
    python scripts/run_profiles.py --headless
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from scrape_profiles import build_parser as build_scrape_parser, run as run_scrape
from translate_profiles import run as run_translate


def main() -> None:
    """主入口函数"""
    parser = build_scrape_parser()

    parser.description = "ITTF 运动员档案完整流程主入口"
    parser.epilog = """
示例:
    # 抓取并翻译女子单打前50名运动员档案
    python run_profiles.py --category women --top 50

    # 无头模式运行完整流程
    python run_profiles.py --headless --category women --top 50

    # 使用 CDP 模式连接已有 Chrome
    python run_profiles.py --cdp-port 9222 --category women --top 50

输出:
    - data/player_profiles/orig/           # 原始运动员档案
    - data/player_profiles/cn/             # 中文运动员档案
    - data/player_avatars/                 # 运动员头像
    - web/db/ittf_rankings.sqlite          # SQLite 数据库
"""

    args = parser.parse_args()

    print("=" * 60)
    print("ITTF 运动员档案完整流程")
    print("=" * 60)
    print(f"类别: {args.category}")
    print(f"数量: 前 {args.top} 名")
    print(f"CDP 端口: {args.cdp_port}")
    print("阶段: scrape -> translate")
    print("=" * 60)

    rc = run_scrape(args)
    if rc == 0:
        translate_args = argparse.Namespace(
            file=None,
            orig_dir=str(Path(args.profile_dir) / "orig"),
            cn_dir=str(Path(args.profile_dir) / "cn"),
            checkpoint="data/player_profiles/checkpoint_translate_profiles.json",
            force=bool(args.force),
            rebuild_checkpoint=bool(args.rebuild_checkpoint),
        )
        rc = run_translate(translate_args)

    if rc == 0:
        print("\n✓ 完整流程完成!")
        print(f"  - 原始档案: data/player_profiles/orig/")
        print(f"  - 中文档案: data/player_profiles/cn/")
        print(f"  - 运动员头像: data/player_avatars/")
    else:
        print(f"\n✗ 流程失败 (退出码: {rc})")

    sys.exit(rc)


if __name__ == "__main__":
    main()
