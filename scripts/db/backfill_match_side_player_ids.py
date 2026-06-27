#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回填 match_side_players.player_id：把橡皮比赛里的选手关联到 players 表。

问题背景
--------
import_team_matches.py（以及历史 import_matches.py）写入 match_side_players 时
把 player_id 写死为 NULL，只保留 player_name / player_country。前端
buildTeamTiesForSubEvent 通过 LEFT JOIN players 取 name_zh 显示中文名，
player_id 为 NULL 时 join 落空，只能 fallback 到英文 player_name。
表现：团体赛 tie 详情页 / 赛程页的具体 match（橡皮）选手显示英文名。

匹配策略
--------
对每个 player_id IS NULL 且 player_name、player_country 都非空的
match_side_players 行：
  candidates = players WHERE name = player_name AND country_code = player_country
  - 恰好 1 个候选 → 写入 player_id
  - 0 个（players 表没有该选手，多为小赛事无档案球员）→ 跳过
  - >1 个（同名同国，需人工消歧）→ 跳过
要求 player_country 非空，避免跨国同名误配。

用法
----
  python scripts/db/backfill_match_side_player_ids.py                 # 试运行，默认仅团体赛
  python scripts/db/backfill_match_side_player_ids.py --apply         # 正式写入（仅团体赛）
  python scripts/db/backfill_match_side_player_ids.py --event-id 3263 --apply
  python scripts/db/backfill_match_side_player_ids.py --all-sub-events # 含单打/双打（慎用）
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

try:
    import config  # type: ignore
    PROJECT_ROOT = config.PROJECT_ROOT
    DB_PATH = Path(config.DB_PATH)
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"

TEAM_SUB_EVENTS = ("WT", "MT", "XT")


def build_player_index(cur: sqlite3.Cursor) -> dict[tuple[str, str], list[int]]:
    """(name, country_code) -> [player_id, ...]"""
    cur.execute("SELECT player_id, name, country_code FROM players")
    index: dict[tuple[str, str], list[int]] = defaultdict(list)
    for pid, name, country_code in cur.fetchall():
        if name is None or country_code is None:
            continue
        index[(name.strip(), country_code.strip())].append(pid)
    return index


def fetch_unlinked(cur: sqlite3.Cursor, event_filter: int | None, team_only: bool) -> list[tuple]:
    sql = """
        SELECT
            msp.rowid AS msp_rowid,
            msp.player_name,
            msp.player_country,
            m.event_id
        FROM match_side_players msp
        JOIN match_sides ms ON ms.match_side_id = msp.match_side_id
        JOIN matches m ON m.match_id = ms.match_id
        WHERE msp.player_id IS NULL
          AND msp.player_name IS NOT NULL
          AND msp.player_country IS NOT NULL
    """
    params: list = []
    if team_only:
        sql += " AND m.sub_event_type_code IN ({})".format(",".join("?" for _ in TEAM_SUB_EVENTS))
        params.extend(TEAM_SUB_EVENTS)
    if event_filter is not None:
        sql += " AND m.event_id = ?"
        params.append(event_filter)
    cur.execute(sql, params)
    return cur.fetchall()


def run(dry_run: bool, event_filter: int | None, team_only: bool) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print(f"数据库: {DB_PATH}")
    print(f"模式: {'试运行（不写库）' if dry_run else '正式写入'}")
    print(f"范围: {'仅团体赛(WT/MT/XT)' if team_only else '全部子项目'}"
          + (f" / event_id={event_filter}" if event_filter else ""))
    print()

    player_index = build_player_index(cur)
    rows = fetch_unlinked(cur, event_filter, team_only)

    print(f"待处理 match_side_players: {len(rows)} 行")

    updates: list[tuple[int, int]] = []   # (player_id, msp_rowid)
    no_match = 0
    ambiguous = 0
    ambiguous_samples: list[str] = []
    no_match_samples: Counter = Counter()

    for msp_rowid, name, country, _event_id in rows:
        key = (name.strip(), country.strip())
        candidates = player_index.get(key, [])
        if len(candidates) == 1:
            updates.append((candidates[0], msp_rowid))
        elif len(candidates) == 0:
            no_match += 1
            no_match_samples[f"{name} ({country})"] += 1
        else:
            ambiguous += 1
            if len(ambiguous_samples) < 10:
                ambiguous_samples.append(f"{name} ({country}) -> player_ids={candidates}")

    print(f"  唯一匹配（将写入）: {len(updates)} 行")
    print(f"  无匹配（players 表无此人）: {no_match} 行")
    print(f"  同名同国歧义（跳过）: {ambiguous} 行")

    if ambiguous_samples:
        print("\n--- 歧义样例 ---")
        for s in ambiguous_samples:
            print(f"  {s}")
    if no_match_samples:
        print("\n--- 无匹配样例（前 10，按出现次数）---")
        for name, cnt in no_match_samples.most_common(10):
            print(f"  {name}: {cnt} 行")

    if not updates:
        print("\n无可写入项。")
        conn.close()
        return

    if dry_run:
        print("\n试运行完成，未写入。加 --apply 正式执行。")
        conn.close()
        return

    print(f"\n正在更新 {len(updates)} 行 match_side_players.player_id …")
    cur.executemany(
        "UPDATE match_side_players SET player_id = ? WHERE rowid = ?",
        updates,
    )
    conn.commit()
    print("完成。")
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="回填 match_side_players.player_id")
    parser.add_argument("--apply", action="store_true", help="正式写入（默认试运行）")
    parser.add_argument("--event-id", type=int, default=None, metavar="ID", help="只处理指定 event_id")
    parser.add_argument("--all-sub-events", action="store_true",
                        help="包含单打/双打（默认仅团体赛 WT/MT/XT）")
    args = parser.parse_args()
    run(dry_run=not args.apply, event_filter=args.event_id, team_only=not args.all_sub_events)


if __name__ == "__main__":
    main()
