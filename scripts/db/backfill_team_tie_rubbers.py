#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回填 matches.team_tie_id：将团体赛的橡皮比赛关联到对应的 team_ties 行。

问题背景
--------
import_matches.py 导入橡皮比赛时没有设置 team_tie_id，导致
buildTeamTiesForSubEvent 无法加载橡皮（查询条件为 team_tie_id IS NOT NULL），
从而合并详情页和 override 聚合详情页的 rubbers 始终为空。

匹配策略
--------
对于每个 (event_id, sub_event_type_code, stage, round) 分组，
从 match_side_players.player_country 推断该局比赛属于哪个 team_tie：
  - 取 side_no=1 所有选手的国籍 → 比较 team_tie_sides(side_no=1).team_code
  - 取 side_no=2 所有选手的国籍 → 比较 team_tie_sides(side_no=2).team_code
  - 若两侧国籍集合与某个 team_tie 的 teamA/teamB 完全对应（允许正反两种顺序），
    且只有唯一匹配，则写入 team_tie_id。

多对一情况：同一 team_tie 可能有多场橡皮比赛，脚本会把所有匹配到的比赛
都关联到同一个 team_tie_id；若同一 (stage, round) 下某场比赛无法唯一匹配，
则跳过并报告。

用法
----
  python scripts/db/backfill_team_tie_rubbers.py             # 试运行（不写库）
  python scripts/db/backfill_team_tie_rubbers.py --apply     # 正式写入
  python scripts/db/backfill_team_tie_rubbers.py --event-id 896
  python scripts/db/backfill_team_tie_rubbers.py --event-id 896 --apply
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
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


def majority_country(countries: list[str]) -> str | None:
    """返回出现次数最多的国籍；若无则返回 None。"""
    if not countries:
        return None
    most_common, _ = Counter(countries).most_common(1)[0]
    return most_common


def build_tie_index(cur: sqlite3.Cursor, event_filter: int | None) -> dict:
    """
    构建 team_tie 索引：
      key = (event_id, sub_event_type_code, stage_key, round_key)
      value = list of { tie_id, team_a_code, team_b_code }
    """
    sql = """
        SELECT
            t.team_tie_id,
            t.event_id,
            t.sub_event_type_code,
            COALESCE(t.stage, '') AS stage,
            COALESCE(t.round, '') AS round,
            s.side_no,
            s.team_code
        FROM team_ties t
        JOIN team_tie_sides s ON s.team_tie_id = t.team_tie_id
        WHERE t.sub_event_type_code IN ({})
    """.format(",".join("?" for _ in TEAM_SUB_EVENTS))
    params: list = list(TEAM_SUB_EVENTS)

    if event_filter is not None:
        sql += " AND t.event_id = ?"
        params.append(event_filter)

    cur.execute(sql, params)

    # tie_id -> {side_no: team_code}
    tie_sides: dict[int, dict] = {}
    tie_meta: dict[int, dict] = {}
    for row in cur.fetchall():
        tid, eid, se, stage, rnd, side_no, team_code = row
        if tid not in tie_meta:
            tie_meta[tid] = dict(event_id=eid, sub_event_type_code=se, stage=stage, round=rnd)
        tie_sides.setdefault(tid, {})[side_no] = team_code

    index: dict[tuple, list[dict]] = defaultdict(list)
    for tid, meta in tie_meta.items():
        sides = tie_sides.get(tid, {})
        team_a = sides.get(1)
        team_b = sides.get(2)
        if not team_a or not team_b:
            continue
        key = (meta["event_id"], meta["sub_event_type_code"], meta["stage"], meta["round"])
        index[key].append(dict(tie_id=tid, team_a=team_a, team_b=team_b))

    return index


def build_match_player_countries(cur: sqlite3.Cursor, event_filter: int | None) -> dict:
    """
    从 match_side_players 归集每场橡皮比赛两侧的国籍列表。
    返回 { match_id: {1: [country,...], 2: [country,...]} }
    """
    sql = """
        SELECT
            m.rowid AS match_id,
            ms.side_no,
            msp.player_country
        FROM matches m
        JOIN match_sides ms ON ms.match_id = m.rowid
        JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
        WHERE m.team_tie_id IS NULL
          AND m.sub_event_type_code IN ({})
          AND msp.player_country IS NOT NULL
    """.format(",".join("?" for _ in TEAM_SUB_EVENTS))
    params: list = list(TEAM_SUB_EVENTS)

    if event_filter is not None:
        sql += " AND m.event_id = ?"
        params.append(event_filter)

    cur.execute(sql, params)

    result: dict[int, dict[int, list[str]]] = defaultdict(lambda: {1: [], 2: []})
    for match_id, side_no, country in cur.fetchall():
        result[match_id][side_no].append(country)

    return result


