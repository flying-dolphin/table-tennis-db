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

        self.assertEqual(2, len(refresh_jobs))
        self.assertIn(("match_details",), range_lines)
        self.assertIn(("live",), range_lines)
        self.assertTrue(range_lines[("match_details",)].startswith("0,30 1-5 2 7 * "))
        self.assertTrue(range_lines[("live",)].startswith("10,20,40,50 1-5 2 7 * "))
        self.assertNotIn("completed", set().union(*(job.sources for job in refresh_jobs)))


if __name__ == "__main__":
    unittest.main()
