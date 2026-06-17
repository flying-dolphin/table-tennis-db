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


def normalize_key_name(value: str) -> str:
    return re.sub(r"\s+", " ", normalize_player_name(value or "")).strip().casefold()


def normalize_key_name_variants(value: str) -> set[str]:
    full = normalize_key_name(value)
    variants = {full}
    without_birth_year = _BIRTH_YEAR_SUFFIX_RE.sub("", full).strip()
    if without_birth_year:
        variants.add(without_birth_year)
    return variants


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
    used_player_ids: set[str] | None = None,
) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]]]:
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
        return None, "unmatched", []
    candidate, status = _best_rank_candidate(weekly, loose)
    return candidate, status, loose


def merge_rankings_with_results_ids(
    weekly_rows: list[dict[str, Any]],
    results_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    merged: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    used_player_ids: set[str] = set()

    for weekly in weekly_rows:
        row = copy.deepcopy(weekly)
        candidate, status, candidates = _resolve_candidate(row, results_rows, used_player_ids)
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


def merge_payloads(weekly_payload: dict[str, Any], results_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    merged_rows, unresolved = merge_rankings_with_results_ids(
        list(weekly_payload.get("rankings") or []),
        list(results_payload.get("rankings") or []),
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
        "matched": sum(1 for row in merged_rows if row.get("id_resolution_status") in {"matched", "rank_fallback"}),
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
    merged_payload, unresolved_payload = merge_payloads(weekly_payload, results_payload)

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
    return parser


def main() -> None:
    parser = build_parser()
    sys.exit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
