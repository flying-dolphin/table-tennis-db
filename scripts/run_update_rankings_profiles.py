#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键更新 Rankings & Profiles（带阶段级断点续跑）。

把日常更新的抓取 → 合并 → 翻译 → 入库 → 发布 串联成一个入口，
并用状态文件记录每个阶段的执行结果，失败后下次运行自动从断点继续。

阶段：
  1. scrape_rankings      抓 ranking + results + merge player_id（不抓 profile）
  2. resolve_ids          检查 unresolved；有则暂停，提示人工处理别名后重跑
  3. scrape_profiles      按 scope 抓 profile（weekly=top100+CHN / monthly=全部世排）
  4. translate_rankings   翻译 ranking
  5. translate_profiles   增量翻译 profile
  6. import_players       本地入库 players
  7. update_ages          非世排球员按 birth_year 每年更新一次年龄
  8. import_rankings      本地入库 rankings
  9. deploy               发布到线上（deploy/server/update_rankings_profiles.sh）

用法：
    python scripts/run_update_rankings_profiles.py --cdp-port 9223 --cdp-only
    python scripts/run_update_rankings_profiles.py --scope monthly
    python scripts/run_update_rankings_profiles.py --skip-deploy
    python scripts/run_update_rankings_profiles.py --reset          # 重新开始
    python scripts/run_update_rankings_profiles.py --dry-run        # 只预览
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_update_pipeline")

STATE_FILE = ROOT / "data" / "rankings" / "update_pipeline_state.json"
DEFAULT_ALIASES = "scripts/data/player_name_aliases.json"
REVIEW_OUTPUT = ROOT / "data" / "review" / "ranking_profile_review.json"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_SKIPPED = "skipped"

_COMPLETE_STATUSES = (STATUS_DONE, STATUS_SKIPPED)

# 阶段执行顺序
STAGES = [
    "scrape_rankings",
    "resolve_ids",
    "scrape_profiles",
    "translate_rankings",
    "translate_profiles",
    "import_players",
    "update_ages",
    "import_rankings",
    "deploy",
]


class PipelineError(RuntimeError):
    """A stage failed; stop the run so it can be resumed later."""


def utc_now_iso() -> str:
    return datetime.now().isoformat()


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("stages", {})
                return data
        except (OSError, json.JSONDecodeError):
            logger.warning("状态文件损坏，将重新开始: %s", state_file)
    return {
        "updated_at": "",
        "since_ts": "",
        "scope": "",
        "last_full_profile_refresh": "",
        "stages": {},
    }


def save_state(state_file: Path, state: dict) -> None:
    state["updated_at"] = utc_now_iso()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def stage_status(state: dict, stage: str) -> str:
    return state["stages"].get(stage, {}).get("status", STATUS_PENDING)


def set_stage(state: dict, stage: str, status: str, meta: dict | None = None) -> None:
    state["stages"][stage] = {
        "status": status,
        "at": utc_now_iso(),
        "meta": meta or {},
    }
    save_state(STATE_FILE, state)


def has_incomplete_run(state: dict) -> bool:
    """是否有未完成的阶段（failed/needs_review/running）。"""
    for stage in STAGES:
        if stage_status(state, stage) in (STATUS_FAILED, STATUS_NEEDS_REVIEW, STATUS_RUNNING):
            return True
    return False


def all_done(state: dict) -> bool:
    return all(stage_status(state, stage) in _COMPLETE_STATUSES for stage in STAGES)


def first_incomplete_stage(state: dict) -> str | None:
    for stage in STAGES:
        if stage_status(state, stage) not in _COMPLETE_STATUSES:
            return stage
    return None


# --------------------------------------------------------------------------- #
# 文件发现
# --------------------------------------------------------------------------- #

def latest_weekly_file(orig_dir: Path, top: int) -> Path | None:
    pat = re.compile(rf"^women_singles_top{top}_week\d+\.json$")
    candidates = [p for p in orig_dir.glob("women_singles_top*_week*.json") if pat.fullmatch(p.name)]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def latest_results_file(results_dir: Path, category: str, top: int) -> Path | None:
    candidates = list(results_dir.glob(f"results_{category}_top{top}_*.json"))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def latest_merged_file(orig_dir: Path, top: int) -> Path | None:
    pat = re.compile(rf"^women_singles_top{top}_week\d+_with_ids\.json$")
    candidates = [p for p in orig_dir.glob("women_singles_top*_week*_with_ids.json") if pat.fullmatch(p.name)]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def unresolved_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("total_unresolved") or 0)
    except (OSError, json.JSONDecodeError, ValueError):
        return 0


