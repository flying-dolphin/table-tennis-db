#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入字典表：event_types 和 sub_event_types
"""

import sqlite3
import sys
from pathlib import Path

# Windows 编码兼容
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# 赛事类别映射（name -> name_zh, code）
EVENT_TYPE_MAPPING = {
    "Continental": ("洲际锦标赛", "Continental"),
    "Continental Games": ("洲际运动会", "CG"),
    "ITTF Challenge": ("ITTF 挑战赛", "Challenge"),
    "ITTF WJTTC": ("ITTF 世界青少年团体锦标赛", "WJTTC"),
    "ITTF World Cadet Challenge": ("ITTF 世界少年挑战赛", "Cadet"),
    "ITTF World Cup": ("ITTF 世界杯", "WC"),
    "ITTF World Junior Circuit": ("ITTF 世界青年巡回赛", "JrCircuit"),
    "ITTF World Tour / Pro Tour": ("ITTF 世界巡回赛/职业巡回赛", "Tour"),
    "ITTF World Youth Championships": ("ITTF 世界青年锦标赛", "YChamps"),
    "ITTF WTTC": ("ITTF 世界乒乓球锦标赛", "WTTC"),
    "Multi sport events": ("综合运动会", "MultiSport"),
    "Olympic Games": ("奥运会", "Olympics"),
    "Olympic Qualification": ("奥运会资格赛", "OlympicQual"),
    "Other events": ("其他赛事", "Other"),
    "Regional": ("地区赛事", "Regional"),
    "T2 Diamond": ("T2 钻石赛", "T2Diamond"),
    "WTT Champions": ("WTT 冠军赛", "Champions"),
    "WTT Contender Series": ("WTT 挑战赛", "Contender"),
    "WTT Feeder Series": ("WTT 支线赛", "Feeder"),
    "WTT Finals": ("WTT 总决赛", "Finals"),
    "WTT Grand Smash": ("WTT 大满贯", "GS"),
    "WTT Youth Contender Series": ("WTT 青少年挑战赛", "YouthContender"),
    "WTT Youth Grand Smash": ("WTT 青少年大满贯", "YouthGS"),
    "Youth Olympic Games": ("青年奥运会", "YOG"),
    "Youth Olympic Games Qualification": ("青年奥运会资格赛", "YOGQual"),
}

# 标记为重要赛事的类别
SELECTED_EVENTS = {
    "Continental",
    "Continental Games",
    "ITTF Challenge",
    "ITTF World Cup",
    "ITTF WTTC",
    "Olympic Games",
    "Olympic Qualification",
    "WTT Champions",
    "WTT Contender Series",
    "WTT Feeder Series",
    "WTT Finals",
    "WTT Grand Smash",
}


def import_event_types(db_path: str, event_type_file: str) -> bool:
    """导入赛事类别"""
    try:
        # 读取 event_type.txt
        with open(event_type_file, 'r', encoding='utf-8') as f:
            event_types = [line.strip() for line in f if line.strip()]

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        inserted = 0
        for i, event_type in enumerate(event_types, 1):
            if event_type not in EVENT_TYPE_MAPPING:
                print(f"  [WARN {i:2d}] Unknown event type: {event_type}")
                continue

            name_zh, code = EVENT_TYPE_MAPPING[event_type]
            is_selected = 1 if event_type in SELECTED_EVENTS else 0

            try:
                cursor.execute("""
                    INSERT INTO event_types (name, name_zh, code, is_selected)
                    VALUES (?, ?, ?, ?)
                """, (event_type, name_zh, code, is_selected))
                print(f"  [{i:2d}] {event_type:40s} -> {name_zh:20s} (code: {code:8s}, selected: {is_selected})")
                inserted += 1
            except sqlite3.IntegrityError as e:
                print(f"  [SKIP {i:2d}] {event_type} (already exists)")

        conn.commit()
        conn.close()

        print(f"\nInserted event_types: {inserted}/{len(event_types)}")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to import event_types: {e}")
        return False


def import_sub_event_types(db_path: str) -> bool:
    """导入项目类别（预置数据）"""
    try:
        sub_events_data = [
            ("WS", "Women's Singles", "女子单打"),
            ("MS", "Men's Singles", "男子单打"),
            ("WD", "Women's Doubles", "女子双打"),
            ("MD", "Men's Doubles", "男子双打"),
            ("XD", "Mixed Doubles", "混合双打"),
            ("XT", "Mixed Team", "混合团队"),
            ("WT", "Women's Team", "女子团体"),
            ("MT", "Men's Team", "男子团体"),
        ]

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for i, (code, name, name_zh) in enumerate(sub_events_data, 1):
            try:
                cursor.execute("""
                    INSERT INTO sub_event_types (code, name, name_zh)
                    VALUES (?, ?, ?)
                """, (code, name, name_zh))
                print(f"  [{i}] {code:3s} -> {name_zh:10s}")
            except sqlite3.IntegrityError:
                print(f"  [SKIP {i}] {code} (already exists)")

        conn.commit()
        conn.close()

        print(f"\nInserted sub_event_types: {len(sub_events_data)}")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to import sub_event_types: {e}")
        return False


def verify_dictionaries(db_path: str):
    """验证字典表"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM event_types;")
        event_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM sub_event_types;")
        sub_count = cursor.fetchone()[0]

        print(f"\nVerification:")
        print(f"  event_types:     {event_count} records")
        print(f"  sub_event_types: {sub_count} records")

        conn.close()
    except Exception as e:
        print(f"[VERIFY FAILED] {e}")


if __name__ == '__main__':
    project_root = Path(__file__).parent.parent.parent
    db_path = project_root / "scripts" / "db" / "ittf.db"
    event_type_file = project_root / "data" / "event_type.txt"

    print("=" * 70)
    print("Import Dictionaries")
    print("=" * 70)
    print(f"Database:        {db_path}")
    print(f"Event type file: {event_type_file}")
    print("=" * 70 + "\n")

    if not db_path.exists():
        print(f"[ERROR] Database file not found: {db_path}")
        sys.exit(1)

    if not event_type_file.exists():
        print(f"[ERROR] Event type file not found: {event_type_file}")
        sys.exit(1)

    print("Importing event_types...")
    success1 = import_event_types(str(db_path), str(event_type_file))

    print("\nImporting sub_event_types...")
    success2 = import_sub_event_types(str(db_path))

    verify_dictionaries(str(db_path))

    sys.exit(0 if success1 and success2 else 1)
