#!/usr/bin/env python3
"""Merge weekly wp-content rankings with same-day results.ittf.link player IDs."""

from __future__ import annotations

import argparse
import copy
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from lib.capture import save_json
from lib.name_normalizer import normalize_player_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_merge_ranking_ids")

_BIRTH_YEAR_SUFFIX_RE = re.compile(r"\s+\((?:19|20)\d{2}\)$")
DEFAULT_ALIASES_PATH = Path("scripts/data/player_name_aliases.json")


def normalize_key_name(value: str) -> str:
    return re.sub(r"\s+", " ", normalize_player_name(value or "")).strip().casefold()


def normalize_key_name_variants(value: str) -> set[str]:
    full = normalize_key_name(value)
    variants = {full}
    without_birth_year = _BIRTH_YEAR_SUFFIX_RE.sub("", full).strip()
    if without_birth_year:
        variants.add(without_birth_year)
    return variants


def _name_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for variant in normalize_key_name_variants(value):
        tokens.update(token for token in variant.split(" ") if token)
    return tokens


def is_partial_name_match(left: str, right: str) -> bool:
    left_tokens = _name_tokens(left)
    right_tokens = _name_tokens(right)
    if len(left_tokens) < 2 or len(right_tokens) < 2:
        return False
    return left_tokens == right_tokens or left_tokens < right_tokens or right_tokens < left_tokens


def identity_key(row: dict[str, Any], include_points: bool = True) -> tuple[Any, ...]:
    key: tuple[Any, ...] = (
        normalize_key_name(str(row.get("english_name") or row.get("name") or "")),
        str(row.get("country_code") or row.get("country") or "").upper(),
    )
    if include_points:
        key = (*key, int(row.get("points") or 0))
    return key


def identity_key_variants(row: dict[str, Any], include_points: bool = True) -> set[tuple[Any, ...]]:
    country_code = str(row.get("country_code") or row.get("country") or "").upper()
    keys: set[tuple[Any, ...]] = set()
    for name in normalize_key_name_variants(str(row.get("english_name") or row.get("name") or "")):
        key: tuple[Any, ...] = (name, country_code)
        if include_points:
            key = (*key, int(row.get("points") or 0))
        keys.add(key)
    return keys


def _candidate_score(weekly: dict[str, Any], candidate: dict[str, Any]) -> tuple[int, int]:
    weekly_rank = int(weekly.get("rank") or 0)
    candidate_rank = int(candidate.get("rank") or 0)
    return (abs(weekly_rank - candidate_rank), candidate_rank)


def _rank_distance(weekly: dict[str, Any], candidate: dict[str, Any]) -> int:
    weekly_rank = int(weekly.get("rank") or 0)
    candidate_rank = int(candidate.get("rank") or 0)
    return abs(weekly_rank - candidate_rank)


def _same_country(weekly: dict[str, Any], candidate: dict[str, Any]) -> bool:
    weekly_country = str(weekly.get("country_code") or weekly.get("country") or "").upper()
    candidate_country = str(candidate.get("country_code") or candidate.get("country") or "").upper()
    return weekly_country == candidate_country


def _same_points(weekly: dict[str, Any], candidate: dict[str, Any]) -> bool:
    return int(weekly.get("points") or 0) == int(candidate.get("points") or 0)


def _row_name(row: dict[str, Any]) -> str:
    return str(row.get("english_name") or row.get("name") or "")


