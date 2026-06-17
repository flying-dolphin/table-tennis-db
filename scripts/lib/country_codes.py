from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COUNTRY_CODE_MAP_PATH = PROJECT_ROOT / "scripts" / "data" / "country_code_map.json"
COUNTRY_CODE_RE = re.compile(r"^[A-Z]{3}$")


def normalize_country_code(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def normalize_country_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().upper()


def is_country_code(value: Any) -> bool:
    return bool(COUNTRY_CODE_RE.fullmatch(normalize_country_name(value)))


def load_country_code_map(path: Path = DEFAULT_COUNTRY_CODE_MAP_PATH) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    raw = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, str]] = {}
    if not isinstance(raw, dict):
        return result

    for code, value in raw.items():
        normalized_code = normalize_country_code(code)
        if not normalized_code or not isinstance(value, dict):
            continue
        country_en = normalize_country_name(value.get("country_en"))
        country_zh = re.sub(r"\s+", " ", str(value.get("country_zh") or "")).strip()
        if country_en:
            result[normalized_code] = {
                "country_en": country_en,
                "country_zh": country_zh,
            }
    return result


def country_name_for_code(code: Any, mapping: dict[str, dict[str, str]] | None = None) -> str:
    normalized_code = normalize_country_code(code)
    if not normalized_code:
        return ""
    entries = mapping if mapping is not None else load_country_code_map()
    return entries.get(normalized_code, {}).get("country_en", "")


def country_zh_for_code(code: Any, mapping: dict[str, dict[str, str]] | None = None) -> str:
    normalized_code = normalize_country_code(code)
    if not normalized_code:
        return ""
    entries = mapping if mapping is not None else load_country_code_map()
    return entries.get(normalized_code, {}).get("country_zh", "")


def normalize_profile_country(
    profile: dict[str, Any],
    *,
    include_country_zh: bool = False,
    mapping: dict[str, dict[str, str]] | None = None,
) -> tuple[dict[str, Any], bool]:
    entries = mapping if mapping is not None else load_country_code_map()
    changed = False

    code = normalize_country_code(profile.get("country_code"))
    country = normalize_country_name(profile.get("country"))
    country_en = normalize_country_name(profile.get("country_en"))

    if not code and is_country_code(country):
        code = country
        profile["country_code"] = code
        changed = True

    mapped = entries.get(code, {}) if code else {}
    mapped_en = mapped.get("country_en", "")
    mapped_zh = mapped.get("country_zh", "")

    target_en = ""
    if country and not is_country_code(country):
        target_en = country
    elif country_en and not is_country_code(country_en):
        target_en = country_en
    elif mapped_en:
        target_en = mapped_en

    if code and profile.get("country_code") != code:
        profile["country_code"] = code
        changed = True

    if target_en:
        if profile.get("country") != target_en:
            profile["country"] = target_en
            changed = True
        if profile.get("country_en") != target_en:
            profile["country_en"] = target_en
            changed = True

    if include_country_zh and mapped_zh and profile.get("country_zh") != mapped_zh:
        profile["country_zh"] = mapped_zh
        changed = True

    return profile, changed
