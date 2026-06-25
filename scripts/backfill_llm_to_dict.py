#!/usr/bin/env python3
"""
将 events_list/cn 文件中 LLM 翻译的结果回填到翻译词典。

用法：
  python scripts/backfill_llm_to_dict.py                       # 使用最新的 cn 文件
  python scripts/backfill_llm_to_dict.py --file events_list_cn_20250625.json
  python scripts/backfill_llm_to_dict.py --dry-run             # 预览，不写入
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.event_translation import split_event_name

CN_DIR = PROJECT_ROOT / "data" / "events_list" / "cn"
DEFAULT_DICT_PATH = PROJECT_ROOT / "scripts" / "data" / "translation_dict_v2.json"

TRANSLATE_FIELDS = ("name", "event_type", "event_kind")
SKIP_VALUES = {"--", ""}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_latest_file(directory: Path) -> Path | None:
    files = sorted(directory.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将 events_list/cn 中的翻译结果回填到词典")
    parser.add_argument("--file", type=str, help="cn 文件名（默认 cn/ 下最新文件）")
    parser.add_argument("--dict", type=Path, default=DEFAULT_DICT_PATH, help="词典文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印待添加条目，不写入词典")
    return parser


def load_dict(dict_path: Path) -> dict[str, dict]:
    return json.loads(dict_path.read_text(encoding="utf-8")).get("entries", {})


def normalize_original(field: str, value: str) -> str:
    if field == "name":
        return split_event_name(value).base_name
    return value.strip()


def normalize_translation(field: str, value: str) -> str:
    text = value.strip()
    if field == "name":
        text = re.sub(r"^\d{4}年", "", text).strip()
        text = re.sub(r"\d{4}年$", "", text).strip()
    return text


def choose_translation(original: str, translations: Counter[str]) -> str:
    choices = translations.most_common()
    print(f"\n同一原文存在多个译文: {original}")
    for index, (translated, count) in enumerate(choices, 1):
        print(f"  {index}. {translated} (出现 {count} 次)")

    while True:
        choice = input("请选择译文编号，或输入 m 手工输入新译文: ").strip().lower()
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(choices):
                return choices[index - 1][0]
        if choice in {"m", "manual"}:
            manual = input("请输入新译文: ").strip()
            if manual:
                return manual
        print("无效输入，请输入有效编号或 m")


def resolve_existing_conflict(original: str, existing: str, candidate: str) -> str | None:
    print(f"\n词典中已有不同译文: {original}")
    print(f"  1. 保留现有: {existing}")
    print(f"  2. 使用新译文: {candidate}")
    while True:
        choice = input("请选择 1/2，输入 m 手工输入新译文，或 n 跳过: ").strip().lower()
        if choice in {"1", "k", "keep"}:
            return existing
        if choice in {"2", "u", "use"}:
            return candidate
        if choice in {"m", "manual"}:
            manual = input("请输入新译文: ").strip()
            if manual:
                return manual
        if choice in {"n", "no", "skip"}:
            return None
        print("无效输入，请输入 1/2/m/n")


def extract_entries(cn_data: dict, dict_path: Path | None = None) -> list[tuple[str, str, str]]:
    translations_by_key: dict[str, Counter[str]] = {}
    original_casing: dict[str, str] = {}
    dict_entries = load_dict(dict_path) if dict_path else None

    for event in cn_data.get("events", []):
        for field in TRANSLATE_FIELDS:
            original = event.get(field, "")
            translated = event.get(f"{field}_zh", "")
            if original in SKIP_VALUES or not translated:
                continue

            store_orig = normalize_original(field, original)
            store_trans = normalize_translation(field, translated)

            if not store_orig or not store_trans:
                continue

            key = store_orig.lower()
            original_casing.setdefault(key, store_orig)
            translations_by_key.setdefault(key, Counter())[store_trans] += 1

    entries: list[tuple[str, str, str]] = []
    for key, translations in translations_by_key.items():
        store_orig = original_casing[key]
        store_trans = (
            next(iter(translations))
            if len(translations) == 1
            else choose_translation(store_orig, translations)
        )

        # 如果词典中已有相同键且翻译一致，跳过
        if dict_entries and dict_entries.get(key, {}).get("translated") == store_trans:
            continue

        entries.append((store_orig, store_trans, "events"))

    return entries


def update_dict(entries: list[tuple[str, str, str]], dict_path: Path) -> None:
    data = json.loads(dict_path.read_text(encoding="utf-8"))
    dict_entries = data.setdefault("entries", {})
    now = datetime.now().isoformat()
    changed_count = 0

    for store_orig, store_trans, data_type in entries:
        key = store_orig.strip().lower()
        if not key:
            continue

        if key in dict_entries:
            entry = dict_entries[key]
            entry_changed = False
            existing_trans = (entry.get("translated") or "").strip()
            if existing_trans and existing_trans != store_trans:
                resolved = resolve_existing_conflict(store_orig, existing_trans, store_trans)
                if resolved is None:
                    logger.info("跳过已有词典冲突: %s", store_orig)
                    continue
                store_trans = resolved
            cats = set(entry.get("categories", []))
            cats.add(data_type)
            sorted_cats = sorted(cats)
            if entry.get("categories") != sorted_cats:
                entry["categories"] = sorted_cats
                entry_changed = True
            if existing_trans != store_trans:
                entry["translated"] = store_trans
                entry["source"] = "api"
                entry["review_status"] = "verified"
                entry_changed = True
            validators = dict(entry.get("validators") or {})
            if validators.get(data_type) != "event_name":
                validators[data_type] = "event_name"
                entry["validators"] = validators
                entry_changed = True
            if entry_changed:
                entry["updated_at"] = now
                changed_count += 1
        else:
            dict_entries[key] = {
                "original": store_orig,
                "translated": store_trans,
                "categories": [data_type],
                "source": "api",
                "review_status": "verified",
                "validators": {data_type: "event_name"},
                "updated_at": now,
            }
            changed_count += 1

    if changed_count == 0:
        logger.info("没有词典变更")
        return

    data.setdefault("metadata", {})["total_entries"] = len(dict_entries)
    data["metadata"]["updated_at"] = now

    tmp_path = dict_path.with_suffix(dict_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(dict_path)
    logger.info("回写词典 %d 条 -> %s", changed_count, dict_path)


def main() -> int:
    args = build_parser().parse_args()

    if not CN_DIR.exists():
        logger.error("CN 目录不存在: %s", CN_DIR)
        return 1
    if not args.dict.exists():
        logger.error("词典文件不存在: %s", args.dict)
        return 1

    cn_path = CN_DIR / args.file if args.file else find_latest_file(CN_DIR)
    if not cn_path or not cn_path.exists():
        logger.error("找不到 cn 文件%s", "" if args.file else "（或 cn/ 下无文件）")
        return 1
    logger.info("读取: %s", cn_path)

    cn_data = load_json(cn_path)
    entries = extract_entries(cn_data, args.dict)

    if not entries:
        logger.info("未找到可回填的条目")
        return 0

    unique_orig = len(set(e[0] for e in entries))
    logger.info("提取 %d 条翻译（%d 个独立原文）", len(entries), unique_orig)

    if args.dry_run:
        print(f"\n将回填 {len(entries)} 条到词典：")
        for store_orig, store_trans, _ in sorted(entries, key=lambda x: x[0]):
            print(f"  {store_orig} -> {store_trans}")
        return 0

    update_dict(entries, args.dict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
