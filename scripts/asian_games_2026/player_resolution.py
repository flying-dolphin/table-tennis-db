from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALIAS_PATH = PROJECT_ROOT / "scripts" / "data" / "asian_games_player_aliases.json"

PROJECT_GENDER = {
    "MT": "Male",
    "MS": "Male",
    "MD": "Male",
    "WT": "Female",
    "WS": "Female",
    "WD": "Female",
}


@dataclass(frozen=True)
class PlayerRecord:
    player_id: int
    name: str
    country_code: str
    gender: str | None


@dataclass(frozen=True)
class SourceAlias:
    country_code: str
    source_key: str
    canonical_name: str
    sub_event_codes: frozenset[str]


def _normalized_name(value: str | None) -> str:
    return " ".join((value or "").replace(",", " ").split()).upper()


def _compact_name(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "").upper()
    return "".join(char for char in normalized if char.isalnum())


def _name_tokens(value: str | None) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKD", value or "").upper()
    return tuple(sorted(re.findall(r"[A-Z0-9]+", normalized)))


def _load_aliases(path: Path) -> list[SourceAlias]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_aliases = payload.get("aliases", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_aliases, list):
        raise ValueError(f"player aliases must contain an aliases list: {path}")

    aliases: list[SourceAlias] = []
    for item in raw_aliases:
        if not isinstance(item, dict):
            continue
        country_code = str(item.get("country_code") or "").strip().upper()
        source_key = _compact_name(str(item.get("source_name") or ""))
        canonical_name = str(item.get("canonical_name") or "").strip()
        sub_event_codes = frozenset(
            str(code).strip().upper()
            for code in item.get("sub_event_codes") or []
            if str(code).strip()
        )
        if country_code and source_key and canonical_name:
            aliases.append(SourceAlias(country_code, source_key, canonical_name, sub_event_codes))
    return aliases


def _unique_ids(records: Iterable[PlayerRecord]) -> list[int]:
    return sorted({record.player_id for record in records})


def player_resolver(
    conn,
    *,
    aliases_path: Path = DEFAULT_ALIAS_PATH,
) -> Callable[[str | None, str | None, str | None], int | None]:
    records = [
        PlayerRecord(
            player_id=int(player_id),
            name=str(name or ""),
            country_code=str(country_code or "").strip().upper(),
            gender=str(gender or "").strip() or None,
        )
        for player_id, name, country_code, gender in conn.execute(
            "SELECT player_id, name, country_code, gender FROM players"
        )
    ]
    aliases = _load_aliases(aliases_path)

    def resolve(
        country: str | None,
        name: str | None,
        sub_event_type_code: str | None = None,
    ) -> int | None:
        country_key = str(country or "").strip().upper()
        source_name = str(name or "").strip()
        if not country_key or not source_name:
            return None
        expected_gender = PROJECT_GENDER.get(str(sub_event_type_code or "").strip().upper())

        def eligible(record: PlayerRecord) -> bool:
            return (
                record.country_code == country_key
                and (expected_gender is None or record.gender in (None, expected_gender))
            )

        eligible_records = [record for record in records if eligible(record)]
        source_compact = _compact_name(source_name)

        matching_aliases = [
            alias
            for alias in aliases
            if alias.country_code == country_key
            and alias.source_key == source_compact
            and (not alias.sub_event_codes or str(sub_event_type_code or "").upper() in alias.sub_event_codes)
        ]
        for alias in matching_aliases:
            alias_key = _normalized_name(alias.canonical_name)
            alias_records = [record for record in eligible_records if _normalized_name(record.name) == alias_key]
            alias_ids = _unique_ids(alias_records)
            if len(alias_ids) == 1:
                return alias_ids[0]

        strict_ids = _unique_ids(
            record for record in eligible_records if _normalized_name(record.name) == _normalized_name(source_name)
        )
        if len(strict_ids) == 1:
            return strict_ids[0]

        compact_ids = _unique_ids(record for record in eligible_records if _compact_name(record.name) == source_compact)
        if len(compact_ids) == 1:
            return compact_ids[0]

        source_tokens = _name_tokens(source_name)
        if len(source_tokens) >= 2:
            token_ids = _unique_ids(record for record in eligible_records if _name_tokens(record.name) == source_tokens)
            if len(token_ids) == 1:
                return token_ids[0]

        return None

    return resolve
