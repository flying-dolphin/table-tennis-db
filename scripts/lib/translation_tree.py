#!/usr/bin/env python3
"""
JSON 树结构翻译工具

递归遍历 JSON 数据，收集需要翻译的字符串字段，
批量调用 LLMTranslator 翻译后回填。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from lib.translator import LLMTranslator

_ENGLISH_WORD_RE = re.compile(r"[A-Za-z]")
_URL_RE = re.compile(r"^(?:https?://|www\.)", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_SKIP_KEY_EXACT = {
    "id",
    "uuid",
    "url",
    "href",
    "link",
    "source_url",
    "api_url",
    "image_url",
    "avatar_url",
    "thumbnail_url",
    "file_url",
    "pdf_url",
}

_SKIP_KEY_SUFFIXES = (
    "_id",
    "_url",
    "_href",
    "_path",
    "_file",
)

_LOCATION_KEYS = {
    "country",
    "country_code",
    "countryname",
    "country_name",
    "location",
    "location_name",
    "nationality",
    "origin",
    "opponent_country",
}

_PLAYER_KEYS = {
    "name",
    "player",
    "player_name",
    "opponent",
    "athlete",
}

_EVENT_KEYS = {
    "event",
    "event_name",
    "event_type",
    "sub_event",
}

_TERM_KEYS = {
    "date",
    "gender",
    "grip",
    "playing_hand",
    "result",
    "round",
    "stage",
    "style",
    "term",
    "terms",
}


@dataclass(frozen=True)
class TranslationFailure:
    path: str
    original: str
    category: str
    translated: str | None


class TranslationTreeError(RuntimeError):
    pass


def _path_to_str(path: tuple[str, ...]) -> str:
    if not path:
        return "$"
    return "$." + ".".join(path)


def _last_key(path: tuple[str, ...]) -> str:
    for segment in reversed(path):
        if not segment.startswith("["):
            return segment.lower()
    return ""


def should_translate_value(path: tuple[str, ...], value: str) -> bool:
    if not isinstance(value, str):
        return False

    text = value.strip()
    if not text:
        return False
    if not _ENGLISH_WORD_RE.search(text):
        return False

    key = _last_key(path)
    if key in _SKIP_KEY_EXACT:
        return False
    if any(key.endswith(suffix) for suffix in _SKIP_KEY_SUFFIXES):
        return False
    if _URL_RE.match(text) or _EMAIL_RE.match(text):
        return False
    return True


def infer_category(path: tuple[str, ...], value: str) -> str:
    key = _last_key(path)
    path_lower = [segment.lower() for segment in path if not segment.startswith("[")]

    if key in _LOCATION_KEYS:
        return "locations"
    if key in _PLAYER_KEYS:
        if "event" in path_lower:
            return "events"
        return "players"
    if key in _EVENT_KEYS or "event" in path_lower or "calendar" in path_lower:
        return "events"
    if key in _TERM_KEYS:
        return "terms"

    if key == "name":
        if "event" in path_lower:
            return "events"
        if "player" in path_lower or "rank" in path_lower or "opponent" in path_lower:
            return "players"
        return "players"

    if "country" in key or "location" in key:
        return "locations"
    if "stage" in key or "round" in key or "gender" in key or "grip" in key or "hand" in key or "style" in key:
        return "terms"
    if "event" in key:
        return "events"
    if "player" in key or "opponent" in key:
        return "players"

    return "others"


def translate_json_tree(data: Any, translator: LLMTranslator) -> Any:
    """
    递归遍历 JSON 树，收集需要翻译的字符串，批量调用 LLM 翻译后回填。

    Args:
        data: JSON 数据（dict/list/str/其他）
        translator: LLMTranslator 实例

    Returns:
        翻译后的 JSON 数据

    Raises:
        TranslationTreeError: 存在未翻译完成的字段
    """
    # 第一步：收集所有需要翻译的节点
    to_translate: dict[str, str] = {}  # path_str -> original_value
    path_to_key: dict[str, str] = {}  # path_str -> category hint as part of key

    def collect(node: Any, path: tuple[str, ...]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                collect(value, path + (key,))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                collect(item, path + (f"[{index}]",))
        elif isinstance(node, str):
            if should_translate_value(path, node):
                path_str = _path_to_str(path)
                category = infer_category(path, node)
                # 用 "path[category]" 作为 key 给 LLM 参考上下文
                ref_key = f"{path_str}[{category}]"
                to_translate[ref_key] = node
                path_to_key[path_str] = ref_key

    collect(data, ())

    if not to_translate:
        return data

    # 第二步：批量翻译
    translated_map = translator.translate(to_translate)

    # 第三步：回填翻译结果
    failures: list[TranslationFailure] = []

    def fill(node: Any, path: tuple[str, ...]) -> Any:
        if isinstance(node, dict):
            return {key: fill(value, path + (key,)) for key, value in node.items()}
        if isinstance(node, list):
            return [fill(item, path + (f"[{index}]",)) for index, item in enumerate(node)]
        if isinstance(node, str):
            path_str = _path_to_str(path)
            ref_key = path_to_key.get(path_str)
            if ref_key is None:
                return node
            translated = translated_map.get(ref_key)
            if not isinstance(translated, str) or translated.strip() == node.strip():
                category = infer_category(path, node)
                failures.append(
                    TranslationFailure(
                        path=path_str,
                        original=node,
                        category=category,
                        translated=translated if isinstance(translated, str) else None,
                    )
                )
                return node
            return translated
        return node

    result = fill(data, ())
    if failures:
        lines = [
            f"{f.path} [{f.category}]: {f.original!r} -> {f.translated!r}"
            for f in failures[:20]
        ]
        more = "" if len(failures) <= 20 else f" (+{len(failures) - 20} more)"
        raise TranslationTreeError("未翻译完成的字段:\n" + "\n".join(lines) + more)
    return result
