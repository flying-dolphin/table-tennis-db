"""Print the isolated event's cron block; installation is explicit."""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from .common import ROOT

BEGIN = "# BEGIN ITTF AC2006 3474"
END = "# END ITTF AC2006 3474"


def generate_crontab(project_root: Path = ROOT, python: str = sys.executable) -> str:
    root = shlex.quote(str(project_root.resolve()))
    executable = shlex.quote(python)
    prefix = f"cd {root} && mkdir -p data/ac2006/3474/logs && [ \"$(TZ=Asia/Shanghai date +\\%Y)\" = 2026 ] && {executable} -m scripts.ac2006."
    # Poll all day: local event time is Beijing minus three hours, and source
    # schedules may change. The module's lock prevents overlapping refreshes.
    return "\n".join([BEGIN, "CRON_TZ=Asia/Shanghai",
        f"*/5 * 19-25 10 * {prefix}refresh >> data/ac2006/3474/logs/refresh.log 2>&1",
        f"30 23 19-25 10 * {prefix}refresh --full >> data/ac2006/3474/logs/reconcile.log 2>&1",
        f"55 4 26 10 * {prefix}refresh --full >> data/ac2006/3474/logs/reconcile.log 2>&1",
        f"0 5 26 10 * {prefix}finalize --skip-refresh >> data/ac2006/3474/logs/finalize.log 2>&1",
        END]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="预览亚锦赛定时任务（不安装）")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    print(generate_crontab(args.project_root, args.python), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
