#!/usr/bin/env python3
"""
Translate match files from orig to cn using dictionary only.

Translated fields (adds _zh suffix):
  - player_name, country
  - years[].events[]: event_name, event_type
  - years[].events[].matches[]: sub_event, stage, round, side_a, side_b

Values not found in the dictionary are collected and written to a missing
translations file for human review.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.capture import save_json
from lib.dict_translator import DictTranslator
from lib.event_translation import split_event_name, translate_event_name_dict_only

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
ORIG_DIR = PROJECT_ROOT / "data" / "matches_complete" / "orig"
CN_DIR = PROJECT_ROOT / "data" / "matches_complete" / "cn"
MISSING_PATH = PROJECT_ROOT / "data" / "matches_complete" / "missing_translations.txt"

# e.g. "U21XD" -> prefix="U21", code="XD"
SUB_EVENT_PREFIX_RE = re.compile(r"^([A-Z]\d+)([A-Z]+)$")

# field name -> DictTranslator category
FIELD_CATEGORY: dict[str, str] = {
    "player_name": "players",
    "country": "locations",
    "event_name": "events",
    "event_type": "events",
    "event": "events",
    "sub_event": "terms_others",
    "stage": "round",
    "round": "round",
    "side_a_player": "players",
    "side_a_country": "locations",
    "side_b_player": "players",
    "side_b_country": "locations",
    "winner": "players",
}

SKIP_VALUES = {"", "--"}
SIDE_ENTRY_RE = re.compile(r"^(.+?)\s+\(([^)]+)\)$")


def translate_value(
    value: str,
    field: str,
    dt: DictTranslator,
    missing: dict[str, set[str]],
) -> str:
    """Translate a single field value via dictionary. Records misses in missing."""
    if value in SKIP_VALUES:
        return value

    category = FIELD_CATEGORY[field]

    if field in ("event_name", "event"):
        translated = translate_event_name_dict_only(value, dt)
        base_name = split_event_name(value).base_name
        if translated is None:
            missing[field].add(base_name)
            return value  # keep original
        missing[field].discard(base_name)
        return translated

    if field == "sub_event":
        m = SUB_EVENT_PREFIX_RE.match(value)
        if m:
            prefix, code = m.group(1), m.group(2)
            translated_code = dt.translate(code, category)
            if translated_code != code:
                missing[field].discard(value)
                return f"{prefix}{translated_code}"
            missing[field].add(value)
            return value

    translated = dt.translate(value, category)
    if translated == value:
        missing[field].add(value)
    else:
        missing[field].discard(value)
    return translated


def translate_side_entry(
    entry: str,
    dt: DictTranslator,
    missing: dict[str, set[str]],
) -> str:
    """Translate 'NAME (COUNTRY)' entry. Returns translated or original."""
    if entry in SKIP_VALUES:
        return entry

    m = SIDE_ENTRY_RE.match(entry)
    if not m:
        missing["side_a_player"].add(entry)
        return entry

    name, country = m.group(1).strip(), m.group(2).strip()

    translated_name = dt.translate(name, "players")
    if translated_name == name:
        missing["side_a_player"].add(name)

    translated_country = dt.translate(country, "locations")
    if translated_country == country:
        missing["side_a_country"].add(country)

    if translated_name == name and translated_country == country:
        return entry

    return f"{translated_name} ({translated_country})"


def translate_file_data(data: dict, dt: DictTranslator, missing: dict[str, set[str]]) -> dict:
    """Return a new dict with _zh fields added for all translatable fields."""
    result = dict(data)

    schema = data.get("schema_version", "")
    if schema.startswith("event_match"):
        for field in ("event",):
            value = data.get(field, "")
            if value and value not in SKIP_VALUES:
                result[f"{field}_zh"] = translate_value(value, field, dt, missing)

        matches_result = []
        for match in data.get("matches", []):
            m = dict(match)
            for field in ("sub_event", "stage", "round", "winner"):
                value = match.get(field, "")
                if value and value not in SKIP_VALUES:
                    m[f"{field}_zh"] = translate_value(value, field, dt, missing)

            side_a_list = match.get("side_a", [])
            side_b_list = match.get("side_b", [])
            m["side_a_zh"] = [translate_side_entry(e, dt, missing) for e in side_a_list]
            m["side_b_zh"] = [translate_side_entry(e, dt, missing) for e in side_b_list]

            matches_result.append(m)

        result["matches"] = matches_result
        return result

    for field in ("player_name", "country"):
        value = data.get(field, "")
        if value and value not in SKIP_VALUES:
            result[f"{field}_zh"] = translate_value(value, field, dt, missing)

    years_result: dict[str, dict] = {}
    for year, year_data in data.get("years", {}).items():
        year_result = dict(year_data)
        events_result = []

        for event in year_data.get("events", []):
            ev = dict(event)

            for field in ("event_name", "event_type"):
                value = event.get(field, "")
                if value and value not in SKIP_VALUES:
                    ev[f"{field}_zh"] = translate_value(value, field, dt, missing)

            matches_result = []
            for match in event.get("matches", []):
                m = dict(match)
                for field in ("sub_event", "stage", "round"):
                    value = match.get(field, "")
                    if value and value not in SKIP_VALUES:
                        m[f"{field}_zh"] = translate_value(value, field, dt, missing)

                side_a_list = match.get("side_a", [])
                side_b_list = match.get("side_b", [])
                m["side_a_zh"] = [translate_side_entry(e, dt, missing) for e in side_a_list]
                m["side_b_zh"] = [translate_side_entry(e, dt, missing) for e in side_b_list]

                matches_result.append(m)

            ev["matches"] = matches_result
            events_result.append(ev)

        year_result["events"] = events_result
        years_result[year] = year_result

    result["years"] = years_result
    return result


def save_missing(path: Path, missing: dict[str, set[str]]) -> None:
    """Write missing translations to file, sorted by field then value. Only writes if there are missing entries."""
    lines: list[str] = []
    for field in FIELD_CATEGORY:
        for value in sorted(missing.get(field, set())):
            lines.append(f"{field}: {value}")
    if not lines:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    logger.info("Missing translations written to %s (%d entries)", path, len(lines))


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
    return [f for f in files if f.stat().st_mtime > since_timestamp]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate match files from orig to cn")
    parser.add_argument("--file", type=str, help="Translate only one file from orig/")
    parser.add_argument(
        "--since",
        type=parse_since,
        help="Translate only orig/*.json files modified after this local time. "
        "Formats: YYYY-MM-DD, YYYY-MM-DD HH:MM[:SS], YYYY-MM-DDTHH:MM[:SS]. Ignored when --file is set.",
    )
    parser.add_argument("--orig-dir", default=str(ORIG_DIR))
    parser.add_argument("--cn-dir", default=str(CN_DIR))
    parser.add_argument("--missing", default=str(MISSING_PATH), help="Path to missing translations output file")
    return parser


def run(args: argparse.Namespace) -> int:
    orig_dir = Path(args.orig_dir)
    cn_dir = Path(args.cn_dir)
    missing_path = Path(args.missing)

    if not orig_dir.exists():
        logger.error("Orig directory does not exist: %s", orig_dir)
        return 1

    cn_dir.mkdir(parents=True, exist_ok=True)
    dt = DictTranslator()
    missing: dict[str, set[str]] = {f: set() for f in FIELD_CATEGORY}

    if args.file:
        files = [orig_dir / args.file]
    else:
        all_files = sorted(orig_dir.glob("*.json"))
        if args.since:
            files = filter_files_since(all_files, args.since)
            logger.info(
                "Incremental match translation since %s: %d/%d files selected",
                args.since.isoformat(sep=" "),
                len(files),
                len(all_files),
            )
        else:
            files = all_files

    for file_path in files:
        if not file_path.exists():
            logger.error("Orig file does not exist: %s", file_path)
            return 1

        cn_file = cn_dir / file_path.name
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            translated = translate_file_data(data, dt, missing)
            save_json(cn_file, translated)
            logger.info("Translated: %s", file_path.name)
        except Exception as exc:
            logger.error("Translate failed: %s (%s)", file_path.name, exc)
            return 1

    save_missing(missing_path, missing)
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
