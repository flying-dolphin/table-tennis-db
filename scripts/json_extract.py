#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def get_nested_values(data, key_path, _all=False):
    parts = key_path.split(".")
    results = []

    def traverse(current, idx):
        if idx == len(parts):
            results.append(current)
            return
        part = parts[idx]
        if part == "*":
            if isinstance(current, dict):
                for v in current.values():
                    traverse(v, idx + 1)
            elif isinstance(current, list):
                for v in current:
                    traverse(v, idx + 1)
        elif isinstance(current, dict):
            traverse(current.get(part), idx + 1)
        elif isinstance(current, list):
            try:
                index = int(part)
                if index < len(current):
                    traverse(current[index], idx + 1)
            except ValueError:
                pass
        else:
            pass

    traverse(data, 0)
    return results


def main():
    parser = argparse.ArgumentParser(description="Extract values from JSON by key path")
    parser.add_argument("file", type=str, help="Input JSON file path")
    parser.add_argument("key", type=str, help="Key path (e.g., 'name', 'data.players.0.name', 'years.*.events.*.sub_event')")
    parser.add_argument("--array", "-a", action="store_true", help="Iterate array/object and extract field from each item")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if args.array:
        parts = args.key.split(".")
        if len(parts) < 2:
            print("Error: --array requires parent path + field (e.g., 'events.name' or 'years.*.events.*.sub_event')", file=sys.stderr)
            sys.exit(1)
        arr_path = ".".join(parts[:-1])
        field = parts[-1]

        if field == "*":
            for item in get_nested_values(data, arr_path):
                if isinstance(item, (dict, list)):
                    print(json.dumps(item, ensure_ascii=False))
                elif item is not None:
                    print(item)
        else:
            for item in get_nested_values(data, arr_path):
                if isinstance(item, list):
                    for sub in item:
                        if isinstance(sub, dict):
                            val = sub.get(field)
                            if val is not None:
                                print(val)
                elif isinstance(item, dict):
                    val = item.get(field)
                    if val is not None:
                        print(val)
    else:
        values = get_nested_values(data, args.key)
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
