import sys
import unittest
from argparse import Namespace
from datetime import datetime, timedelta
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_update_rankings_profiles as pipeline  # noqa: E402


def _state(stages: dict[str, str] | None = None, **extra) -> dict:
    state = {
        "updated_at": "",
        "since_ts": "2026-10-08 16:00:00",
        "scope": "weekly",
        "last_full_profile_refresh": "",
        "stages": {},
    }
    for name, status in (stages or {}).items():
        state["stages"][name] = {"status": status, "at": "", "meta": {}}
    state.update(extra)
    return state


def _args(scope: str = "auto", interval: int = 30) -> Namespace:
    return Namespace(scope=scope, monthly_interval_days=interval)


class ScopeResolutionTests(unittest.TestCase):
    def test_auto_with_no_full_refresh_is_monthly(self):
        self.assertEqual(pipeline.resolve_scope(_args(), _state()), "monthly")

    def test_auto_with_old_full_refresh_is_monthly(self):
        old = (datetime.now() - timedelta(days=40)).isoformat()
        self.assertEqual(
            pipeline.resolve_scope(_args(), _state(last_full_profile_refresh=old)),
            "monthly",
        )

    def test_auto_with_recent_full_refresh_is_weekly(self):
        recent = (datetime.now() - timedelta(days=5)).isoformat()
        self.assertEqual(
            pipeline.resolve_scope(_args(), _state(last_full_profile_refresh=recent)),
            "weekly",
        )

    def test_explicit_scope_wins_over_auto(self):
        recent = (datetime.now() - timedelta(days=5)).isoformat()
        self.assertEqual(
            pipeline.resolve_scope(_args(scope="monthly"), _state(last_full_profile_refresh=recent)),
            "monthly",
        )


class RunDetectionTests(unittest.TestCase):
    def test_all_done_means_no_incomplete_run(self):
        done = {name: "done" for name in pipeline.STAGES}
        state = _state(done)
        self.assertTrue(pipeline.all_done(state))
        self.assertFalse(pipeline.has_incomplete_run(state))

    def test_failed_stage_marks_incomplete_run(self):
        state = _state({"scrape_rankings": "done", "resolve_ids": "failed"})
        self.assertTrue(pipeline.has_incomplete_run(state))
        self.assertFalse(pipeline.all_done(state))

    def test_needs_review_marks_incomplete_run(self):
        state = _state({"resolve_ids": "needs_review"})
        self.assertTrue(pipeline.has_incomplete_run(state))

    def test_pending_stage_is_not_incomplete_but_not_done(self):
        state = _state({"scrape_rankings": "done", "resolve_ids": "pending"})
        self.assertFalse(pipeline.has_incomplete_run(state))
        self.assertFalse(pipeline.all_done(state))
        self.assertEqual(pipeline.first_incomplete_stage(state), "resolve_ids")

    def test_first_incomplete_stage_skips_done_stages(self):
        state = _state({"scrape_rankings": "done", "resolve_ids": "done", "scrape_profiles": "failed"})
        self.assertEqual(pipeline.first_incomplete_stage(state), "scrape_profiles")

    def test_skipped_stage_counts_as_complete(self):
        stages = {name: "done" for name in pipeline.STAGES}
        stages["deploy"] = "skipped"
        state = _state(stages)
        self.assertTrue(pipeline.all_done(state))
        self.assertFalse(pipeline.has_incomplete_run(state))


class FileDiscoveryTests(unittest.TestCase):
    def test_latest_weekly_file_excludes_merged_and_other_top(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "women_singles_top1000_week16.json").write_text("{}", encoding="utf-8")
            (d / "women_singles_top1000_week17.json").write_text("{}", encoding="utf-8")
            (d / "women_singles_top1000_week17_with_ids.json").write_text("{}", encoding="utf-8")
            (d / "women_singles_top100_week17.json").write_text("{}", encoding="utf-8")

            self.assertEqual(
                pipeline.latest_weekly_file(d, top=1000).name,
                "women_singles_top1000_week17.json",
            )
            self.assertEqual(
                pipeline.latest_merged_file(d, top=1000).name,
                "women_singles_top1000_week17_with_ids.json",
            )

    def test_unresolved_count_reads_report(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            report = d / "x_unresolved.json"
            report.write_text(json.dumps({"total_unresolved": 5}), encoding="utf-8")

            self.assertEqual(pipeline.unresolved_count(report), 5)
            self.assertEqual(pipeline.unresolved_count(d / "missing.json"), 0)


if __name__ == "__main__":
    unittest.main()