def load_player_name_aliases(path: Path | str | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    alias_path = Path(path)
    if not alias_path.exists():
        return []
    payload = json.loads(alias_path.read_text(encoding="utf-8"))
    aliases = payload.get("aliases", payload) if isinstance(payload, dict) else payload
    if not isinstance(aliases, list):
        raise ValueError(f"player name aliases must be a list or object with aliases list: {alias_path}")
    return [alias for alias in aliases if isinstance(alias, dict)]


def _alias_name_matches(value: str, expected: str) -> bool:
    return bool(normalize_key_name_variants(value) & normalize_key_name_variants(expected))


def _alias_matches_weekly(alias: dict[str, Any], weekly: dict[str, Any]) -> bool:
    alias_country = str(alias.get("country_code") or alias.get("country") or "").upper()
    weekly_country = str(weekly.get("country_code") or weekly.get("country") or "").upper()
    if not alias_country or alias_country != weekly_country:
        return False
    weekly_name = str(alias.get("weekly_name") or "").strip()
    return bool(weekly_name and _alias_name_matches(_row_name(weekly), weekly_name))


def _manual_alias_candidates(
    weekly: dict[str, Any],
    results_rows: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
    include_points: bool,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    for alias in aliases:
        if not _alias_matches_weekly(alias, weekly):
            continue

        player_id = str(alias.get("player_id") or "").strip()
        results_name = str(alias.get("results_name") or "").strip()
        if not player_id and not results_name:
            continue

        for row in results_rows:
            if id(row) in seen:
                continue
            if not _same_country(weekly, row):
                continue
            if include_points and not _same_points(weekly, row):
                continue
            if player_id:
                if str(row.get("player_id") or "").strip() != player_id:
                    continue
            elif not _alias_name_matches(_row_name(row), results_name):
                continue
            candidates.append(row)
            seen.add(id(row))

    return candidates


def _partial_name_candidates(
    weekly: dict[str, Any],
    results_rows: list[dict[str, Any]],
    include_points: bool,
) -> list[dict[str, Any]]:
    return [
        row
        for row in results_rows
        if _same_country(weekly, row)
        and (not include_points or _same_points(weekly, row))
        and is_partial_name_match(_row_name(weekly), _row_name(row))
    ]


def _best_rank_candidate(
    weekly: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    if len(candidates) == 1:
        return candidates[0], "matched"

    candidates = sorted(candidates, key=lambda row: _candidate_score(weekly, row))
    if _rank_distance(weekly, candidates[0]) == _rank_distance(weekly, candidates[1]):
        return None, "ambiguous"
    return candidates[0], "rank_fallback"


def _resolve_candidate(
    weekly: dict[str, Any],
    results_rows: list[dict[str, Any]],
    aliases: list[dict[str, Any]] | None = None,
    used_player_ids: set[str] | None = None,
) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]]]:
    aliases = aliases or []
    used_player_ids = used_player_ids or set()
    available_rows = [
        row
        for row in results_rows
        if not row.get("player_id") or str(row.get("player_id")) not in used_player_ids
    ]

    weekly_exact_keys = identity_key_variants(weekly, include_points=True)
    exact = [
        row
        for row in available_rows
        if identity_key_variants(row, include_points=True) & weekly_exact_keys
    ]
    if len(exact) == 1:
        return exact[0], "matched", exact
    if len(exact) > 1:
        candidate, status = _best_rank_candidate(weekly, exact)
        return candidate, status, exact

    weekly_loose_keys = identity_key_variants(weekly, include_points=False)
    loose = [
        row
        for row in available_rows
        if identity_key_variants(row, include_points=False) & weekly_loose_keys
    ]
    if not loose:
        alias_exact = _manual_alias_candidates(weekly, available_rows, aliases, include_points=True)
        if len(alias_exact) == 1:
            return alias_exact[0], "manual_alias", alias_exact
        if len(alias_exact) > 1:
            candidate, status = _best_rank_candidate(weekly, alias_exact)
            return candidate, "manual_alias_rank_fallback" if status == "rank_fallback" else status, alias_exact

        alias_loose = _manual_alias_candidates(weekly, available_rows, aliases, include_points=False)
        if len(alias_loose) == 1:
            return alias_loose[0], "manual_alias_rank_fallback", alias_loose
        if len(alias_loose) > 1:
            candidate, status = _best_rank_candidate(weekly, alias_loose)
            return candidate, "manual_alias_rank_fallback" if status == "rank_fallback" else status, alias_loose

        partial_exact = _partial_name_candidates(weekly, available_rows, include_points=True)
        if len(partial_exact) == 1:
            return partial_exact[0], "partial_name", partial_exact
        if len(partial_exact) > 1:
            candidate, status = _best_rank_candidate(weekly, partial_exact)
            return candidate, "partial_name" if status == "matched" else status, partial_exact

        partial_loose = _partial_name_candidates(weekly, available_rows, include_points=False)
        if not partial_loose:
            return None, "unmatched", []
        candidate, status = _best_rank_candidate(weekly, partial_loose)
        return candidate, "partial_name" if status == "matched" else status, partial_loose
    candidate, status = _best_rank_candidate(weekly, loose)
    return candidate, status, loose