def fetch_unlinked_matches(cur: sqlite3.Cursor, event_filter: int | None) -> list[dict]:
    """返回所有 team_tie_id IS NULL 的团体赛橡皮比赛基本信息。"""
    sql = """
        SELECT
            m.rowid AS match_id,
            m.event_id,
            m.sub_event_type_code,
            COALESCE(m.stage, '') AS stage,
            COALESCE(m.round, '') AS round
        FROM matches m
        WHERE m.team_tie_id IS NULL
          AND m.sub_event_type_code IN ({})
    """.format(",".join("?" for _ in TEAM_SUB_EVENTS))
    params: list = list(TEAM_SUB_EVENTS)

    if event_filter is not None:
        sql += " AND m.event_id = ?"
        params.append(event_filter)

    cur.execute(sql, params)
    cols = ["match_id", "event_id", "sub_event_type_code", "stage", "round"]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def find_tie(side1_countries: list[str], side2_countries: list[str],
             candidates: list[dict]) -> int | None:
    """
    在候选 team_ties 中查找唯一匹配。
    side1 / side2 是橡皮比赛中两侧选手的国籍列表。
    返回 team_tie_id 或 None（未找到 / 存在歧义）。
    """
    c1 = majority_country(side1_countries)
    c2 = majority_country(side2_countries)
    if not c1 or not c2:
        return None

    matched = []
    for cand in candidates:
        ta, tb = cand["team_a"], cand["team_b"]
        if (c1 == ta and c2 == tb) or (c1 == tb and c2 == ta):
            matched.append(cand["tie_id"])

    return matched[0] if len(matched) == 1 else None


def run(dry_run: bool, event_filter: int | None) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print(f"数据库: {DB_PATH}")
    print(f"模式: {'试运行（不写库）' if dry_run else '正式写入'}")
    if event_filter:
        print(f"仅处理 event_id = {event_filter}")
    print()

    tie_index = build_tie_index(cur, event_filter)
    player_countries = build_match_player_countries(cur, event_filter)
    unlinked = fetch_unlinked_matches(cur, event_filter)

    print(f"待处理橡皮比赛: {len(unlinked)} 场")
    print(f"team_tie 分组: {len(tie_index)} 个")
    print()

    updates: list[tuple[int, int]] = []  # (tie_id, match_id)
    skipped_no_candidate: list[dict] = []
    skipped_ambiguous: list[dict] = []
    skipped_no_country: list[dict] = []

    for m in unlinked:
        mid = m["match_id"]
        key = (m["event_id"], m["sub_event_type_code"], m["stage"], m["round"])
        candidates = tie_index.get(key, [])

        if not candidates:
            skipped_no_candidate.append(m)
            continue

        countries = player_countries.get(mid, {1: [], 2: []})
        s1, s2 = countries[1], countries[2]

        if not s1 or not s2:
            skipped_no_country.append(m)
            continue

        tie_id = find_tie(s1, s2, candidates)
        if tie_id is None:
            skipped_ambiguous.append(m)
            continue

        updates.append((tie_id, mid))

    print(f"成功匹配: {len(updates)} 场")
    print(f"  无 team_tie 候选（stage/round 无对应）: {len(skipped_no_candidate)} 场")
    print(f"  无国籍信息: {len(skipped_no_country)} 场")
    print(f"  歧义（多个候选）: {len(skipped_ambiguous)} 场")

    if skipped_ambiguous:
        print("\n--- 歧义详情（前 10 条）---")
        for m in skipped_ambiguous[:10]:
            mid = m["match_id"]
            key = (m["event_id"], m["sub_event_type_code"], m["stage"], m["round"])
            countries = player_countries.get(mid, {1: [], 2: []})
            cands = tie_index.get(key, [])
            print(f"  match {mid}: side1={countries[1]} side2={countries[2]} "
                  f"candidates={[c['team_a']+'-'+c['team_b'] for c in cands]}")

    if not updates:
        print("\n无需更新。")
        conn.close()
        return

    # 按 event 汇总
    event_counts: Counter = Counter()
    for tie_id, mid in updates:
        # tie_id can look up event via tie_index values
        pass
    cur.execute(
        "SELECT team_tie_id, event_id FROM team_ties WHERE team_tie_id IN ({})".format(
            ",".join("?" for _ in {tid for tid, _ in updates})
        ),
        list({tid for tid, _ in updates}),
    )
    tie_event_map = {row[0]: row[1] for row in cur.fetchall()}
    for tid, _ in updates:
        event_counts[tie_event_map.get(tid, "?")] += 1

    print("\n按 event_id 统计:")
    for eid, cnt in sorted(event_counts.items()):
        print(f"  event {eid}: {cnt} 场")

    if dry_run:
        print("\n试运行完成，未写入数据库。加 --apply 正式执行。")
        conn.close()
        return

    print(f"\n正在更新 {len(updates)} 行 matches.team_tie_id …")
    cur.executemany(
        "UPDATE matches SET team_tie_id = ? WHERE rowid = ?",
        updates,
    )
    conn.commit()
    print("完成。")
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="回填 matches.team_tie_id")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="正式写入数据库（默认为试运行）",
    )
    parser.add_argument(
        "--event-id",
        type=int,
        default=None,
        metavar="ID",
        help="只处理指定的 event_id（不填则处理全部）",
    )
    args = parser.parse_args()
    run(dry_run=not args.apply, event_filter=args.event_id)


if __name__ == "__main__":
    main()