# --------------------------------------------------------------------------- #
# 子进程执行
# --------------------------------------------------------------------------- #

def run_cmd(cmd: list[str]) -> int:
    logger.info("RUN: %s", " ".join(map(str, cmd)))
    proc = subprocess.run(cmd, cwd=ROOT)
    return proc.returncode


def py(*args: object) -> list[str]:
    return [sys.executable, *[str(a) for a in args]]


# --------------------------------------------------------------------------- #
# 各阶段实现
# --------------------------------------------------------------------------- #

def stage_scrape_rankings(args: argparse.Namespace, state: dict) -> dict:
    cmd = py(
        "scripts/run_ranking_profile.py",
        "--category", args.category,
        "--top", str(args.top),
        "--cdp-port", str(args.cdp_port),
        "--ranking-only",
    )
    if args.cdp_only:
        cmd.append("--cdp-only")
    # 重试失败/中断阶段时复用已抓取的快照，避免重新抓取。
    if stage_status(state, "scrape_rankings") in (STATUS_FAILED, STATUS_RUNNING):
        cmd.append("--resume")
    rc = run_cmd(cmd)
    if rc != 0:
        raise PipelineError(f"scrape_rankings 失败，退出码 {rc}")

    weekly_dir = ROOT / "data" / "rankings" / "orig"
    results_dir = ROOT / "data" / "rankings" / "id_snapshots"
    weekly_file = latest_weekly_file(weekly_dir, args.top)
    results_file = latest_results_file(results_dir, args.category, args.top)
    merged_file = latest_merged_file(weekly_dir, args.top)
    if merged_file is None:
        raise PipelineError("scrape_rankings 完成但未找到 _with_ids.json 合并文件")

    return {
        "weekly_file": str(weekly_file) if weekly_file else None,
        "results_file": str(results_file) if results_file else None,
        "merged_file": str(merged_file),
        "unresolved_file": str(merged_file.with_name(merged_file.stem + "_unresolved.json")),
    }


def stage_resolve_ids(args: argparse.Namespace, state: dict) -> dict:
    meta = state["stages"]["scrape_rankings"].get("meta", {})
    merged_file = Path(meta["merged_file"])
    unresolved_file = Path(meta["unresolved_file"])
    weekly_file = Path(meta["weekly_file"]) if meta.get("weekly_file") else None
    results_file = Path(meta["results_file"]) if meta.get("results_file") else None

    # 断点续跑时先重新合并，以拾取人工修改的别名。
    if stage_status(state, "resolve_ids") == STATUS_NEEDS_REVIEW:
        if weekly_file and results_file and weekly_file.exists() and results_file.exists():
            logger.info("检测到人工处理，重新执行 merge 拾取别名变更")
            rc = run_cmd(py(
                "scripts/merge_ranking_ids.py",
                "--weekly", str(weekly_file),
                "--results", str(results_file),
                "--output", str(merged_file),
                "--unresolved-output", str(unresolved_file),
                "--aliases", args.aliases,
            ))
            if rc not in (0, 1):
                raise PipelineError(f"重新 merge 失败，退出码 {rc}")
        else:
            logger.warning("缺少 weekly/results 文件，无法重新 merge，直接读取 unresolved 报告")

    if unresolved_count(unresolved_file) == 0:
        return {}

    # 生成人工审核文件并暂停。
    run_cmd(py(
        "scripts/review_ranking_profile_outputs.py",
        "--ranking-unresolved", str(unresolved_file),
        "--output", str(REVIEW_OUTPUT),
    ))
    set_stage(state, "resolve_ids", STATUS_NEEDS_REVIEW, {"unresolved_file": str(unresolved_file)})
    raise PipelineError(
        f"存在 {unresolved_count(unresolved_file)} 条 unresolved 记录，详见:\n"
        f"  - 报告: {unresolved_file}\n"
        f"  - 审核: {REVIEW_OUTPUT}\n"
        f"请编辑 {args.aliases} 补充别名映射后，重新运行本脚本（会自动重新 merge 并继续）。"
    )


