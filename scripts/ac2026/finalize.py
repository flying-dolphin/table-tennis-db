"""Validate this event's local snapshot before invoking the shared promoter."""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys

from .common import EVENT_ID, PROJECT_NAMES, PROJECTS, ROOT, add_options, read_json
from .refresh import event_lock
from .normalize import is_double_walkover


def unplayed_double_walkover(row) -> bool:
    if row["status"] != "walkover" or row["match_score"] != "WO-WO":
        return False
    try:
        payload = json.loads(row["raw_source_payload"] or "{}")
        return (isinstance(payload, dict) and json.loads(row["games"] or "[]") == []
                and is_double_walkover(payload.get("Home"), payload.get("Away")))
    except (ValueError, TypeError):
        return False


def final_result_matches(conn, final: dict, actual) -> bool:
    """Compare results after aligning competitors, since feeds can reverse sides."""
    if not actual or actual["status"] not in ("completed", "walkover"):
        return False
    if final["sub_event_type_code"] in ("MT", "WT"):
        bracket_sides = [final.get(f"side_{side}_team_code") for side in ("a", "b")]
        actual_sides = [row[0] for row in conn.execute(
            "SELECT team_code FROM current_event_team_tie_sides WHERE current_team_tie_id=? ORDER BY side_no",
            (actual["current_team_tie_id"],))]
    else:
        from .normalize import competitor_players

        def identity(comp):
            # Doubles partners may also be listed in a different order.
            return tuple(sorted((p["source_id"], p["name"], p["country"] or "")
                                for p in competitor_players(comp)))

        bracket_payload = final["raw_source_payload"]
        actual_payload = json.loads(actual["raw_source_payload"] or "{}")
        bracket_sides = [identity(bracket_payload.get(side) or {}) for side in ("Home", "Away")]
        actual_sides = [identity(actual_payload.get(side) or {}) for side in ("Home", "Away")]
    if len(actual_sides) != 2 or not all(bracket_sides) or bracket_sides[0] == bracket_sides[1]:
        return False
    if bracket_sides == actual_sides:
        winner, score = actual["winner_side"], actual["match_score"]
    elif bracket_sides == actual_sides[::-1]:
        winner = {"A": "B", "B": "A"}.get(actual["winner_side"])
        score = "-".join(reversed((actual["match_score"] or "").split("-")))
    else:
        return False
    return winner == final["winner_side"] and score == final["match_score"]


