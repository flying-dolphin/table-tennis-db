"""One locked championship refresh, also usable entirely offline."""
from __future__ import annotations

import argparse
import fcntl
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .common import DATA_ROOT, DB_PATH, add_options, write_json
from .import_current import import_snapshot
from .normalize import normalize_capture
from .scrape import capture


@contextmanager
def event_lock(data_root: Path, *, wait: bool = False):
    data_root.mkdir(parents=True, exist_ok=True)
    with (data_root / "refresh.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another Asian Championships refresh is running") from exc
        yield


def refresh(*, data_root: Path = DATA_ROOT, db_path: Path = DB_PATH, offline=False,
            full=False, all_linked=False, no_proxy=False, dry_run=False) -> dict:
    with event_lock(data_root):
        if not offline:
            manifest = capture(data_root, full=full, all_linked=all_linked, no_proxy=no_proxy)
        else:
            manifest = None
        snapshot = normalize_capture(data_root, manifest)
        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=rw", uri=True)
        try:
            report = import_snapshot(conn, snapshot, dry_run=dry_run)
        finally:
            conn.close()
        report.update(batch_id=snapshot["batch_id"], captured_at=snapshot["captured_at"])
        write_json(data_root / "normalized/import-report.json", report)
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新 2026 亚锦赛：采集 → 标准化 → 导入")
    add_options(parser, database=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--all-linked", action="store_true")
    parser.add_argument("--no-proxy", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = refresh(**{k: v for k, v in vars(args).items() if k != "event_id"})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
