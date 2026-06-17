#!/usr/bin/env python3
"""Shared event-name translation helpers."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable

from lib.dict_translator import DictTranslator
from lib.translator import LLMTranslator

logger = logging.getLogger(__name__)

SPONSOR_SUFFIX_RE = re.compile(r"\s+Presented by .*$", re.IGNORECASE)
YEAR_SUFFIX_RE = re.compile(r"^(?P<name>.*?)(?:\s+(?P<year>\d{4}))?$")


@dataclass(frozen=True)
class EventNameParts:
    original: str
    base_name: str
    year: str | None


def split_event_name(value: str) -> EventNameParts:
    stripped = SPONSOR_SUFFIX_RE.sub("", (value or "")).strip()
    match = YEAR_SUFFIX_RE.match(stripped)
    if not match:
        return EventNameParts(original=value, base_name=stripped, year=None)

    base_name = (match.group("name") or "").strip()
    year = match.group("year")
    return EventNameParts(original=value, base_name=base_name or stripped, year=year)


def format_event_translation(translated_base: str, year: str | None) -> str:
    return f"{year}年{translated_base}" if year else translated_base


def _fold_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _dict_lookup(value: str, dict_translator: DictTranslator) -> str | None:
    candidates = []
    for candidate in (value, _fold_accents(value)):
        candidate = candidate.strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        translated = dict_translator.translate(candidate, "events")
        if translated and translated != candidate:
            return translated
    return None


def translate_event_name_dict_only(
    name: str,
    dict_translator: DictTranslator | None = None,
) -> str | None:
    """Translate one event name by dictionary only."""
    translator = dict_translator or DictTranslator()
    parts = split_event_name(name)

    translated_base = _dict_lookup(parts.base_name, translator)
    if translated_base:
        return format_event_translation(translated_base, parts.year)

    translated_full = _dict_lookup(SPONSOR_SUFFIX_RE.sub("", (name or "")).strip(), translator)
    if translated_full:
        return translated_full

    return None


def _translate_event_batch_llm_only(
    items: dict[str, str],
    llm_translator: LLMTranslator,
    on_batch_complete: Callable[[int, int, dict[str, str]], None] | None = None,
) -> dict[str, str] | None:
    if hasattr(llm_translator, "translate_event_batch"):
        result = llm_translator.translate_event_batch(items)
        if on_batch_complete is not None:
            on_batch_complete(1, 1, dict(result))
        return result

    if getattr(llm_translator, "api_key", None) is None:
        logger.error("未配置 API Key，无法进行 LLM-only event 翻译")
        return None

    batches = llm_translator._split_batches(items)  # noqa: SLF001 - centralized wrapper for legacy translator.
    results: dict[str, str] = {}
    for index, batch in enumerate(batches, 1):
        batch_result = llm_translator._translate_batch(batch, category="event")  # noqa: SLF001
        if not batch_result:
            return None
        results.update(batch_result)
        if on_batch_complete is not None:
            on_batch_complete(index, len(batches), dict(batch_result))
    return results


def translate_event_names_llm_only(
    items: dict[str, str],
    llm_translator: LLMTranslator | None = None,
    on_batch_complete: Callable[[int, int, dict[str, str]], None] | None = None,
) -> dict[str, str] | None:
    """Translate event names with LLM only, bypassing dictionary lookup."""
    translator = llm_translator or LLMTranslator()
    llm_items: dict[str, str] = {}
    years: dict[str, str] = {}

    for key, value in items.items():
        parts = split_event_name(value)
        llm_items[key] = parts.base_name
        if parts.year:
            years[key] = parts.year

    translated = _translate_event_batch_llm_only(llm_items, translator, on_batch_complete)
    if translated is None:
        return None

    return {
        key: format_event_translation(translated.get(key, value), years.get(key))
        for key, value in llm_items.items()
    }


def translate_event_names_dict_then_llm(
    items: dict[str, str],
    dict_translator: DictTranslator | None = None,
    llm_translator: LLMTranslator | None = None,
    on_batch_complete: Callable[[int, int, dict[str, str]], None] | None = None,
) -> dict[str, str] | None:
    """Translate event names via dictionary first, then LLM for dictionary misses."""
    dict_translator = dict_translator or DictTranslator()
    dict_results: dict[str, str] = {}
    llm_items: dict[str, str] = {}

    for key, value in items.items():
        translated = translate_event_name_dict_only(value, dict_translator)
        if translated is None:
            llm_items[key] = value
        else:
            dict_results[key] = translated

    if not llm_items:
        if on_batch_complete is not None and dict_results:
            on_batch_complete(1, 1, dict(dict_results))
        return dict_results

    llm_results = translate_event_names_llm_only(
        llm_items,
        llm_translator=llm_translator,
        on_batch_complete=on_batch_complete,
    )
    if llm_results is None:
        return None

    merged: dict[str, str] = {}
    for key in items:
        if key in dict_results:
            merged[key] = dict_results[key]
        elif key in llm_results:
            merged[key] = llm_results[key]
        else:
            merged[key] = items[key]
    return merged