def stage_scrape_profiles(args: argparse.Namespace, state: dict) -> dict:
    scope = state.get("scope") or "weekly"
    cmd = py(
        "scripts/run_ranking_profile.py",
        "--category", args.category,
        "--top", str(args.top),
        "--cdp-port", str(args.cdp_port),
        "--resume",
        "--profile-scope", scope,
    )
    if args.cdp_only:
        cmd.append("--cdp-only")
    rc = run_cmd(cmd)
    if rc != 0:
        raise PipelineError(f"scrape_profiles 失败，退出码 {rc}")

    if scope == "monthly":
        state["last_full_profile_refresh"] = utc_now_iso()
        save_state(STATE_FILE, state)
        logger.info("已记录本月全量 profile 刷新时间")
    return {"scope": scope}


def stage_translate_rankings(args: argparse.Namespace, state: dict) -> dict:
    meta = state["stages"]["scrape_rankings"]["meta"]
    merged_file = Path(meta["merged_file"])
    rc = run_cmd(py(
        "scripts/translate_rankings.py",
        "--file", str(merged_file),
        "--force",
    ))
    if rc != 0:
        raise PipelineError(f"translate_rankings 失败，退出码 {rc}")
    return {"cn_file": str(ROOT / "data" / "rankings" / "cn" / merged_file.name)}


def stage_translate_profiles(args: argparse.Namespace, state: dict) -> dict:
    since_ts = state.get("since_ts")
    cmd = py("scripts/translate_profiles.py", "--since", since_ts)
    rc = run_cmd(cmd)
    if rc != 0:
        raise PipelineError(f"translate_profiles 失败，退出码 {rc}")
    return {"since": since_ts}


def stage_import_players(args: argparse.Namespace, state: dict) -> dict:
    rc = run_cmd(py("scripts/db/import_players.py", "--dir", "data/player_profiles/cn"))
    if rc != 0:
        raise PipelineError(f"import_players 失败，退出码 {rc}")
    return {}


def stage_update_ages(args: argparse.Namespace, state: dict) -> dict:
    rc = run_cmd(py("scripts/db/update_inactive_player_ages.py"))
    if rc != 0:
        raise PipelineError(f"update_ages 失败，退出码 {rc}")
    return {}


def stage_import_rankings(args: argparse.Namespace, state: dict) -> dict:
    cn_file = state["stages"]["translate_rankings"]["meta"].get("cn_file")
    if not cn_file:
        meta = state["stages"]["scrape_rankings"]["meta"]
        merged_file = Path(meta["merged_file"])
        cn_file = str(ROOT / "data" / "rankings" / "cn" / merged_file.name)
    rc = run_cmd(py("scripts/db/import_rankings.py", "--file", cn_file))
    if rc != 0:
        raise PipelineError(f"import_rankings 失败，退出码 {rc}")
    return {"cn_file": cn_file}


def stage_deploy(args: argparse.Namespace, state: dict) -> dict:
    since_ts = state.get("since_ts")
    rc = run_cmd([
        "bash", "deploy/server/update_rankings_profiles.sh",
        "--changed-since", since_ts,
    ])
    if rc != 0:
        raise PipelineError(f"deploy 失败，退出码 {rc}")
    return {"changed_since": since_ts}


STAGE_RUNNERS = {
    "scrape_rankings": stage_scrape_rankings,
    "resolve_ids": stage_resolve_ids,
    "scrape_profiles": stage_scrape_profiles,
    "translate_rankings": stage_translate_rankings,
    "translate_profiles": stage_translate_profiles,
    "import_players": stage_import_players,
    "update_ages": stage_update_ages,
    "import_rankings": stage_import_rankings,
    "deploy": stage_deploy,
}


def resolve_scope(args: argparse.Namespace, state: dict) -> str:
    if args.scope in ("weekly", "monthly"):
        return args.scope
    last = state.get("last_full_profile_refresh")
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if (datetime.now() - last_dt).days < args.monthly_interval_days:
                return "weekly"
        except ValueError:
            pass
    return "monthly"


