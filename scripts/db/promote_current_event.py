#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Promote 一场赛事的 current_event_* 数据到历史事实表。

赛事完结后由 cron 触发。把 current_event_team_ties / current_event_matches
等运行态数据写入 team_ties / matches / event_draw_matches / sub_events，
让球员统计、H2H、冠军数等读历史事实表的链路自然包含该赛事。

current_event_* 表本身不动，详情页继续读它。

设计原则与字段映射见 docs/design/promote_current_event.md。

CLI:
    python scripts/db/promote_current_event.py --event-id 3216 --dry-run
    python scripts/db/promote_current_event.py --event-id 3216
    python scripts/db/promote_current_event.py --event-id 3216 --replace
    python scripts/db/promote_current_event.py --event-id 3216 --force

退出码:
    0  成功 / 增量跳过 / dry-run
    1  前置校验失败
    2  promote 过程异常（已 rollback）
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if sys.platform == "win32" and getattr(sys.stdout, "encoding", "").lower() != "utf-8":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import config

    DB_PATH = config.DB_PATH
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"

from _match_keys import make_side_key  # noqa: E402

# 复用既有 import 脚本的核心函数：保持 promote 与历史 bootstrap 输出一致。
import import_event_draw_matches  # noqa: E402
import import_sub_events  # noqa: E402
from import_sub_events import build_player_index, lookup_player_id  # noqa: E402


# ---------------------------------------------------------------------------
# Round-code → 历史 matches.round 形态映射
# 历史 `matches.round` 取值见 schema.sql 注释和 import_event_draw_matches.py
# 的 normalize_round。promote 必须输出 normalize_round 能识别的形态，
# 否则 event_draw_matches 分类会失败。
# ---------------------------------------------------------------------------
ROUND_CODE_TO_HISTORICAL = {
    "F": "Final",
    "SF": "SemiFinal",
    "QF": "QuarterFinal",
    "BR": "Bronze",
    "RR": "Round Robin",
}


def historical_round_label(round_code: Optional[str], fallback_label: Optional[str]) -> str:
    """把 current 表的 round_code 翻成历史 matches.round 形态。"""
    if not round_code:
        return (fallback_label or "").strip()
    if round_code in ROUND_CODE_TO_HISTORICAL:
        return ROUND_CODE_TO_HISTORICAL[round_code]
    # R256 / R128 / R64 / R32 / R16 / R8 / R4 — 代码即历史形态
    if round_code.startswith("R") and round_code[1:].isdigit():
        return round_code
    # 资格赛 QR256 ... QR2
    if round_code.startswith("QR") and round_code[2:].isdigit():
        return round_code
    # 小组赛 G1 ... G16 → "Group N"
    if round_code.startswith("G") and round_code[1:].isdigit():
        return f"Group {round_code[1:]}"
    return (fallback_label or round_code).strip()


# ---------------------------------------------------------------------------
# Error & utility helpers
# ---------------------------------------------------------------------------

class PromoteError(Exception):
    """前置校验或字段缺失类错误。"""


