#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate Beijing-time crontab entries for current-event refresh jobs."""

from __future__ import annotations

import argparse
import json
import shlex
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"
TARGET_TIME_ZONE = "Asia/Shanghai"

SCRAPE_IMPORT_SOURCES = {
    "schedule": ("schedule", "schedule"),
    "standings": ("standings", "standings"),
    "brackets": ("brackets", "brackets"),
    "live": ("live", "live"),
    "completed": ("completed", "completed"),
}

SOURCE_ORDER = ["schedule", "standings", "brackets", "live", "completed"]
MAIN_DRAW_ROUNDS = {
    "R256",
    "R128",
    "R64",
    "R48",
    "R32",
    "R24",
    "R16",
    "R8",
    "QF",
    "SF",
    "BR",
    "F",
}


@dataclass(frozen=True)
class Event:
    event_id: int
    name: str
    time_zone: str


@dataclass(frozen=True)
class SessionDay:
    local_date: date
    morning_session_start: str | None
    afternoon_session_start: str | None
    raw_sub_events_text: str | None
    parsed_rounds_json: str | None


@dataclass
class CronJob:
    run_at: datetime
    sources: set[str]
    labels: set[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate crontab lines for current-event schedule, standings, brackets, "
            "live matches, and official completed results. Times are emitted for Asia/Shanghai."
        )
    )
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument(
        "--runtime-python-dir",
        default="scripts/runtime",
        help="Directory containing scrape/import runtime scripts in generated commands.",
    )
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--live-event-data-root", default=str(PROJECT_ROOT / "data" / "live_event_data"))
    parser.add_argument(
        "--emit-db-path",
        default=None,
        help="DB path to place in generated cron commands. Defaults to --db-path as written.",
    )
    parser.add_argument("--cron-time-zone", default=TARGET_TIME_ZONE)
    parser.add_argument("--headless", action="store_true", help="Pass --headless to browser-backed scrape sources.")
    parser.add_argument("--use-cdp", action="store_true", help="Pass --use-cdp to browser-backed scrape sources.")
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument(
        "--include-past",
        action="store_true",
        help="Include cron entries whose Beijing run time is already in the past.",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Directory for cron job log files (e.g. /opt/ittf-data/logs). "
             "If omitted, cron output is not redirected and may be silently discarded.",
    )
    return parser.parse_args()


