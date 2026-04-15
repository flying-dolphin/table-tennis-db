#!/usr/bin/env python3
"""
Translate events calendar files from orig to cn using dictionary only.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.capture import save_json
from lib.checkpoint import CheckpointStore
from lib.translate_constant import MONTH_MAP

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
ORIG_DIR = PROJECT_ROOT / "data" / "events_calendar" / "orig"
CN_DIR = PROJECT_ROOT / "data" / "events_calendar" / "cn"
CHECKPOINT_PATH = PROJECT_ROOT / "data" / "events_calendar" / "checkpoint_translate_events_calendar.json"
DICT_PATH = PROJECT_ROOT / "scripts" / "data" / "translation_dict_v2.json"


def _translate_ck(filename: str) -> str:
    return f"events_calendar|file:{filename}|translate"


def load_dictionary() -> dict[str, str]:
    """Load translation dictionary."""
    if not DICT_PATH.exists():
        logger.warning("Dictionary not found: %s", DICT_PATH)
        return {}

    try:
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("Failed to load dictionary: %s", e)
        return {}

    entries = data.get("entries", {})
    result = {}
    for key, value in entries.items():
        if isinstance(value, dict) and "translated" in value:
            result[key] = value["translated"]
    return result


DICTIONARY: dict[str, str] = {}


def translated_field_name(field: str) -> str:
    return f"{field}_zh"


def translate_text(text: str) -> str:
    """Translate text using dictionary only."""
    key = text.strip().lower()
    return DICTIONARY.get(key, text)


def translate_date(date_str: str) -> str:
    """Translate date field: '02-05 Jan' -> '01-02至01-05'."""
    match = re.match(r"(\d+)-(\d+)\s+(\w+)", date_str.strip())
    if not match:
        return date_str

    start_day, end_day, month_abbr = match.groups()

    month_key = month_abbr.lower()
    month_num = MONTH_MAP.get(month_key, {}).get("translated", month_abbr)
    if month_num == month_abbr:
        return date_str

    return f"{month_num}-{start_day}至{month_num}-{end_day}"


def translate_event(event: dict) -> dict:
    """Translate a single event using dictionary."""
    translated = dict(event)

    if "name" in event:
        translated[translated_field_name("name")] = translate_text(event["name"])

    if "date" in event:
        translated[translated_field_name("date")] = translate_date(event["date"])

    if "location" in event:
        translated[translated_field_name("location")] = translate_text(event["location"])

    return translated


def translate_calendar_data(data: dict) -> dict:
    """Translate calendar data using dictionary only."""
    global DICTIONARY
    if not DICTIONARY:
        DICTIONARY = load_dictionary()

    translated = dict(data)
    translated["events"] = []

    for event in data.get("events", []):
        translated["events"].append(translate_event(event))

    return translated


def bootstrap_checkpoint(checkpoint: CheckpointStore, orig_dir: Path, cn_dir: Path) -> None:
    if checkpoint.path.exists() and checkpoint.has_any_completed():
        return
    if not orig_dir.exists():
        return
    with checkpoint.bulk():
        for orig_file in sorted(orig_dir.glob("events_calendar_*.json")):
            cn_file = cn_dir / orig_file.name
            if not cn_file.exists():
                continue
            try:
                json.loads(cn_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            ck = _translate_ck(orig_file.name)
            if not checkpoint.is_done(ck):
                checkpoint.mark_done(ck, meta={"bootstrapped_from": str(cn_file)})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate events calendar files from orig to cn")
    parser.add_argument("--file", type=str, help="Translate only one file from orig/")
    parser.add_argument("--year", type=int, help="Translate only events_calendar_{year}.json")
    parser.add_argument("--orig-dir", default=str(ORIG_DIR))
    parser.add_argument("--cn-dir", default=str(CN_DIR))
    parser.add_argument("--checkpoint", default=str(CHECKPOINT_PATH))
    parser.add_argument("--force", action="store_true", help="Ignore checkpoint and regenerate cn files")
    parser.add_argument("--rebuild-checkpoint", action="store_true", help="Rebuild checkpoint from existing cn files")
    return parser


def run(args: argparse.Namespace) -> int:
    global DICTIONARY
    orig_dir = Path(args.orig_dir)
    cn_dir = Path(args.cn_dir)
    checkpoint = CheckpointStore(Path(args.checkpoint))
    if args.rebuild_checkpoint:
        checkpoint.reset()

    if not orig_dir.exists():
        logger.error("Orig directory does not exist: %s", orig_dir)
        return 1

    DICTIONARY = load_dictionary()
    logger.info("Loaded %d dictionary entries", len(DICTIONARY))

    cn_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_checkpoint(checkpoint, orig_dir, cn_dir)

    if args.file:
        files = [orig_dir / args.file]
    elif args.year:
        files = [orig_dir / f"events_calendar_{args.year}.json"]
    else:
        files = sorted(orig_dir.glob("events_calendar_*.json"))

    for file_path in files:
        if not file_path.exists():
            logger.error("Orig file does not exist: %s", file_path)
            return 1

        ck = _translate_ck(file_path.name)
        cn_file = cn_dir / file_path.name

        if (not args.force) and checkpoint.is_done(ck) and cn_file.exists():
            try:
                json.loads(cn_file.read_text(encoding="utf-8"))
                logger.info("Skipping translated file (checkpoint): %s", file_path.name)
                continue
            except Exception:
                logger.warning("Checkpoint done but cn file unreadable, re-translating: %s", cn_file)

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            translated = translate_calendar_data(data)
            save_json(cn_file, translated)
            checkpoint.mark_done(ck, meta={"orig_path": str(file_path), "cn_path": str(cn_file)})
            logger.info("Translated: %s", file_path.name)
        except Exception as exc:
            checkpoint.mark_failed(ck, str(exc), meta={"orig_path": str(file_path), "cn_path": str(cn_file)})
            logger.error("Translate failed: %s (%s)", file_path.name, exc)
            return 1

    return 0


def main() -> int:
    try:
        args = build_parser().parse_args()
        return run(args)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
