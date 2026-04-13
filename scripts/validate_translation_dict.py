#!/usr/bin/env python3
"""
词典校验脚本

支持：
- V2 结构：entries 主索引
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

BANNED_LOCATION_TOKENS = ["WTT", "冠军赛", "公开赛", "挑战赛", "锦标赛", "乒联", "联盟", "赛事"]


def _validate_v2(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    entries = data.get("entries", {})
    if not isinstance(entries, dict):
        return ["V2 格式错误：entries 不是对象"], warnings

    meta_total = data.get("metadata", {}).get("total_entries")
    if isinstance(meta_total, int) and meta_total != len(entries):
        errors.append(f"metadata.total_entries={meta_total} 与 entries 数量 {len(entries)} 不一致")

    for k, v in entries.items():
        if not isinstance(v, dict):
            errors.append(f"entries[{k}] 不是对象")
            continue
        translated = (v.get("translated") or "").strip()
        categories = v.get("categories", [])
        validators = v.get("validators")
        if not isinstance(validators, dict):
            validators = {}
        if not translated:
            errors.append(f"entries[{k}] translated 为空")
        if "locations" in categories and any(token in translated for token in BANNED_LOCATION_TOKENS):
            errors.append(f"entries[{k}] locations 污染: {translated}")
        if not categories:
            warnings.append(f"entries[{k}] categories 为空")
        if any(category not in validators for category in categories):
            warnings.append(f"entries[{k}] validators 未覆盖全部 categories")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 translation_dict")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("scripts/data/translation_dict_v2.json"),
        help="词典文件路径",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：有 warning 也返回非 0",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"文件不存在: {args.input}")
        return 1

    data = json.loads(args.input.read_text(encoding="utf-8"))
    if not (isinstance(data, dict) and "entries" in data):
        print("仅支持 V2 entries 结构")
        return 1

    errors, warnings = _validate_v2(data)

    print("格式: v2")
    print(f"errors: {len(errors)}")
    print(f"warnings: {len(warnings)}")

    for msg in errors:
        print(f"[ERROR] {msg}")
    for msg in warnings:
        print(f"[WARN] {msg}")

    if errors:
        return 2
    if warnings and args.strict:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
