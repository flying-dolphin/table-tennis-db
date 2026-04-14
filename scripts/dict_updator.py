#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dict_updator.py
读取 key:value:category 格式的输入文件，将其添加到 translation_dict_v2.json 中。
用法:
    python scripts/dict_updator.py <input_file> [--dict scripts/data/translation_dict_v2.json]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_DICT_PATH = Path("scripts/data/translation_dict_v2.json")

CATEGORY_VALIDATORS: dict[str, str] = {
    "players": "player_name",
    "events": "event_name",
    "locations": "location",
    "terms": "none",
    "others": "none",
}


def parse_input_file(path: Path) -> list[tuple[str, str, str]]:
    """解析输入文件，返回 [(original, translated, category)] 列表。"""
    results: list[tuple[str, str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":", 2)
            if len(parts) < 2:
                print(f"[跳过] 格式错误: {line}")
                continue
            original = parts[0].strip()
            translated = parts[1].strip()
            category = parts[2].strip().lower() if len(parts) >= 3 else "others"
            if not original or not translated:
                print(f"[跳过] 空 key 或 value: {line}")
                continue
            results.append((original, translated, category))
    return results


def build_entry(original: str, translated: str, category: str, now: str) -> dict[str, Any]:
    """构造新的词典条目。"""
    return {
        "original": original,
        "translated": translated,
        "categories": [category],
        "source": "manual",
        "review_status": "pending",
        "validators": {category: CATEGORY_VALIDATORS.get(category, "none")},
        "updated_at": now,
    }


def merge_entry(existing: dict[str, Any], translated: str, category: str, now: str) -> dict[str, Any]:
    """合并新数据到已有条目。"""
    existing["translated"] = translated
    cats = existing.get("categories", [])
    if category not in cats:
        cats.append(category)
        existing["categories"] = cats

    validators = existing.get("validators", {})
    if category not in validators:
        validators[category] = CATEGORY_VALIDATORS.get(category, "none")
        existing["validators"] = validators

    existing["updated_at"] = now
    return existing


def main() -> None:
    parser = argparse.ArgumentParser(description="将 key:value:category 文件添加到 translation_dict_v2.json")
    parser.add_argument("input_file", type=Path, help="输入文件路径（每行格式：key:value:category）")
    parser.add_argument("--dict", dest="dict_path", type=Path, default=DEFAULT_DICT_PATH, help="词典文件路径")
    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"错误：输入文件不存在: {args.input_file}")
        return

    items = parse_input_file(args.input_file)
    if not items:
        print("未解析到任何有效条目，退出。")
        return

    with args.dict_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    entries: dict[str, Any] = data.setdefault("entries", {})
    now = datetime.now().isoformat()
    added = 0
    updated = 0

    for original, translated, category in items:
        key = original.lower()
        if key not in entries:
            entries[key] = build_entry(original, translated, category, now)
            added += 1
        else:
            entries[key] = merge_entry(entries[key], translated, category, now)
            updated += 1

    metadata = data.setdefault("metadata", {})
    metadata["total_entries"] = len(entries)
    metadata["updated_at"] = now

    with args.dict_path.open("w", encoding="utf-8", newline="") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"完成。新增 {added} 条，更新 {updated} 条，词典总计 {len(entries)} 条。")
    print(f"已保存到: {args.dict_path}")


if __name__ == "__main__":
    main()
