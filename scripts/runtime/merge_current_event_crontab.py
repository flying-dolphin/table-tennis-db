#!/usr/bin/env python3
"""Merge one event's generated jobs into the managed crontab block."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


BLOCK_BEGIN = "# ITTF current-event refresh begin"
BLOCK_END = "# ITTF current-event refresh end"
EVENT_BEGIN = "# ITTF current-event event {event_id} begin"
EVENT_END = "# ITTF current-event event {event_id} end"
GENERATED_EVENT_RE = re.compile(r"^# Generated for event (\d+):")
CRON_LINE_RE = re.compile(r"^[0-9]+\s+[0-9]+\s+[0-9*]+\s+[0-9*]+\s+")


def _managed_parts(crontab: str) -> tuple[str, str, str]:
    begin = crontab.find(BLOCK_BEGIN)
    if begin < 0:
        return crontab, "", ""
    end_marker = crontab.find(BLOCK_END, begin)
    if end_marker < 0:
        raise ValueError("managed current-event block has no end marker")
    end = end_marker + len(BLOCK_END)
    return crontab[:begin], crontab[begin:end_marker], crontab[end:]


def _normalise_events(body: str) -> dict[int, list[str]]:
    """Read both legacy single-event and current per-event managed bodies."""
    events: dict[int, list[str]] = {}
    current_id: int | None = None
    current_lines: list[str] = []

    def finish() -> None:
        nonlocal current_id, current_lines
        if current_id is not None:
            events[current_id] = current_lines
        current_id = None
        current_lines = []

    for line in body.splitlines():
        if line.startswith("# ITTF current-event event ") and line.endswith(" begin"):
            finish()
            current_id = int(line[len("# ITTF current-event event ") : -len(" begin")])
            continue
        if line.startswith("# ITTF current-event event ") and line.endswith(" end"):
            finish()
            continue

        match = GENERATED_EVENT_RE.match(line)
        if match:
            finish()
            current_id = int(match.group(1))
            current_lines = [line]
            continue

        if current_id is not None:
            current_lines.append(line)

    finish()
    return events


def _has_cron_jobs(generated: str) -> bool:
    return any(CRON_LINE_RE.match(line) for line in generated.splitlines())


def merge_crontab(existing: str, generated: str, event_id: int) -> str:
    """Replace one event's managed jobs while preserving all other crontab lines."""
    prefix, managed, suffix = _managed_parts(existing)
    events = _normalise_events(managed)
    if _has_cron_jobs(generated):
        events[event_id] = generated.rstrip("\n").splitlines()
    else:
        events.pop(event_id, None)

    if not events:
        return existing if not managed else prefix + suffix

    lines = []
    if prefix.rstrip("\n"):
        lines.append(prefix.rstrip("\n"))
    lines.append(BLOCK_BEGIN)
    for current_id in sorted(events):
        lines.append(EVENT_BEGIN.format(event_id=current_id))
        lines.extend(events[current_id])
        lines.append(EVENT_END.format(event_id=current_id))
    lines.append(BLOCK_END)
    if suffix.lstrip("\n"):
        lines.append(suffix.lstrip("\n"))
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--generated-file", type=Path, required=True)
    args = parser.parse_args()
    generated = args.generated_file.read_text()
    sys.stdout.write(merge_crontab(sys.stdin.read(), generated, args.event_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
