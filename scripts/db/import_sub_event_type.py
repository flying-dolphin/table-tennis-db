#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入字典表：sub_event_types
数据来源：data/sub_event_type.txt
"""

import sqlite3
import sys
from pathlib import Path

import config

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def load_sub_events_from_file(file_path: str) -> list:
    """从 txt 文件加载 sub_event_types 数据"""
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(':')
            if len(parts) >= 3:
                code = parts[0].strip()
                name = parts[1].strip()
                name_zh = parts[2].strip()
                data.append((code, name, name_zh))
    return data


def import_sub_event_types(db_path: str, txt_path: str) -> bool:
    """导入项目类别"""
    try:
        sub_events_data = load_sub_events_from_file(txt_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for i, (code, name, name_zh) in enumerate(sub_events_data, 1):
            try:
                cursor.execute("""
                    INSERT INTO sub_event_types (code, name, name_zh)
                    VALUES (?, ?, ?)
                """, (code, name, name_zh))
                print(f"  [{i:2d}] {code:5s} {name:30s} {name_zh}")
            except sqlite3.IntegrityError:
                print(f"  [SKIP {i:2d}] {code} (already exists)")

        conn.commit()
        conn.close()

        print(f"\nInserted sub_event_types: {len(sub_events_data)}")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to import sub_event_types: {e}")
        return False


def verify_tables(db_path: str):
    """验证字典表"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM sub_event_types;")
        sub_count = cursor.fetchone()[0]

        print(f"\nVerification:")
        print(f"  sub_event_types: {sub_count} records")

        conn.close()
    except Exception as e:
        print(f"[VERIFY FAILED] {e}")


if __name__ == '__main__':
    db_path = Path(config.DB_PATH)
    txt_path = Path(__file__).parent.parent.parent / 'data' / 'sub_event_type.txt'

    print("=" * 70)
    print("Import Sub Event Types")
    print("=" * 70)
    print(f"Database:        {db_path}")
    print(f"Source file:     {txt_path}")
    print("=" * 70 + "\n")

    if not db_path.exists():
        print(f"[ERROR] Database file not found: {db_path}")
        sys.exit(1)

    if not txt_path.exists():
        print(f"[ERROR] Source file not found: {txt_path}")
        sys.exit(1)

    print("\nImporting sub_event_types...")
    success = import_sub_event_types(str(db_path), str(txt_path))

    verify_tables(str(db_path))

    sys.exit(0 if success else 1)
