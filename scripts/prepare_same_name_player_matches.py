#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare player-centric match evidence for same-name player resolution.

Historical event match files only contain names and countries. When a side
mentions a same-name player group, import_matches.py needs player-centric
matches for every candidate player_id in that group before it can resolve the
canonical player_id conservatively.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "data" / "event_matches" / "cn"
DEFAULT_SAME_NAME_PLAYERS_PATH = PROJECT_ROOT / "scripts" / "data" / "same_name_players.txt"
DEFAULT_MATCHES_COMPLETE_DIR = PROJECT_ROOT / "data" / "matches_complete"
DEFAULT_FROM_DATE = "2024-01-01"

PLAYER_TOKEN_RE = re.compile(r"^(.+?)\s*\(([A-Za-z]{3})\)$")


def normalize_name_key(name: str) -> str:
    return " ".join(sorted((name or "").lower().split()))


def sanitize_filename(value: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return s[:120] if s else "unknown"


def player_output_filename(player_name: str, player_id: int) -> str:
    return f"player_{sanitize_filename(str(player_id))}_{sanitize_filename(player_name)}.json"


def parse_event_id(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_event_id_from_filename(path: Path) -> int | None:
    match = re.search(r"_(\d+)\.json$", path.name, flags=re.IGNORECASE)
    return parse_event_id(match.group(1)) if match else None


def load_same_name_groups(path: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    if not path.exists():
        return groups

    seen: set[tuple[int, str, str]] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",", 2)]
        if len(parts) != 3 or not parts[0].isdigit():
            continue
        player_id = int(parts[0])
        player_name = parts[1]
        country_code = parts[2].upper()
        if not player_name or not country_code:
            continue
        row_key = (player_id, player_name, country_code)
        if row_key in seen:
            continue
        seen.add(row_key)
        groups.setdefault((normalize_name_key(player_name), country_code), []).append(
            {
                "player_id": player_id,
                "player_name": player_name,
                "country_code": country_code,
            }
        )

    for rows in groups.values():
        rows.sort(key=lambda row: int(row["player_id"]))
    return groups


def iter_side_entries(match: dict[str, Any]) -> list[str]:
    entries: list[str] = []
    for key in ("side_a", "side_b"):
        raw_items = match.get(key) or []
        if isinstance(raw_items, list):
            entries.extend(str(item).strip() for item in raw_items if str(item).strip())

    raw_row_text = str(match.get("raw_row_text") or "")
    for segment in raw_row_text.split("|"):
        segment = segment.strip()
        if PLAYER_TOKEN_RE.match(segment):
            entries.append(segment)
    return entries


def parse_player_entry(entry: str) -> tuple[str, str] | None:
    match = PLAYER_TOKEN_RE.match(entry.strip())
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip().upper()


def selected_event_files(source_dir: Path, event_ids: set[int] | None) -> list[tuple[Path, dict[str, Any]]]:
    files: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(source_dir.glob("*.json")):
        filename_event_id = parse_event_id_from_filename(path)
        if event_ids is not None and filename_event_id is not None and filename_event_id not in event_ids:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload_event_id = parse_event_id(payload.get("event_id"))
        event_id = payload_event_id if payload_event_id is not None else filename_event_id
        if event_ids is not None and event_id not in event_ids:
            continue
        files.append((path, payload))
    return files


def cn_evidence_exists(matches_complete_dir: Path, player_id: int) -> bool:
    cn_dir = matches_complete_dir / "cn"
    return any(cn_dir.glob(f"player_{player_id}_*.json"))


def build_preparation_plan(
    *,
    source_dir: Path,
    event_ids: Sequence[int] | None,
    same_name_players_path: Path,
    matches_complete_dir: Path,
    from_date: str | None,
    force: bool,
) -> dict[str, Any]:
    selected_ids = sorted({int(event_id) for event_id in event_ids}) if event_ids else []
    selected_ids_set = set(selected_ids) if selected_ids else None
    groups = load_same_name_groups(same_name_players_path)

    targets_by_id: dict[int, dict[str, Any]] = {}
    years: list[int] = []

    for _path, payload in selected_event_files(source_dir, selected_ids_set):
        year = parse_event_id(payload.get("event_year"))
        if year is not None:
            years.append(year)
        for match in payload.get("matches") or []:
            if not isinstance(match, dict):
                continue
            for entry in iter_side_entries(match):
                parsed = parse_player_entry(entry)
                if parsed is None:
                    continue
                player_name, country_code = parsed
                for row in groups.get((normalize_name_key(player_name), country_code), []):
                    player_id = int(row["player_id"])
                    targets_by_id[player_id] = {
                        "player_id": player_id,
                        "player_name": row["player_name"],
                        "country_code": row["country_code"],
                    }

    effective_from_date = from_date
    if effective_from_date is None:
        effective_from_date = f"{min(years):04d}-01-01" if years else DEFAULT_FROM_DATE

    targets: list[dict[str, Any]] = []
    for player_id in sorted(targets_by_id):
        row = dict(targets_by_id[player_id])
        exists = cn_evidence_exists(matches_complete_dir, player_id)
        row["cn_exists"] = exists
        row["needs_scrape"] = bool(force or not exists)
        targets.append(row)

    return {
        "event_ids": selected_ids,
        "from_date": effective_from_date,
        "source_dir": str(source_dir),
        "same_name_players": str(same_name_players_path),
        "matches_complete_dir": str(matches_complete_dir),
        "targets": targets,
    }


def run_command(cmd: list[str]) -> None:
    print("[INFO] " + " ".join(cmd))
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


def prepare_targets(
    plan: dict[str, Any], *, headless: bool, force: bool, cdp_port: int | None = None
) -> None:
    matches_complete_dir = Path(plan["matches_complete_dir"])
    orig_dir = matches_complete_dir / "orig"
    cn_dir = matches_complete_dir / "cn"
    from_date = str(plan["from_date"])

    for target in plan["targets"]:
        if not target["needs_scrape"]:
            print(
                "[INFO] Player-centric matches already translated: "
                f"{target['player_name']} ({target['country_code']}) #{target['player_id']}"
            )
            continue

        expected_file = player_output_filename(target["player_name"], int(target["player_id"]))
        scrape_cmd = [
            sys.executable,
            "scripts/scrape_matches_from_player.py",
            "--player-name",
            target["player_name"],
            "--player-country",
            target["country_code"],
            "--player-id",
            str(target["player_id"]),
            "--from-date",
            from_date,
            "--output-dir",
            str(matches_complete_dir),
            # 同名消歧证据：某成员窗口内无比赛是合法结果，不应视为致命错误。
            "--allow-empty",
        ]
        if cdp_port is not None:
            scrape_cmd += ["--cdp-port", str(cdp_port)]
        if headless:
            scrape_cmd.append("--headless")
        if force:
            scrape_cmd.append("--force")
        run_command(scrape_cmd)

        orig_file = orig_dir / expected_file
        if not orig_file.exists():
            candidates = sorted(orig_dir.glob(f"player_{target['player_id']}_*.json"))
            if candidates:
                expected_file = candidates[-1].name
            else:
                raise FileNotFoundError(f"Scrape did not produce player-centric matches for player_id={target['player_id']}")

        translate_cmd = [
            sys.executable,
            "scripts/translate_matches.py",
            "--file",
            expected_file,
            "--orig-dir",
            str(orig_dir),
            "--cn-dir",
            str(cn_dir),
        ]
        run_command(translate_cmd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare same-name player-centric match evidence")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--event-id", type=int, nargs="+", default=None)
    parser.add_argument("--same-name-players", type=Path, default=DEFAULT_SAME_NAME_PLAYERS_PATH)
    parser.add_argument("--matches-complete-dir", type=Path, default=DEFAULT_MATCHES_COMPLETE_DIR)
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--force", action="store_true", help="Re-scrape even when translated player evidence exists")
    parser.add_argument("--headless", action="store_true", help="Pass --headless to scrape_matches_from_player.py")
    parser.add_argument(
        "--cdp-port",
        type=int,
        default=None,
        help="Pass --cdp-port to scrape_matches_from_player.py (reuse an existing Chrome).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print the preparation plan")
    parser.add_argument("--summary-json", default=None, help="Write preparation plan/result JSON to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan = build_preparation_plan(
        source_dir=args.source_dir,
        event_ids=args.event_id,
        same_name_players_path=args.same_name_players,
        matches_complete_dir=args.matches_complete_dir,
        from_date=args.from_date,
        force=args.force,
    )

    needed = [target for target in plan["targets"] if target["needs_scrape"]]
    print("Same-name player-centric matches preparation:")
    print(f"  Event ids:       {' '.join(str(e) for e in plan['event_ids']) if plan['event_ids'] else '(full scan)'}")
    print(f"  From date:       {plan['from_date']}")
    print(f"  Targets:         {len(plan['targets'])}")
    print(f"  Need scrape:     {len(needed)}")
    for target in plan["targets"]:
        status = "needs scrape" if target["needs_scrape"] else "exists"
        print(f"    - {target['player_id']} {target['player_name']} ({target['country_code']}): {status}")

    result = {**plan, "dry_run": bool(args.dry_run)}
    if not args.dry_run:
        prepare_targets(plan, headless=args.headless, force=args.force, cdp_port=args.cdp_port)
        result["completed"] = True

    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Summary JSON: {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