def load_event_and_schedule(db_path: Path, event_id: int) -> tuple[Event, list[SessionDay]]:
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        event_row = conn.execute(
            """
            SELECT event_id, name, time_zone
            FROM events
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()
        if event_row is None:
            raise ValueError(f"events table has no event_id={event_id}")

        time_zone = (event_row["time_zone"] or "").strip()
        if not time_zone:
            raise ValueError(
                f"events.time_zone is empty for event_id={event_id}; "
                "set an IANA time zone before generating cron entries"
            )
        validate_time_zone(time_zone)

        rows = conn.execute(
            """
            SELECT local_date, morning_session_start, afternoon_session_start,
                   raw_sub_events_text, parsed_rounds_json
            FROM current_event_session_schedule
            WHERE event_id = ?
            ORDER BY local_date, current_session_schedule_id
            """,
            (event_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise ValueError(
            f"current_event_session_schedule has no rows for event_id={event_id}; "
            "import the session schedule first"
        )

    event = Event(event_id=int(event_row["event_id"]), name=event_row["name"], time_zone=time_zone)
    schedule = [
        SessionDay(
            local_date=date.fromisoformat(row["local_date"]),
            morning_session_start=row["morning_session_start"],
            afternoon_session_start=row["afternoon_session_start"],
            raw_sub_events_text=row["raw_sub_events_text"],
            parsed_rounds_json=row["parsed_rounds_json"],
        )
        for row in rows
    ]
    return event, schedule


def validate_time_zone(time_zone: str) -> None:
    try:
        ZoneInfo(time_zone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"invalid IANA time zone: {time_zone}") from exc


def is_main_draw_day(day: SessionDay) -> bool:
    parsed = parse_rounds(day.parsed_rounds_json)
    for item in parsed:
        stage_code = str(item.get("stage_code") or "").upper()
        round_code = str(item.get("round_code") or "").upper()
        if stage_code == "MAIN_DRAW" and (round_code in MAIN_DRAW_ROUNDS or round_code != "UNKNOWN"):
            return True

    raw = (day.raw_sub_events_text or "").lower()
    knockout_markers = (
        "main draw",
        "32强赛",
        "16强赛",
        "8强赛",
        "四分之一决赛",
        "半决赛",
        "铜牌赛",
        "决赛",
        "round of 32",
        "round of 16",
        "quarter",
        "semi",
        "final",
    )
    excluded_markers = ("预选赛", "种子排位赛", "qualification", "seeding", "group")
    return any(marker in raw for marker in knockout_markers) and not any(marker in raw for marker in excluded_markers)


def parse_rounds(raw_json: str | None) -> list[dict]:
    if not raw_json:
        return []
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def find_main_draw_start(schedule: list[SessionDay]) -> date:
    for day in schedule:
        if is_main_draw_day(day):
            return day.local_date
    raise ValueError("could not detect Main Draw start date from current_event_session_schedule")


def parse_local_time(value: str | None) -> time | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"invalid session time: {value}")


def session_starts(day: SessionDay) -> list[tuple[str, time]]:
    sessions: list[tuple[str, time]] = []
    morning = parse_local_time(day.morning_session_start)
    afternoon = parse_local_time(day.afternoon_session_start)
    if morning:
        sessions.append(("morning", morning))
    if afternoon and afternoon != morning:
        sessions.append(("afternoon", afternoon))
    return sessions


def second_session_or_fallback(day: SessionDay) -> time | None:
    starts = session_starts(day)
    if len(starts) >= 2:
        return starts[1][1]
    if starts:
        return starts[0][1]
    return None


def to_target_datetime(local_day: date, local_session_time: time, event_tz: ZoneInfo, target_tz: ZoneInfo) -> datetime:
    local_dt = datetime.combine(local_day, local_session_time).replace(tzinfo=event_tz)
    return local_dt.astimezone(target_tz)


def add_job(jobs: dict[datetime, CronJob], run_at: datetime, source: str, label: str) -> None:
    key = run_at.replace(second=0, microsecond=0)
    job = jobs.get(key)
    if job is None:
        jobs[key] = CronJob(run_at=key, sources={source}, labels={label})
        return
    job.sources.add(source)
    job.labels.add(label)


def build_jobs(event: Event, schedule: list[SessionDay], target_time_zone: str) -> tuple[date, list[CronJob]]:
    main_draw_start = find_main_draw_start(schedule)
    event_tz = ZoneInfo(event.time_zone)
    target_tz = ZoneInfo(target_time_zone)
    jobs: dict[datetime, CronJob] = {}

    for day in schedule:
        evening_start = second_session_or_fallback(day)
        if evening_start:
            run_at = to_target_datetime(day.local_date, evening_start, event_tz, target_tz) + timedelta(hours=5)
            add_job(jobs, run_at, "schedule", "daily-schedule")

    for day in schedule:
        second_start = second_session_or_fallback(day)
        if second_start and day.local_date < main_draw_start:
            run_at = to_target_datetime(day.local_date, second_start, event_tz, target_tz) + timedelta(hours=3)
            add_job(jobs, run_at, "standings", "standings")

    pre_main_day = next((day for day in schedule if day.local_date == main_draw_start - timedelta(days=1)), None)
    if pre_main_day:
        second_start = second_session_or_fallback(pre_main_day)
        if second_start:
            run_at = to_target_datetime(pre_main_day.local_date, second_start, event_tz, target_tz) + timedelta(hours=3)
            add_job(jobs, run_at, "brackets", "pre-main-draw-brackets")

    for day in schedule:
        starts = session_starts(day)
        if day.local_date >= main_draw_start:
            for session_label, start in starts:
                run_at = to_target_datetime(day.local_date, start, event_tz, target_tz) + timedelta(hours=3)
                add_job(jobs, run_at, "brackets", f"{session_label}-brackets")

        for session_label, start in starts:
            session_start = to_target_datetime(day.local_date, start, event_tz, target_tz)
            for idx in range(1, 7):
                run_at = session_start + timedelta(minutes=30 * idx)
                add_job(jobs, run_at, "live", f"{session_label}-live-{idx}")
            for idx in range(1, 3):
                run_at = session_start + timedelta(hours=2 * idx)
                add_job(jobs, run_at, "completed", f"{session_label}-completed-{idx}")

    return main_draw_start, sorted(jobs.values(), key=lambda item: item.run_at)


def shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def build_refresh_command(args: argparse.Namespace, sources: set[str]) -> str:
    ordered_sources = [source for source in SOURCE_ORDER if source in sources]
    scrape_sources = [SCRAPE_IMPORT_SOURCES[source][0] for source in ordered_sources]
    import_sources = [SCRAPE_IMPORT_SOURCES[source][1] for source in ordered_sources]

    python_bin = str(args.python_bin)
    project_root = str(args.project_root)
    live_root = str(args.live_event_data_root)
    command_db_path = str(args.emit_db_path or args.db_path)
    runtime_python_dir = str(args.runtime_python_dir).rstrip("/")
    event_id = str(args.event_id)

    scrape_cmd = [
        python_bin,
        f"{runtime_python_dir}/scrape_current_event.py",
        "--event-id",
        event_id,
        "--sources",
        *scrape_sources,
        "--live-event-data-root",
        live_root,
    ]
    browser_sources = {"standings", "live"}
    if browser_sources.intersection(sources):
        if args.headless:
            scrape_cmd.append("--headless")
        if args.use_cdp:
            scrape_cmd.append("--use-cdp")
        scrape_cmd.extend(["--cdp-port", str(args.cdp_port)])

    import_cmd = [
        python_bin,
        f"{runtime_python_dir}/import_current_event.py",
        "--event-id",
        event_id,
        "--sources",
        *import_sources,
        "--db-path",
        command_db_path,
        "--live-event-data-root",
        live_root,
    ]

    cmd = f"cd {shlex.quote(project_root)} && {shell_join(scrape_cmd)} && {shell_join(import_cmd)}"

    if args.log_dir:
        log_file = f"{args.log_dir}/event_{event_id}_$(date +\\%Y\\%m\\%d).log"
        cmd = f"mkdir -p {shlex.quote(args.log_dir)} && {cmd} >> {log_file} 2>&1"

    return cmd


def cron_line(job: CronJob, command: str) -> str:
    run_date = job.run_at.strftime("%Y-%m-%d")
    guard = f'test "$(date +\\%Y-\\%m-\\%d)" = "{run_date}"'
    return (
        f"{job.run_at.minute} {job.run_at.hour} {job.run_at.day} {job.run_at.month} * "
        f"{guard} && {command}"
    )


def render_crontab(args: argparse.Namespace, event: Event, main_draw_start: date, jobs: list[CronJob]) -> str:
    now = datetime.now(ZoneInfo(args.cron_time_zone)).replace(second=0, microsecond=0)
    selected_jobs = jobs if args.include_past else [job for job in jobs if job.run_at >= now]

    lines = [
        f"# Generated for event {event.event_id}: {event.name}",
        f"# Event time zone: {event.time_zone}",
        f"# Cron time zone: {args.cron_time_zone}",
        f"# Main Draw starts on event-local date: {main_draw_start.isoformat()}",
        "# Install with care; entries are date-guarded and are safe to leave in crontab after the event.",
        f"CRON_TZ={args.cron_time_zone}",
    ]

    if not selected_jobs:
        lines.append("# No future jobs to emit. Re-run with --include-past to inspect the full event window.")
        return "\n".join(lines)

    for job in selected_jobs:
        labels = ",".join(sorted(job.labels))
        sources = ",".join(source for source in SOURCE_ORDER if source in job.sources)
        lines.append(f"# {job.run_at.isoformat()} sources={sources} labels={labels}")
        lines.append(cron_line(job, build_refresh_command(args, job.sources)))

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        validate_time_zone(args.cron_time_zone)
        event, schedule = load_event_and_schedule(args.db_path, args.event_id)
        main_draw_start, jobs = build_jobs(event, schedule, args.cron_time_zone)
        print(render_crontab(args, event, main_draw_start, jobs))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
