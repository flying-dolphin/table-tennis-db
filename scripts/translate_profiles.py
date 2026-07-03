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
from datetime import datetime
from pathlib import Path

from lib.country_codes import normalize_profile_country
from lib.translator import Translator

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


def translate_value(value: str, categories: list[str], translator: Translator, field_name: str, filename: str) -> str | None:
    if not value or not value.strip():
        return value

    for category in categories:
        translated = translator.translate_one(value, category)
        if translated is not None and translated != value:
            return translated

    logger.error("Missing translation [%s] in %s: %r", field_name, filename, value)
    return None


_ENGLISH_LETTER_RE = re.compile(r"[A-Za-z]")


def _career_best_rank(profile: dict) -> int | None:
    raw_value = profile.get("career_best_rank")
    if raw_value in (None, ""):
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def should_translate_profile(profile: dict, career_best_rank_lte: int | None = None) -> bool:
    if career_best_rank_lte is None:
        return True
    rank = _career_best_rank(profile)
    return rank is not None and rank <= career_best_rank_lte


def translate_profile(
    profile: dict,
    translator: Translator,
    filename: str,
    career_best_rank_lte: int | None = None,
) -> dict:
    profile.pop("recent_matches", None)
    allow_chinese_fields = should_translate_profile(profile, career_best_rank_lte)
    normalize_profile_country(profile, include_country_zh=allow_chinese_fields)

    if not allow_chinese_fields:
        for key in list(profile):
            if key.endswith("_zh"):
                profile.pop(key, None)
        return profile

    for field, categories in TRANSLATE_FIELDS.items():
        if field == "country" and profile.get("country_zh"):
            continue
        original = profile.get(field)
        if not isinstance(original, str) or not original.strip():
            continue
        if not _ENGLISH_LETTER_RE.search(original):
            continue
        translated = translate_value(original, categories, translator, field, filename)
        if translated is not None:
            profile[translated_field_name(field)] = translated

    return profile


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate player profiles from orig to cn (dictionary only)")
    parser.add_argument("--file", type=str, help="Translate only one file from orig/")
    parser.add_argument(
        "--since",
        type=parse_since,
        help="Translate only orig/player_*.json files modified after this local time. "
        "Formats: YYYY-MM-DD, YYYY-MM-DD HH:MM[:SS], YYYY-MM-DDTHH:MM[:SS]. Ignored when --file is set.",
    )
    parser.add_argument("--orig-dir", default=str(ORIG_DIR))
    parser.add_argument("--cn-dir", default=str(CN_DIR))
    parser.add_argument("--dict-path", default=str(DICT_PATH))
    parser.add_argument("--mode", choices=("dict", "llm", "both"), default="dict", help="翻译模式（默认 dict）")
    parser.add_argument("--provider", default="minimax", help="LLM provider（mode 含 llm 时生效）")
    parser.add_argument("--model", default=None, help="LLM model")
    parser.add_argument("--confirm", action="store_true", help="LLM 译文逐条人工确认并回写词典（mode 含 llm 时生效）")
    parser.add_argument(
        "--career-best-rank-lte",
        type=int,
        default=None,
        help="Only add Chinese profile fields when career_best_rank is less than or equal to this value.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    orig_dir = Path(args.orig_dir)
    cn_dir = Path(args.cn_dir)
    dict_path = Path(args.dict_path)

    if not orig_dir.exists():
        logger.error("Orig directory does not exist: %s", orig_dir)
        return 1

    if not dict_path.exists():
        logger.error("Dictionary not found: %s", dict_path)
        return 1

    cn_dir.mkdir(parents=True, exist_ok=True)
    translator = Translator(mode=args.mode, provider=args.provider, model=args.model, dict_path=dict_path, confirm=args.confirm)

    if args.file:
        files = [orig_dir / args.file]
    else:
        all_files = sorted(orig_dir.glob("player_*.json"))
        if args.since:
            files = filter_files_since(all_files, args.since)
            logger.info(
                "Incremental profile translation since %s: %d/%d files selected",
                args.since.isoformat(sep=" "),
                len(files),
                len(all_files),
            )
        else:
            files = all_files

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

        translated = translate_profile(data, translator, file_path.name, args.career_best_rank_lte)
        cn_file = cn_dir / file_path.name
        save_json(cn_file, translated)
        logger.info("Translated: %s", file_path.name)

        if translator.stopped:
            logger.warning("用户停止翻译，已保存当前进度")
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
