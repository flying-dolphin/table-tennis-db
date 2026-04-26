#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from lib.career_best import normalize_career_best_month


logger = logging.getLogger("normalize_career_best_month")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize legacy career_best_week values to career_best_month")
    parser.add_argument("--profile-dir", default="data/player_profiles")
    parser.add_argument("--corrupt-file", default="", help="Single known-corrupt JSON file path to handle specially")
    parser.add_argument(
        "--missing-log",
        default="data/player_profiles/logs/missing_career_best_fields.log",
        help="Log file for JSON files missing both career_best_week and career_best_month",
    )
    return parser


def normalize_file(json_path: Path, corrupt_file: Path | None) -> tuple[str, str | None]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return "skipped", None

    current_rank = data.get("current_rank")
    try:
        has_current_rank = current_rank is not None and int(current_rank) > 0
    except (TypeError, ValueError):
        has_current_rank = False
    has_best_rank = data.get("career_best_rank") is not None

    if data.get("career_best_month"):
        return "already_month", None

    if json_path == corrupt_file:
        raw_week = str(data.get("career_best_week") or "")
        raw_week = raw_week.split("Events:", 1)[0].strip()
        normalized = normalize_career_best_month(raw_week, "week")
    elif data.get("career_best_week"):
        normalized = normalize_career_best_month(str(data.get("career_best_week")), "week")
    else:
        if has_current_rank or has_best_rank:
            reason = "missing_best_period_with_best_rank" if has_best_rank else "missing_best_with_rank"
            return (
                "missing_field",
                f"{reason}\t{json_path}\tplayer_id={data.get('player_id', '')}\tenglish_name={data.get('english_name') or data.get('name') or ''}\tcurrent_rank={data.get('current_rank')}\tcareer_best_rank={data.get('career_best_rank')}",
            )
        return "normal_no_rank", None

    if not normalized.month:
        return "unparsed", f"unparsed\t{json_path}\tplayer_id={data.get('player_id', '')}\traw={data.get('career_best_week', '')}"

    data["career_best_month"] = normalized.month
    data.pop("career_best_week", None)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return "updated", None


def main() -> int:
    args = build_parser().parse_args()
    profile_dir = Path(args.profile_dir)
    targets = [profile_dir / "orig", profile_dir / "cn"]
    corrupt_file = Path(args.corrupt_file).resolve() if args.corrupt_file else None
    missing_log_path = Path(args.missing_log)
    missing_log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    missing_entries: list[str] = []
    counts = {
        "updated": 0,
        "already_month": 0,
        "missing_field": 0,
        "normal_no_rank": 0,
        "unparsed": 0,
        "skipped": 0,
    }

    for directory in targets:
        if not directory.exists():
            logger.info("Skip missing directory: %s", directory)
            continue
        for json_path in sorted(directory.glob("player_*.json")):
            status, detail = normalize_file(json_path.resolve(), corrupt_file)
            counts[status] += 1
            if detail:
                missing_entries.append(detail)

    missing_log_path.write_text("\n".join(missing_entries) + ("\n" if missing_entries else ""), encoding="utf-8")

    logger.info(
        "Finished normalization: updated=%d already_month=%d missing_field=%d normal_no_rank=%d unparsed=%d skipped=%d",
        counts["updated"],
        counts["already_month"],
        counts["missing_field"],
        counts["normal_no_rank"],
        counts["unparsed"],
        counts["skipped"],
    )
    logger.info("Missing-field log: %s", missing_log_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
