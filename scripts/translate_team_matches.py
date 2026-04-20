#!/usr/bin/env python3
"""
Translate team match files from orig to cn using dictionary only.

Input structure:
  team_match.v1 (root-level matches list)
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
from lib.dict_translator import DictTranslator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
ORIG_DIR = PROJECT_ROOT / "data" / "team_matches" / "orig"
CN_DIR = PROJECT_ROOT / "data" / "team_matches" / "cn"
CHECKPOINT_PATH = PROJECT_ROOT / "data" / "team_matches" / "checkpoint_translate_team_matches.json"
MISSING_PATH = PROJECT_ROOT / "data" / "team_matches" / "missing_translations.txt"

SPONSOR_SUFFIX_RE = re.compile(r"\s+Presented by .*$", re.IGNORECASE)
SUB_EVENT_PREFIX_RE = re.compile(r"^([A-Z]\d+)([A-Z]+)$")
SIDE_ENTRY_RE = re.compile(r"^(.+?)\s+\(([^)]+)\)$")

FIELD_CATEGORY: dict[str, str] = {
    "event_name": "events",
    "sub_event_type_code": "terms_others",
    "stage": "round",
    "round": "round",
    "side_a_player": "players",
    "side_a_country": "locations",
    "side_b_player": "players",
    "side_b_country": "locations",
    "winner_name": "players",
}

SKIP_VALUES = {"", "--"}


def _translate_ck(filename: str) -> str:
    return f"team_matches|file:{filename}|translate"


def split_event_name(name: str) -> tuple[str, str | None]:
    stripped = SPONSOR_SUFFIX_RE.sub("", (name or "")).strip()
    match = re.match(r"^(.*?)\s+(\d{4})\s*$", stripped)
    if match:
        return match.group(1).strip(), match.group(2)
    return stripped, None


def translate_value(value: str, field: str, dt: DictTranslator, missing: dict[str, set[str]]) -> str:
    if value in SKIP_VALUES:
        return value
    category = FIELD_CATEGORY[field]

    if field == "event_name":
        base_name, year = split_event_name(value)
        translated_base = dt.translate(base_name, category)
        if translated_base == base_name:
            missing[field].add(base_name)
            return value
        return f"{year}年{translated_base}" if year else translated_base

    if field == "sub_event_type_code":
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


def translate_side_entry(entry: str, side_prefix: str, dt: DictTranslator, missing: dict[str, set[str]]) -> str:
    if entry in SKIP_VALUES:
        return entry

    m = SIDE_ENTRY_RE.match(entry)
    if not m:
        missing[f"{side_prefix}_player"].add(entry)
        return entry

    name, country = m.group(1).strip(), m.group(2).strip()
    translated_name = dt.translate(name, "players")
    translated_country = dt.translate(country, "locations")

    if translated_name == name:
        missing[f"{side_prefix}_player"].add(name)
    if translated_country == country:
        missing[f"{side_prefix}_country"].add(country)

    if translated_name == name and translated_country == country:
        return entry
    return f"{translated_name} ({translated_country})"


def translate_winner_name(value: str, dt: DictTranslator, missing: dict[str, set[str]]) -> str:
    text = (value or "").strip()
    if not text:
        return text
    parts = [p.strip() for p in text.split("/") if p.strip()]
    if not parts:
        return text

    out_parts: list[str] = []
    unchanged = True
    for p in parts:
        translated = dt.translate(p, "players")
        if translated != p:
            unchanged = False
        else:
            missing["winner_name"].add(p)
        out_parts.append(translated)
    return text if unchanged else " / ".join(out_parts)


def translate_file_data(data: dict, dt: DictTranslator, missing: dict[str, set[str]]) -> dict:
    result = dict(data)

    event_name = data.get("event_name", "")
    if event_name and event_name not in SKIP_VALUES:
        result["event_name_zh"] = translate_value(event_name, "event_name", dt, missing)

    matches_result: list[dict] = []
    for match in data.get("matches", []):
        m = dict(match)
        for field in ("sub_event_type_code", "stage", "round"):
            value = match.get(field, "")
            if value and value not in SKIP_VALUES:
                m[f"{field}_zh"] = translate_value(str(value), field, dt, missing)

        side_a = match.get("side_a", [])
        side_b = match.get("side_b", [])
        m["side_a_zh"] = [translate_side_entry(e, "side_a", dt, missing) for e in side_a]
        m["side_b_zh"] = [translate_side_entry(e, "side_b", dt, missing) for e in side_b]

        winner_name = match.get("winner_name", "")
        if winner_name:
            m["winner_name_zh"] = translate_winner_name(str(winner_name), dt, missing)

        matches_result.append(m)

    result["matches"] = matches_result
    return result


def load_missing(path: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {f: set() for f in FIELD_CATEGORY}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        field, sep, value = line.partition(": ")
        if sep and field in result:
            result[field].add(value)
    return result


def save_missing(path: Path, missing: dict[str, set[str]]) -> None:
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


def bootstrap_checkpoint(checkpoint: CheckpointStore, orig_dir: Path, cn_dir: Path) -> None:
    if checkpoint.path.exists() and checkpoint.has_any_completed():
        return
    if not orig_dir.exists():
        return
    with checkpoint.bulk():
        for orig_file in sorted(orig_dir.glob("*.json")):
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
    parser = argparse.ArgumentParser(description="Translate team match files from orig to cn")
    parser.add_argument("--file", type=str, help="Translate only one file from orig/")
    parser.add_argument("--orig-dir", default=str(ORIG_DIR))
    parser.add_argument("--cn-dir", default=str(CN_DIR))
    parser.add_argument("--checkpoint", default=str(CHECKPOINT_PATH))
    parser.add_argument("--missing", default=str(MISSING_PATH))
    parser.add_argument("--force", action="store_true", help="Ignore checkpoint and regenerate cn files")
    parser.add_argument("--rebuild-checkpoint", action="store_true", help="Rebuild checkpoint from existing cn files")
    return parser


def run(args: argparse.Namespace) -> int:
    orig_dir = Path(args.orig_dir)
    cn_dir = Path(args.cn_dir)
    missing_path = Path(args.missing)
    checkpoint = CheckpointStore(Path(args.checkpoint))

    if args.rebuild_checkpoint:
        checkpoint.reset()

    if not orig_dir.exists():
        logger.error("Orig directory does not exist: %s", orig_dir)
        return 1

    cn_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_checkpoint(checkpoint, orig_dir, cn_dir)

    dt = DictTranslator()
    missing = {f: set() for f in FIELD_CATEGORY} if args.force else load_missing(missing_path)
    files = [orig_dir / args.file] if args.file else sorted(orig_dir.glob("*.json"))

    for file_path in files:
        if not file_path.exists():
            logger.error("Orig file does not exist: %s", file_path)
            return 1

        ck = _translate_ck(file_path.name)
        cn_file = cn_dir / file_path.name
        if (not args.force) and checkpoint.is_done(ck) and cn_file.exists():
            try:
                json.loads(cn_file.read_text(encoding="utf-8"))
                logger.info("Skipping (checkpoint): %s", file_path.name)
                continue
            except Exception:
                logger.warning("Checkpoint done but cn file unreadable, re-translating: %s", cn_file)

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            translated = translate_file_data(data, dt, missing)
            save_json(cn_file, translated)
            checkpoint.mark_done(ck, meta={"orig_path": str(file_path), "cn_path": str(cn_file)})
            logger.info("Translated: %s", file_path.name)
        except Exception as exc:
            checkpoint.mark_failed(ck, str(exc), meta={"orig_path": str(file_path), "cn_path": str(cn_file)})
            logger.error("Translate failed: %s (%s)", file_path.name, exc)
            return 1

    save_missing(missing_path, missing)
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
