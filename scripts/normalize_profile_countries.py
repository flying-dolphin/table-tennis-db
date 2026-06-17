#!/usr/bin/env python3
"""Normalize country fields in player profile JSON files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from lib.country_codes import (
    DEFAULT_COUNTRY_CODE_MAP_PATH,
    is_country_code,
    load_country_code_map,
    normalize_country_code,
    normalize_country_name,
    normalize_profile_country,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_DIR = PROJECT_ROOT / "data" / "player_profiles"
DEFAULT_DICT_PATH = PROJECT_ROOT / "scripts" / "data" / "translation_dict_v2.json"

MANUAL_COUNTRY_MAP: dict[str, dict[str, str]] = {
    "AIN": {"country_en": "INDIVIDUAL NEUTRAL ATHLETES", "country_zh": "中立个人运动员"},
    "BDI": {"country_en": "BURUNDI", "country_zh": "布隆迪"},
    "BIZ": {"country_en": "BELIZE", "country_zh": "伯利兹"},
    "BOL": {"country_en": "BOLIVIA", "country_zh": "玻利维亚"},
    "BRN": {"country_en": "BAHRAIN", "country_zh": "巴林"},
    "CYP": {"country_en": "CYPRUS", "country_zh": "塞浦路斯"},
    "EST": {"country_en": "ESTONIA", "country_zh": "爱沙尼亚"},
    "ETH": {"country_en": "ETHIOPIA", "country_zh": "埃塞俄比亚"},
    "FIJ": {"country_en": "FIJI", "country_zh": "斐济"},
    "IRL": {"country_en": "IRELAND", "country_zh": "爱尔兰"},
    "KEN": {"country_en": "KENYA", "country_zh": "肯尼亚"},
    "KUW": {"country_en": "KUWAIT", "country_zh": "科威特"},
    "LBA": {"country_en": "LIBYA", "country_zh": "利比亚"},
    "MAR": {"country_en": "MOROCCO", "country_zh": "摩洛哥"},
    "MLT": {"country_en": "MALTA", "country_zh": "马耳他"},
    "MNE": {"country_en": "MONTENEGRO", "country_zh": "黑山"},
    "MYA": {"country_en": "MYANMAR", "country_zh": "缅甸"},
    "PAK": {"country_en": "PAKISTAN", "country_zh": "巴基斯坦"},
    "PNG": {"country_en": "PAPUA NEW GUINEA", "country_zh": "巴布亚新几内亚"},
    "REF": {"country_en": "REFUGEE TEAM", "country_zh": "难民队"},
    "RWA": {"country_en": "RWANDA", "country_zh": "卢旺达"},
    "SCO": {"country_en": "SCOTLAND", "country_zh": "苏格兰"},
    "SEY": {"country_en": "SEYCHELLES", "country_zh": "塞舌尔"},
    "SOL": {"country_en": "SOLOMON ISLANDS", "country_zh": "所罗门群岛"},
    "TGA": {"country_en": "TONGA", "country_zh": "汤加"},
    "TKM": {"country_en": "TURKMENISTAN", "country_zh": "土库曼斯坦"},
    "UAE": {"country_en": "UNITED ARAB EMIRATES", "country_zh": "阿联酋"},
    "USA": {"country_en": "UNITED STATES", "country_zh": "美国"},
    "VAN": {"country_en": "VANUATU", "country_zh": "瓦努阿图"},
    "ZAM": {"country_en": "ZAMBIA", "country_zh": "赞比亚"},
}


def load_location_translations(dict_path: Path) -> dict[str, str]:
    if not dict_path.exists():
        return {}
    raw = json.loads(dict_path.read_text(encoding="utf-8"))
    translations: dict[str, str] = {}
    for key, value in raw.get("entries", {}).items():
        if not isinstance(value, dict):
            continue
        code = normalize_country_code(key)
        if not re.fullmatch(r"[A-Z]{3}", code):
            continue
        if "locations" not in value.get("categories", []):
            continue
        translated = str(value.get("translated") or "").strip()
        if translated:
            translations[code] = translated
    return translations


def iter_profile_files(profile_dir: Path) -> list[Path]:
    files: list[Path] = []
    for subdir in (profile_dir / "orig", profile_dir / "cn"):
        if subdir.exists():
            files.extend(sorted(subdir.glob("player_*.json")))
    return files


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def build_country_code_map(profile_dir: Path, dict_path: Path, map_path: Path) -> dict[str, dict[str, str]]:
    mapping = load_country_code_map(map_path)

    for code, value in MANUAL_COUNTRY_MAP.items():
        mapping.setdefault(code, value)

    for path in iter_profile_files(profile_dir):
        data = load_json(path)
        if not data:
            continue
        code = normalize_country_code(data.get("country_code"))
        country = normalize_country_name(data.get("country"))
        if not code or not country or is_country_code(country):
            continue
        mapping.setdefault(code, {"country_en": country, "country_zh": ""})

    translations = load_location_translations(dict_path)
    for code, translated in translations.items():
        if code in mapping:
            mapping[code]["country_zh"] = mapping[code].get("country_zh") or translated

    return dict(sorted(mapping.items()))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_files(profile_dir: Path, mapping: dict[str, dict[str, str]], dry_run: bool) -> tuple[int, list[str]]:
    changed_count = 0
    unresolved: list[str] = []

    for path in iter_profile_files(profile_dir):
        data = load_json(path)
        if not data:
            unresolved.append(f"{path}: invalid json")
            continue

        include_country_zh = path.parent.name == "cn"
        before = json.dumps(data, ensure_ascii=False, sort_keys=True)
        normalize_profile_country(data, include_country_zh=include_country_zh, mapping=mapping)
        after = json.dumps(data, ensure_ascii=False, sort_keys=True)

        code = normalize_country_code(data.get("country_code"))
        country = normalize_country_name(data.get("country"))
        if code and (not country or is_country_code(country)):
            unresolved.append(f"{path}: country_code={code} country={country or '<empty>'}")

        if before != after:
            changed_count += 1
            if not dry_run:
                write_json(path, data)

    return changed_count, unresolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize country fields in player profile JSON files")
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR))
    parser.add_argument("--dict-path", default=str(DEFAULT_DICT_PATH))
    parser.add_argument("--map-path", default=str(DEFAULT_COUNTRY_CODE_MAP_PATH))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    profile_dir = Path(args.profile_dir)
    dict_path = Path(args.dict_path)
    map_path = Path(args.map_path)

    mapping = build_country_code_map(profile_dir, dict_path, map_path)
    changed_count, unresolved = normalize_files(profile_dir, mapping, args.dry_run)

    if not args.dry_run:
        write_json(map_path, mapping)

    print(f"country map entries: {len(mapping)}")
    print(f"profile files changed: {changed_count}")
    print(f"unresolved country fields: {len(unresolved)}")
    for item in unresolved[:50]:
        print(item)
    if len(unresolved) > 50:
        print(f"... {len(unresolved) - 50} more")
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
