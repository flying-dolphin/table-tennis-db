#!/usr/bin/env python3
"""
Translate ranking files from orig to cn using dictionary only.
Only translates specific fields: name, location, country,
event, category, expires_on, position.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.capture import save_json
from lib.dict_translator import DictTranslator
from lib.translate_constant import MONTH_MAP

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
ORIG_DIR = PROJECT_ROOT / "data" / "rankings" / "orig"
CN_DIR = PROJECT_ROOT / "data" / "rankings" / "cn"
DICT_PATH = PROJECT_ROOT / "scripts" / "data" / "translation_dict_v2.json"
LOGS_DIR = PROJECT_ROOT / "scripts" / "logs"


def _translated_field_name(field: str) -> str:
    return f"{field}_zh"


def _translate_expires_on(value: str | None) -> str | None:
    """翻译 expires_on 字段中的月份"""
    if not value:
        return value
    for month_key, entry in MONTH_MAP.items():
        if month_key in value.lower():
            return value.replace(entry["original"], entry["translated"])
    return value


def _translate_name(name: str | None, translator: DictTranslator) -> str | None:
    """翻译人名，先查词典，未命中则尝试交换名字顺序"""
    if not name:
        return name
    original = name
    translated = translator.translate(name, "players")
    if translated != name:
        return translated
    swapped = " ".join(name.split()[::-1])
    translated = translator.translate(swapped, "players")
    if translated != swapped:
        return translated
    return original


def _translate_position(value: str | None, translator: DictTranslator) -> str | None:
    """翻译position字段，处理带有 -n% 后缀的情况"""
    if not value:
        return value
    original = value
    if "-" in value:
        parts = value.split("-")
        prefix = parts[0]
        suffix = "-".join(parts[1:])
        translated = translator.translate(prefix, "position")
        if translated != prefix:
            return f"{translated}-{suffix}"
        return original
    translated = translator.translate(value, "position")
    if translated != value:
        return translated
    return original


def _write_missing_log(missing: dict, output_file: str) -> None:
    """将未翻译的词条写入单个日志文件"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "translate_ranks.log"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"=== {output_file} ===\n\n")
        for field, items in missing.items():
            if not items:
                continue
            f.write(f"--- {field} ({len(items)}) ---\n")
            unique_items = sorted(set(items))
            for item in unique_items:
                f.write(f"{item}\n")
            f.write("\n")


def translate_rankings(data: dict, translator: DictTranslator, output_file: str) -> dict:
    result = json.loads(json.dumps(data))
    missing: dict[str, list[str]] = {
        "name": [],
        "country": [],
        "location": [],
        "event": [],
        "category": [],
        "expires_on": [],
        "position": [],
    }

    for record in result.get("rankings", []):
        if "name" in record:
            original = record["name"]
            translated = _translate_name(original, translator)
            if translated != original:
                record[_translated_field_name("name")] = translated
            else:
                missing["name"].append(original)

        if "country" in record:
            original = record["country"]
            translated = translator.translate(original, "countries")
            if translated != original:
                record[_translated_field_name("country")] = translated
            else:
                missing["country"].append(original)

        if "location" in record:
            original = record["location"]
            translated = translator.translate(original, "locations")
            if translated != original:
                record[_translated_field_name("location")] = translated
            else:
                missing["location"].append(original)

        for pb in record.get("points_breakdown", []):
            if "event" in pb:
                original = pb["event"]
                translated = translator.translate(original, "events")
                if translated != original:
                    pb[_translated_field_name("event")] = translated
                else:
                    missing["event"].append(original)

            if "category" in pb:
                original = pb["category"]
                translated = translator.translate(original, "terms_others")
                if translated != original:
                    pb[_translated_field_name("category")] = translated
                else:
                    missing["category"].append(original)

            if "expires_on" in pb:
                original = pb["expires_on"]
                translated = _translate_expires_on(original)
                if translated != original:
                    pb[_translated_field_name("expires_on")] = translated
                else:
                    missing["expires_on"].append(original)

            if "position" in pb:
                original = pb["position"]
                translated = _translate_position(original, translator)
                if translated != original:
                    pb[_translated_field_name("position")] = translated
                else:
                    missing["position"].append(original)

    has_missing = any(values for values in missing.values())
    if has_missing:
        _write_missing_log(missing, output_file)

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate ranking files from orig to cn")
    parser.add_argument("--file", type=str, help="Translate only one file from orig/")
    parser.add_argument("--orig-dir", default=str(ORIG_DIR))
    parser.add_argument("--cn-dir", default=str(CN_DIR))
    parser.add_argument("--dict-path", default=str(DICT_PATH))
    parser.add_argument("--force", action="store_true", help="Overwrite existing cn files")
    return parser


def run(args: argparse.Namespace) -> int:
    orig_dir = Path(args.orig_dir)
    cn_dir = Path(args.cn_dir)
    dict_path = Path(args.dict_path)

    if not orig_dir.exists():
        logger.error("Orig directory does not exist: %s", orig_dir)
        return 1

    if not dict_path.exists():
        logger.error("Dictionary file does not exist: %s", dict_path)
        return 1

    cn_dir.mkdir(parents=True, exist_ok=True)
    translator = DictTranslator(dict_path)

    if args.file:
        file_arg = Path(args.file)
        if file_arg.exists():
            files = [file_arg]
        elif file_arg.is_absolute():
            files = [file_arg]
        else:
            files = [orig_dir / file_arg]
    else:
        files = sorted(orig_dir.glob("*.json"))

    for file_path in files:
        if not file_path.exists():
            logger.error("File not found: %s", file_path)
            return 1

        cn_file = cn_dir / file_path.name
        if cn_file.exists() and not args.force:
            logger.info("Skipping (already exists): %s", file_path.name)
            continue

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            output_file = file_path.stem
            translated = translate_rankings(data, translator, output_file)
            save_json(cn_file, translated)
            logger.info("Translated: %s -> %s", file_path.name, cn_file)
        except Exception as exc:
            logger.error("Failed to translate %s: %s", file_path.name, exc)
            return 1

    return 0


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
