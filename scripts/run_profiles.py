#!/usr/bin/env python3
"""
ITTF 运动员档案抓取主入口

自动完成以下流程:
1. 从排名页获取运动员列表
2. 逐个抓取运动员详情档案
3. 保存原始数据到 orig 目录
4. 自动翻译并保存中文数据到 cn 目录

用法:
    python scripts/run_profiles.py
    python scripts/run_profiles.py --category women --top 50
    python scripts/run_profiles.py --headless
"""

from __future__ import annotations

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from scrape_profiles import build_parser, run


def main() -> None:
    """主入口函数"""
    parser = build_parser()

    parser.description = "ITTF 运动员档案抓取主入口 (自动翻译为中文)"
    parser.epilog = """
示例:
    # 抓取女子单打前50名运动员档案
    python run_profiles.py --category women --top 50

    # 无头模式运行
    python run_profiles.py --headless --category women --top 50

输出:
    - data/player_profiles/orig/           # 原始运动员档案
    - data/player_profiles/cn/             # 中文翻译版档案
    - data/player_avatars/                 # 运动员头像
    - web/db/ittf_rankings.sqlite          # SQLite 数据库
"""

    args = parser.parse_args()

    print("=" * 60)
    print("ITTF 运动员档案抓取")
    print("=" * 60)
    print(f"类别: {args.category}")
    print(f"数量: 前 {args.top} 名")
    print(f"输出: data/player_profiles/orig/")
    print("=" * 60)

    rc = run(args)

    if rc == 0:
        print("\n✓ 抓取完成!")
        print(f"  - 原始档案: data/player_profiles/orig/")
        print(f"  - 中文档案: data/player_profiles/cn/")
        print(f"  - 运动员头像: data/player_avatars/")
    else:
        print(f"\n✗ 抓取失败 (退出码: {rc})")

    sys.exit(rc)


if __name__ == "__main__":
    main()
