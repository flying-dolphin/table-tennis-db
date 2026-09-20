#!/usr/bin/env python3
"""Run one complete Asian Games schedule → result → SQLite refresh."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from scripts.asian_games_2026.common import DEFAULT_DB_PATH


def run_refresh(*, db_path: Path, all_linked: bool = False) -> None:
    commands = [
        [sys.executable, "-m", "scripts.asian_games_2026.scrape_schedule"],
        [sys.executable, "-m", "scripts.asian_games_2026.scrape_brackets"],
        [sys.executable, "-m", "scripts.asian_games_2026.scrape_matches"],
        [sys.executable, "-m", "scripts.asian_games_2026.import_current", "--db-path", str(db_path)],
    ]
    if all_linked:
        commands[2].append("--all-linked")
    for command in commands:
        subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新 2026 亚运会乒乓球当前赛事数据")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--all-linked", action="store_true")
    args = parser.parse_args()
    try:
        run_refresh(db_path=args.db_path, all_linked=args.all_linked)
    except subprocess.CalledProcessError as exc:
        print(f"刷新失败：{exc}", file=sys.stderr)
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
