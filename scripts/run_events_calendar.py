#!/usr/bin/env python3
"""
ITTF Events Calendar 完整流程主入口
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scrape_events_calendar import scrape_events_calendar
from translate_events_calendar import run as run_translate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF Events Calendar 完整流程主入口")
    parser.add_argument("--year", "-y", type=int, required=True, help="年份（如 2026）")
    parser.add_argument("--output", "-o", type=str, default=None, help="orig 输出文件路径（默认: data/events_calendar/orig/events_calendar_{year}.json）")
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP 远程调试端口（默认: 9222）")
    parser.add_argument("--headless", action="store_true", help="无头模式运行")
    parser.add_argument("--slow-mo", type=int, default=100, help="慢动作延迟毫秒（默认: 100）")
    parser.add_argument("--force", action="store_true", help="强制重新抓取和翻译（忽略 checkpoint）")
    parser.add_argument("--rebuild-checkpoint", action="store_true", help="基于现有输出文件重建 checkpoint")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.output:
        output_dir = Path(args.output).parent
    else:
        output_dir = Path("data/events_calendar/orig")

    print("=" * 60)
    print("ITTF Events Calendar 完整流程")
    print("=" * 60)
    print(f"年份: {args.year}")
    print("阶段: scrape -> translate")
    print("=" * 60)

    if args.rebuild_checkpoint and not args.force:
        from lib.checkpoint import CheckpointStore

        ck_scrape = CheckpointStore(output_dir / f"checkpoint_scrape_{args.year}.json")
        ck_scrape.reset()

    result = scrape_events_calendar(
        year=args.year,
        output_dir=output_dir,
        headless=args.headless,
        slow_mo=args.slow_mo,
        cdp_port=args.cdp_port,
        force=args.force,
    )
    rc = 0 if result.get("success") else 1

    if rc == 0:
        translate_args = argparse.Namespace(
            file=f"events_calendar_{args.year}.json",
            year=None,
            orig_dir=str(output_dir),
            cn_dir="data/events_calendar/cn",
            checkpoint="data/events_calendar/checkpoint_translate_events_calendar.json",
            force=bool(args.force),
            rebuild_checkpoint=bool(args.rebuild_checkpoint),
        )
        rc = run_translate(translate_args)

    if rc == 0:
        print("\n✓ 完整流程完成!")
        print("  - 原始数据: data/events_calendar/orig/")
        print("  - 中文数据: data/events_calendar/cn/")
    else:
        print(f"\n✗ 流程失败 (退出码: {rc})")

    sys.exit(rc)


if __name__ == "__main__":
    main()