def validate_current(conn, snapshot: dict, *, allow_archived=False) -> dict:
    errors = [i for i in snapshot["issues"] if i["severity"] == "error"]
    if errors:
        raise ValueError(f"{len(errors)} unresolved source errors; see normalized/issues.json")
    conn.row_factory = sqlite3.Row
    event = conn.execute("SELECT last_synced_at,lifecycle_status FROM events WHERE event_id=?", (EVENT_ID,)).fetchone()
    if not event:
        raise ValueError("database does not contain this exact captured batch")
    if event[0] != snapshot["captured_at"]:
        # The shared promoter updates events.last_synced_at. Current rows stay
        # intact; their individual timestamps prove the archived batch instead.
        if not allow_archived or event[1] != "completed":
            raise ValueError("database does not contain this exact captured batch")
        for table in ("current_event_matches", "current_event_team_ties", "current_event_brackets", "current_event_group_standings"):
            column = "updated_at" if table.endswith("standings") else "last_synced_at"
            mismatch = conn.execute(f"SELECT count(*) FROM {table} WHERE event_id=? AND ({column} IS NULL OR {column} != ?)",
                                    (EVENT_ID, snapshot["captured_at"])).fetchone()[0]
            if mismatch:
                raise ValueError(f"{table}: current data no longer matches archived batch")
    if not snapshot.get("full"):
        raise ValueError("finalization requires a --full reconciled capture")
    if not snapshot["champ"].get("isFinished"):
        raise ValueError("official championship is not finished")
    if {p["Key"] for p in snapshot["champ"]["events"]} != set(PROJECTS):
        raise ValueError("latest capture is missing championship projects")
    required = {"champ.json", "match/live.json"}
    required.update(f"match/d2026-10-{day:02d}.json" for day in range(19, 26))
    required.update(f"{section}/{project}.json" for project in PROJECTS for section in ("entries", "brackets"))
    required.update(f"groups/{project}.json" for project in PROJECTS if PROJECTS[project] in ("MT", "WT"))
    if any(not snapshot.get("resources", {}).get(path) for path in required):
        raise ValueError("latest capture is missing required dates/resources")
    if set(snapshot.get("bracket_projects", [])) != set(PROJECT_NAMES) or set(snapshot.get("standings_projects", [])) != {"MT", "WT"}:
        raise ValueError("latest capture has unpublished brackets/standings")
    snapshot_finals = [b for b in snapshot["brackets"] if b["draw_code"] == "MAIN" and b["round_code"] == "F"]
    if {b["sub_event_type_code"] for b in snapshot_finals if b["status"] in ("completed", "walkover") and b["winner_side"]} != set(PROJECT_NAMES):
        raise ValueError("latest capture has unfinished finals")
    for final in snapshot_finals:
        table = "current_event_team_ties" if final["sub_event_type_code"] in ("MT", "WT") else "current_event_matches"
        actual = conn.execute(f"SELECT * FROM {table} WHERE event_id=? AND external_match_code=?",
                              (EVENT_ID, final["external_unit_code"])).fetchone()
        if not final_result_matches(conn, final, actual):
            raise ValueError(f"{final['sub_event_type_code']}: missing or conflicting actual final result")
    if any(item["status"] in ("scheduled", "live") for item in snapshot["matches"] + snapshot["team_ties"]):
        raise ValueError("latest capture has unfinished matches/ties")
    counts = {}
    for table in ("current_event_matches", "current_event_team_ties"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE event_id=?", (EVENT_ID,)).fetchone()[0]
        pending = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE event_id=? AND status IN ('scheduled','live')", (EVENT_ID,)).fetchone()[0]
        missing_winners = conn.execute(f"SELECT * FROM {table} WHERE event_id=? AND status IN ('completed','walkover') AND winner_side IS NULL", (EVENT_ID,)).fetchall()
        invalid = sum(not (table == "current_event_matches" and unplayed_double_walkover(row))
                      for row in missing_winners)
        if pending or invalid:
            raise ValueError(f"{table}: {pending} pending units, {invalid} missing winners")
    if not counts["current_event_matches"]:
        raise ValueError("no actual matches to archive")
    for code in PROJECT_NAMES:
        final = conn.execute("SELECT status,winner_side FROM current_event_brackets WHERE event_id=? AND sub_event_type_code=? AND draw_code='MAIN' AND round_code='F'", (EVENT_ID, code)).fetchall()
        if len(final) != 1 or final[0]["status"] not in ("completed", "walkover") or not final[0]["winner_side"]:
            raise ValueError(f"{code}: official final not complete")
    for prefix, parent_col, side_col in (("current_event_match", "current_match_id", "current_match_side_id"),
                                          ("current_event_team_tie", "current_team_tie_id", "current_team_tie_side_id")):
        parents = "current_event_matches" if prefix.endswith("match") else "current_event_team_ties"
        invalid = conn.execute(f"""SELECT COUNT(*) FROM {parents} p WHERE event_id=? AND status IN ('completed','walkover')
            AND ((SELECT COUNT(*) FROM {prefix}_sides s WHERE s.{parent_col}=p.{parent_col}) != 2
            OR EXISTS (SELECT 1 FROM {prefix}_sides s WHERE s.{parent_col}=p.{parent_col}
              AND NOT EXISTS (SELECT 1 FROM {prefix}_side_players sp WHERE sp.{side_col}=s.{side_col})))""", (EVENT_ID,)).fetchone()[0]
        if invalid:
            raise ValueError(f"{parents}: {invalid} completed units missing players/rosters")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="校验本地快照并归档 2026 亚锦赛（不联网）")
    add_options(parser, database=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true", help="兼容旧命令；归档现在默认只读取本地快照")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    with event_lock(args.data_root, wait=True):
        snapshot = read_json(args.data_root / "normalized/current.json")
        with sqlite3.connect(f"{args.db_path.resolve().as_uri()}?mode=ro", uri=True) as conn:
            print(json.dumps(validate_current(conn, snapshot, allow_archived=args.replace), ensure_ascii=False))
        command = [sys.executable, str(ROOT / "scripts/db/promote_current_event.py"), "--event-id", str(EVENT_ID), "--db-path", str(args.db_path)]
        if args.dry_run:
            command.append("--dry-run")
        if args.replace:
            command.append("--replace")
        return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"亚锦赛归档中止：{exc}", file=sys.stderr)
        raise SystemExit(1)
