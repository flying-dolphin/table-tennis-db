#!/usr/bin/env python3
"""
One-time migration: normalize player names in existing data files.

What this script changes
------------------------
1. data/matches_complete/orig/*.json  — rename file + update raw_capture_file paths
                                        + fix player_name/english_name if still wrong
2. data/matches_complete/cn/*.json    — same
3. data/raw_event_payloads/{name}/    — rename directory

What it does NOT touch
-----------------------
- data/player_profiles/orig/  (already correct)
- data/player_avatars/        (already correct)
- checkpoint files            (rebuild with --rebuild-checkpoint after migration)

Conflict strategy (5 players have two files with different name order)
-----------------------------------------------------------------------
  Anna_HURSEY vs HURSEY_Anna   → Anna_HURSEY has 7 years vs 4 → overwrite HURSEY_Anna
  Mima_ITO vs ITO_Mima         → ITO_Mima has more events (158 vs 146) → backup Mima_ITO
  Miwa_HARIMOTO vs HARIMOTO_Miwa → equal events → backup Miwa_HARIMOTO
  Sabine_WINTER vs WINTER_Sabine → WINTER_Sabine has more (119 vs 113) → backup Sabine_WINTER  *wrong*
  Yangzi_LIU vs LIU_Yangzi    → LIU_Yangzi has more (39 vs 37) → backup Yangzi_LIU

"Backup" means the file is renamed to <name>.bak.json (not deleted) so no data is lost.

Usage
-----
  # Preview only (default)
  python scripts/migrate_player_names.py --dry-run

  # Apply
  python scripts/migrate_player_names.py
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from lib.capture import sanitize_filename
from lib.name_normalizer import normalize_player_name

DATA_DIR = Path("data")
ORIG_DIR = DATA_DIR / "matches_complete" / "orig"
CN_DIR = DATA_DIR / "matches_complete" / "cn"
PAYLOADS_DIR = DATA_DIR / "raw_event_payloads"

# Conflict resolution: which wrong-named file wins (True = source wins → overwrite target)
# All others: target (correctly-named file) wins → source is backed up.
CONFLICT_SOURCE_WINS: set[str] = {
    "Anna_HURSEY",  # 7 years vs 4 — wrong-named file has more data
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def count_events(data: dict[str, Any]) -> int:
    return sum(len(yr.get("events", [])) for yr in data.get("years", {}).values())


def _replace_payload_dir_in_str(s: str, old_stem: str, new_stem: str) -> str:
    """Replace raw_event_payloads/<old_stem>/ with .../<new_stem>/ in a path string."""
    pattern = re.compile(
        r"(raw_event_payloads[/\\]+)" + re.escape(old_stem) + r"([/\\])"
    )
    return pattern.sub(r"\g<1>" + new_stem + r"\g<2>", s)


def update_payload_paths(obj: Any, old_stem: str, new_stem: str) -> Any:
    """Recursively replace payload dir names in all string values."""
    if isinstance(obj, dict):
        return {k: update_payload_paths(v, old_stem, new_stem) for k, v in obj.items()}
    if isinstance(obj, list):
        return [update_payload_paths(item, old_stem, new_stem) for item in obj]
    if isinstance(obj, str):
        return _replace_payload_dir_in_str(obj, old_stem, new_stem)
    return obj


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="")


# ---------------------------------------------------------------------------
# Compute rename plan
# ---------------------------------------------------------------------------


def build_rename_plan(directory: Path) -> list[dict[str, Any]]:
    """
    For each JSON in directory, decide what needs to happen.

    Returns list of action dicts with keys:
      src_path, dst_path, old_stem, new_stem,
      action: "rename" | "conflict_source_wins" | "conflict_target_wins" | "ok"
      name_content_wrong: bool (player_name/english_name field needs fixing)
      paths_need_update: bool (raw_capture_file paths need old_stem → new_stem)
    """
    plan = []
    for src in sorted(directory.glob("*.json")):
        old_stem = src.stem
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  WARN: cannot read {src}: {exc}")
            continue

        raw_name = data.get("player_name") or data.get("english_name") or ""
        normalized = normalize_player_name(raw_name) if raw_name else ""
        new_stem = sanitize_filename(normalized) if normalized else old_stem

        name_content_wrong = bool(raw_name and raw_name != normalized)
        paths_need_update = old_stem != new_stem  # raw_capture_file paths embed dir name

        if new_stem == old_stem and not name_content_wrong:
            plan.append({"src_path": src, "dst_path": src, "old_stem": old_stem,
                         "new_stem": new_stem, "action": "ok",
                         "name_content_wrong": False, "paths_need_update": False,
                         "data": data})
            continue

        dst = directory / f"{new_stem}.json"

        if dst.exists() and dst != src:
            # Conflict
            if old_stem in CONFLICT_SOURCE_WINS:
                action = "conflict_source_wins"
            else:
                action = "conflict_target_wins"
        else:
            action = "rename"

        plan.append({
            "src_path": src,
            "dst_path": dst,
            "old_stem": old_stem,
            "new_stem": new_stem,
            "action": action,
            "name_content_wrong": name_content_wrong,
            "paths_need_update": paths_need_update,
            "data": data,
        })

    return plan


def build_payload_plan() -> list[dict[str, Any]]:
    """Decide which raw_event_payloads directories need renaming."""
    plan = []
    if not PAYLOADS_DIR.exists():
        return plan
    for d in sorted(PAYLOADS_DIR.iterdir()):
        if not d.is_dir():
            continue
        old_stem = d.name
        # Reconstruct approximate player name from dir name and normalize
        approx = old_stem.replace("_", " ")
        normalized = normalize_player_name(approx)
        new_stem = sanitize_filename(normalized)

        if new_stem == old_stem:
            continue

        dst = PAYLOADS_DIR / new_stem
        if dst.exists():
            if old_stem in CONFLICT_SOURCE_WINS:
                action = "conflict_source_wins"  # merge source into target
            else:
                action = "conflict_target_wins"   # source becomes orphan
        else:
            action = "rename"

        plan.append({
            "src_path": d,
            "dst_path": dst,
            "old_stem": old_stem,
            "new_stem": new_stem,
            "action": action,
        })
    return plan


# ---------------------------------------------------------------------------
# Print plan
# ---------------------------------------------------------------------------


def print_plan(orig_plan: list, cn_plan: list, payload_plan: list) -> None:
    def summarise(plan: list, label: str) -> None:
        renames = [p for p in plan if p["action"] == "rename"]
        wins    = [p for p in plan if p["action"] == "conflict_source_wins"]
        loses   = [p for p in plan if p["action"] == "conflict_target_wins"]
        already = [p for p in plan if p["action"] == "ok"]
        content_fixes = [p for p in plan if p.get("name_content_wrong")]

        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
        print(f"  Already correct : {len(already)}")
        print(f"  Simple renames  : {len(renames)}")
        print(f"  Conflicts total : {len(wins) + len(loses)}")
        print(f"    source wins (overwrite target) : {len(wins)}")
        print(f"    target wins (backup source)    : {len(loses)}")
        print(f"  Content name fixes needed : {len(content_fixes)}")

        if renames:
            print(f"\n  Renames:")
            for p in renames:
                tag = " [content fix]" if p.get("name_content_wrong") else ""
                print(f"    {p['old_stem']} → {p['new_stem']}{tag}")

        if wins:
            print(f"\n  Conflicts — source overwrites target (source has more data):")
            for p in wins:
                tag = " [content fix]" if p.get("name_content_wrong") else ""
                print(f"    {p['old_stem']} → {p['new_stem']} (overwrites){tag}")

        if loses:
            print(f"\n  Conflicts — target kept, source backed up as .bak.json:")
            for p in loses:
                print(f"    {p['old_stem']} → {p['new_stem']}.bak.json")

    summarise(orig_plan, "matches_complete/orig/")
    summarise(cn_plan,   "matches_complete/cn/")

    print(f"\n{'='*60}")
    print(f"  raw_event_payloads/")
    print(f"{'='*60}")
    renames = [p for p in payload_plan if p["action"] == "rename"]
    wins    = [p for p in payload_plan if p["action"] == "conflict_source_wins"]
    loses   = [p for p in payload_plan if p["action"] == "conflict_target_wins"]
    print(f"  Simple renames        : {len(renames)}")
    print(f"  Merge into target dir : {len(wins)}")
    print(f"  Backup source dir     : {len(loses)}")
    if renames:
        print(f"\n  Renames:")
        for p in renames:
            print(f"    {p['old_stem']} → {p['new_stem']}")
    if wins:
        print(f"\n  Merges (source files moved into target dir):")
        for p in wins:
            print(f"    {p['old_stem']} → {p['new_stem']} (merge)")
    if loses:
        print(f"\n  Backed up (dir renamed to .bak):")
        for p in loses:
            print(f"    {p['old_stem']} → {p['new_stem']}.bak")


# ---------------------------------------------------------------------------
# Apply plan
# ---------------------------------------------------------------------------


def apply_json_plan(plan: list[dict[str, Any]], dry_run: bool) -> None:
    for p in plan:
        if p["action"] == "ok":
            continue

        src: Path = p["src_path"]
        dst: Path = p["dst_path"]
        old_stem: str = p["old_stem"]
        new_stem: str = p["new_stem"]
        data: dict = p["data"]
        action: str = p["action"]

        # Prepare updated data
        new_data = data
        if p.get("name_content_wrong") or p["paths_need_update"]:
            new_data = dict(data)
            if p.get("name_content_wrong"):
                normalized = normalize_player_name(new_data.get("player_name", ""))
                if normalized:
                    new_data["player_name"] = normalized
                    new_data["english_name"] = normalized
            if p["paths_need_update"]:
                new_data = update_payload_paths(new_data, old_stem, new_stem)

        if action == "rename":
            print(f"  RENAME  {src.name} → {dst.name}")
            if not dry_run:
                write_json(dst, new_data)
                src.unlink()

        elif action == "conflict_source_wins":
            bak = dst.parent / f"{dst.stem}.bak.json"
            print(f"  OVERWRITE  {src.name} → {dst.name}  (old {dst.name} backed up as {bak.name})")
            if not dry_run:
                if dst.exists():
                    shutil.move(str(dst), str(bak))
                write_json(dst, new_data)
                src.unlink()

        elif action == "conflict_target_wins":
            bak = src.parent / f"{src.stem}.bak.json"
            print(f"  BACKUP  {src.name} → {bak.name}  (keeping {dst.name})")
            if not dry_run:
                # Still fix content in target if needed (player_name may be wrong in target too)
                try:
                    target_data = json.loads(dst.read_text(encoding="utf-8"))
                    target_norm = normalize_player_name(target_data.get("player_name", ""))
                    if target_norm and target_data.get("player_name") != target_norm:
                        target_data["player_name"] = target_norm
                        target_data["english_name"] = target_norm
                        write_json(dst, target_data)
                        print(f"    (also fixed player_name in {dst.name})")
                except Exception:
                    pass
                shutil.move(str(src), str(bak))


def apply_payload_plan(plan: list[dict[str, Any]], dry_run: bool) -> None:
    for p in plan:
        src: Path = p["src_path"]
        dst: Path = p["dst_path"]
        action: str = p["action"]

        if action == "rename":
            print(f"  RENAME DIR  {src.name} → {dst.name}")
            if not dry_run:
                shutil.move(str(src), str(dst))

        elif action == "conflict_source_wins":
            # Merge: move all files from src into dst
            print(f"  MERGE DIR  {src.name} → {dst.name}  (move contents)")
            if not dry_run:
                dst.mkdir(parents=True, exist_ok=True)
                for f in src.iterdir():
                    target_f = dst / f.name
                    if not target_f.exists():
                        shutil.move(str(f), str(target_f))
                    else:
                        print(f"    SKIP (already exists): {f.name}")
                if not any(src.iterdir()):
                    src.rmdir()
                else:
                    print(f"    NOTE: {src} not empty after merge, left in place")

        elif action == "conflict_target_wins":
            bak = src.parent / f"{src.name}.bak"
            print(f"  BACKUP DIR  {src.name} → {bak.name}")
            if not dry_run:
                shutil.move(str(src), str(bak))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate player names to SURNAME Given_name standard")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Preview only, make no changes (default: True)")
    parser.add_argument("--apply", action="store_true",
                        help="Actually apply the changes (disables dry-run)")
    args = parser.parse_args()

    dry_run = not args.apply

    print("\nBuilding rename plans...")
    orig_plan    = build_rename_plan(ORIG_DIR)
    cn_plan      = build_rename_plan(CN_DIR)
    payload_plan = build_payload_plan()

    print_plan(orig_plan, cn_plan, payload_plan)

    if dry_run:
        print("\n" + "="*60)
        print("  DRY RUN — no files changed.")
        print("  Run with --apply to execute the changes.")
        print("="*60)
        return

    print("\n" + "="*60)
    print("  APPLYING CHANGES")
    print("="*60)

    print("\n--- matches_complete/orig/ ---")
    apply_json_plan(orig_plan, dry_run=False)

    print("\n--- matches_complete/cn/ ---")
    apply_json_plan(cn_plan, dry_run=False)

    print("\n--- raw_event_payloads/ ---")
    apply_payload_plan(payload_plan, dry_run=False)

    print("\nDone. Reminder: checkpoint files may be stale.")
    print("Run scrape scripts with --rebuild-checkpoint if needed.")


if __name__ == "__main__":
    main()