def _resolve_stage(cursor, stage_code: Optional[str], stage_label: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """返回 (stage_en, stage_zh)。优先走 stage_codes 查表。"""
    if stage_code:
        row = cursor.execute(
            "SELECT name, name_zh FROM stage_codes WHERE code = ?",
            (stage_code,),
        ).fetchone()
        if row:
            return row[0], row[1]
    # 兜底：用原始 label 当英文，中文留空
    return (stage_label or None), None


def _resolve_round(cursor, round_code: Optional[str], round_label: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """返回 (round_en_for_classifier, round_zh)。"""
    round_en = historical_round_label(round_code, round_label) or None
    round_zh: Optional[str] = None
    if round_code:
        row = cursor.execute(
            "SELECT name_zh FROM round_codes WHERE code = ?",
            (round_code,),
        ).fetchone()
        if row:
            round_zh = row[0]
    return round_en, round_zh


def _fetch_event_meta(cursor, event_id: int) -> Dict:
    row = cursor.execute(
        "SELECT name, name_zh, year, lifecycle_status FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if row is None:
        raise PromoteError(f"event {event_id} not found in events table")
    return {
        "name": row[0],
        "name_zh": row[1],
        "year": row[2],
        "lifecycle_status": row[3],
    }


def _fetch_side_players(cursor, current_match_id: int) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """返回 ([(name, country), ...] for side 1, ... for side 2)。"""
    rows = cursor.execute(
        """
        SELECT s.side_no, p.player_order, p.player_name, p.player_country
          FROM current_event_match_sides s
          JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
         WHERE s.current_match_id = ?
         ORDER BY s.side_no, p.player_order
        """,
        (current_match_id,),
    ).fetchall()
    side_a: List[Tuple[str, str]] = []
    side_b: List[Tuple[str, str]] = []
    for side_no, _order, name, country in rows:
        bucket = side_a if side_no == 1 else side_b
        bucket.append((name or "", country or ""))
    return side_a, side_b


def _winner_name_from_sides(
    winner_side: Optional[str],
    side_a: List[Tuple[str, str]],
    side_b: List[Tuple[str, str]],
) -> Optional[str]:
    """与历史 import_matches 行为对齐：多人时用 '/' 连接。"""
    if winner_side == "A":
        names = [n for n, _c in side_a if n]
    elif winner_side == "B":
        names = [n for n, _c in side_b if n]
    else:
        return None
    return "/".join(names) if names else None


# ---------------------------------------------------------------------------
# Pre-check
# ---------------------------------------------------------------------------

def pre_check(cursor, event_id: int, force: bool, replace: bool) -> Tuple[bool, Dict]:
    """返回 (proceed, summary)。proceed=False 表示无需做事（已 promote 过 + 非 replace）。"""
    meta = _fetch_event_meta(cursor, event_id)
    summary = {"event_id": event_id, "lifecycle_status": meta["lifecycle_status"]}

    if not force and meta["lifecycle_status"] not in ("in_progress", "completed"):
        raise PromoteError(
            f"lifecycle_status={meta['lifecycle_status']!r}, expected in_progress/completed; "
            "use --force to override"
        )

    completed_cnt = cursor.execute(
        "SELECT COUNT(*) FROM current_event_matches "
        "WHERE event_id = ? AND status IN ('completed','walkover')",
        (event_id,),
    ).fetchone()[0]
    summary["current_completed_matches"] = completed_cnt
    if completed_cnt == 0:
        raise PromoteError(f"event {event_id} has no completed current_event_matches")

    pending_cnt = cursor.execute(
        "SELECT COUNT(*) FROM current_event_matches "
        "WHERE event_id = ? AND status IN ('scheduled','live')",
        (event_id,),
    ).fetchone()[0]
    summary["current_pending_matches"] = pending_cnt

    historical_cnt = cursor.execute(
        "SELECT COUNT(*) FROM matches WHERE event_id = ?",
        (event_id,),
    ).fetchone()[0]
    summary["historical_matches_before"] = historical_cnt

    if historical_cnt > 0 and not replace:
        summary["proceed"] = False
        return False, summary

    summary["proceed"] = True
    return True, summary


# ---------------------------------------------------------------------------
# Step 1: promote team_ties
# ---------------------------------------------------------------------------

def promote_team_ties(
    cursor,
    event_id: int,
    player_index: Dict[Tuple[str, str], int],
    miss_log: List[Tuple[str, str]],
) -> Dict[int, int]:
    """返回 current_team_tie_id → team_tie_id 映射。

    promote 过程中如果 current_event_team_tie_side_players.player_id 为 NULL，
    会按 (name, country) 在 players 表里查回填，避免历史 match_side_players
    缺 player_id 导致前端按 player_id JOIN 时拿不到该赛事的比赛。
    """
    mapping: Dict[int, int] = {}
    rows = cursor.execute(
        """
        SELECT current_team_tie_id, sub_event_type_code,
               stage_label, stage_code, round_label, round_code,
               group_code, match_score, winner_side, winner_team_code,
               external_match_code, status
          FROM current_event_team_ties
         WHERE event_id = ? AND status IN ('completed','walkover')
         ORDER BY current_team_tie_id
        """,
        (event_id,),
    ).fetchall()

    for (
        current_tie_id, sub_event, stage_label, stage_code,
        round_label, round_code, group_code, match_score,
        winner_side, winner_team_code, external_code, status,
    ) in rows:
        stage_en, stage_zh = _resolve_stage(cursor, stage_code, stage_label)
        round_en, round_zh = _resolve_round(cursor, round_code, round_label)

        cursor.execute(
            """
            INSERT OR IGNORE INTO team_ties (
                event_id, sub_event_type_code,
                stage, stage_zh, stage_code,
                round, round_zh, round_code,
                group_code, match_score, winner_side, winner_team_code,
                status, source_type, source_key, promoted_from_event_id, promoted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      'promoted_from_current', ?, ?, datetime('now'))
            """,
            (
                event_id, sub_event,
                stage_en, stage_zh, stage_code,
                round_en, round_zh, round_code,
                group_code, match_score, winner_side, winner_team_code,
                status, external_code, event_id,
            ),
        )

        # 回查 team_tie_id（INSERT OR IGNORE 时 lastrowid 可能为 0）
        team_tie_id = cursor.execute(
            "SELECT team_tie_id FROM team_ties "
            "WHERE event_id = ? AND sub_event_type_code = ? "
            "  AND IFNULL(source_key, '') = IFNULL(?, '')",
            (event_id, sub_event, external_code),
        ).fetchone()[0]
        mapping[current_tie_id] = team_tie_id

        # promote sides
        side_rows = cursor.execute(
            """
            SELECT current_team_tie_side_id, side_no, team_code, team_name,
                   seed, qualifier, is_winner
              FROM current_event_team_tie_sides
             WHERE current_team_tie_id = ?
             ORDER BY side_no
            """,
            (current_tie_id,),
        ).fetchall()
        for (current_side_id, side_no, team_code, team_name,
             seed, qualifier, is_winner) in side_rows:
            cursor.execute(
                """
                INSERT OR IGNORE INTO team_tie_sides (
                    team_tie_id, side_no, team_code, team_name,
                    seed, qualifier, is_winner
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (team_tie_id, side_no, team_code, team_name,
                 seed, qualifier, is_winner),
            )
            tie_side_id = cursor.execute(
                "SELECT team_tie_side_id FROM team_tie_sides "
                "WHERE team_tie_id = ? AND side_no = ?",
                (team_tie_id, side_no),
            ).fetchone()[0]

            # promote side players
            player_rows = cursor.execute(
                """
                SELECT player_order, player_id, player_name, player_country
                  FROM current_event_team_tie_side_players
                 WHERE current_team_tie_side_id = ?
                 ORDER BY player_order
                """,
                (current_side_id,),
            ).fetchall()
            for player_order, player_id, player_name, player_country in player_rows:
                if player_id is None and player_name:
                    player_id = lookup_player_id(player_index, player_name, player_country)
                    if player_id is None:
                        miss_log.append((player_name, player_country or ""))
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO team_tie_side_players (
                        team_tie_side_id, player_order,
                        player_id, player_name, player_country
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (tie_side_id, player_order,
                     player_id, player_name, player_country),
                )

    return mapping


# ---------------------------------------------------------------------------
# Step 2: promote matches
# ---------------------------------------------------------------------------

def promote_matches(
    cursor,
    event_id: int,
    event_meta: Dict,
    team_tie_map: Dict[int, int],
    player_index: Dict[Tuple[str, str], int],
    miss_log: List[Tuple[str, str]],
) -> Tuple[Dict[int, int], int, int]:
    """返回 (current_match_id → match_id 映射, skipped_no_winner, skipped_walkover)。

    跳过 match_score 含 'WO' 的弃权比赛 —— 这些场次实际未进行，
    导入历史 matches 会污染球员胜负、H2H、连胜等统计。
    """
    rows = cursor.execute(
        """
        SELECT current_match_id, current_team_tie_id, sub_event_type_code,
               stage_label, stage_code, round_label, round_code,
               match_score, games, winner_side, winner_name,
               external_match_code, raw_source_payload, status
          FROM current_event_matches
         WHERE event_id = ? AND status IN ('completed','walkover')
         ORDER BY current_match_id
        """,
        (event_id,),
    ).fetchall()

    mapping: Dict[int, int] = {}
    skipped_no_winner = 0
    skipped_walkover = 0

    for (
        current_match_id, current_team_tie_id, sub_event,
        stage_label, stage_code, round_label, round_code,
        match_score, games, winner_side, winner_name,
        external_code, raw_payload, status,
    ) in rows:
        # 弃权比赛：match_score 含 "WO" / status='walkover'。
        # 这些场次没有真打，跳过以免污染历史统计。
        if status == "walkover" or (match_score and "WO" in match_score.upper()):
            skipped_walkover += 1
            continue

        side_a, side_b = _fetch_side_players(cursor, current_match_id)
        if not side_a and not side_b:
            skipped_no_winner += 1
            continue
        side_a_key = make_side_key(side_a)
        side_b_key = make_side_key(side_b)

        stage_en, stage_zh = _resolve_stage(cursor, stage_code, stage_label)
        round_en, round_zh = _resolve_round(cursor, round_code, round_label)

        effective_winner_name = winner_name or _winner_name_from_sides(winner_side, side_a, side_b)
        if not effective_winner_name:
            # matches.winner_name NOT NULL — 无法落库，跳过并计数
            skipped_no_winner += 1
            continue

        raw_row_text = raw_payload or (
            f"promoted:event={event_id};code={external_code};match={current_match_id}"
        )
        team_tie_id = team_tie_map.get(current_team_tie_id) if current_team_tie_id else None

        cursor.execute(
            """
            INSERT INTO matches (
                event_id, event_name, event_name_zh, event_year,
                sub_event_type_code,
                stage, stage_zh, stage_code,
                round, round_zh, round_code,
                side_a_key, side_b_key,
                match_score, games, winner_side, winner_name,
                raw_row_text, scraped_at, team_tie_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
            """,
            (
                event_id, event_meta["name"], event_meta["name_zh"], event_meta["year"],
                sub_event,
                stage_en, stage_zh, stage_code,
                round_en, round_zh, round_code,
                side_a_key, side_b_key,
                match_score, games, winner_side, effective_winner_name,
                raw_row_text, team_tie_id,
            ),
        )
        match_id = cursor.lastrowid
        mapping[current_match_id] = match_id

        # promote sides + side players
        side_rows = cursor.execute(
            """
            SELECT current_match_side_id, side_no, is_winner
              FROM current_event_match_sides
             WHERE current_match_id = ?
             ORDER BY side_no
            """,
            (current_match_id,),
        ).fetchall()
        for current_side_id, side_no, is_winner in side_rows:
            side_key = side_a_key if side_no == 1 else side_b_key
            cursor.execute(
                """
                INSERT INTO match_sides (match_id, side_no, side_key, is_winner)
                VALUES (?, ?, ?, ?)
                """,
                (match_id, side_no, side_key, is_winner),
            )
            match_side_id = cursor.lastrowid

            player_rows = cursor.execute(
                """
                SELECT player_order, player_id, player_name, player_country
                  FROM current_event_match_side_players
                 WHERE current_match_side_id = ?
                 ORDER BY player_order
                """,
                (current_side_id,),
            ).fetchall()
            for player_order, player_id, player_name, player_country in player_rows:
                if player_id is None and player_name:
                    player_id = lookup_player_id(player_index, player_name, player_country)
                    if player_id is None:
                        miss_log.append((player_name, player_country or ""))
                cursor.execute(
                    """
                    INSERT INTO match_side_players (
                        match_side_id, player_order,
                        player_id, player_name, player_country
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (match_side_id, player_order,
                     player_id, player_name, player_country),
                )

    return mapping, skipped_no_winner, skipped_walkover


# ---------------------------------------------------------------------------
# Step 3 / 4 / 5 / 6 wrappers
# ---------------------------------------------------------------------------

def replace_purge(cursor, event_id: int) -> Dict:
    """--replace 模式：清空该 event 的历史数据。"""
    # 1. event_draw_matches 在 matches FK ON DELETE CASCADE 时会被带走，
    #    但保险起见显式 DELETE
    cursor.execute("DELETE FROM event_draw_matches WHERE event_id = ?", (event_id,))
    # 2. match_sides / match_side_players 也是 CASCADE，DELETE matches 即可
    cursor.execute("DELETE FROM matches WHERE event_id = ?", (event_id,))
    # 3. team_tie_sides / team_tie_side_players CASCADE 跟随 team_ties
    cursor.execute(
        "DELETE FROM team_ties WHERE event_id = ? AND source_type = 'promoted_from_current'",
        (event_id,),
    )
    cursor.execute("DELETE FROM sub_events WHERE event_id = ?", (event_id,))
    return {"replace_purged": True}


def set_lifecycle_completed(cursor, event_id: int) -> None:
    cursor.execute(
        "UPDATE events SET lifecycle_status = 'completed', last_synced_at = datetime('now') "
        "WHERE event_id = ?",
        (event_id,),
    )


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def promote(db_path: str, event_id: int, *, dry_run: bool, replace: bool, force: bool) -> Dict:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    report: Dict = {
        "event_id": event_id,
        "dry_run": dry_run,
        "replace": replace,
        "force": force,
    }

    try:
        proceed, pre_summary = pre_check(cursor, event_id, force=force, replace=replace)
        report.update(pre_summary)
        if not proceed:
            print(f"[skip] event {event_id} already promoted "
                  f"({pre_summary['historical_matches_before']} historical matches). "
                  f"Use --replace to rebuild.")
            conn.close()
            return report

        event_meta = _fetch_event_meta(cursor, event_id)

        if dry_run:
            # dry-run: 不开事务，只统计
            team_tie_count = cursor.execute(
                "SELECT COUNT(*) FROM current_event_team_ties "
                "WHERE event_id = ? AND status IN ('completed', 'walkover')",
                (event_id,),
            ).fetchone()[0]
            walkover_count = cursor.execute(
                "SELECT COUNT(*) FROM current_event_matches "
                "WHERE event_id = ? AND status IN ('completed','walkover') "
                "  AND (status = 'walkover' OR UPPER(IFNULL(match_score,'')) LIKE '%WO%')",
                (event_id,),
            ).fetchone()[0]
            print(f"[dry-run] event {event_id} ({event_meta['name']})")
            print(f"  current completed matches: {pre_summary['current_completed_matches']}")
            print(f"  current pending matches:   {pre_summary['current_pending_matches']}")
            print(f"  walkover (to skip):        {walkover_count}")
            print(f"  would promote matches:     {pre_summary['current_completed_matches'] - walkover_count}")
            print(f"  would promote team_ties:   {team_tie_count}")
            print(f"  would set lifecycle_status='completed' (currently {pre_summary['lifecycle_status']})")
            report["dry_run_ok"] = True
            report["team_ties_to_promote"] = team_tie_count
            report["matches_to_promote"] = pre_summary["current_completed_matches"] - walkover_count
            report["walkover_to_skip"] = walkover_count
            conn.close()
            return report

        # 实跑：单事务包裹所有写入
        cursor.execute("BEGIN IMMEDIATE")

        if replace:
            purge_stats = replace_purge(cursor, event_id)
            report.update(purge_stats)

        # 一次性构建 (name, country) → player_id 索引，promote 过程中
        # 复用以回填 current_event_match_side_players.player_id（运行态
        # import 没做这步，100% 行 player_id=NULL）。
        player_index = build_player_index(cursor)
        miss_log: List[Tuple[str, str]] = []

        team_tie_map = promote_team_ties(cursor, event_id, player_index, miss_log)
        report["team_ties_promoted"] = len(team_tie_map)

        match_map, skipped_no_winner, skipped_walkover = promote_matches(
            cursor, event_id, event_meta, team_tie_map, player_index, miss_log
        )
        report["matches_promoted"] = len(match_map)
        report["matches_skipped_no_winner"] = skipped_no_winner
        report["matches_skipped_walkover"] = skipped_walkover

        # 报告未匹配球员（main() 据此决定是否写文件）
        counter = Counter((name, country) for name, country in miss_log)
        unique_misses = sorted(counter.keys())
        report["player_id_unmatched"] = len(unique_misses)
        report["player_id_unmatched_rows"] = sum(counter.values())
        if unique_misses:
            report["player_id_unmatched_samples"] = [
                f"{name} ({country})" for name, country in unique_misses[:10]
            ]
        # 私有键：完整未匹配明细，main() 写文件用，普通报告里不打印
        report["_player_id_misses"] = [
            {"name": name, "country": country, "occurrences": count}
            for (name, country), count in sorted(counter.items(), key=lambda x: (-x[1], x[0]))
        ]

        draw_stats = import_event_draw_matches.rebuild_for_event(cursor, event_id)
        report["draw_matches_rebuilt"] = draw_stats["draw_rows"]

        sub_stats = import_sub_events.rebuild_for_event(cursor, event_id)
        report["sub_events_inserted"] = sub_stats["sub_events_inserted"]
        if sub_stats.get("problem_events"):
            report["sub_events_problems"] = sub_stats["problem_events"]

        set_lifecycle_completed(cursor, event_id)
        report["lifecycle_status_after"] = "completed"

        conn.commit()
        conn.close()
        return report

    except Exception:
        try:
            conn.rollback()
        finally:
            conn.close()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--dry-run", action="store_true",
                        help="Only print what would happen; no writes.")
    parser.add_argument("--replace", action="store_true",
                        help="Purge existing historical rows for this event and rebuild.")
    parser.add_argument("--force", action="store_true",
                        help="Skip lifecycle_status check.")
    parser.add_argument(
        "--unmatched-out",
        default=None,
        help=(
            "Optional path to write JSON of players whose player_id could not be "
            "resolved during promote. Used as input for follow-up profile scraping. "
            "Pass 'auto' to write to data/promote_unmatched/event_<id>_<ts>.json."
        ),
    )
    args = parser.parse_args()

    if not Path(args.db_path).exists():
        print(f"[ERROR] Database not found: {args.db_path}", file=sys.stderr)
        return 1

    print("=" * 70)
    print(f"Promote Current Event → Historical Facts")
    print(f"  event_id : {args.event_id}")
    print(f"  db_path  : {args.db_path}")
    print(f"  dry_run  : {args.dry_run}")
    print(f"  replace  : {args.replace}")
    print(f"  force    : {args.force}")
    print("=" * 70)

    try:
        report = promote(args.db_path, args.event_id,
                         dry_run=args.dry_run, replace=args.replace, force=args.force)
    except PromoteError as exc:
        print(f"[ERROR] pre-check failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[ERROR] promote failed and rolled back: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2

    # 拆出私有 keys：不在普通报告里打印，但供文件持久化用
    misses_detail = report.pop("_player_id_misses", [])

    print()
    print("Report:")
    for k, v in report.items():
        if k == "sub_events_problems":
            print(f"  {k}: {len(v)}")
            for item in v[:5]:
                print(f"    - {item}")
            if len(v) > 5:
                print(f"    ... and {len(v) - 5} more")
        else:
            print(f"  {k}: {v}")

    # 写未匹配名单
    if args.unmatched_out and misses_detail:
        if args.unmatched_out == "auto":
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            out_dir = Path("data") / "promote_unmatched"
            out_path = out_dir / f"event_{args.event_id}_{ts}.json"
        else:
            out_path = Path(args.unmatched_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "event_id": args.event_id,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "total_unmatched_rows": report.get("player_id_unmatched_rows", 0),
            "total_unique_players": report.get("player_id_unmatched", 0),
            "players": misses_detail,
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n[unmatched] wrote {len(misses_detail)} entries to {out_path}")
    elif args.unmatched_out and not misses_detail:
        print(f"\n[unmatched] nothing to write (all player_id resolved)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
