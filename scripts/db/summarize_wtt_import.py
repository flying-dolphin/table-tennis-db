"""Aggregate the per-command JSON summaries of one WTT import run.

`run_import_wtt_events.sh` writes structured `--summary-json` files into a
per-run log directory:

    <run_dir>/import_matches.json
    <run_dir>/draw/<event_id>.json
    <run_dir>/sub_events/<event_id>.json

This script reads them and prints a single, compact "manual check" block so the
human-facing信息 is not scattered across every per-event command's stdout.

It always exits 0 — the import itself already succeeded; this is reporting only.
See docs/wtt-event-import-issues-plan.md (问题 2).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

LINE = "=" * 62


def _load(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[WARN] cannot read {path}: {exc}")
        return None


def _categorize_skipped(skipped_files: list[str]) -> dict[str, list[str]]:
    """Group skipped_files entries by reason for a compact display."""
    buckets: dict[str, list[str]] = {
        "not in events": [],
        "name mismatch": [],
        "no event_id": [],
        "other": [],
    }
    for item in skipped_files:
        low = item.lower()
        if "not found in events" in low:
            buckets["not in events"].append(item)
        elif "payload event mismatch" in low:
            buckets["name mismatch"].append(item)
        elif "missing/invalid event_id" in low:
            buckets["no event_id"].append(item)
        else:
            buckets["other"].append(item)
    return {k: v for k, v in buckets.items() if v}


def summarize(run_dir: Path) -> bool:
    """Render the summary. Returns True if manual-check items were found."""
    import_events = _load(run_dir / "import_events.json")
    event_summary_files = sorted((run_dir / "events").glob("*.json")) if (run_dir / "events").is_dir() else []
    event_summaries = [data for path in event_summary_files if (data := _load(path)) is not None]
    player_prepare = _load(run_dir / "player_matches" / "prepare_same_name_player_matches.json")
    matches = _load(run_dir / "import_matches.json")
    draw_files = sorted((run_dir / "draw").glob("*.json")) if (run_dir / "draw").is_dir() else []
    sub_files = sorted((run_dir / "sub_events").glob("*.json")) if (run_dir / "sub_events").is_dir() else []

    draws = {d.stem: data for d in draw_files if (data := _load(d)) is not None}
    subs = {s.stem: data for s in sub_files if (data := _load(s)) is not None}

    manual = False
    lines: list[str] = []

    # --- import_events ----------------------------------------------------
    if import_events is not None:
        lines.append(
            f"import_events: inserted={import_events.get('inserted', 0)} "
            f"skipped={import_events.get('skipped', 0)} errors={len(import_events.get('errors') or [])}"
        )
        if import_events.get("errors"):
            manual = True
    elif event_summaries:
        inserted = sum(int(item.get("inserted", 0)) for item in event_summaries)
        skipped = sum(int(item.get("skipped", 0)) for item in event_summaries)
        errors = sum(len(item.get("errors") or []) for item in event_summaries)
        lines.append(
            f"import_events: files={len(event_summaries)} inserted={inserted} skipped={skipped} errors={errors}"
        )
        if errors:
            manual = True

    # --- same-name player evidence ---------------------------------------
    if player_prepare is not None:
        targets = player_prepare.get("targets") or []
        needed = [target for target in targets if target.get("needs_scrape")]
        lines.append(
            f"same-name player matches: targets={len(targets)} prepared={len(needed)} "
            f"from_date={player_prepare.get('from_date')}"
        )

    # --- import_matches ---------------------------------------------------
    if matches is not None:
        event_ids = matches.get("event_ids") or []
        ids_label = " ".join(str(e) for e in event_ids) if event_ids else "(full refresh)"
        lines.append(f"Event ids ({len(event_ids)}): {ids_label}")
        skipped = matches.get("skipped_files") or []
        unresolved = matches.get("unresolved_winner_side", 0)
        lines.append(
            f"import_matches: inserted={matches.get('inserted', 0)} "
            f"unresolved_winner_side={unresolved} "
            f"skipped_files={len(skipped)}"
        )
        if skipped:
            manual = True
            for reason, items in _categorize_skipped(skipped).items():
                lines.append(f"  skipped ({reason}): {len(items)}")
                for item in items:
                    lines.append(f"    - {item}")
        if unresolved:
            manual = True
            lines.append(f"  unresolved winner_side: {unresolved} (检查源数据是否未完赛)")
        for key, label in (
            ("unmatched_events", "unmatched events"),
            ("unmatched_players", "unmatched players"),
            ("ambiguous_players", "ambiguous players"),
            ("unresolved_same_name_players", "unresolved same-name players"),
            ("ambiguous_same_name_players", "ambiguous same-name players"),
            ("errors", "errors"),
        ):
            values = matches.get(key) or []
            if values:
                manual = True
                lines.append(f"  {label} ({len(values)}):")
                for item in values[:15]:
                    lines.append(f"    - {item}")
                if len(values) > 15:
                    lines.append(f"    ... and {len(values) - 15} more")
    else:
        lines.append("import_matches: (no summary JSON found)")

    # --- per-event draw + sub_events -------------------------------------
    problem_lines: list[str] = []
    for eid in sorted(set(draws) | set(subs), key=lambda x: (len(x), x)):
        d = draws.get(eid) or {}
        s = subs.get(eid) or {}
        unsupported = d.get("unsupported_main_round", 0)
        dup = d.get("duplicate_match_ids", 0)
        problems = s.get("problem_events") or []
        unmatched_champs = s.get("unmatched_champion_members") or []

        event_notes: list[str] = []
        if unsupported:
            event_notes.append(f"draw: unsupported_main_round={unsupported}")
        if dup:
            event_notes.append(f"draw: duplicate_match_ids={dup}")
        if unmatched_champs:
            preview = ", ".join(unmatched_champs[:4])
            more = f", +{len(unmatched_champs) - 4}" if len(unmatched_champs) > 4 else ""
            event_notes.append(
                f"sub_events: unmatched champion members={len(unmatched_champs)} ({preview}{more})"
            )
        for p in problems:
            event_notes.append(
                f"sub_events: {p.get('issue_type')} [{p.get('sub_event_type_code')}] {p.get('detail')}"
            )

        if event_notes:
            manual = True
            problem_lines.append(f"  {eid}:")
            for note in event_notes:
                problem_lines.append(f"    {note}")

    if problem_lines:
        lines.append("per-event problems:")
        lines.extend(problem_lines)

    lines.append(f"detailed logs: {run_dir}")

    # --- render -----------------------------------------------------------
    print()
    header = "⚠ MANUAL CHECK REQUIRED" if manual else "WTT Import Summary (clean)"
    print(LINE)
    print(f"  {header}  run={run_dir.name}")
    print(LINE)
    for line in lines:
        print(line)
    print(LINE)
    return manual


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate one WTT import run's JSON summaries")
    parser.add_argument("--run-dir", required=True, type=Path, help="Per-run log directory")
    args = parser.parse_args()

    if not args.run_dir.is_dir():
        print(f"[ERROR] run dir not found: {args.run_dir}")
        return 0  # reporting-only; do not break the import pipeline

    summarize(args.run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
