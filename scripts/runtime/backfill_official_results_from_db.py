#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-import an event's *stored* GetOfficialResult payloads from the DB.

WTT's ``GetOfficialResult`` endpoint only returns a rolling window (~100) of the
most recent results, so once early-round matches scroll out of that window a
fresh scrape no longer covers them. Any importer fix that lands *after* those
matches dropped out (e.g. the player_id / round-label fixes) can therefore never
reach them through a normal re-scrape + re-import.

This rebuilds the official-results payload from
``current_event_matches.raw_source_payload`` — the raw item we captured when each
match was still fresh — and re-runs the regular official-results importer against
it. The current importer logic (player_id resolution, round mapping, scores, …)
is thus applied to every match ever captured, not just the ones still in WTT's
window. The importer is an idempotent upsert keyed on ``external_match_code``, so
this is safe to run repeatedly.

Usage::

    python scripts/runtime/backfill_official_results_from_db.py --event-id 3242
    python scripts/runtime/backfill_official_results_from_db.py --event-id 3242 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"


def collect_stored_payload(db_path: Path, event_id: int) -> list[dict]:
    """Reconstruct the official-results item list from stored raw payloads."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT raw_source_payload
            FROM current_event_matches
            WHERE event_id = ?
              AND source_status = 'Official'
              AND raw_source_payload IS NOT NULL
            """,
            (event_id,),
        ).fetchall()
    finally:
        conn.close()

    payload: list[dict] = []
    for row in rows:
        try:
            item = json.loads(row["raw_source_payload"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(item, dict) and isinstance(item.get("match_card"), dict):
            payload.append(item)
    return payload


def null_player_count(db_path: Path, event_id: int) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM current_event_matches m
                JOIN current_event_match_sides s ON s.current_match_id = m.current_match_id
                JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
                WHERE m.event_id = ?
                  AND m.current_team_tie_id IS NULL
                  AND m.source_status = 'Official'
                  AND p.player_id IS NULL
                """,
                (event_id,),
            ).fetchone()[0]
        )
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只重建并统计可回填规模，不实际导入",
    )
    args = parser.parse_args()

    db_path = args.db_path.resolve()
    payload = collect_stored_payload(db_path, args.event_id)
    if not payload:
        print(f"no stored official payloads found for event {args.event_id}", file=sys.stderr)
        return 1

    before = null_player_count(db_path, args.event_id)
    print(
        f"Reconstructed {len(payload)} stored official item(s) for event {args.event_id}; "
        f"NULL player_id (Official individual) before: {before}"
    )

    if args.dry_run:
        print("--dry-run: skip import")
        return 0

    with tempfile.TemporaryDirectory(prefix="ittf-official-backfill-") as tmp:
        event_dir = Path(tmp) / str(args.event_id)
        event_dir.mkdir(parents=True)
        (event_dir / "GetOfficialResult.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "import_current_event_official_results.py"),
            "--event-id",
            str(args.event_id),
            "--db-path",
            str(db_path),
            "--live-event-data-root",
            str(Path(tmp).resolve()),
        ]
        print(f"> {' '.join(cmd)}")
        rc = subprocess.run(cmd).returncode
        if rc != 0:
            return rc

    after = null_player_count(db_path, args.event_id)
    print(f"NULL player_id (Official individual) after: {after} (was {before})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
