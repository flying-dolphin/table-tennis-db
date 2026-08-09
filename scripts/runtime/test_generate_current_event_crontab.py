import argparse
import sys
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import generate_current_event_crontab as cron


class GenerateCurrentEventCrontabTests(unittest.TestCase):
    def test_match_details_refresh_scrapes_match_details_and_imports_live_and_completed(self):
        args = argparse.Namespace(
            python_bin="/venv/bin/python",
            project_root="/srv/ittf",
            live_event_data_root="data/live_event_data",
            emit_db_path=None,
            db_path=Path("data/db/ittf.db"),
            runtime_python_dir="scripts/runtime",
            event_id=3242,
            headless=True,
            use_cdp=False,
            cdp_port=9223,
            log_dir=None,
        )

        command = cron.build_refresh_command(args, {"match_details"})

        self.assertIn("--sources match_details", command)
        self.assertIn("--db-path data/db/ittf.db", command)
        self.assertIn("--sources live completed --db-path", command)
        self.assertNotIn("--sources completed match_details", command)

    def test_live_refresh_includes_official_recent_completed_matches(self):
        args = argparse.Namespace(
            python_bin="/venv/bin/python",
            project_root="/srv/ittf",
            live_event_data_root="data/live_event_data",
            emit_db_path=None,
            db_path=Path("data/db/ittf.db"),
            runtime_python_dir="scripts/runtime",
            event_id=3242,
            headless=True,
            use_cdp=False,
            cdp_port=9223,
            log_dir=None,
        )

        command = cron.build_refresh_command(args, {"live"})

        self.assertIn("--sources live", command)
        self.assertIn("--include-official", command)

    def test_official_reconcile_refresh_only_scrapes_and_imports_completed(self):
        args = argparse.Namespace(
            python_bin="/venv/bin/python",
            project_root="/srv/ittf",
            live_event_data_root="data/live_event_data",
            emit_db_path=None,
            db_path=Path("data/db/ittf.db"),
            runtime_python_dir="scripts/runtime",
            event_id=3242,
            headless=True,
            use_cdp=False,
            cdp_port=9223,
            log_dir=None,
        )

        command = cron.build_refresh_command(args, {"official_reconcile"})

        self.assertEqual(2, command.count("--sources completed"))
        self.assertNotIn("match_details", command)
        self.assertNotIn("--include-official", command)

    def test_refresh_commands_scrape_before_locking_only_the_import(self):
        args = argparse.Namespace(
            python_bin="/venv/bin/python",
            project_root="/srv/ittf",
            live_event_data_root="data/live_event_data",
            emit_db_path=None,
            db_path=Path("data/db/ittf.db"),
            runtime_python_dir="scripts/runtime",
            event_id=3242,
            headless=True,
            use_cdp=False,
            cdp_port=9223,
            log_dir=None,
        )

        live_command = cron.build_refresh_command(args, {"live"})
        official_command = cron.build_refresh_command(args, {"official_reconcile"})
        lock_command = (
            "flock --conflict-exit-code 75 --wait 60 "
            "/srv/ittf/data/db/ittf.db.current-event.lock"
        )

        for command in (live_command, official_command):
            scrape_index = command.index("scrape_current_event.py")
            lock_index = command.index(lock_command)
            import_index = command.index("import_current_event.py")
            self.assertLess(scrape_index, lock_index)
            self.assertLess(lock_index, import_index)
            self.assertNotIn("scrape_current_event.py", command[lock_index:])

    def test_lock_timeout_has_a_distinct_exit_code_and_clear_context(self):
        args = argparse.Namespace(
            python_bin="/venv/bin/python",
            project_root="/srv/ittf",
            live_event_data_root="data/live_event_data",
            emit_db_path=None,
            db_path=Path("data/db/ittf.db"),
            runtime_python_dir="scripts/runtime",
            event_id=3242,
            headless=True,
            use_cdp=False,
            cdp_port=9223,
            log_dir=None,
        )

        command = cron.build_refresh_command(args, {"official_reconcile"})

        self.assertIn("--conflict-exit-code 75 --wait 60", command)
        self.assertIn(
            "lock timeout event_id=3242 sources=official_reconcile wait_seconds=60",
            command,
        )
        self.assertIn('if [ "$lock_rc" -eq 75 ]', command)
        self.assertIn('exit "$lock_rc"', command)

    def test_import_failure_is_not_classified_as_lock_timeout(self):
        args = argparse.Namespace(
            python_bin="/venv/bin/python",
            project_root="/srv/ittf",
            live_event_data_root="data/live_event_data",
            emit_db_path=None,
            db_path=Path("data/db/ittf.db"),
            runtime_python_dir="scripts/runtime",
            event_id=3242,
            headless=True,
            use_cdp=False,
            cdp_port=9223,
            log_dir=None,
        )

        command = cron.build_refresh_command(args, {"official_reconcile"})
        timeout_check = 'if [ "$lock_rc" -eq 75 ]'

        self.assertIn(timeout_check, command)
        self.assertIn(
            'if [ "$import_rc" -eq 75 ]; then exit 74; fi',
            command,
        )
        self.assertLess(command.index("flock "), command.index("lock_rc=$?"))
        self.assertLess(command.index("lock_rc=$?"), command.index(timeout_check))

    def test_session_official_reconcile_times_run_hourly_and_at_session_end(self):
        session_start = cron.datetime(2026, 7, 1, 10, 0, 42, 999)

        times = cron.session_official_reconcile_times(session_start)

        self.assertEqual(
            ["10:05", "11:05", "12:05", "13:05", "14:05", "15:00"],
            [run_at.strftime("%H:%M") for run_at in times],
        )
        self.assertTrue(all(run_at.second == 0 and run_at.microsecond == 0 for run_at in times))

    def test_session_refreshes_use_cron_ranges_instead_of_per_tick_jobs(self):
        event = cron.Event(3242, "United States Smash 2026", "America/Los_Angeles")
        schedule = [
            cron.SessionDay(
                local_date=cron.date(2026, 7, 1),
                morning_session_start="10:00",
                afternoon_session_start=None,
                raw_sub_events_text="Main Draw",
                parsed_rounds_json='[{"stage_code":"MAIN_DRAW","round_code":"R32"}]',
            ),
            cron.SessionDay(
                local_date=cron.date(2026, 7, 1),
                morning_session_start="10:00",
                afternoon_session_start=None,
                raw_sub_events_text="Main Draw",
                parsed_rounds_json='[{"stage_code":"MAIN_DRAW","round_code":"R32"}]',
            )
        ]

        _main_draw_start, jobs = cron.build_jobs(event, schedule, "Asia/Shanghai")
        refresh_jobs = [
            job
            for job in jobs
            if job.run_at.date() == cron.date(2026, 7, 2)
            and ("live" in job.sources or "match_details" in job.sources)
        ]
        range_lines = {
            tuple(sorted(job.sources)): cron.cron_line(job, "run")
            for job in refresh_jobs
        }

        self.assertEqual(1, len(refresh_jobs))
        self.assertIn(("live",), range_lines)
        self.assertTrue(range_lines[("live",)].startswith("0,10,20,30,40,50 1-5 2 7 * "))
        self.assertNotIn("completed", set().union(*(job.sources for job in refresh_jobs)))

    def test_build_jobs_adds_official_reconcile_after_live_for_each_session(self):
        event = cron.Event(3242, "Test Event", "Asia/Shanghai")
        schedule = [
            cron.SessionDay(
                local_date=cron.date(2026, 7, 1),
                morning_session_start="10:00",
                afternoon_session_start=None,
                raw_sub_events_text="Main Draw",
                parsed_rounds_json='[{"stage_code":"MAIN_DRAW","round_code":"R32"}]',
            )
        ]

        _main_draw_start, jobs = cron.build_jobs(event, schedule, "Asia/Shanghai")
        reconcile_jobs = [job for job in jobs if job.sources == {"official_reconcile"}]

        self.assertEqual(
            ["10:05", "11:05", "12:05", "13:05", "14:05", "15:00"],
            [job.run_at.strftime("%H:%M") for job in reconcile_jobs],
        )
        self.assertTrue(
            all(job.labels == {"morning-official-reconcile"} for job in reconcile_jobs)
        )

    def test_session_end_brackets_and_official_reconcile_share_the_db_lock(self):
        event = cron.Event(3242, "Test Event", "Asia/Shanghai")
        schedule = [
            cron.SessionDay(
                local_date=cron.date(2026, 7, 1),
                morning_session_start="10:00",
                afternoon_session_start=None,
                raw_sub_events_text="Main Draw",
                parsed_rounds_json='[{"stage_code":"MAIN_DRAW","round_code":"R32"}]',
            ),
            cron.SessionDay(
                local_date=cron.date(2026, 7, 2),
                morning_session_start="10:00",
                afternoon_session_start=None,
                raw_sub_events_text="Main Draw",
                parsed_rounds_json='[{"stage_code":"MAIN_DRAW","round_code":"R16"}]',
            ),
        ]
        args = argparse.Namespace(
            python_bin="/venv/bin/python",
            project_root="/srv/ittf",
            live_event_data_root="data/live_event_data",
            emit_db_path=None,
            db_path=Path("data/db/ittf.db"),
            runtime_python_dir="scripts/runtime",
            event_id=3242,
            headless=True,
            use_cdp=False,
            cdp_port=9223,
            log_dir=None,
        )

        _main_draw_start, jobs = cron.build_jobs(event, schedule, "Asia/Shanghai")
        collision_jobs = [
            job
            for job in jobs
            if job.run_at == cron.datetime(2026, 7, 1, 15, 0, tzinfo=job.run_at.tzinfo)
        ]
        collision_sources = {tuple(sorted(job.sources)) for job in collision_jobs}
        commands = [cron.build_refresh_command(args, job.sources) for job in collision_jobs]

        self.assertIn(("brackets",), collision_sources)
        self.assertIn(("official_reconcile",), collision_sources)
        self.assertTrue(
            all("/srv/ittf/data/db/ittf.db.current-event.lock" in command for command in commands)
        )

    def test_previous_session_end_and_next_live_share_the_db_lock(self):
        event = cron.Event(3242, "Test Event", "Asia/Shanghai")
        schedule = [
            cron.SessionDay(
                local_date=cron.date(2026, 7, 1),
                morning_session_start="10:00",
                afternoon_session_start="15:00",
                raw_sub_events_text="Main Draw",
                parsed_rounds_json='[{"stage_code":"MAIN_DRAW","round_code":"R32"}]',
            )
        ]
        args = argparse.Namespace(
            python_bin="/venv/bin/python",
            project_root="/srv/ittf",
            live_event_data_root="data/live_event_data",
            emit_db_path=None,
            db_path=Path("data/db/ittf.db"),
            runtime_python_dir="scripts/runtime",
            event_id=3242,
            headless=True,
            use_cdp=False,
            cdp_port=9223,
            log_dir=None,
        )

        _main_draw_start, jobs = cron.build_jobs(event, schedule, "Asia/Shanghai")
        official_job = next(
            job
            for job in jobs
            if job.run_at.hour == 15
            and job.run_at.minute == 0
            and job.sources == {"official_reconcile"}
        )
        next_live_job = next(
            job
            for job in jobs
            if job.run_at.hour == 15 and job.sources == {"live"}
        )

        official_command = cron.build_refresh_command(args, official_job.sources)
        live_command = cron.build_refresh_command(args, next_live_job.sources)

        self.assertIn("/srv/ittf/data/db/ittf.db.current-event.lock", official_command)
        self.assertIn("/srv/ittf/data/db/ittf.db.current-event.lock", live_command)
        self.assertNotEqual(official_command, live_command)

    def test_cross_midnight_reconcile_times_deduplicate_repeated_sessions(self):
        event = cron.Event(3242, "Test Event", "Asia/Shanghai")
        repeated_day = cron.SessionDay(
            local_date=cron.date(2026, 7, 1),
            morning_session_start="22:00",
            afternoon_session_start=None,
            raw_sub_events_text="Main Draw",
            parsed_rounds_json='[{"stage_code":"MAIN_DRAW","round_code":"R32"}]',
        )

        _main_draw_start, jobs = cron.build_jobs(
            event,
            [repeated_day, repeated_day],
            "Asia/Shanghai",
        )
        reconcile_jobs = [job for job in jobs if job.sources == {"official_reconcile"}]

        self.assertEqual(
            [
                "2026-07-01 22:05",
                "2026-07-01 23:05",
                "2026-07-02 00:05",
                "2026-07-02 01:05",
                "2026-07-02 02:05",
                "2026-07-02 03:00",
            ],
            [job.run_at.strftime("%Y-%m-%d %H:%M") for job in reconcile_jobs],
        )


if __name__ == "__main__":
    unittest.main()
