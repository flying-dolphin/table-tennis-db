#!/usr/bin/env python3
"""
Translate player profile files from orig to cn.

Rules:
1. Skip the recent_matches field entirely.
2. Only translate: name, country, gender, style, playing_hand, grip.
3. Dictionary lookup only (no API fallback):
   - name        -> players category
   - country     -> locations category
   - gender/style/playing_hand/grip -> terms, then others
4. Log any missing words.
5. Save translated profiles to data/player_profiles/cn/.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / "scripts" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "translate_profiles.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)
ORIG_DIR = PROJECT_ROOT / "data" / "player_profiles" / "orig"
CN_DIR = PROJECT_ROOT / "data" / "player_profiles" / "cn"
DICT_PATH = PROJECT_ROOT / "scripts" / "data" / "translation_dict_v2.json"

TRANSLATE_FIELDS = {
    "name": ["players"],
    "country": ["locations"],
    "gender": ["terms", "others"],
    "style": ["terms", "others"],
    "playing_hand": ["terms", "others"],
    "grip": ["terms", "others"],
}


def translated_field_name(field: str) -> str:
    return f"{field}_zh"


def _normalize_key(text: str) -> str:
    return (text or "").strip().lower()


def load_dictionary(dict_path: Path) -> dict[str, dict[str, str]]:
    if not dict_path.exists():
        logger.error("Dictionary not found: %s", dict_path)
        sys.exit(1)

    with open(dict_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    entries = raw.get("entries", {})
    indexes: dict[str, dict[str, str]] = {
        "players": {},
        "locations": {},
        "terms": {},
        "others": {},
    }

    for key, value in entries.items():
        if not isinstance(value, dict):
            continue
        normalized_key = _normalize_key(key)
        if not normalized_key:
            continue
        translated = value.get("translated", "").strip()
        if not translated:
            continue
        for category in value.get("categories", []):
            if category in indexes:
                indexes[category][normalized_key] = translated

    return indexes


def translate_value(value: str, categories: list[str], indexes: dict[str, dict[str, str]], field_name: str, filename: str) -> str | None:
    lookup_key = _normalize_key(value)
    if not lookup_key:
        return value

    for category in categories:
        translated = indexes.get(category, {}).get(lookup_key)
        if translated:
            return translated

    logger.error("Missing translation [%s] in %s: %r", field_name, filename, value)
    return None


_ENGLISH_LETTER_RE = re.compile(r"[A-Za-z]")


def translate_profile(profile: dict, indexes: dict[str, dict[str, str]], filename: str) -> dict:
    profile.pop("recent_matches", None)

    for field, categories in TRANSLATE_FIELDS.items():
        original = profile.get(field)
        if not isinstance(original, str) or not original.strip():
            continue
        if not _ENGLISH_LETTER_RE.search(original):
            continue
        translated = translate_value(original, categories, indexes, field, filename)
        if translated is not None:
            profile[translated_field_name(field)] = translated

    return profile


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate player profiles from orig to cn (dictionary only)")
    parser.add_argument("--file", type=str, help="Translate only one file from orig/")
    parser.add_argument("--orig-dir", default=str(ORIG_DIR))
    parser.add_argument("--cn-dir", default=str(CN_DIR))
    parser.add_argument("--dict-path", default=str(DICT_PATH))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    orig_dir = Path(args.orig_dir)
    cn_dir = Path(args.cn_dir)
    dict_path = Path(args.dict_path)

    if not orig_dir.exists():
        logger.error("Orig directory does not exist: %s", orig_dir)
        return 1

    cn_dir.mkdir(parents=True, exist_ok=True)
    indexes = load_dictionary(dict_path)

    if args.file:
        files = [orig_dir / args.file]
    else:
        files = sorted(orig_dir.glob("player_*.json"))

    for file_path in files:
        if not file_path.exists():
            logger.error("File not found: %s", file_path)
            return 1

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.error("Failed to load %s: %s", file_path.name, exc)
            return 1

        translated = translate_profile(data, indexes, file_path.name)
        cn_file = cn_dir / file_path.name
        save_json(cn_file, translated)
        logger.info("Translated: %s", file_path.name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
