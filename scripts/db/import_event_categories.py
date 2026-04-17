#!/usr/bin/env python3
"""
Import event categories from event_category_mapping.json to database
"""

import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

import config

# Windows 编码兼容
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def load_mapping(mapping_file):
    """Load event category mapping from JSON file"""
    with open(mapping_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_insert_sql(mapping_data):
    """Generate SQL INSERT statements for event categories"""

    lines = []
    lines.append("-- Generated INSERT statements for event_categories")
    lines.append(f"-- Generated at: {datetime.now().isoformat()}")
    lines.append("")

    # 生成INSERT语句
    lines.append("INSERT INTO event_categories (")
    lines.append("    category_id, category_name, category_name_zh, json_code,")
    lines.append("    points_tier, points_eligible, filtering_only, ittf_rule_name,")
    lines.append("    applicable_formats, sort_order")
    lines.append(") VALUES")

    values = []
    for i, event in enumerate(mapping_data['events'], start=1):
        applicable_formats = json.dumps(event.get('applicable_formats', []))
        ittf_rule = event.get('ittf_rule_name')
        json_code = f"'{event['json_code']}'" if event.get('json_code') else 'NULL'
        rule_sql = f"'{escape_sql(ittf_rule)}'" if ittf_rule else 'NULL'

        value_str = (
            f"('{event['category_id']}', "
            f"'{escape_sql(event['category_name'])}', "
            f"'{escape_sql(event['category_name_zh'])}', "
            f"{json_code}, "
            f"'{event['points_tier']}', "
            f"{1 if event['points_eligible'] else 0}, "
            f"{1 if event['filtering_only'] else 0}, "
            f"{rule_sql}, "
            f"'{applicable_formats}', "
                f"{i})"
        )
        values.append(value_str)

    lines.append(",\n".join(values))
    lines.append("ON CONFLICT(category_id) DO UPDATE SET")
    lines.append("    category_name=excluded.category_name,")
    lines.append("    category_name_zh=excluded.category_name_zh,")
    lines.append("    json_code=excluded.json_code,")
    lines.append("    points_tier=excluded.points_tier,")
    lines.append("    points_eligible=excluded.points_eligible,")
    lines.append("    filtering_only=excluded.filtering_only,")
    lines.append("    ittf_rule_name=excluded.ittf_rule_name,")
    lines.append("    applicable_formats=excluded.applicable_formats,")
    lines.append("    sort_order=excluded.sort_order;")
    lines.append("")

    return "\n".join(lines)

def generate_mapping_sql(mapping_data):
    """Generate SQL statements for refreshing event_type_mapping"""

    lines = []
    lines.append("\n-- Generated INSERT statements for event_type_mapping")
    lines.append(f"-- Generated at: {datetime.now().isoformat()}")
    lines.append("")

    mappings = []
    for event in mapping_data['events']:
        kinds = [event['event_kind']]
        kinds += event.get('event_kind_aliases', [])
        for kind in kinds:
            delete_sql = (
                "DELETE FROM event_type_mapping "
                f"WHERE event_type = '{escape_sql(event['event_type'])}' "
                f"AND event_kind = '{escape_sql(kind)}';"
            )
            insert_sql = (
                "INSERT INTO event_type_mapping (event_type, event_kind, category_id, priority)\n"
                "SELECT "
                f"'{escape_sql(event['event_type'])}', "
                f"'{escape_sql(kind)}', "
                "id, 10\n"
                "FROM event_categories\n"
                f"WHERE category_id = '{event['category_id']}';"
            )
            mappings.append(delete_sql)
            mappings.append(insert_sql)

    lines.append("-- Refresh event_type/event_kind to category mappings")
    lines.extend(mappings)
    lines.append("")

    return "\n".join(lines)


def import_to_sqlite(db_path, mapping_data):
    """Import mapping data directly into SQLite database."""
    conn = sqlite3.connect(str(db_path))

    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        category_sql = """
            INSERT INTO event_categories (
                category_id, category_name, category_name_zh, json_code,
                points_tier, points_eligible, filtering_only, ittf_rule_name,
                applicable_formats, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(category_id) DO UPDATE SET
                category_name=excluded.category_name,
                category_name_zh=excluded.category_name_zh,
                json_code=excluded.json_code,
                points_tier=excluded.points_tier,
                points_eligible=excluded.points_eligible,
                filtering_only=excluded.filtering_only,
                ittf_rule_name=excluded.ittf_rule_name,
                applicable_formats=excluded.applicable_formats,
                sort_order=excluded.sort_order
        """

        categories = []
        mapping_keys = []
        for i, event in enumerate(mapping_data['events'], start=1):
            applicable_formats = json.dumps(event.get('applicable_formats', []))
            categories.append((
                event['category_id'],
                event['category_name'],
                event['category_name_zh'],
                event.get('json_code'),
                event['points_tier'],
                1 if event['points_eligible'] else 0,
                1 if event['filtering_only'] else 0,
                event.get('ittf_rule_name'),
                applicable_formats,
                i,
            ))
            kinds = [event['event_kind'], *event.get('event_kind_aliases', [])]
            for kind in kinds:
                mapping_keys.append((event['event_type'], kind))

        cursor.executemany(category_sql, categories)

        cursor.executemany(
            "DELETE FROM event_type_mapping WHERE event_type = ? AND event_kind = ?",
            mapping_keys,
        )

        mapping_rows = []
        for event in mapping_data['events']:
            cursor.execute(
                "SELECT id FROM event_categories WHERE category_id = ?",
                (event['category_id'],),
            )
            category_row = cursor.fetchone()
            if not category_row:
                raise RuntimeError(f"Category not found after upsert: {event['category_id']}")

            category_pk = category_row[0]
            kinds = [event['event_kind'], *event.get('event_kind_aliases', [])]
            for kind in kinds:
                mapping_rows.append((event['event_type'], kind, category_pk, 10))

        cursor.executemany(
            """
            INSERT INTO event_type_mapping (event_type, event_kind, category_id, priority)
            VALUES (?, ?, ?, ?)
            """,
            mapping_rows,
        )

        conn.commit()
        return {
            "categories": len(categories),
            "mappings": len(mapping_rows),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def escape_sql(s):
    """Escape single quotes in SQL strings"""
    if not s:
        return ""
    return s.replace("'", "''")

def main():
    mapping_file = config.PROJECT_ROOT / "data" / "event_category_mapping.json"
    db_path = Path(config.DB_PATH)
    output_file = db_path.parent / "import_event_categories_data.sql"

    if not mapping_file.exists():
        print(f"Error: {mapping_file} not found")
        return 1

    print(f"Loading mapping from {mapping_file}...")
    mapping_data = load_mapping(mapping_file)

    print(f"Generating SQL for {len(mapping_data['events'])} categories...")
    sql_lines = []
    sql_lines.append("-- ============================================================================")
    sql_lines.append("-- Event Categories Data Import")
    sql_lines.append(f"-- Generated: {datetime.now().isoformat()}")
    sql_lines.append("-- Source: data/event_category_mapping.json")
    sql_lines.append("-- ============================================================================")
    sql_lines.append("")

    sql_lines.append(generate_insert_sql(mapping_data))
    sql_lines.append(generate_mapping_sql(mapping_data))

    sql_content = "\n".join(sql_lines)

    print(f"Writing SQL to {output_file}...")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(sql_content)

    if not db_path.exists():
        print(f"Error: database not found: {db_path}")
        print("Run scripts/db/init_database.py first.")
        return 1

    print(f"Importing into SQLite database: {db_path}...")
    result = import_to_sqlite(db_path, mapping_data)

    print(f"[OK] SQL file generated: {output_file}")
    print(f"  Total categories: {len(mapping_data['events'])}")
    print(f"  Imported categories: {result['categories']}")
    print(f"  Imported mappings:   {result['mappings']}")
    print("")
    print("Verify with:")
    print("  SELECT category_id, sort_order FROM event_categories ORDER BY sort_order;")
    print("  SELECT event_type, event_kind, category_id FROM event_type_mapping LIMIT 10;")

    return 0

if __name__ == "__main__":
    sys.exit(main())