def merge_rankings_with_results_ids(
    weekly_rows: list[dict[str, Any]],
    results_rows: list[dict[str, Any]],
    aliases: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    merged: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    used_player_ids: set[str] = set()

    for weekly in weekly_rows:
        row = copy.deepcopy(weekly)
        candidate, status, candidates = _resolve_candidate(row, results_rows, aliases, used_player_ids)
        if candidate is not None and candidate.get("id_resolution_hint") == "db_profile_rank":
            status = "db_profile_rank"
        row["id_resolution_status"] = status

        if candidate is not None:
            row["player_id"] = candidate.get("player_id")
            row["profile_url"] = candidate.get("profile_url")
            row["country_code"] = candidate.get("country_code") or row.get("country_code")
            row["results_rank"] = candidate.get("rank")
            row["results_points"] = candidate.get("points")
            if row.get("player_id"):
                used_player_ids.add(str(row["player_id"]))
        else:
            row.setdefault("player_id", None)
            row.setdefault("profile_url", None)
            unresolved.append(
                {
                    "reason": status,
                    "weekly": {
                        "rank": row.get("rank"),
                        "name": row.get("name"),
                        "country_code": row.get("country_code"),
                        "points": row.get("points"),
                    },
                    "candidate_count": len(candidates),
                    "candidates": [
                        {
                            "rank": candidate_row.get("rank"),
                            "name": candidate_row.get("name"),
                            "country_code": candidate_row.get("country_code"),
                            "points": candidate_row.get("points"),
                            "player_id": candidate_row.get("player_id"),
                        }
                        for candidate_row in candidates[:10]
                    ],
                }
            )
        merged.append(row)
    return merged, unresolved


def merge_payloads(
    weekly_payload: dict[str, Any],
    results_payload: dict[str, Any],
    aliases: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    merged_rows, unresolved = merge_rankings_with_results_ids(
        list(weekly_payload.get("rankings") or []),
        list(results_payload.get("rankings") or []),
        aliases=aliases,
    )
    out_payload = copy.deepcopy(weekly_payload)
    out_payload["rankings"] = merged_rows
    out_payload["player_id_source"] = {
        "source": results_payload.get("source", "results.ittf.link"),
        "source_url": results_payload.get("source_url"),
        "scraped_at": results_payload.get("scraped_at"),
        "total_players": results_payload.get("total_players"),
    }
    out_payload["player_id_resolution"] = {
        "matched": sum(
            1
            for row in merged_rows
            if row.get("id_resolution_status")
            in {
                "matched",
                "rank_fallback",
                "partial_name",
                "manual_alias",
                "manual_alias_rank_fallback",
                "db_profile_rank",
            }
        ),
        "unresolved": len(unresolved),
    }
    unresolved_payload = {
        "weekly_file_meta": {
            "ranking_week": weekly_payload.get("ranking_week"),
            "ranking_date": weekly_payload.get("ranking_date"),
            "total_players": weekly_payload.get("total_players"),
        },
        "results_file_meta": out_payload["player_id_source"],
        "total_unresolved": len(unresolved),
        "unresolved": unresolved,
    }
    return out_payload, unresolved_payload


def run(args: argparse.Namespace) -> int:
    weekly_path = Path(args.weekly)
    results_path = Path(args.results)
    weekly_payload = json.loads(weekly_path.read_text(encoding="utf-8"))
    results_payload = json.loads(results_path.read_text(encoding="utf-8"))
    aliases = load_player_name_aliases(getattr(args, "aliases", None))
    merged_payload, unresolved_payload = merge_payloads(weekly_payload, results_payload, aliases=aliases)

    output_path = Path(args.output) if args.output else weekly_path.with_name(weekly_path.stem + "_with_ids.json")
    unresolved_path = Path(args.unresolved_output) if args.unresolved_output else output_path.with_name(output_path.stem + "_unresolved.json")
    save_json(output_path, merged_payload)
    save_json(unresolved_path, unresolved_payload)
    logger.info("Saved merged ranking: %s", output_path)
    logger.info("Saved unresolved report: %s", unresolved_path)
    return 0 if unresolved_payload["total_unresolved"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge weekly ITTF ranking rows with results.ittf.link player IDs")
    parser.add_argument("--weekly", required=True, help="wp-content weekly ranking JSON")
    parser.add_argument("--results", required=True, help="results.ittf.link ranking snapshot JSON")
    parser.add_argument("--output", default=None)
    parser.add_argument("--unresolved-output", default=None)
    parser.add_argument("--aliases", default=str(DEFAULT_ALIASES_PATH), help="JSON file with manual player name aliases")
    return parser


def main() -> None:
    parser = build_parser()
    sys.exit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
