#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初始化 ITTF 数据库：执行 DDL 建表
"""

import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime

import config

# Windows 编码兼容
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def init_database(db_path: str, schema_path: str) -> bool:
    """
    初始化数据库，执行 DDL 建表

    Args:
        db_path: 数据库文件路径
        schema_path: DDL schema 文件路径

    Returns:
        成功返回 True，失败返回 False
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # 如果数据库已存在，备份旧版本
        if os.path.exists(db_path):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{db_path}.backup.{timestamp}"
            os.rename(db_path, backup_path)
            print(f"[BACKUP] Old database: {backup_path}")

        # 读取 schema
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        # 连接数据库并执行 DDL
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 启用外键约束
        cursor.execute("PRAGMA foreign_keys = ON;")

        # 执行所有 DDL（按分号分割）
        statements = [s.strip() for s in schema_sql.split(';') if s.strip()]

        for i, stmt in enumerate(statements, 1):
            try:
                cursor.execute(stmt)
                print(f"  [{i:2d}/{len(statements):2d}] DDL executed")
            except sqlite3.Error as e:
                print(f"  [ERROR {i:2d}] {e}")
                print(f"     SQL: {stmt[:100]}...")
                return False

        conn.commit()
        conn.close()

        print(f"\n[SUCCESS] Database initialized: {db_path}")

        # 验证表
        verify_tables(db_path)

        return True

    except Exception as e:
        print(f"[FAILED] {e}")
        return False


def verify_tables(db_path: str):
    """验证数据库中的表"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = cursor.fetchall()

        print(f"\nTotal tables: {len(tables)}")
        print("Table list:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND tbl_name='{table[0]}';")
            index_count = cursor.fetchone()[0]
            print(f"  - {table[0]:20s} (indexes: {index_count})")

        conn.close()
    except Exception as e:
        print(f"[VERIFY FAILED] {e}")


if __name__ == '__main__':
    db_path = Path(config.DB_PATH)
    schema_path = Path(config.SCHEMA_PATH)

    print("=" * 70)
    print("Initialize ITTF Database")
    print("=" * 70)
    print(f"Database: {db_path}")
    print(f"Schema:   {schema_path}")
    print("=" * 70 + "\n")

    if not schema_path.exists():
        print(f"[ERROR] Schema file not found: {schema_path}")
        sys.exit(1)

    success = init_database(str(db_path), str(schema_path))
    sys.exit(0 if success else 1)
