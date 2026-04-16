#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
赛事数据规范化：统一四个数据源的赛事名称，建立 event_name → event_id 映射。

数据源：
  1. events_list     (有 event_id)  -> data/events_list/cn/*.json
  2. events_calendar (href 中有 eventId) -> data/events_calendar/cn/*.json
  3. matches_list    (无 event_id)  -> tmp/matches_list
  4. rankings_event  (无 event_id)  -> tmp/rankings_event.txt

输出：
  - tmp/event_mapping.json    统一映射表
  - tmp/event_unmatched.txt   无法匹配的事件（人工审查）
  - tmp/event_report.txt      对账报告
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent.parent


# ============================================================================
# 规范化
# ============================================================================

def normalize_event_name(name: str) -> str:
    """
    规范化赛事名称，用于精确匹配。

    规则：
    - 转小写
    - 去除首尾空格
    - 压缩多余空格
    - 去除 "Presented by ..." 赞助商后缀
    - 去除多余标点
    """
    s = name.strip().lower()
    # 去掉赞助商后缀
    s = re.sub(r'\s+presented\s+by\s+.*$', '', s)
    # 去掉多余标点（保留连字符和撇号）
    s = re.sub(r'[,.]', '', s)
    # 压缩空格
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


# ============================================================================
# 加载数据
# ============================================================================

def load_events_list() -> dict:
    """从 events_list JSON 加载 {normalized_name: {event_id, name, year, ...}}"""
    result = {}
    json_dir = PROJECT_ROOT / "data" / "events_list" / "cn"
    for json_file in json_dir.glob("*.json"):
        data = json.load(open(json_file, encoding='utf-8'))
        for event in data.get('events', []):
            event_id = event.get('event_id')
            name = event.get('name', '')
            if not event_id or not name:
                continue
            norm = normalize_event_name(name)
            result[norm] = {
                'event_id': event_id,
                'name': name,
                'name_zh': event.get('name_zh'),
                'year': event.get('year'),
                'event_type': event.get('event_type'),
                'source': 'events_list',
            }
    return result


def load_events_calendar() -> dict:
    """从 events_calendar JSON 加载 {normalized_name: {event_id (from href), name, ...}}"""
    result = {}
    json_dir = PROJECT_ROOT / "data" / "events_calendar" / "cn"
    for json_file in json_dir.glob("*.json"):
        data = json.load(open(json_file, encoding='utf-8'))
        for event in data.get('events', []):
            name = event.get('name', '')
            if not name:
                continue
            # 从 href 提取 eventId
            href = event.get('href', '')
            event_id = None
            m = re.search(r'eventId=(\d+)', href)
            if m:
                event_id = int(m.group(1))

            norm = normalize_event_name(name)
            result[norm] = {
                'event_id': event_id,
                'name': name,
                'name_zh': event.get('name_zh'),
                'source': 'events_calendar',
            }
    return result


def load_txt_list(filepath: Path) -> list:
    """从文本文件加载事件名列表（每行一个）"""
    if not filepath.exists():
        return []
    with open(filepath, encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


# ============================================================================
# 匹配逻辑
# ============================================================================

def build_unified_mapping():
    """
    构建统一映射表。

    优先级：
    1. events_list 有 event_id → 直接作为事实
    2. events_calendar 有 event_id（从 href）→ 补充事实
    3. matches_list / rankings_event → 通过规范化名称匹配上面两个源
    """

    print("Loading data sources...")

    # 加载两个有 event_id 的源
    events_list = load_events_list()
    events_calendar = load_events_calendar()

    # 加载两个无 event_id 的源
    matches_names = load_txt_list(PROJECT_ROOT / "tmp" / "matches_list")
    rankings_names = load_txt_list(PROJECT_ROOT / "tmp" / "rankings_event.txt")

    print(f"  events_list:     {len(events_list)} events (with event_id)")
    print(f"  events_calendar: {len(events_calendar)} events (event_id from href)")
    print(f"  matches_list:    {len(matches_names)} events (name only)")
    print(f"  rankings_event:  {len(rankings_names)} events (name only)")

    # ---- Step 1: 合并两个有 ID 的源，建立 norm_name → event_id 索引 ----
    id_index = {}  # norm_name → {event_id, name, source, ...}

    # events_list 优先
    for norm, info in events_list.items():
        id_index[norm] = info

    # events_calendar 补充（如果 events_list 没有，或者 events_list 没 event_id）
    calendar_new = 0
    calendar_conflict = 0
    for norm, info in events_calendar.items():
        if norm not in id_index:
            if info['event_id'] is not None:
                id_index[norm] = info
                calendar_new += 1
        else:
            # 已在 events_list 中，校验 event_id 是否一致
            existing_id = id_index[norm].get('event_id')
            cal_id = info.get('event_id')
            if existing_id and cal_id and existing_id != cal_id:
                calendar_conflict += 1

    print(f"\n  ID index: {len(id_index)} unique events")
    print(f"  Calendar contributed {calendar_new} new events")
    if calendar_conflict:
        print(f"  WARNING: {calendar_conflict} event_id conflicts between sources")

    # ---- Step 2: 匹配 matches_list 和 rankings_event ----
    mapping = {}       # 最终映射：original_name → {event_id, norm_name, source, ...}
    unmatched = []     # 无法匹配的事件
    source_stats = defaultdict(lambda: {'total': 0, 'matched': 0, 'unmatched': 0})

    # 处理所有四个源
    all_names_with_source = []
    for name in matches_names:
        all_names_with_source.append((name, 'matches'))
    for name in rankings_names:
        all_names_with_source.append((name, 'rankings'))

    for original_name, source in all_names_with_source:
        norm = normalize_event_name(original_name)
        source_stats[source]['total'] += 1

        if norm in id_index:
            info = id_index[norm]
            mapping[original_name] = {
                'event_id': info['event_id'],
                'matched_name': info['name'],
                'normalized': norm,
                'source': source,
                'id_source': info['source'],
            }
            source_stats[source]['matched'] += 1
        else:
            unmatched.append({
                'name': original_name,
                'normalized': norm,
                'source': source,
            })
            source_stats[source]['unmatched'] += 1

    # 也检查 events_calendar 中无 event_id 且不在 events_list 中的
    for norm, info in events_calendar.items():
        if info['event_id'] is None and norm not in events_list:
            unmatched.append({
                'name': info['name'],
                'normalized': norm,
                'source': 'events_calendar (no event_id)',
            })

    return {
        'id_index': id_index,
        'mapping': mapping,
        'unmatched': unmatched,
        'source_stats': dict(source_stats),
        'events_list_count': len(events_list),
        'events_calendar_count': len(events_calendar),
    }


# ============================================================================
# 输出
# ============================================================================

def save_results(result: dict):
    """保存映射表、未匹配清单、对账报告"""
    tmp_dir = PROJECT_ROOT / "tmp"
    tmp_dir.mkdir(exist_ok=True)

    # 1. 映射表（event_name → event_id 的完整索引）
    mapping_output = {}
    for norm, info in result['id_index'].items():
        mapping_output[norm] = {
            'event_id': info['event_id'],
            'name': info['name'],
            'name_zh': info.get('name_zh'),
            'source': info['source'],
        }

    mapping_path = tmp_dir / "event_mapping.json"
    with open(mapping_path, 'w', encoding='utf-8') as f:
        json.dump(mapping_output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {mapping_path} ({len(mapping_output)} entries)")

    # 2. 未匹配清单
    unmatched_path = tmp_dir / "event_unmatched.txt"
    with open(unmatched_path, 'w', encoding='utf-8') as f:
        f.write(f"# Unmatched events - {len(result['unmatched'])} total\n")
        f.write(f"# Format: [source] original_name | normalized\n\n")
        for item in sorted(result['unmatched'], key=lambda x: x['source']):
            f.write(f"[{item['source']:12s}] {item['name']}\n")
            f.write(f"               -> {item['normalized']}\n\n")
    print(f"Saved: {unmatched_path} ({len(result['unmatched'])} entries)")

    # 3. 对账报告
    report_path = tmp_dir / "event_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("Event Normalization Report\n")
        f.write("=" * 70 + "\n\n")

        f.write("Data sources:\n")
        f.write(f"  events_list:     {result['events_list_count']:5d} events (truth source, has event_id)\n")
        f.write(f"  events_calendar: {result['events_calendar_count']:5d} events (event_id from href)\n")
        f.write(f"  Unified ID index: {len(result['id_index']):5d} unique events with event_id\n\n")

        f.write("Matching results:\n")
        for source, stats in result['source_stats'].items():
            total = stats['total']
            matched = stats['matched']
            pct = (matched / total * 100) if total else 0
            f.write(f"  {source:15s}: {matched:4d}/{total:4d} matched ({pct:.1f}%)\n")

        f.write(f"\nUnmatched events: {len(result['unmatched'])} (need manual review)\n")

    print(f"Saved: {report_path}")


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    print("=" * 70)
    print("Event Normalization")
    print("=" * 70 + "\n")

    result = build_unified_mapping()

    # 打印摘要
    print(f"\n{'='*70}")
    print("Summary")
    print("=" * 70)
    print(f"Unified ID index: {len(result['id_index'])} events with event_id")
    for source, stats in result['source_stats'].items():
        total = stats['total']
        matched = stats['matched']
        unmatched = stats['unmatched']
        pct = (matched / total * 100) if total else 0
        print(f"  {source:15s}: {matched:4d}/{total:4d} matched ({pct:.1f}%), {unmatched} unmatched")
    print(f"  Total unmatched: {len(result['unmatched'])}")

    save_results(result)

    print("\nDone. Review tmp/event_unmatched.txt for manual mapping.")
