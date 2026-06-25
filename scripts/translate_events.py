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
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.capture import save_json
from lib.event_translation import split_event_name
from lib.translator import Translator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
ORIG_DIR = PROJECT_ROOT / "data" / "events_list" / "orig"
CN_DIR = PROJECT_ROOT / "data" / "events_list" / "cn"

TRANSLATE_FIELDS = ("name", "event_type", "event_kind")
SKIP_VALUES = {"--", ""}


def translated_field_name(field: str) -> str:
    return f"{field}_zh"


def find_latest_file(directory: Path) -> Path | None:
    files = sorted(directory.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_since(value: str) -> datetime:
    normalized = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        "Expected --since in one of these formats: YYYY-MM-DD, YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM:SS, "
        "YYYY-MM-DDTHH:MM, YYYY-MM-DDTHH:MM:SS"
    )


def filter_files_since(files: list[Path], since: datetime) -> list[Path]:
    since_timestamp = since.timestamp()
    return [file_path for file_path in files if file_path.stat().st_mtime > since_timestamp]


def load_cn_event_ids(cn_path: Path) -> set[int]:
    if not cn_path.exists():
        return set()
    try:
        data = load_json(cn_path)
        translated_ids: set[int] = set()
        for event in data.get("events", []):
            eid = event.get("event_id")
            if eid is None:
                continue

            complete = True
            for field in TRANSLATE_FIELDS:
                original = event.get(field, "")
                if original in SKIP_VALUES:
                    continue
                if translated_field_name(field) not in event:
                    complete = False
                    break

            if complete:
                translated_ids.add(eid)
        return translated_ids
    except Exception:
        return set()


def translate_event_field(value: str, translator: Translator) -> str | None:
    """翻译单个赛事相关字段；未命中返回 None。"""
    translated = translator.translate_one(value, "events")
    if translated is None or translated == value:
        return None
    return translated


def apply_translations(
    events: list[dict],
    translated: dict[str, str],
    translate_skip_ids: set[int],
    output_skip_ids: set[int] | None = None,
) -> list[dict]:
    result = []
    for event in events:
        ev = dict(event)
        eid = event.get("event_id")
        if eid not in translate_skip_ids:
            for field in TRANSLATE_FIELDS:
                key = f"{eid}.{field}"
                if key in translated:
                    ev[translated_field_name(field)] = translated[key].replace(" ", "")
        if output_skip_ids is None or eid not in output_skip_ids:
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


def build_result(
    orig_data: dict,
    base_events: list[dict],
    excluded_event_ids: set[int],
    output_skip_ids: set[int] | None,
) -> dict:
    final_events = [
        ev
        for ev in base_events
        if ev.get("event_id") not in excluded_event_ids
        and (output_skip_ids is None or ev.get("event_id") not in output_skip_ids)
    ]
    result = dict(orig_data)
    result["events"] = final_events
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate events_list files from orig to cn")
    parser.add_argument("--file", type=str, help="Specify orig file name (default: latest in orig/)")
    parser.add_argument(
        "--since",
        type=parse_since,
        help="Translate only orig/*.json files modified after this local time. "
        "Formats: YYYY-MM-DD, YYYY-MM-DD HH:MM[:SS], YYYY-MM-DDTHH:MM[:SS]. Ignored when --file is set.",
    )
    parser.add_argument("--orig-dir", default=str(ORIG_DIR))
    parser.add_argument("--cn-dir", default=str(CN_DIR))
    parser.add_argument("--force", action="store_true", help="Re-translate all events, ignoring existing cn file")
    parser.add_argument("--event-id", type=int, nargs="+", help="Only translate specific event_id(s)")
    parser.add_argument("--top", type=int, help="Only translate the first N events (in file order)")
    parser.add_argument("--mode", choices=("dict", "llm", "both"), default="dict", help="翻译模式（默认 dict）")
    parser.add_argument("--provider", default="minimax", help="LLM provider（mode 含 llm 时生效）")
    parser.add_argument("--model", default=None, help="LLM model")
    parser.add_argument("--confirm", action="store_true", help="LLM 译文逐条人工确认并回写词典（mode 含 llm 时生效）")
    return parser


def run(args: argparse.Namespace) -> int:
    orig_dir = Path(args.orig_dir)
    cn_dir = Path(args.cn_dir)

    if not orig_dir.exists():
        logger.error("Orig directory does not exist: %s", orig_dir)
        return 1

    if args.file:
        files = [orig_dir / args.file]
    else:
        if args.since:
            all_files = sorted(orig_dir.glob("*.json"))
            files = filter_files_since(all_files, args.since)
            logger.info(
                "Incremental event translation since %s: %d/%d files selected",
                args.since.isoformat(sep=" "),
                len(files),
                len(all_files),
            )
        else:
            orig_path = find_latest_file(orig_dir)
            if not orig_path:
                logger.error("No JSON files found in %s", orig_dir)
                return 1
            files = [orig_path]

    cn_dir.mkdir(parents=True, exist_ok=True)
    translator = Translator(mode=args.mode, provider=args.provider, model=args.model, confirm=args.confirm)

    for orig_path in files:
        if not orig_path.exists():
            logger.error("Orig file does not exist: %s", orig_path)
            return 1

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

        # Load existing CN translations and merge into base events first
        cn_events_by_id: dict[int, dict] = {}
        if not args.force and cn_path.exists():
            try:
                cn_data = load_json(cn_path)
                cn_events_by_id = {e["event_id"]: e for e in cn_data.get("events", []) if "event_id" in e}
            except Exception:
                pass
        base_events: list[dict] = []
        for e in events:
            ev = dict(e)
            eid = ev.get("event_id")
            if eid in cn_events_by_id:
                for field in TRANSLATE_FIELDS:
                    zh_field = translated_field_name(field)
                    if zh_field in cn_events_by_id[eid]:
                        ev[zh_field] = cn_events_by_id[eid][zh_field]
            base_events.append(ev)

        existing_ids = set() if args.force else load_cn_event_ids(cn_path)
        translate_skip_ids = existing_ids
        output_skip_ids: set[int] | None = None

        if target_ids is not None:
            non_target_ids = {e["event_id"] for e in events if e["event_id"] not in target_ids}
            translate_skip_ids = translate_skip_ids | non_target_ids
            output_skip_ids = non_target_ids

        if translate_skip_ids:
            logger.info("Skipping %d events", len(translate_skip_ids))

        missing: dict[str, set[str]] = {field: set() for field in TRANSLATE_FIELDS}
        translated_count = 0

        for ev in base_events:
            eid = ev.get("event_id")
            if eid in translate_skip_ids:
                continue
            for field in TRANSLATE_FIELDS:
                value = ev.get(field, "")
                if value in SKIP_VALUES:
                    continue
                translated = translate_event_field(value, translator)
                if translated is None:
                    missing[field].add(split_event_name(value).base_name)
                    continue
                ev[translated_field_name(field)] = translated
                translated_count += 1
            if translator.stopped:
                logger.warning("用户停止翻译，已保存当前进度")
                break

        result = build_result(orig_data, base_events, set(), output_skip_ids)
        missing_count = sum(len(values) for values in missing.values())
        logger.info("Dictionary translated %d fields; missing %d fields", translated_count, missing_count)
        for field, values in missing.items():
            if values:
                logger.warning("Missing %s translations: %s", field, sorted(values)[:10])

        save_json(cn_path, result)
        logger.info("Saved: %s", cn_path)

    return 0


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
