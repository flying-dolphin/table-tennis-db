#!/usr/bin/env python3
"""
纯词典翻译器

从 translation_dict_v2.json 加载词典，提供纯词典查询翻译。
不调用任何 LLM API。
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_DICT_PATH = Path(__file__).parent.parent / "data" / "translation_dict_v2.json"


class DictTranslator:
    def __init__(self, dict_path: Path | str | None = None):
        path = Path(dict_path) if dict_path else DEFAULT_DICT_PATH
        self.players: dict[str, str] = {}
        self.locations: dict[str, str] = {}
        self.countries: dict[str, str] = {}
        self.events: dict[str, str] = {}
        self.position: dict[str, str] = {}
        self.terms_others: dict[str, str] = {}
        self._load(path)

    def _load(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, entry in data.get("entries", {}).items():
            key_lower = key.lower()
            cats = set(entry.get("categories", []))
            translated = entry.get("translated", key)
            if "players" in cats:
                self.players[key_lower] = translated
            if "locations" in cats:
                self.locations[key_lower] = translated
            if "country" in cats:
                self.countries[key_lower] = translated
            if "events" in cats:
                self.events[key_lower] = translated
            if "position" in cats:
                self.position[key_lower] = translated
            if "terms" in cats or "others" in cats:
                self.terms_others[key_lower] = translated

    def translate(self, value: str | None, category: str) -> str | None:
        if value is None:
            return None
        val_lower = value.lower()
        mapping = {
            "players": self.players,
            "locations": self.locations,
            "countries": self.countries,
            "events": self.events,
            "position": self.position,
            "terms_others": self.terms_others,
        }[category]
        result = mapping.get(val_lower)
        if result:
            return result
        if category == "countries":
            return self.locations.get(val_lower) or value
        if category == "locations":
            return self.countries.get(val_lower) or value
        return value