def run(args: argparse.Namespace) -> int:
    state = load_state(STATE_FILE)

    if args.reset:
        # 清空阶段进度，但保留「月度全量」这类长周期标记。
        last_full = state.get("last_full_profile_refresh", "")
        state = {
            "updated_at": "",
            "since_ts": "",
            "scope": "",
            "last_full_profile_refresh": last_full,
            "stages": {},
        }
        logger.info("已重置阶段进度（保留月度全量标记）")

    # 判断是继续上次未完成 run，还是开启新 run。
    if not has_incomplete_run(state):
        if not state.get("since_ts") or all_done(state):
            logger.info("开启新一轮更新")
            state["since_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            state["scope"] = resolve_scope(args, state)
            state["stages"] = {}
            save_state(STATE_FILE, state)
        elif args.scope in ("weekly", "monthly"):
            # 显式指定 scope 覆盖（例如 skip-deploy 后手动指定范围续跑）。
            state["scope"] = args.scope
            save_state(STATE_FILE, state)

    scope = state.get("scope") or "weekly"
    since_ts = state.get("since_ts")
    logger.info("=" * 70)
    logger.info("Rankings & Profiles 更新流水线")
    logger.info("  scope:     %s", scope)
    logger.info("  since_ts:  %s", since_ts)
    logger.info("  state:     %s", STATE_FILE)
    logger.info("=" * 70)

    # 打印各阶段状态
    for stage in STAGES:
        logger.info("  [%s] %s", stage_status(state, stage).ljust(12), stage)

    if args.dry_run:
        logger.info("DRY RUN：不执行任何阶段")
        return 0

    for stage in STAGES:
        if stage == "deploy" and args.skip_deploy:
            set_stage(state, stage, STATUS_SKIPPED, {"note": "skipped by --skip-deploy"})
            logger.info("跳过 deploy（--skip-deploy），本地阶段已全部完成")
            continue

        if stage_status(state, stage) in _COMPLETE_STATUSES:
            logger.info("跳过已完成阶段: %s", stage)
            continue

        logger.info("-" * 70)
        logger.info("执行阶段: %s", stage)
        set_stage(state, stage, STATUS_RUNNING)
        try:
            meta = STAGE_RUNNERS[stage](args, state)
            set_stage(state, stage, STATUS_DONE, meta)
            logger.info("阶段完成: %s", stage)
        except PipelineError as exc:
            # resolve_ids 的 needs_review 已经由 stage_resolve_ids 写入状态，
            # 这里避免把 needs_review 覆盖为 failed。
            if stage == "resolve_ids" and stage_status(state, stage) == STATUS_NEEDS_REVIEW:
                logger.warning("暂停：%s", exc)
            else:
                set_stage(state, stage, STATUS_FAILED, {"error": str(exc)})
                logger.error("阶段失败: %s -> %s", stage, exc)
            return 3

    logger.info("=" * 70)
    logger.info("流水线完成（scope=%s）", scope)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="一键更新 Rankings & Profiles（带断点续跑）")
    parser.add_argument("--category", choices=["women", "men"], default="women")
    parser.add_argument("--top", type=int, default=1000)
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP 端口（默认 9222，日常可传 9223）")
    parser.add_argument("--cdp-only", action="store_true", help="仅连接已存在的 CDP Chrome")
    parser.add_argument("--scope", choices=["auto", "weekly", "monthly"], default="auto",
                        help="profile 抓取范围：auto=按上次全量时间自动判断")
    parser.add_argument("--monthly-interval-days", type=int, default=30,
                        help="auto 模式下距上次全量多少天内视为 weekly（默认 30）")
    parser.add_argument("--aliases", default=DEFAULT_ALIASES, help="球员别名映射 JSON")
    parser.add_argument("--skip-deploy", action="store_true", help="只执行本地阶段，不发布到线上")
    parser.add_argument("--reset", action="store_true", help="清空状态，重新开始")
    parser.add_argument("--dry-run", action="store_true", help="只预览计划，不执行")
    parser.add_argument("--state-file", default=str(STATE_FILE), help="流水线状态文件路径")
    return parser


def main() -> None:
    global STATE_FILE  # noqa: PLW0603
    args = build_parser().parse_args()
    STATE_FILE = Path(args.state_file)
    sys.exit(run(args))


if __name__ == "__main__":
    main()
