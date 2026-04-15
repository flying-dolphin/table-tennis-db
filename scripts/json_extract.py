#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def get_nested_value(data, key_path):
    keys = key_path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        elif isinstance(value, list):
            try:
                index = int(key)
                value = value[index] if index < len(value) else None
            except ValueError:
                return None
        else:
            return None
        if value is None:
            return None
    return value


def get_nested_value(data, key_path):
    parts = key_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                index = int(part)
                current = current[index] if index < len(current) else None
            except ValueError:
                return None
        else:
            return None
        if current is None:
            return None
    return current


def main():
    parser = argparse.ArgumentParser(description="Extract values from JSON by key path")
    parser.add_argument("file", type=str, help="Input JSON file path")
    parser.add_argument("key", type=str, help="Key path (e.g., 'name' or 'data.players.0.name')")
    parser.add_argument("--array", "-a", action="store_true", help="Iterate array and extract field from each item")
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
            print("Error: --array requires at least one parent path segment (e.g., 'events.name')", file=sys.stderr)
            sys.exit(1)
        arr_path = ".".join(parts[:-1])
        field = parts[-1]
        arr = get_nested_value(data, arr_path)
        if not isinstance(arr, list):
            print(f"Error: '{arr_path}' is not an array", file=sys.stderr)
            sys.exit(1)
        for item in arr:
            value = item.get(field) if isinstance(item, dict) else None
            if value is not None:
                if isinstance(value, (dict, list)):
                    print(json.dumps(value, ensure_ascii=False))
                else:
                    print(value)
    else:
        value = get_nested_value(data, args.key)
        if value is not None:
            if isinstance(value, (dict, list)):
                print(json.dumps(value, ensure_ascii=False, indent=2))
            else:
                print(value)
        else:
            print(f"Error: Key '{args.key}' not found", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
