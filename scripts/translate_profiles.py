#!/usr/bin/env python3
"""
Translate player profile files from orig to cn.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.capture import save_json
from lib.checkpoint import CheckpointStore
from lib.translator import Translator
from lib.translation_tree import translate_json_tree

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
ORIG_DIR = PROJECT_ROOT / "data" / "player_profiles" / "orig"
CN_DIR = PROJECT_ROOT / "data" / "player_profiles" / "cn"
CHECKPOINT_PATH = PROJECT_ROOT / "data" / "player_profiles" / "checkpoint_translate_profiles.json"

def _extract_player_id(filename: str) -> str | None:
    match = re.match(r"^player_(\d+)_.*\.json$", filename, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _translate_ck(filename: str) -> str:
    player_id = _extract_player_id(filename) or filename
    return f"profile|player:{player_id}|translate"


def bootstrap_checkpoint(checkpoint: CheckpointStore, orig_dir: Path, cn_dir: Path) -> None:
    if checkpoint.path.exists() and checkpoint.has_any_completed():
        return
    if not orig_dir.exists():
        return
    with checkpoint.bulk():
        for orig_file in sorted(orig_dir.glob("player_*.json")):
            cn_file = cn_dir / orig_file.name
            if not cn_file.exists():
                continue
            try:
                json.loads(cn_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            ck = _translate_ck(orig_file.name)
            if not checkpoint.is_done(ck):
                checkpoint.mark_done(ck, meta={"bootstrapped_from": str(cn_file)})

def translate_profile_data(data: dict, translator: Translator) -> dict:
    translated = translate_json_tree(data, translator)
    if not isinstance(translated, dict):
        raise TypeError("profile data must be a dict")
    return translated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate player profiles from orig to cn")
    parser.add_argument("--file", type=str, help="Translate only one file from orig/")
    parser.add_argument("--orig-dir", default=str(ORIG_DIR))
    parser.add_argument("--cn-dir", default=str(CN_DIR))
    parser.add_argument("--checkpoint", default=str(CHECKPOINT_PATH))
    parser.add_argument("--force", action="store_true", help="Ignore checkpoint and regenerate cn files")
    parser.add_argument("--rebuild-checkpoint", action="store_true", help="Rebuild checkpoint from existing cn files")
    return parser


def run(args: argparse.Namespace) -> int:
    orig_dir = Path(args.orig_dir)
    cn_dir = Path(args.cn_dir)
    checkpoint = CheckpointStore(Path(args.checkpoint))
    if args.rebuild_checkpoint:
        checkpoint.reset()

    if not orig_dir.exists():
        logger.error("Orig directory does not exist: %s", orig_dir)
        return 1

    cn_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_checkpoint(checkpoint, orig_dir, cn_dir)

    translator = Translator()
    if args.file:
        files = [orig_dir / args.file]
    else:
        files = sorted(orig_dir.glob("player_*.json"))

    for file_path in files:
        if not file_path.exists():
            logger.error("Orig file does not exist: %s", file_path)
            return 1

        ck = _translate_ck(file_path.name)
        cn_file = cn_dir / file_path.name

        if (not args.force) and checkpoint.is_done(ck) and cn_file.exists():
            try:
                json.loads(cn_file.read_text(encoding="utf-8"))
                logger.info("Skipping translated file (checkpoint): %s", file_path.name)
                continue
            except Exception:
                logger.warning("Checkpoint done but cn file unreadable, re-translating: %s", cn_file)

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            translated = translate_profile_data(data, translator)
            save_json(cn_file, translated)
            checkpoint.mark_done(ck, meta={"orig_path": str(file_path), "cn_path": str(cn_file)})
            logger.info("Translated: %s", file_path.name)
        except Exception as exc:
            checkpoint.mark_failed(ck, str(exc), meta={"orig_path": str(file_path), "cn_path": str(cn_file)})
            logger.error("Translate failed: %s (%s)", file_path.name, exc)
            return 1

    return 0


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
