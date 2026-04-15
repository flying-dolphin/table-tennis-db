#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Export translation dictionary to CSV")
    parser.add_argument("--input", type=str, default="scripts/data/translation_dict_v2.json", help="Input JSON file path")
    parser.add_argument("--category", type=str, help="Filter entries by category (e.g., players, events, terms)")
    parser.add_argument("--output", type=str, help="Output CSV file path (default: stdout)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", {})

    if args.category:
        filtered = {
            k: v for k, v in entries.items()
            if args.category in v.get("categories", [])
        }
    else:
        filtered = entries

    output_file = open(args.output, "w", encoding="utf-8", newline="") if args.output else sys.stdout

    try:
        writer = csv.writer(output_file, lineterminator="\n")
        for entry in filtered.values():
            original = entry.get("original", "")
            translated = entry.get("translated", "")
            categories = ",".join(entry.get("categories", []))
            writer.writerow([original, translated, categories])
    finally:
        if output_file is not sys.stdout:
            output_file.close()


if __name__ == "__main__":
    main()
