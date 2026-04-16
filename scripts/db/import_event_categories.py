#!/usr/bin/env python3
"""
Import event categories from event_category_mapping.json to database
"""

import json
import sys
from pathlib import Path
from datetime import datetime

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
    lines.append("    applicable_formats")
    lines.append(") VALUES")

    values = []
    for i, event in enumerate(mapping_data['events']):
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
            f"'{applicable_formats}')"
        )
        values.append(value_str)

    lines.append(",\n".join(values))
    lines.append("ON DUPLICATE KEY UPDATE")
    lines.append("    category_name=VALUES(category_name),")
    lines.append("    category_name_zh=VALUES(category_name_zh),")
    lines.append("    json_code=VALUES(json_code),")
    lines.append("    points_tier=VALUES(points_tier),")
    lines.append("    points_eligible=VALUES(points_eligible),")
    lines.append("    filtering_only=VALUES(filtering_only),")
    lines.append("    ittf_rule_name=VALUES(ittf_rule_name),")
    lines.append("    applicable_formats=VALUES(applicable_formats);")
    lines.append("")

    return "\n".join(lines)

def generate_mapping_sql(mapping_data):
    """Generate SQL INSERT statements for event_type_mapping"""

    lines = []
    lines.append("\n-- Generated INSERT statements for event_type_mapping")
    lines.append(f"-- Generated at: {datetime.now().isoformat()}")
    lines.append("")

    # 创建临时映射关系
    lines.append("-- Map event_type/event_kind to categories")
    lines.append("INSERT INTO event_type_mapping (event_type, event_kind, category_id, priority)")
    lines.append("SELECT")
    lines.append("    em.event_type,")
    lines.append("    em.event_kind,")
    lines.append("    ec.id,")
    lines.append("    em.priority")
    lines.append("FROM (")

    mappings = []
    for event in mapping_data['events']:
        # 主 event_kind
        kinds = [event['event_kind']]
        # 追加 aliases（如 ITTF WTTC 的 'WTTC Finals'）
        kinds += event.get('event_kind_aliases', [])
        for kind in kinds:
            mapping = (
                f"  SELECT '{escape_sql(event['event_type'])}' as event_type, "
                f"'{escape_sql(kind)}' as event_kind, "
                f"'{event['category_id']}' as category_id, "
                f"10 as priority"
            )
            mappings.append(mapping)

    lines.append("\n  UNION ALL\n".join(mappings))
    lines.append(") em")
    lines.append("JOIN event_categories ec ON em.category_id = ec.category_id")
    lines.append("ON DUPLICATE KEY UPDATE priority=VALUES(priority);")
    lines.append("")

    return "\n".join(lines)

def escape_sql(s):
    """Escape single quotes in SQL strings"""
    if not s:
        return ""
    return s.replace("'", "''")

def main():
    mapping_file = Path("data/event_category_mapping.json")
    output_file = Path("scripts/db/import_event_categories_data.sql")

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

    print(f"[OK] SQL file generated: {output_file}")
    print(f"  Total categories: {len(mapping_data['events'])}")
    print("")
    print("Next steps:")
    print(f"  1. Run: mysql -u root -p your_database < {output_file}")
    print(f"  2. Verify the import with:")
    print("     SELECT * FROM event_categories LIMIT 10;")
    print("     SELECT * FROM event_type_mapping LIMIT 10;")

    return 0

if __name__ == "__main__":
    sys.exit(main())
