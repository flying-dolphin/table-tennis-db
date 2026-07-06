#!/usr/bin/env python3
"""One-shot ITTF ranking + results ID + profile refresh orchestration."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path

from merge_ranking_ids import run as run_merge
from scrape_rankings import run as run_weekly_wp
from scrape_results_rankings import run as run_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_ranking_profile")

ANCHOR_DATE = date(2026, 6, 8)
START_TIME = datetime_time(21, 0)


def is_due_window(
    now: datetime,
    anchor: date = ANCHOR_DATE,
    start_time: datetime_time = START_TIME,
) -> bool:
    if now.date() < anchor:
        return False
    days_since_anchor = (now.date() - anchor).days
    return days_since_anchor % 7 == 0 and now.time() >= start_time


def latest_ranking_file(output_dir: Path, before: set[Path] | None = None, top: int | None = None) -> Path | None:
    before = before or set()
    pattern = f"women_singles_top{top}_week*.json" if top is not None else "women_singles_top*_week*.json"
    candidates = sorted(output_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        if path not in before:
            return path
    return candidates[0] if candidates else None


def latest_results_file(output_dir: Path, before: set[Path] | None = None) -> Path | None:
    before = before or set()
    candidates = sorted(output_dir.glob("results_*_top*_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        if path not in before:
            return path
    return candidates[0] if candidates else None


def _file_set(path: Path, pattern: str) -> set[Path]:
    return set(path.glob(pattern)) if path.exists() else set()


def run(args: argparse.Namespace) -> int:
    if args.check_due and not is_due_window(datetime.now()):
        logger.info(
            "Not in due window; anchor=%s interval=7d start_time=%s",
            ANCHOR_DATE.isoformat(),
            START_TIME.strftime("%H:%M"),
        )
        return 0

    weekly_output_dir = Path(args.weekly_output_dir)
    results_output_dir = Path(args.results_output_dir)
    weekly_output_dir.mkdir(parents=True, exist_ok=True)
    results_output_dir.mkdir(parents=True, exist_ok=True)

    weekly_before = _file_set(weekly_output_dir, f"women_singles_top{args.top}_week*.json")
    weekly_file = None
    resume = bool(getattr(args, "resume", False)) and not args.force
    if resume:
        weekly_file = latest_ranking_file(weekly_output_dir, top=args.top)
        if weekly_file is not None:
            logger.info("Resume enabled; reusing weekly ranking file: %s", weekly_file)

    if weekly_file is None:
        weekly_args = argparse.Namespace(
            top=args.top,
            cdp_port=args.cdp_port,
            cdp_only=args.cdp_only,
            headless=args.headless,
            slow_mo=args.slow_mo,
            output_dir=str(weekly_output_dir),
            checkpoint=args.weekly_checkpoint,
            force=args.force,
            rebuild_checkpoint=False,
        )
        rc = run_weekly_wp(weekly_args)
        if rc != 0:
            logger.error("weekly wp-content ranking scrape failed with rc=%s", rc)
            return rc

        weekly_file = latest_ranking_file(weekly_output_dir, weekly_before, top=args.top)
    if weekly_file is None:
        logger.error("weekly ranking output file not found")
        return 5
    logger.info("Weekly ranking file: %s", weekly_file)

    results_before = _file_set(results_output_dir, "results_*_top*_*.json")
    results_args = argparse.Namespace(
        category=args.category,
        top=args.top,
        output_dir=str(results_output_dir),
        output=None,
        checkpoint=args.results_checkpoint,
        storage_state=args.storage_state,
        profile_dir=args.profile_dir,
        avatar_dir=args.avatar_dir,
        ranking_only=args.ranking_only,
        force=args.force or not resume,
        resume=resume,
        init_session=False,
        headless=args.headless,
        slow_mo=args.slow_mo,
        cdp_port=args.cdp_port,
        cdp_only=args.cdp_only,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        min_player_gap=args.min_player_gap,
        max_player_gap=args.max_player_gap,
    )
    rc = run_results(results_args)
    if rc != 0:
        logger.error("results.ittf.link ranking scrape failed with rc=%s", rc)
        return rc
    results_file = latest_results_file(results_output_dir, results_before)
    if results_file is None:
        logger.error("results ranking output file not found")
        return 5
    logger.info("Results ranking file: %s", results_file)

    merged_output = Path(args.merged_output) if args.merged_output else weekly_file.with_name(weekly_file.stem + "_with_ids.json")
    unresolved_output = Path(args.unresolved_output) if args.unresolved_output else merged_output.with_name(merged_output.stem + "_unresolved.json")
    merge_args = argparse.Namespace(
        weekly=str(weekly_file),
        results=str(results_file),
        output=str(merged_output),
        unresolved_output=str(unresolved_output),
        aliases=args.aliases,
    )
    merge_rc = run_merge(merge_args)
    if merge_rc == 0:
        # 无不resolved记录，删除空的unresolved报告文件
        if unresolved_output.exists():
            unresolved_output.unlink()
            logger.info("无不resolved记录，已删除报告文件: %s", unresolved_output)
    else:
        logger.warning("合并完成但存在未resolved记录，详见: %s", unresolved_output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one ITTF ranking/profile update")
    parser.add_argument(
        "--check-due",
        action="store_true",
        help="Run only on 2026-06-08 + 7n days at or after 21:00; intended for crontab",
    )
    parser.add_argument("--category", choices=["women", "men"], default="women")
    parser.add_argument("--top", type=int, default=1000)
    parser.add_argument("--weekly-output-dir", default="data/rankings/orig")
    parser.add_argument("--results-output-dir", default="data/rankings/id_snapshots")
    parser.add_argument("--merged-output", default=None)
    parser.add_argument("--unresolved-output", default=None)
    parser.add_argument("--aliases", default="scripts/data/player_name_aliases.json", help="Manual player name alias JSON")
    parser.add_argument("--weekly-checkpoint", default="data/rankings/checkpoint_rankings.json")
    parser.add_argument("--results-checkpoint", default="data/rankings/checkpoint_results_rankings.json")
    parser.add_argument("--storage-state", default="data/session/ittf_results_storage_state.json")
    parser.add_argument("--profile-dir", default="data/player_profiles")
    parser.add_argument("--avatar-dir", default="data/player_avatars")
    parser.add_argument("--ranking-only", action="store_true", help="Skip profile refresh after results ranking scrape")
    parser.add_argument("--resume", action="store_true", help="Reuse completed ranking snapshots and continue profile refresh")
    parser.add_argument("--force", action="store_true", help="Ignore checkpoints and existing products; start a fresh scrape")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--cdp-only", action="store_true")
    parser.add_argument("--min-delay", type=float, default=2.0)
    parser.add_argument("--max-delay", type=float, default=5.0)
    parser.add_argument("--min-player-gap", type=float, default=2.0)
    parser.add_argument("--max-player-gap", type=float, default=5.0)
    return parser


def main() -> None:
    parser = build_parser()
    sys.exit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
