#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为非世排（不在最新 ranking snapshot 中）的球员按出生年份更新年龄。

策略：
- 只更新「不在最新 ranking snapshot」且「有 birth_year」的球员；
- age = 当前年份 - birth_year；
- 每年最多执行一次（用状态文件记录 last_age_update_year），--force 可强制。

用法：
    python scripts/db/update_inactive_player_ages.py
    python scripts/db/update_inactive_player_ages.py --dry-run
    python scripts/db/update_inactive_player_ages.py --force
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CURRENT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = CURRENT_DIR.parent
for _path in (str(CURRENT_DIR), str(SCRIPTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import config  # noqa: E402

DEFAULT_STATE_FILE = config.PROJECT_ROOT / "data" / "rankings" / "inactive_ages_state.json"


def current_year() -> int:
    return date.today().year


def compute_age(birth_year: int | None, year: int | None = None) -> int | None:
    if birth_year is None:
        return None
    year = year or current_year()
    age = year - int(birth_year)
    return age if age >= 0 else None


def latest_ranked_player_ids(conn: sqlite3.Connection) -> set[int]:
    """返回最新 ranking snapshot 中的 player_id 集合。"""
    row = conn.execute(
        "SELECT snapshot_id FROM ranking_snapshots ORDER BY snapshot_id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return set()
    snapshot_id = row[0]
    return {
        int(player_id)
        for (player_id,) in conn.execute(
            "SELECT DISTINCT player_id FROM ranking_entries WHERE snapshot_id = ?",
            (snapshot_id,),
        )
    }


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_inactive_player_ages(
    db_path: str,
    *,
    year: int | None = None,
    force: bool = False,
    dry_run: bool = False,
    state_file: Path = DEFAULT_STATE_FILE,
) -> dict:
    year = year or current_year()
    state = load_state(state_file)
    last_year = state.get("last_age_update_year")

    if not force and last_year == year:
        return {
            "updated": 0,
            "skipped": 0,
            "skipped_reason": f"already updated in {year}",
            "ranked_players": None,
            "dry_run": dry_run,
        }

    db = Path(db_path)
    if not db.exists():
        return {"updated": 0, "skipped": 0, "errors": [f"database not found: {db}"], "dry_run": dry_run}

    conn = sqlite3.connect(str(db))
    try:
        ranked_ids = latest_ranked_player_ids(conn)
        rows = conn.execute(
            "SELECT player_id, birth_year FROM players WHERE birth_year IS NOT NULL"
        ).fetchall()

        updates: list[tuple[int, int]] = []  # (age, player_id)
        skipped = 0
        for player_id, birth_year in rows:
            if player_id in ranked_ids:
                continue
            age = compute_age(birth_year, year)
            if age is None:
                skipped += 1
                continue
            updates.append((age, player_id))

        if not dry_run:
            conn.executemany(
                "UPDATE players SET age = ?, updated_at = datetime('now') WHERE player_id = ?",
                updates,
            )
            conn.commit()
            save_state(state_file, {**state, "last_age_update_year": year})
    finally:
        conn.close()

    return {
        "updated": len(updates),
        "skipped": skipped,
        "ranked_players": len(ranked_ids),
        "year": year,
        "dry_run": dry_run,
    }


def run(args: argparse.Namespace) -> int:
    db_path = str(Path(args.db_path) if args.db_path else Path(config.DB_PATH))
    state_file = Path(args.state_file) if args.state_file else DEFAULT_STATE_FILE

    print("=" * 70)
    print("Update Inactive Player Ages")
    print("=" * 70)
    print(f"Database:   {db_path}")
    print(f"State file: {state_file}")
    print(f"Year:       {current_year()}")
    if args.dry_run:
        print("Mode:       DRY RUN (不修改数据库)")
    print("=" * 70 + "\n")

    result = update_inactive_player_ages(
        db_path,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
        state_file=state_file,
    )

    if result.get("errors"):
        for error in result["errors"]:
            print(f"[ERROR] {error}")
        return 1

    if "skipped_reason" in result:
        print(f"跳过：{result['skipped_reason']}")
    else:
        ranked = result.get("ranked_players")
        print(f"最新 snapshot 世排球员数：{ranked if ranked is not None else 'N/A'}")
        print(f"待更新年龄的球员数：{result['updated']}")
        print(f"跳过（birth_year 无效）：{result['skipped']}")
        if result["dry_run"]:
            print("[DRY RUN] 未写入数据库与状态文件")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="为非世排球员按出生年份更新年龄（每年一次）")
    parser.add_argument("--db-path", default=None, help="SQLite 数据库路径（默认 data/db/ittf.db）")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE), help="状态文件路径")
    parser.add_argument("--force", action="store_true", help="忽略年度去重，强制执行")
    parser.add_argument("--dry-run", "--dry", action="store_true", help="只预览，不写入")
    return parser


def main() -> None:
    parser = build_parser()
    sys.exit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
