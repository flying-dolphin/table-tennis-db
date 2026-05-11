#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
比赛 side / dedup 键生成的公共逻辑。

抽出自 import_matches.py，供 import_matches.py、promote_current_event.py
共用，避免 key 生成规则在多处实现导致 H2H 去重失效。

⚠ 修改任何函数前必须确认所有调用方都一起更新，否则 promote 与 historical
import 写出的 side_a_key / side_b_key 会不一致，导致同一场比赛被记两份。
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Tuple

__all__ = [
    "normalize_event_name",
    "normalize_name_key",
    "make_side_key",
    "make_dedup_key",
]


def normalize_event_name(name: str) -> str:
    """统一赛事名格式，用于 dedup key 与跨表比对。"""
    s = (name or "").strip().lower()
    s = re.sub(r"\s+presented\s+by\s+.*$", "", s)
    s = re.sub(r"[,.]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_name_key(name: str) -> str:
    """把球员名规范成可比对的 key（顺序无关）。"""
    parts = sorted((name or "").lower().split())
    return " ".join(parts)


def make_side_key(side: Iterable[Tuple[str, Optional[str]]]) -> str:
    """把一侧的所有球员（name, country）拼成稳定可比对的 key。

    规则：
    - 每个球员转为 `lower(name)|lower(country)`
    - 按 ASCII 排序后用 `||` 连接
    - 同侧多人顺序无关；country 为 None / 空串时空字段保留
    """
    keys = []
    for name, country in side:
        n = (name or "").strip().lower()
        c = (country or "").strip().lower()
        keys.append(f"{n}|{c}")
    keys.sort()
    return "||".join(keys)


def make_dedup_key(
    event_name: str,
    sub_event: str,
    stage: str,
    round_: str,
    side_a_key: str,
    side_b_key: str,
) -> str:
    """构造比赛 dedup key。side_a/side_b 顺序无关。"""
    pair = sorted([side_a_key, side_b_key])
    return f"{normalize_event_name(event_name)}|{sub_event}|{stage}|{round_}|{pair[0]}|{pair[1]}"
