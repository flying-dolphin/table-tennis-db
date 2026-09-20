#!/usr/bin/env python3
"""Validate, reconcile, and promote Asian Games data to historical tables."""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.asian_games_2026.common import DEFAULT_DB_PATH, EVENT_ID, PROJECT_ROOT
from scripts.asian_games_2026.refresh import run_refresh


class FinalizeError(RuntimeError):
    pass


def validate_current(conn: sqlite3.Connection, *, force: bool = False) -> dict[str, Any]:
    completed = conn.execute(
        "SELECT COUNT(*) FROM current_event_matches WHERE event_id=? AND status IN ('completed','walkover')",
        (EVENT_ID,),
    ).fetchone()[0]
    pending = conn.execute(
        """SELECT COUNT(*) FROM current_event_matches m
           LEFT JOIN current_event_team_ties t ON t.current_team_tie_id=m.current_team_tie_id
           WHERE m.event_id=? AND m.status IN ('scheduled','live')
             AND NOT (m.status='scheduled' AND t.status IN ('completed','walkover'))""",
        (EVENT_ID,),
    ).fetchone()[0]
    pending += conn.execute(
        "SELECT COUNT(*) FROM current_event_team_ties WHERE event_id=? AND status IN ('scheduled','live')",
        (EVENT_ID,),
    ).fetchone()[0]
    ties_without_roster = conn.execute(
        """SELECT COUNT(*) FROM current_event_team_ties t
           WHERE t.event_id=? AND t.status IN ('completed','walkover') AND (
             (SELECT COUNT(*) FROM current_event_team_tie_sides s
              WHERE s.current_team_tie_id=t.current_team_tie_id) != 2
             OR EXISTS (
               SELECT 1 FROM current_event_team_tie_sides s
               WHERE s.current_team_tie_id=t.current_team_tie_id AND NOT EXISTS (
                 SELECT 1 FROM current_event_team_tie_side_players p
                 WHERE p.current_team_tie_side_id=s.current_team_tie_side_id
               )
             )
           )""",
        (EVENT_ID,),
    ).fetchone()[0]
    invalid_sides = conn.execute(
        """SELECT COUNT(*) FROM current_event_matches m WHERE m.event_id=? AND m.status='completed'
           AND (
             (SELECT COUNT(*) FROM current_event_match_sides s WHERE s.current_match_id=m.current_match_id) != 2
             OR EXISTS (
               SELECT 1 FROM current_event_match_sides s
               WHERE s.current_match_id=m.current_match_id AND NOT EXISTS (
                 SELECT 1 FROM current_event_match_side_players p
                 WHERE p.current_match_side_id=s.current_match_side_id
               )
             )
           )""",
        (EVENT_ID,),
    ).fetchone()[0]
    missing_winners = conn.execute(
        """SELECT COUNT(*) FROM current_event_matches WHERE event_id=? AND status='completed'
           AND winner_side IS NULL AND UPPER(IFNULL(match_score,'')) NOT LIKE '%WO%'""",
        (EVENT_ID,),
    ).fetchone()[0]
    report = {
        "completed_matches": completed,
        "pending_units": pending,
        "completed_ties_without_roster": ties_without_roster,
        "completed_matches_invalid_sides": invalid_sides,
        "completed_matches_missing_winner": missing_winners,
    }
    errors = []
    if completed == 0:
        errors.append("no completed matches")
    if pending:
        errors.append(f"{pending} live/scheduled units remain")
    if ties_without_roster:
        errors.append(f"{ties_without_roster} completed team ties have no nominated roster")
    if invalid_sides:
        errors.append(f"{invalid_sides} completed matches do not have two sides")
    if missing_winners:
        errors.append(f"{missing_winners} completed matches have no winner")
    if errors and not force:
        raise FinalizeError("; ".join(errors))
    report["forced_errors"] = errors if force else []
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="核对并归档 2026 亚运会乒乓球数据")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true", help="仅供离线核查/测试")
    args = parser.parse_args()
    try:
        if not args.skip_refresh:
            run_refresh(db_path=args.db_path, all_linked=True)
        conn = sqlite3.connect(args.db_path)
        try:
            report = validate_current(conn, force=args.force)
        finally:
            conn.close()
        print("归档前核查：" + ", ".join(f"{key}={value}" for key, value in report.items()))
        command = [
            sys.executable, str(PROJECT_ROOT / "scripts/db/promote_current_event.py"),
            "--event-id", str(EVENT_ID), "--db-path", str(args.db_path),
        ]
        if args.dry_run:
            command.append("--dry-run")
        if args.force:
            command.append("--force")
        if args.replace:
            command.append("--replace")
        subprocess.run(command, check=True)
    except (FinalizeError, OSError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        print(f"归档失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
