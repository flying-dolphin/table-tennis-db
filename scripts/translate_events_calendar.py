#!/usr/bin/env python3
"""
Translate events calendar files from orig to cn using dictionary + LLM fallback.

Name field: dict first, LLM fallback if not found.
Location field: dict only; logs error if not found.
Date field: rule-based conversion.
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
from lib.translator import LLMTranslator

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


def translate_date(date_str: str) -> str:
    """Translate date field: '02-05 Jan' -> '01-02至01-05'; '28 Jan-01 Feb' -> '01-28至02-01'."""
    date_str = date_str.strip()

    two_month_match = re.match(r"(\d+)\s+(\w+)-(\d+)\s+(\w+)", date_str)
    if two_month_match:
        start_day, start_month_abbr, end_day, end_month_abbr = two_month_match.groups()

        start_month_key = start_month_abbr.lower()
        start_month_num = MONTH_MAP.get(start_month_key, {}).get("translated", start_month_abbr)
        if start_month_num == start_month_abbr:
            return date_str

        end_month_key = end_month_abbr.lower()
        end_month_num = MONTH_MAP.get(end_month_key, {}).get("translated", end_month_abbr)
        if end_month_num == end_month_abbr:
            return date_str

        return f"{start_month_num}-{start_day}至{end_month_num}-{end_day}"

    match = re.match(r"(\d+)-(\d+)\s+(\w+)", date_str)
    if not match:
        return date_str

    start_day, end_day, month_abbr = match.groups()

    month_key = month_abbr.lower()
    month_num = MONTH_MAP.get(month_key, {}).get("translated", month_abbr)
    if month_num == month_abbr:
        return date_str

    return f"{month_num}-{start_day}至{month_num}-{end_day}"


def translate_name_dict(name: str) -> str | None:
    """Try dict translation for name. Returns translated string or None if not found in dict."""
    name_stripped = name.strip()
    match = re.match(r"^(.*?)\s+(\d{4})\s*$", name_stripped)
    if match:
        base, year = match.group(1).strip(), match.group(2)
        translated_base = DICTIONARY.get(base.lower())
        if translated_base is not None:
            return f"{year}年{translated_base}"
        translated_full = DICTIONARY.get(name_stripped.lower())
        if translated_full is not None:
            return f"{year}年{translated_full}"
        return None
    return DICTIONARY.get(name_stripped.lower())


def split_name_year(name: str) -> tuple[str, str | None]:
    """Split event name into (base_name, year_str) or (name, None)."""
    name_stripped = name.strip()
    match = re.match(r"^(.*?)\s+(\d{4})\s*$", name_stripped)
    if match:
        return match.group(1).strip(), match.group(2)
    return name_stripped, None


def format_llm_name(translated_base: str, year: str | None) -> str:
    if year:
        return f"{year}年{translated_base}"
    return translated_base


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


def translate_file(file_path: Path, cn_file: Path, args: argparse.Namespace) -> int:
    """Translate a single calendar file. Returns 0 on success, 1 on failure."""
    data = json.loads(file_path.read_text(encoding="utf-8"))
    events = data.get("events", [])
    logger.info("Total events: %d in %s", len(events), file_path.name)

    # Load existing cn translations for incremental skip
    existing_by_name: dict[str, dict] = {}
    if not args.force and cn_file.exists():
        try:
            cn_data = json.loads(cn_file.read_text(encoding="utf-8"))
            existing_by_name = {
                e["name"]: e for e in cn_data.get("events", []) if "name" in e and "name_zh" in e
            }
            if existing_by_name:
                logger.info("Found %d already-translated events in cn file", len(existing_by_name))
        except Exception:
            pass

    # Build base_events: apply date/location (dict), restore name_zh from existing cn
    base_events: list[dict] = []
    llm_items: dict[str, str] = {}   # key -> base_name_without_year
    name_years: dict[str, str] = {}  # key -> year_str
    key_to_idx: dict[str, int] = {}  # key -> index in base_events

    for i, event in enumerate(events):
        ev = dict(event)
        name = event.get("name", "")

        # Date: always translate fresh
        if "date" in event:
            ev["date_zh"] = translate_date(event["date"])

        # Location: dict only, error if missing
        if "location" in event:
            loc = event["location"].strip()
            loc_translated = DICTIONARY.get(loc.lower())
            if loc_translated is not None:
                ev["location_zh"] = loc_translated
            else:
                logger.error("Location not found in dictionary: %r (event: %s)", loc, name)

        # Name: restore from existing cn if available
        if name in existing_by_name:
            ev["name_zh"] = existing_by_name[name]["name_zh"]
            base_events.append(ev)
            continue

        # Name: try dict
        name_zh = translate_name_dict(name)
        if name_zh is not None:
            ev["name_zh"] = name_zh
            base_events.append(ev)
            continue

        # Name: needs LLM
        key = f"event_{i}.name"
        base_name, year = split_name_year(name)
        llm_items[key] = base_name
        if year:
            name_years[key] = year
        key_to_idx[key] = len(base_events)
        base_events.append(ev)

    skipped = len(existing_by_name)
    dict_translated = len(base_events) - skipped - len(llm_items)
    logger.info(
        "Name translation plan: %d skipped (existing), %d dict, %d need LLM",
        skipped, dict_translated, len(llm_items),
    )

    if not llm_items:
        save_json(cn_file, {**data, "events": base_events})
        logger.info("Saved (no LLM needed): %s", cn_file)
        return 0

    # Persist current state excluding events still pending LLM
    pending_indices: set[int] = set(key_to_idx.values())

    def persist_progress() -> None:
        saved_events = [ev for idx, ev in enumerate(base_events) if idx not in pending_indices]
        save_json(cn_file, {**data, "events": saved_events})
        logger.info("Saved progress (%d events): %s", len(saved_events), cn_file)

    def on_batch_complete(batch_index: int, batch_total: int, batch_result: dict[str, str]) -> None:
        for key, translated_base in batch_result.items():
            idx = key_to_idx.get(key)
            if idx is None:
                continue
            year = name_years.get(key)
            base_events[idx]["name_zh"] = format_llm_name(translated_base.replace(" ", ""), year)
            pending_indices.discard(idx)
        persist_progress()
        logger.info("Batch %d/%d done", batch_index, batch_total)

    translator = LLMTranslator(provider=args.provider, model=args.model)
    try:
        result = translator.translate(llm_items, on_batch_complete=on_batch_complete)
    except KeyboardInterrupt:
        logger.warning("Translation interrupted, saving completed batches to %s", cn_file)
        persist_progress()
        raise

    if result is None:
        logger.error("LLM translation failed, saving completed batches only")
        persist_progress()
        return 1

    # Final save with all events
    if pending_indices:
        # Some events were not returned by LLM
        missing = [events[key_to_idx[k]].get("name", k) for k in llm_items if key_to_idx[k] in pending_indices]
        logger.warning("LLM did not return translations for %d events: %s", len(missing), missing[:5])
        persist_progress()
        return 1

    save_json(cn_file, {**data, "events": base_events})
    logger.info("Saved: %s", cn_file)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate events calendar files from orig to cn")
    parser.add_argument("--file", type=str, help="Translate only one file from orig/")
    parser.add_argument("--year", type=int, help="Translate only events_calendar_{year}.json")
    parser.add_argument("--orig-dir", default=str(ORIG_DIR))
    parser.add_argument("--cn-dir", default=str(CN_DIR))
    parser.add_argument("--checkpoint", default=str(CHECKPOINT_PATH))
    parser.add_argument("--force", action="store_true", help="Ignore checkpoint and regenerate cn files")
    parser.add_argument("--rebuild-checkpoint", action="store_true", help="Rebuild checkpoint from existing cn files")
    parser.add_argument("--provider", default="minimax", help="LLM provider (minimax, kimi, qwen, glm, deepseek)")
    parser.add_argument("--model", default=None, help="LLM model name (default: provider's default model)")
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
            rc = translate_file(file_path, cn_file, args)
        except KeyboardInterrupt:
            logger.warning("Interrupted by user")
            return 130
        except Exception as exc:
            checkpoint.mark_failed(ck, str(exc), meta={"orig_path": str(file_path), "cn_path": str(cn_file)})
            logger.error("Translate failed: %s (%s)", file_path.name, exc)
            return 1

        if rc == 0:
            checkpoint.mark_done(ck, meta={"orig_path": str(file_path), "cn_path": str(cn_file)})
            logger.info("Translated: %s", file_path.name)
        else:
            checkpoint.mark_failed(ck, "translation failed", meta={"orig_path": str(file_path), "cn_path": str(cn_file)})
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
