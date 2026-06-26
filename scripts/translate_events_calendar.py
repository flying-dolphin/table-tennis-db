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
from lib.translator import Translator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
ORIG_DIR = PROJECT_ROOT / "data" / "events_calendar" / "orig"
CN_DIR = PROJECT_ROOT / "data" / "events_calendar" / "cn"
CHECKPOINT_PATH = PROJECT_ROOT / "data" / "events_calendar" / "checkpoint_translate_events_calendar.json"
DICT_PATH = PROJECT_ROOT / "scripts" / "data" / "translation_dict_v2.json"


def _translate_ck(filename: str) -> str:
    return f"events_calendar|file:{filename}|translate"


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


def _translate_location_dict_only(translator: Translator, value: str) -> str | None:
    """Translate location via dictionary only, even when event names use LLM."""
    if hasattr(translator, "dict"):
        translated = translator.dict.translate(value, "locations")
    else:
        translated = translator.translate_one(value, "locations")
    if translated is not None and translated != value:
        return translated
    return None


def translate_file(file_path: Path, cn_file: Path, args: argparse.Namespace, translator: Translator) -> int:
    """Translate a single calendar file. Returns 0 on success, 1 on failure."""
    data = json.loads(file_path.read_text(encoding="utf-8"))
    events = data.get("events", [])
    logger.info("Total events: %d in %s", len(events), file_path.name)

    # Build base_events: apply date/location immediately, then batch translate names.
    base_events: list[dict] = []
    name_items: dict[str, str] = {}

    for i, event in enumerate(events):
        ev = dict(event)
        name = event.get("name", "")

        # Date: always translate fresh
        if "date" in event:
            ev["date_zh"] = translate_date(event["date"])

        # Location: dict only, error if missing
        if "location" in event:
            loc = event["location"].strip()
            loc_translated = _translate_location_dict_only(translator, loc)
            if loc_translated is not None:
                ev["location_zh"] = loc_translated
            else:
                logger.error("Location not found in dictionary: %r (event: %s)", loc, name)

        if isinstance(name, str) and name.strip():
            name_items[f"event_{i + 1}.name"] = name
        base_events.append(ev)

    name_results = translator.translate_batch(name_items, "events")
    if name_results is None:
        return 1

    translated_count = 0
    missing_names: list[str] = []
    for i, ev in enumerate(base_events):
        name = ev.get("name", "")
        key = f"event_{i + 1}.name"
        name_zh = name_results.get(key)
        if name_zh is not None and name_zh != name:
            ev["name_zh"] = name_zh
            translated_count += 1
        elif isinstance(name, str) and name.strip():
            missing_names.append(name)

    logger.info("Name translations: %d translated, %d missing", translated_count, len(missing_names))
    if missing_names:
        logger.warning("Missing %d event names: %s", len(missing_names), missing_names[:5])

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
    parser.add_argument("--dict-path", default=str(DICT_PATH))
    parser.add_argument("--force", action="store_true", help="Ignore checkpoint and regenerate cn files")
    parser.add_argument("--rebuild-checkpoint", action="store_true", help="Rebuild checkpoint from existing cn files")
    parser.add_argument("--mode", choices=("dict", "llm", "both"), default="both", help="翻译模式（默认 both）")
    parser.add_argument("--provider", default=None, help="LLM provider（默认读取 DEFAULT_PROVIDER 或 minimax）")
    parser.add_argument("--model", default=None, help="LLM model（默认读取 DEFAULT_MODEL 或 provider 默认模型）")
    parser.add_argument(
        "--confirm",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="LLM 译文逐条人工确认并回写词典；both/llm 默认开启，可用 --no-confirm 关闭",
    )
    return parser


def normalize_args(args: argparse.Namespace) -> argparse.Namespace:
    if not hasattr(args, "dict_path"):
        args.dict_path = str(DICT_PATH)
    if not hasattr(args, "mode"):
        args.mode = "both"
    if not hasattr(args, "provider"):
        args.provider = None
    if not hasattr(args, "model"):
        args.model = None
    if not hasattr(args, "confirm"):
        args.confirm = None
    if args.confirm is None:
        args.confirm = args.mode in ("both", "llm")
    return args


def run(args: argparse.Namespace) -> int:
    normalize_args(args)
    orig_dir = Path(args.orig_dir)
    cn_dir = Path(args.cn_dir)
    checkpoint = CheckpointStore(Path(args.checkpoint))
    if args.rebuild_checkpoint:
        checkpoint.reset()

    if not orig_dir.exists():
        logger.error("Orig directory does not exist: %s", orig_dir)
        return 1

    cn_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_checkpoint(checkpoint, orig_dir, cn_dir)
    translator = Translator(
        mode=args.mode,
        provider=args.provider,
        model=args.model,
        dict_path=args.dict_path,
        confirm=args.confirm,
    )

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
            rc = translate_file(file_path, cn_file, args, translator)
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
            if translator.stopped:
                logger.warning("用户停止翻译，已保存当前文件进度")
                break
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
