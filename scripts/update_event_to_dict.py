#!/usr/bin/env python3
"""
从 events_list 翻译结果中提取 event 词条并更新到翻译词典。

行为：
1. 读取 data/events_list/orig 和 data/events_list/cn 下的最新文件。
2. 要求两个最新文件必须同名。
3. 提取 events[].name / events[].event_type，按 `key:translate:category` 生成输入。
4. 调用 scripts/dict_updator.py 更新 scripts/data/translation_dict_v2.json。
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DICT_PATH = PROJECT_ROOT / "scripts" / "data" / "translation_dict_v2.json"

SKIP_VALUES = {"", None}
EVENT_CATEGORY = "events"
FIELDS = ("name", "event_type")


def resolve_events_root(explicit_root: str | None) -> Path:
    if explicit_root:
        root = Path(explicit_root)
        return root if root.is_absolute() else PROJECT_ROOT / root

    candidates = [
        PROJECT_ROOT / "data" / "events_list",
        PROJECT_ROOT / "data" / "event_list",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError("未找到 data/events_list 或 data/event_list 目录")


def find_latest_json(directory: Path) -> Path:
    files = sorted(
        (path for path in directory.glob("*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"目录下没有 JSON 文件: {directory}")
    return files[0]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"JSON 根节点不是对象: {path}")
    return data


def normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^\d{4}\s*", "", text)
    text = re.sub(r"^\d{4}年", "", text)
    return text.strip()


def normalize_translation(value: str) -> str:
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"^\d{4}年", "", value)
    value = re.sub(r"\d{4}年$", "", value)
    return value.strip()


def collect_cn_events_by_id(data: dict[str, Any]) -> dict[Any, dict[str, Any]]:
    events = data.get("events", [])
    if not isinstance(events, list):
        raise ValueError("CN 文件中的 events 不是数组")

    result: dict[Any, dict[str, Any]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = event.get("event_id")
        if event_id in SKIP_VALUES:
            continue
        result[event_id] = event
    return result


def resolve_conflict(
    original: str,
    translations: Counter[str],
    strategy: str,
) -> str:
    if len(translations) == 1:
        return next(iter(translations))

    if strategy == "error":
        choices = ", ".join(f"{text} x{count}" for text, count in translations.most_common())
        raise ValueError(f"同一原文存在多个译文: {original!r} -> {choices}")

    if strategy == "first":
        return next(iter(translations))

    if strategy == "most-common":
        return translations.most_common(1)[0][0]

    raise ValueError(f"不支持的 conflict strategy: {strategy}")


def extract_entries(
    orig_data: dict[str, Any],
    cn_data: dict[str, Any],
    conflict_strategy: str,
) -> list[tuple[str, str, str]]:
    orig_events = orig_data.get("events", [])
    if not isinstance(orig_events, list):
        raise ValueError("Orig 文件中的 events 不是数组")

    cn_events_by_id = collect_cn_events_by_id(cn_data)
    translated_by_original: dict[str, Counter[str]] = {}
    original_casing: dict[str, str] = {}

    for orig_event in orig_events:
        if not isinstance(orig_event, dict):
            continue

        event_id = orig_event.get("event_id")
        if event_id in SKIP_VALUES:
            continue

        cn_event = cn_events_by_id.get(event_id)
        if cn_event is None:
            continue

        for field in FIELDS:
            original = normalize_text(orig_event.get(field))
            translated = normalize_translation(normalize_text(cn_event.get(field)))
            if not original or not translated:
                continue

            normalized_original = original.lower()
            original_casing.setdefault(normalized_original, original)
            translated_by_original.setdefault(normalized_original, Counter())[translated] += 1

    entries: list[tuple[str, str, str]] = []
    for normalized_original, translations in translated_by_original.items():
        translated = resolve_conflict(
            original_casing[normalized_original],
            translations,
            conflict_strategy,
        )
        entries.append((original_casing[normalized_original], translated, EVENT_CATEGORY))

    return entries


def write_input_file(entries: list[tuple[str, str, str]]) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        suffix=".txt",
        prefix="event_dict_update_",
        delete=False,
        dir=str(PROJECT_ROOT / "scripts"),
    )
    temp_path = Path(tmp.name)
    try:
        for original, translated, category in entries:
            tmp.write(f"{original}:{translated}:{category}\n")
    finally:
        tmp.close()
    return temp_path


def run_dict_updator(input_file: Path, dict_path: Path) -> int:
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "dict_updator.py"),
        str(input_file),
        "--dict",
        str(dict_path),
    ]
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 events_list/cn 中提取 event 翻译并更新词典")
    parser.add_argument(
        "--events-root",
        type=str,
        default=None,
        help="事件目录根路径，默认自动识别 data/events_list 或 data/event_list",
    )
    parser.add_argument(
        "--dict",
        dest="dict_path",
        type=Path,
        default=DEFAULT_DICT_PATH,
        help="词典文件路径",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印即将更新的条目数量，不调用 dict_updator.py",
    )
    parser.add_argument(
        "--conflict-strategy",
        choices=("error", "most-common", "first"),
        default="error",
        help="同一原文对应多个译文时的处理策略，默认 error",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        events_root = resolve_events_root(args.events_root)
        orig_dir = events_root / "orig"
        cn_dir = events_root / "cn"

        if not orig_dir.exists():
            raise FileNotFoundError(f"orig 目录不存在: {orig_dir}")
        if not cn_dir.exists():
            raise FileNotFoundError(f"cn 目录不存在: {cn_dir}")

        orig_path = find_latest_json(orig_dir)
        cn_path = find_latest_json(cn_dir)

        if orig_path.name != cn_path.name:
            raise ValueError(
                "orig 和 cn 下最新文件不同名: "
                f"orig={orig_path.name}, cn={cn_path.name}"
            )

        orig_data = load_json(orig_path)
        cn_data = load_json(cn_path)
        entries = extract_entries(orig_data, cn_data, args.conflict_strategy)

        if not entries:
            print("未提取到可更新的 event 条目，退出。")
            return 0

        print(f"events_root: {events_root}")
        print(f"orig file:   {orig_path.name}")
        print(f"cn file:     {cn_path.name}")
        print(f"entries:     {len(entries)}")

        if args.dry_run:
            for original, translated, category in entries[:10]:
                print(f"{original}:{translated}:{category}")
            if len(entries) > 10:
                print(f"... 其余 {len(entries) - 10} 条未展示")
            return 0

        input_file = write_input_file(entries)
        try:
            return run_dict_updator(input_file, args.dict_path)
        finally:
            input_file.unlink(missing_ok=True)

    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
