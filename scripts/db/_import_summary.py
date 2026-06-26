"""Shared helper: write a structured JSON summary for the WTT import scripts.

`import_matches.py` / `import_event_draw_matches.py` / `import_sub_events.py`
each already build a complete `result`/`stats` dict describing their run. This
helper serializes that dict to JSON so `run_import_wtt_events.sh` can aggregate
the manual-check信息 without parsing human-readable stdout.

See docs/wtt-event-import-issues-plan.md (问题 2) for the design.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def _jsonable(value: Any) -> Any:
    """Convert sets/tuples/Path into JSON-serializable forms (recursively)."""
    if isinstance(value, set):
        return sorted(_jsonable(v) for v in value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def resolve_summary_path(
    raw: str,
    *,
    project_root: Path,
    kind: str,
    event_id: Optional[int] = None,
) -> Path:
    """Resolve a ``--summary-json`` value into a concrete path.

    A literal path is used as-is. ``auto`` writes a timestamped file under
    ``data/logs/wtt-event-import/_adhoc/`` (mirrors the
    ``promote_current_event.py --unmatched-out auto`` convention). The
    orchestrator passes explicit per-run paths; ``auto`` is for ad-hoc runs.
    """
    if raw != "auto":
        return Path(raw)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{event_id}" if event_id is not None else ""
    return (
        project_root
        / "data"
        / "logs"
        / "wtt-event-import"
        / "_adhoc"
        / f"{kind}{suffix}_{ts}.json"
    )


def write_summary(
    result: dict,
    raw_path: str,
    *,
    project_root: Path,
    kind: str,
    event_id: Optional[int] = None,
) -> Path:
    """Serialize ``result`` (plus kind/event_id metadata) to JSON; return path."""
    path = resolve_summary_path(
        raw_path, project_root=project_root, kind=kind, event_id=event_id
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"kind": kind, "event_id": event_id, **_jsonable(result)}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path
