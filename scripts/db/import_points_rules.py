#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入积分规则：points_rules
"""

import sqlite3
import sys
from pathlib import Path

import config

# Windows 编码兼容
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# 女子单打积分规则（部分示例，根据 ITTF-Ranking-Regulations-CN-20260127.md）
# 结构: (event_category, sub_event_category, draw_qualifier, stage_type, position, points)
WOMENS_SINGLES_RULES = [
    # 奥运会
    ("Olympic Games", "singles", None, "main_draw", "W", 2000),
    ("Olympic Games", "singles", None, "main_draw", "F", 1400),
    ("Olympic Games", "singles", None, "main_draw", "SF", 900),
    ("Olympic Games", "singles", None, "main_draw", "QF", 580),
    ("Olympic Games", "singles", None, "main_draw", "R16", 380),
    ("Olympic Games", "singles", None, "main_draw", "R32", 100),
    ("Olympic Games", "singles", None, "main_draw", "R64", 20),

    # WTT 大满贯 (Q48/Q64)
    ("WTT Grand Smash", "singles", "Q48/Q64", "main_draw", "W", 2000),
    ("WTT Grand Smash", "singles", "Q48/Q64", "main_draw", "F", 1400),
    ("WTT Grand Smash", "singles", "Q48/Q64", "main_draw", "SF", 900),
    ("WTT Grand Smash", "singles", "Q48/Q64", "main_draw", "QF", 580),
    ("WTT Grand Smash", "singles", "Q48/Q64", "main_draw", "R16", 380),
    ("WTT Grand Smash", "singles", "Q48/Q64", "main_draw", "R32", 100),
    ("WTT Grand Smash", "singles", "Q48/Q64", "main_draw", "R64", 20),
    ("WTT Grand Smash", "singles", "Q48/Q64", "qualification", "QUAL", 50),
    ("WTT Grand Smash", "singles", "Q48/Q64", "qualification", "R4", 45),
    ("WTT Grand Smash", "singles", "Q48/Q64", "qualification", "R3", 20),
    ("WTT Grand Smash", "singles", "Q48/Q64", "qualification", "R2", 10),

    # WTT 大满贯 (Q24/Q32)
    ("WTT Grand Smash", "singles", "Q24/Q32", "main_draw", "W", 2000),
    ("WTT Grand Smash", "singles", "Q24/Q32", "main_draw", "F", 1400),
    ("WTT Grand Smash", "singles", "Q24/Q32", "main_draw", "SF", 900),
    ("WTT Grand Smash", "singles", "Q24/Q32", "main_draw", "QF", 580),
    ("WTT Grand Smash", "singles", "Q24/Q32", "main_draw", "R16", 380),
    ("WTT Grand Smash", "singles", "Q24/Q32", "main_draw", "R32", 100),
    ("WTT Grand Smash", "singles", "Q24/Q32", "main_draw", "R64", 20),
    ("WTT Grand Smash", "singles", "Q24/Q32", "qualification", "QUAL", 50),
    ("WTT Grand Smash", "singles", "Q24/Q32", "qualification", "R3", 30),
    ("WTT Grand Smash", "singles", "Q24/Q32", "qualification", "R2", 10),

    # WTT 冠军赛
    ("WTT Champions", "singles", None, "main_draw", "W", 1000),
    ("WTT Champions", "singles", None, "main_draw", "F", 700),
    ("WTT Champions", "singles", None, "main_draw", "SF", 450),
    ("WTT Champions", "singles", None, "main_draw", "QF", 300),
    ("WTT Champions", "singles", None, "main_draw", "R16", 140),
    ("WTT Champions", "singles", None, "main_draw", "R32", 15),

    # ITTF 世界杯
    ("ITTF World Cup", "singles", None, "main_draw", "W", 1500),
    ("ITTF World Cup", "singles", None, "main_draw", "F", 1050),
    ("ITTF World Cup", "singles", None, "main_draw", "SF", 680),
    ("ITTF World Cup", "singles", None, "main_draw", "QF", 450),
    ("ITTF World Cup", "singles", None, "main_draw", "R16", 300),
    ("ITTF World Cup", "singles", None, "qualification", "R3", 40),
    ("ITTF World Cup", "singles", None, "qualification", "R2", 15),

    # ITTF 世界乒乓球锦标赛决赛
    ("ITTF World Table Tennis Championships Finals", "singles", None, "main_draw", "W", 2000),
    ("ITTF World Table Tennis Championships Finals", "singles", None, "main_draw", "F", 1400),
    ("ITTF World Table Tennis Championships Finals", "singles", None, "main_draw", "SF", 900),
    ("ITTF World Table Tennis Championships Finals", "singles", None, "main_draw", "QF", 580),
    ("ITTF World Table Tennis Championships Finals", "singles", None, "main_draw", "R16", 380),
    ("ITTF World Table Tennis Championships Finals", "singles", None, "main_draw", "R32", 250),
    ("ITTF World Table Tennis Championships Finals", "singles", None, "main_draw", "R64", 70),
    ("ITTF World Table Tennis Championships Finals", "singles", None, "main_draw", "R128", 10),

    # WTT 球星挑战赛 (Q64)
    ("WTT Star Contender", "singles", "Q64", "main_draw", "W", 600),
    ("WTT Star Contender", "singles", "Q64", "main_draw", "F", 420),
    ("WTT Star Contender", "singles", "Q64", "main_draw", "SF", 270),
    ("WTT Star Contender", "singles", "Q64", "main_draw", "QF", 175),
    ("WTT Star Contender", "singles", "Q64", "main_draw", "R16", 115),
    ("WTT Star Contender", "singles", "Q64", "main_draw", "R32", 30),
    ("WTT Star Contender", "singles", "Q64", "main_draw", "R64", 5),
    ("WTT Star Contender", "singles", "Q64", "qualification", "QUAL", 20),
    ("WTT Star Contender", "singles", "Q64", "qualification", "R4", 12),
    ("WTT Star Contender", "singles", "Q64", "qualification", "R3", 8),
    ("WTT Star Contender", "singles", "Q64", "qualification", "R2", 3),

    # WTT 挑战赛 (Q64)
    ("WTT Contender", "singles", "Q64", "main_draw", "W", 400),
    ("WTT Contender", "singles", "Q64", "main_draw", "F", 280),
    ("WTT Contender", "singles", "Q64", "main_draw", "SF", 180),
    ("WTT Contender", "singles", "Q64", "main_draw", "QF", 120),
    ("WTT Contender", "singles", "Q64", "main_draw", "R16", 30),
    ("WTT Contender", "singles", "Q64", "main_draw", "R32", 4),
    ("WTT Contender", "singles", "Q64", "qualification", "QUAL", 15),
    ("WTT Contender", "singles", "Q64", "qualification", "R4", 10),
    ("WTT Contender", "singles", "Q64", "qualification", "R3", 6),
    ("WTT Contender", "singles", "Q64", "qualification", "R2", 2),

    # WTT 支线赛 (MD32)
    ("WTT Feeder", "singles", "MD32", "main_draw", "W", 125),
    ("WTT Feeder", "singles", "MD32", "main_draw", "F", 90),
    ("WTT Feeder", "singles", "MD32", "main_draw", "SF", 60),
    ("WTT Feeder", "singles", "MD32", "main_draw", "QF", 40),
    ("WTT Feeder", "singles", "MD32", "main_draw", "R16", 10),
    ("WTT Feeder", "singles", "MD32", "main_draw", "R32", 2),
    ("WTT Feeder", "singles", "MD32", "qualification", "R3", 8),
    ("WTT Feeder", "singles", "MD32", "qualification", "R2", 6),
    ("WTT Feeder", "singles", "MD32", "qualification", "R1", 3),
]

# 中文名称映射
EVENT_CATEGORY_ZH = {
    "Olympic Games": "奥运会",
    "WTT Grand Smash": "WTT大满贯",
    "WTT Champions": "WTT冠军赛",
    "ITTF World Cup": "ITTF世界杯",
    "ITTF World Table Tennis Championships Finals": "ITTF世界乒乓球锦标赛决赛",
    "WTT Star Contender": "WTT球星挑战赛",
    "WTT Contender": "WTT挑战赛",
    "WTT Feeder": "WTT支线赛",
}


def import_points_rules(db_path: str) -> bool:
    """导入积分规则"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        effective_date = "2026-01-27"
        inserted = 0

        for event_category, sub_event_category, draw_qualifier, stage_type, position, points in WOMENS_SINGLES_RULES:
            event_category_zh = EVENT_CATEGORY_ZH.get(event_category, "")

            try:
                cursor.execute("""
                    INSERT INTO points_rules
                    (event_category, event_category_zh, sub_event_category, draw_qualifier,
                     stage_type, position, points, effective_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (event_category, event_category_zh, sub_event_category, draw_qualifier,
                      stage_type, position, points, effective_date))
                inserted += 1
            except sqlite3.IntegrityError:
                print(f"  [SKIP] {event_category} | {stage_type} | {position}")

        conn.commit()
        conn.close()

        print(f"Inserted points_rules: {inserted} records")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to import points_rules: {e}")
        return False


def verify_points_rules(db_path: str):
    """验证积分规则"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM points_rules;")
        count = cursor.fetchone()[0]

        cursor.execute("SELECT DISTINCT event_category FROM points_rules ORDER BY event_category;")
        categories = cursor.fetchall()

        print(f"\nVerification:")
        print(f"  Total points_rules: {count}")
        print(f"  Event categories: {len(categories)}")
        for cat in categories:
            print(f"    - {cat[0]}")

        conn.close()
    except Exception as e:
        print(f"[VERIFY FAILED] {e}")


if __name__ == '__main__':
    db_path = Path(config.DB_PATH)

    print("=" * 70)
    print("Import Points Rules")
    print("=" * 70)
    print(f"Database:        {db_path}")
    print(f"Effective date:  2026-01-27")
    print("=" * 70 + "\n")

    if not db_path.exists():
        print(f"[ERROR] Database file not found: {db_path}")
        sys.exit(1)

    print("Importing points_rules (women's singles sample)...")
    success = import_points_rules(str(db_path))

    verify_points_rules(str(db_path))

    print("\nNOTE: This is a sample import for women's singles.")
    print("      Complete rules for all categories can be added from ITTF regulations.")

    sys.exit(0 if success else 1)
