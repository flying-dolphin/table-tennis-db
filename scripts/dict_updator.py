#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dict_updator.py
从爬取的数据中收集尚未被翻译的英文单词，翻译整理成新的词条更新到词典中。
"""

import json
import glob
import re
import string
from collections import defaultdict
from datetime import datetime

# 词典路径
DICT_PATH = "scripts/data/translation_dict_v2.json"
# 临时输出路径
OUTPUT_PATH = "scripts/data/dict_candidates_temp.json"

# 待扫描的源文件 glob 模式
GLOB_PATTERNS = [
    "data/matches_complete/orig/*.json",
    "data/events_calendar/orig/*.json",
    "data/player_profiles/orig/*.json",
]

# 正则：匹配 ISO 时间戳
RE_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[tT]\d{2}:\d{2}:\d{2}")
# 正则：匹配 URL
RE_URL = re.compile(r"^https?://")
# 正则：匹配文件扩展名
RE_FILE_EXT = re.compile(r"\.(png|jpg|jpeg|webp|gif|pdf|json|xml|csv|txt)$", re.IGNORECASE)


def load_dict_keys(path: str) -> set:
    """加载词典，返回所有 entry key 的集合（小写）。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("entries", {}).keys())


def extract_string_values(obj):
    """递归遍历 JSON 对象，提取所有字符串类型的 value。"""
    values = []
    if isinstance(obj, dict):
        for v in obj.values():
            values.extend(extract_string_values(v))
    elif isinstance(obj, list):
        for item in obj:
            values.extend(extract_string_values(item))
    elif isinstance(obj, str):
        values.append(obj)
    return values


def contains_english(text: str) -> bool:
    """判断字符串中是否包含英文字母。"""
    return bool(re.search(r"[a-zA-Z]", text))


def is_noise_value(text: str) -> bool:
    """判断该 value 是否为无需收录的噪音（时间戳、URL 等）。"""
    if RE_URL.match(text):
        return True
    if RE_TIMESTAMP.match(text):
        return True
    return False


def is_noise_word(word: str) -> bool:
    """判断切分后的 word 是否为噪音。"""
    # 纯数字
    if word.isdigit():
        return True
    # 包含文件扩展名
    if RE_FILE_EXT.search(word):
        return True
    # 包含特殊符号（如邮箱、路径等）
    if "/" in word or "\\" in word or "@" in word:
        return True
    return False


def split_words(text: str) -> list:
    """
    对文本按空格切分，清理两端标点，转小写，返回单词列表。
    只保留包含英文字母且非噪音的 token。
    """
    words = []
    for token in text.split():
        clean = token.strip(string.punctuation)
        if not clean:
            continue
        if not re.search(r"[a-zA-Z]", clean):
            continue
        low = clean.lower()
        if is_noise_word(low):
            continue
        words.append(low)
    return words


def main():
    dict_keys = load_dict_keys(DICT_PATH)

    # 1. 从指定文件中提取所有字符串 value
    all_values = []
    for pattern in GLOB_PATTERNS:
        files = glob.glob(pattern)
        for filepath in files:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            all_values.extend(extract_string_values(data))

    # 去重，减少后续处理量
    unique_values = set(all_values)

    # 过滤：只保留包含英文单词且非噪音的 value
    english_values = [v for v in unique_values if contains_english(v) and not is_noise_value(v)]

    # 2. 切分并合并：word -> set(原始词条)
    word_to_sources = defaultdict(set)
    for value in english_values:
        for w in split_words(value):
            word_to_sources[w].add(value)

    # 3. 过滤掉已经在词典中的 word
    candidates = {}
    for word, sources in word_to_sources.items():
        if word not in dict_keys:
            candidates[word] = sorted(sources)

    # 4. 输出到临时文件
    output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_candidates": len(candidates),
            "dict_path": DICT_PATH,
            "source_patterns": GLOB_PATTERNS,
        },
        "candidates": dict(sorted(candidates.items())),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8", newline="") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Done. Found {len(candidates)} candidate words not in dictionary.")
    print(f"Output written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
