#!/usr/bin/env python3
"""Generate the one-off Beijing-time cron block for Asian Games 2026."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.asian_games_2026.common import PROJECT_ROOT

BEGIN_MARKER = "# BEGIN ITTF ASIAN GAMES 2026"
END_MARKER = "# END ITTF ASIAN GAMES 2026"


def generate_crontab(*, project_root: Path = PROJECT_ROOT, python: str | None = None) -> str:
    executable = python or str(project_root / ".venv/bin/python")
    log_dir = project_root / "data/asian_games/2026/logs"
    prefix = f'cd "{project_root}" && [ "$(date +\\%Y)" = "2026" ] &&'
    refresh = f'{prefix} "{executable}" -m scripts.asian_games_2026.refresh'
    finalize = f'{prefix} "{executable}" -m scripts.asian_games_2026.finalize'
    lines = [
        BEGIN_MARKER,
        "CRON_TZ=Asia/Shanghai",
        f'*/5 * 20-28 9 * {refresh} >> "{log_dir}/refresh.log" 2>&1',
        f'30 23 20-28 9 * {refresh} --all-linked >> "{log_dir}/reconcile.log" 2>&1',
        f'0 2 29 9 * {finalize} >> "{log_dir}/finalize.log" 2>&1',
        END_MARKER,
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成亚运会一次性 crontab")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--python")
    args = parser.parse_args()
    print(generate_crontab(project_root=args.project_root.resolve(), python=args.python), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
