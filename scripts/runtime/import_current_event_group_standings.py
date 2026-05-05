#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import captured WTT pool standings into current_event_group_standings."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_stage_label(stage_label: str) -> str:
    normalized = stage_label.strip()
    if "groups" in normalized.lower():
        return "Groups"
    return normalized


def infer_stage_label(input_dir: Path, explicit: str | None) -> str:
    if explicit:
        return canonical_stage_label(explicit)
    summary_path = input_dir / "standings_capture_summary.json"
    if summary_path.exists():
        summary = load_json(summary_path)
        stage_label = summary.get("stage_label")
        if isinstance(stage_label, str) and stage_label.strip():
            return canonical_stage_label(stage_label)
    raise ValueError("stage_label is required when standings_capture_summary.json is missing or incomplete")


def infer_event_id(files: list[Path], explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    for path in files:
        data = load_json(path)
        event_id = ((data.get("competition_meta") or {}).get("event_id"))
        if isinstance(event_id, int):
            return event_id
        if isinstance(event_id, str) and event_id.isdigit():
            return int(event_id)
    raise ValueError("event_id is required when standings files do not include competition_meta.event_id")


def load_source_urls(input_dir: Path) -> dict[str, str]:
    summary_path = input_dir / "standings_capture_summary.json"
    if not summary_path.exists():
        return {}
    summary = load_json(summary_path)
    urls = summary.get("captured_urls")
    return urls if isinstance(urls, dict) else {}


def import_file(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    stage_label: str,
    team_code: str,
    source_url: str | None,
    standings_path: Path,
) -> int:
    payload = load_json(standings_path)
    rows = payload.get("rows") or []
    updated_at = utc_now_iso()

    conn.execute(
        """
        DELETE FROM current_event_group_standings
        WHERE event_id = ? AND stage_label = ? AND team_code = ?
        """,
        (event_id, stage_label, team_code),
    )

    insert_sql = """
        INSERT INTO current_event_group_standings (
            event_id,
            stage_label,
            team_code,
            group_code,
            organization_code,
            team_name,
            qualification_mark,
            played,
            won,
            lost,
            result,
            rank,
            score_for,
            score_against,
            games_won,
            games_lost,
            players_json,
            source_url,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    count = 0
    for row in rows:
        conn.execute(
            insert_sql,
            (
                event_id,
                stage_label,
                team_code,
                row.get("group"),
                row.get("organization"),
                row.get("team_name"),
                row.get("qualification_mark"),
                row.get("played"),
                row.get("won"),
                row.get("lost"),
                row.get("result"),
                row.get("rank"),
                row.get("for"),
                row.get("against"),
                row.get("games_won"),
                row.get("games_lost"),
                json.dumps(row.get("players") or [], ensure_ascii=False),
                source_url,
                updated_at,
            ),
        )
        count += 1
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import WTT pool standings JSON into current_event_group_standings.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory containing MTEAM_standings.json / WTEAM_standings.json")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--event-id", type=int)
    parser.add_argument("--stage-label", type=str)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_dir = args.input_dir.resolve()
    db_path = args.db_path.resolve()

    files = sorted(input_dir.glob("*_standings.json"))
    if not files:
        print(f"No *_standings.json files found in {input_dir}", file=sys.stderr)
        return 1

    stage_label = infer_stage_label(input_dir, args.stage_label)
    event_id = infer_event_id(files, args.event_id)
    source_urls = load_source_urls(input_dir)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN")
        imported: list[tuple[str, int]] = []
        for path in files:
            team_code = path.stem.replace("_standings", "").upper()
            count = import_file(
                conn,
                event_id=event_id,
                stage_label=stage_label,
                team_code=team_code,
                source_url=source_urls.get(team_code),
                standings_path=path,
            )
            imported.append((team_code, count))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for team_code, count in imported:
        print(f"Imported {count} rows for {team_code} ({stage_label}) into current_event_group_standings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
