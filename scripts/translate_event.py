#!/usr/bin/env python3
"""
Translate events_list files from orig to cn.

Only translates: name, event_type, event_kind.
Skips events already present in cn file (by event_id), unless --force.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.capture import save_json
from lib.translator import LLMTranslator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
ORIG_DIR = PROJECT_ROOT / "data" / "events_list" / "orig"
CN_DIR = PROJECT_ROOT / "data" / "events_list" / "cn"

TRANSLATE_FIELDS = ("name", "event_type", "event_kind")
SKIP_VALUES = {"--", ""}


def find_latest_file(directory: Path) -> Path | None:
    files = sorted(directory.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cn_event_ids(cn_path: Path) -> set[int]:
    if not cn_path.exists():
        return set()
    try:
        data = load_json(cn_path)
        return {e["event_id"] for e in data.get("events", []) if "event_id" in e}
    except Exception:
        return set()


def collect_translate_items(events: list[dict], skip_ids: set[int]) -> dict[str, str]:
    """Collect fields to translate from untranslated events.

    Returns dict like {"3298.name": "WTT Youth ...", "3298.event_type": "WTT Youth Contender Series"}
    """
    items: dict[str, str] = {}
    for event in events:
        eid = event.get("event_id")
        if eid in skip_ids:
            continue
        for field in TRANSLATE_FIELDS:
            value = event.get(field, "")
            if value in SKIP_VALUES:
                continue
            items[f"{eid}.{field}"] = value
    return items


def apply_translations(events: list[dict], translated: dict[str, str], skip_ids: set[int]) -> list[dict]:
    result = []
    for event in events:
        ev = dict(event)
        eid = event.get("event_id")
        if eid not in skip_ids:
            for field in TRANSLATE_FIELDS:
                key = f"{eid}.{field}"
                if key in translated:
                    ev[field] = translated[key]
        result.append(ev)
    return result


def merge_with_existing_cn(orig_data: dict, cn_path: Path, translated_events: list[dict]) -> dict:
    """Merge newly translated events with existing cn data."""
    translated_by_id = {e["event_id"]: e for e in translated_events}

    if cn_path.exists():
        try:
            cn_data = load_json(cn_path)
            for e in cn_data.get("events", []):
                eid = e.get("event_id")
                if eid is not None and eid not in translated_by_id:
                    translated_by_id[eid] = e
        except Exception:
            pass

    orig_order = [e["event_id"] for e in orig_data.get("events", [])]
    merged_events = [translated_by_id[eid] for eid in orig_order if eid in translated_by_id]

    result = dict(orig_data)
    result["events"] = merged_events
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate events_list files from orig to cn")
    parser.add_argument("--file", type=str, help="Specify orig file name (default: latest in orig/)")
    parser.add_argument("--orig-dir", default=str(ORIG_DIR))
    parser.add_argument("--cn-dir", default=str(CN_DIR))
    parser.add_argument("--force", action="store_true", help="Re-translate all events, ignoring existing cn file")
    parser.add_argument("--event-id", type=int, nargs="+", help="Only translate specific event_id(s)")
    parser.add_argument("--top", type=int, help="Only translate the first N events (in file order)")
    return parser


def run(args: argparse.Namespace) -> int:
    orig_dir = Path(args.orig_dir)
    cn_dir = Path(args.cn_dir)

    if not orig_dir.exists():
        logger.error("Orig directory does not exist: %s", orig_dir)
        return 1

    if args.file:
        orig_path = orig_dir / args.file
    else:
        orig_path = find_latest_file(orig_dir)
        if not orig_path:
            logger.error("No JSON files found in %s", orig_dir)
            return 1

    if not orig_path.exists():
        logger.error("Orig file does not exist: %s", orig_path)
        return 1

    cn_dir.mkdir(parents=True, exist_ok=True)
    cn_path = cn_dir / orig_path.name

    logger.info("Orig: %s", orig_path)
    logger.info("CN:   %s", cn_path)

    orig_data = load_json(orig_path)
    events = orig_data.get("events", [])
    logger.info("Total events: %d", len(events))

    # Filter by --event-id or --top
    target_ids: set[int] | None = None
    if args.event_id:
        target_ids = set(args.event_id)
        logger.info("Filtering to event_id(s): %s", target_ids)
    elif args.top:
        target_ids = {e["event_id"] for e in events[:args.top]}
        logger.info("Filtering to top %d events", args.top)

    skip_ids = set() if args.force else load_cn_event_ids(cn_path)
    if target_ids is not None:
        # Only translate specified events; skip everything else
        skip_ids = skip_ids | {e["event_id"] for e in events if e["event_id"] not in target_ids}
    if skip_ids:
        logger.info("Skipping %d events", len(skip_ids))

    items = collect_translate_items(events, skip_ids)
    if not items:
        logger.info("No new events to translate")
        if not cn_path.exists():
            save_json(cn_path, orig_data)
        return 0

    logger.info("Translating %d fields from %d events", len(items), len(items) // len(TRANSLATE_FIELDS) + 1)

    translator = LLMTranslator()
    translated = translator.translate(items)

    translated_events = apply_translations(events, translated, skip_ids)
    result = merge_with_existing_cn(orig_data, cn_path, translated_events)

    save_json(cn_path, result)
    logger.info("Saved: %s", cn_path)
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
