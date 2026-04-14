#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lib.translation_tree import should_translate_value


def _infer_raw_path(translated_path: Path) -> Path | None:
    if translated_path.parent.name.lower() == "cn":
        return translated_path.parent.parent / "orig" / translated_path.name

    stem = translated_path.stem
    if stem.endswith("_cn"):
        return translated_path.with_name(f"{stem[:-3]}.json")

    return None


def _validate_tree(raw: Any, translated: Any, path: tuple[str, ...], errors: list[str]) -> None:
    if type(raw) is not type(translated):
        errors.append(f"{'.'.join(path) or '$'} type mismatch: {type(raw).__name__} != {type(translated).__name__}")
        return

    if isinstance(raw, dict):
        raw_keys = list(raw.keys())
        translated_keys = list(translated.keys())
        if raw_keys != translated_keys:
            errors.append(f"{'.'.join(path) or '$'} keys mismatch: {raw_keys} != {translated_keys}")
            return
        for key in raw_keys:
            _validate_tree(raw[key], translated[key], path + (key,), errors)
        return

    if isinstance(raw, list):
        if len(raw) != len(translated):
            errors.append(f"{'.'.join(path) or '$'} list length mismatch: {len(raw)} != {len(translated)}")
            return
        for index, (raw_item, translated_item) in enumerate(zip(raw, translated)):
            _validate_tree(raw_item, translated_item, path + (f"[{index}]",), errors)
        return

    if isinstance(raw, str):
        if should_translate_value(path, raw):
            if raw.strip() == translated.strip():
                errors.append(f"{'.'.join(path) or '$'} not translated: {raw!r}")
        else:
            if raw.strip() != translated.strip():
                errors.append(f"{'.'.join(path) or '$'} unexpectedly changed: {raw!r} -> {translated!r}")
        return

    if raw != translated:
        errors.append(f"{'.'.join(path) or '$'} value mismatch: {raw!r} != {translated!r}")


def validate_translation_file(translated_file: Path, raw_file: Path | None = None) -> dict[str, Any]:
    if not translated_file.exists():
        return {"ok": False, "error": f"translated file not found: {translated_file}"}

    if raw_file is None:
        raw_file = _infer_raw_path(translated_file)
    if raw_file is None or not raw_file.exists():
        return {"ok": False, "error": f"raw file not found: {raw_file or 'unknown'}"}

    raw_data = json.loads(raw_file.read_text(encoding="utf-8"))
    translated_data = json.loads(translated_file.read_text(encoding="utf-8"))

    errors: list[str] = []
    _validate_tree(raw_data, translated_data, (), errors)

    return {
        "ok": not errors,
        "translated_file": str(translated_file),
        "raw_file": str(raw_file),
        "errors": errors[:50],
        "error_count": len(errors),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验 cn 翻译结果是否与 orig 同结构且已翻译")
    parser.add_argument("--translated", "-t", type=Path, required=True, help="翻译输出文件")
    parser.add_argument("--raw", "-r", type=Path, default=None, help="原始输入文件（可选）")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = validate_translation_file(args.translated, args.raw)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

