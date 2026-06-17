#!/usr/bin/env python3
"""Translate event names from CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.dict_translator import DictTranslator
from lib.event_translation import (
    translate_event_name_dict_only,
    translate_event_names_dict_then_llm,
    translate_event_names_llm_only,
)
from lib.translator import LLMTranslator


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
    parser.add_argument("--json", action="store_true", help="Output JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    names = _load_names(args)
    if not names:
        print("No event names provided", file=sys.stderr)
        return 1

    items = {f"event_{index}": name for index, name in enumerate(names, 1)}

    if args.mode == "dict":
        dict_translator = DictTranslator()
        results = {
            key: translate_event_name_dict_only(name, dict_translator) or name
            for key, name in items.items()
        }
    elif args.mode == "llm":
        llm_translator = LLMTranslator(provider=args.provider, model=args.model)
        results = translate_event_names_llm_only(items, llm_translator=llm_translator)
    else:
        llm_translator = LLMTranslator(provider=args.provider, model=args.model)
        results = translate_event_names_dict_then_llm(items, llm_translator=llm_translator)

    if results is None:
        return 1

    _print_results(names, results, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
