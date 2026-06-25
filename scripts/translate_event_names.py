#!/usr/bin/env python3
"""Translate event names from CLI（基于统一 Translator）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.translator import Translator

# CLI mode -> Translator mode
_MODE_MAP = {"dict": "dict", "llm": "llm", "dict-then-llm": "both"}


def _load_names(args: argparse.Namespace) -> list[str]:
    names = list(args.names or [])
    if args.file:
        names.extend(
            line.strip()
            for line in Path(args.file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return names


def _print_results(names: list[str], results: dict[str, str], as_json: bool) -> None:
    if as_json:
        payload = [
            {"original": name, "translated": results.get(f"event_{index}", name)}
            for index, name in enumerate(names, 1)
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    for index, name in enumerate(names, 1):
        print(f"{name}\t{results.get(f'event_{index}', name)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate event names")
    parser.add_argument("names", nargs="*", help="Event names to translate")
    parser.add_argument("--file", help="Read event names from a newline-delimited text file")
    parser.add_argument(
        "--mode",
        choices=("dict", "llm", "dict-then-llm"),
        default="dict-then-llm",
        help="Translation mode",
    )
    parser.add_argument("--provider", default="minimax", help="LLM provider")
    parser.add_argument("--model", default=None, help="LLM model")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="逐条人工确认 LLM 译文并回写词典（仅 llm/dict-then-llm 生效）",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    names = _load_names(args)
    if not names:
        print("No event names provided", file=sys.stderr)
        return 1

    items = {f"event_{index}": name for index, name in enumerate(names, 1)}

    translator = Translator(
        mode=_MODE_MAP[args.mode],
        provider=args.provider,
        model=args.model,
        confirm=args.confirm,
    )
    results = translator.translate_batch(items, "events")
    if results is None:
        return 1

    _print_results(names, results, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
