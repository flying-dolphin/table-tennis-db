#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def find_values_by_key(data, target_key):
    results = []

    def traverse(current):
        if isinstance(current, dict):
            for key, value in current.items():
                if key == target_key:
                    results.append(value)
                traverse(value)
        elif isinstance(current, list):
            for item in current:
                traverse(item)

    traverse(data)
    return results


def main():
    parser = argparse.ArgumentParser(description="Extract values from JSON by key name")
    parser.add_argument("file", type=str, help="Input JSON file path")
    parser.add_argument("key", type=str, help="Key name to match anywhere in the JSON")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    values = find_values_by_key(data, args.key)
    if not values:
        print(f"Error: Key '{args.key}' not found", file=sys.stderr)
        sys.exit(1)

    for value in values:
        if isinstance(value, (dict, list)):
            print(json.dumps(value, ensure_ascii=False, indent=2))
        else:
            print(value)


if __name__ == "__main__":
    main()
