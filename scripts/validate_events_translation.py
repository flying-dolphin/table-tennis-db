#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _is_value_translated(original: str, translated: str) -> bool:
    if not original:
        return True
    if not translated:
        return False
    return original.strip() != translated.strip()


def _is_event_fully_translated(event: dict[str, Any]) -> bool:
    return _is_value_translated(event.get("name", ""), event.get("name_zh", "")) and _is_value_translated(
        event.get("location", ""), event.get("location_zh", "")
    )


def _infer_raw_path(translated_path: Path) -> Path | None:
    stem = translated_path.stem
    if not stem.endswith("_cn"):
        return None
    return translated_path.with_name(f"{stem[:-3]}.json")


def validate_translation_file(translated_file: Path, raw_file: Path | None = None) -> dict[str, Any]:
    if not translated_file.exists():
        return {"ok": False, "error": f"translated file not found: {translated_file}"}

    data = json.loads(translated_file.read_text(encoding="utf-8"))
    events = data.get("events", [])
    if not isinstance(events, list):
        return {"ok": False, "error": "events must be a list", "failed_events": 0}

    raw_total: int | None = None
    if raw_file is None:
        raw_file = _infer_raw_path(translated_file)
    if raw_file and raw_file.exists():
        raw_data = json.loads(raw_file.read_text(encoding="utf-8"))
        raw_events = raw_data.get("events", [])
        if isinstance(raw_events, list):
            raw_total = len(raw_events)

    progress = data.get("progress", {})
    processed = progress.get("processed_events")
    total = progress.get("total_events")

    failed_indices: list[int] = []
    for idx, event in enumerate(events):
        if not _is_event_fully_translated(event):
            failed_indices.append(idx)

    failed_events = len(failed_indices)
    checks: list[str] = []
    ok = True

    if raw_total is not None and len(events) != raw_total:
        ok = False
        checks.append(f"events length mismatch: translated={len(events)} raw={raw_total}")
    if processed is not None and processed != len(events):
        ok = False
        checks.append(f"progress.processed_events mismatch: {processed} != {len(events)}")
    if total is not None:
        expected_total = raw_total if raw_total is not None else len(events)
        if total != expected_total:
            ok = False
            checks.append(f"progress.total_events mismatch: {total} != {expected_total}")
    if failed_events > 0:
        ok = False
        checks.append(f"untranslated events: {failed_events}")

    return {
        "ok": ok,
        "translated_file": str(translated_file),
        "raw_file": str(raw_file) if raw_file else None,
        "total_events": len(events),
        "failed_events": failed_events,
        "failed_indices": failed_indices[:20],
        "checks": checks,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验 events_calendar 翻译结果是否完整")
    parser.add_argument("--translated", "-t", type=Path, required=True, help="翻译输出文件（*_cn.json）")
    parser.add_argument("--raw", "-r", type=Path, default=None, help="原始输入文件（可选）")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = validate_translation_file(args.translated, args.raw)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

