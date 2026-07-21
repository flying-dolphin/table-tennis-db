import sys
import tempfile
import unittest
from datetime import datetime
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from run_ranking_profile import is_due_window
import run_ranking_profile


class DueWindowTests(unittest.TestCase):
    def test_accepts_anchor_cycle_at_or_after_21_00(self):
        self.assertTrue(is_due_window(datetime(2026, 6, 8, 21, 0)))
        self.assertTrue(is_due_window(datetime(2026, 6, 15, 21, 30)))

    def test_rejects_anchor_cycle_before_21_00(self):
        self.assertFalse(is_due_window(datetime(2026, 6, 15, 20, 59)))

    def test_rejects_non_anchor_cycle_days(self):
        self.assertFalse(is_due_window(datetime(2026, 6, 16, 21, 0)))


class RunRankingProfileTests(unittest.TestCase):
    def test_latest_ranking_file_ignores_derived_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            original = output_dir / "women_singles_top1000_week30.json"
            original.write_text("{}", encoding="utf-8")
            (output_dir / "women_singles_top1000_week30_with_ids.json").write_text("{}", encoding="utf-8")
            (output_dir / "women_singles_top1000_week30_with_ids_unresolved.json").write_text(
                "{}",
                encoding="utf-8",
            )

            selected = run_ranking_profile.latest_ranking_file(output_dir, top=1000)

        self.assertEqual(selected, original)

    def test_passes_cdp_only_to_weekly_ranking_scraper(self):
        captured_weekly_args = None
        captured_results_args = None

        def fake_weekly(args):
            nonlocal captured_weekly_args
            captured_weekly_args = args
            return 0

        def fake_results(args):
            nonlocal captured_results_args
            captured_results_args = args
            return 0

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            weekly_file = tmp / "women_singles_top10_week24.json"
            results_file = tmp / "results_women_top10_20260616.json"

            args = Namespace(
                check_due=False,
                top=10,
                cdp_port=9223,
                headless=False,
                slow_mo=100,
                weekly_output_dir=str(tmp / "weekly"),
                results_output_dir=str(tmp / "results"),
                weekly_checkpoint=str(tmp / "weekly_checkpoint.json"),
                force=False,
                resume=False,
                category="women",
                results_checkpoint=str(tmp / "results_checkpoint.json"),
                storage_state=str(tmp / "state.json"),
                profile_dir=str(tmp / "profiles"),
                avatar_dir=str(tmp / "avatars"),
                ranking_only=True,
                cdp_only=True,
                min_delay=2.0,
                max_delay=5.0,
                min_player_gap=2.0,
                max_player_gap=5.0,
                merged_output=None,
                unresolved_output=None,
                aliases="scripts/data/player_name_aliases.json",
                db_path=str(tmp / "ittf.db"),
            )

            with (
                patch.object(run_ranking_profile, "run_weekly_wp", side_effect=fake_weekly),
                patch.object(run_ranking_profile, "run_results", side_effect=fake_results),
                patch.object(run_ranking_profile, "latest_ranking_file", return_value=weekly_file),
                patch.object(run_ranking_profile, "latest_results_file", return_value=results_file),
                patch.object(run_ranking_profile, "run_merge", return_value=0),
            ):
                rc = run_ranking_profile.run(args)

        self.assertEqual(rc, 0)
        self.assertIsNotNone(captured_weekly_args)
        self.assertTrue(captured_weekly_args.cdp_only)
        self.assertIsNotNone(captured_results_args)
        self.assertEqual(captured_results_args.weekly_file, str(weekly_file))
        self.assertEqual(captured_results_args.db_path, str(tmp / "ittf.db"))
        self.assertEqual(captured_results_args.aliases, "scripts/data/player_name_aliases.json")

    def test_resume_reuses_existing_weekly_ranking_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            weekly_dir = tmp / "weekly"
            weekly_dir.mkdir()
            weekly_file = weekly_dir / "women_singles_top10_week24.json"
            weekly_file.write_text("{}", encoding="utf-8")
            results_file = tmp / "results_women_top10_20260616.json"

            args = Namespace(
                check_due=False,
                top=10,
                cdp_port=9223,
                cdp_only=True,
                headless=False,
                slow_mo=100,
                weekly_output_dir=str(weekly_dir),
                results_output_dir=str(tmp / "results"),
                weekly_checkpoint=str(tmp / "weekly_checkpoint.json"),
                force=False,
                resume=True,
                category="women",
                results_checkpoint=str(tmp / "results_checkpoint.json"),
                storage_state=str(tmp / "state.json"),
                profile_dir=str(tmp / "profiles"),
                avatar_dir=str(tmp / "avatars"),
                ranking_only=True,
                min_delay=2.0,
                max_delay=5.0,
                min_player_gap=2.0,
                max_player_gap=5.0,
                merged_output=None,
                unresolved_output=None,
                aliases="scripts/data/player_name_aliases.json",
                db_path=str(tmp / "ittf.db"),
            )

            with (
                patch.object(run_ranking_profile, "run_weekly_wp") as weekly,
                patch.object(run_ranking_profile, "run_results", return_value=0),
                patch.object(run_ranking_profile, "latest_results_file", return_value=results_file),
                patch.object(run_ranking_profile, "run_merge", return_value=0),
            ):
                rc = run_ranking_profile.run(args)

        self.assertEqual(rc, 0)
        weekly.assert_not_called()


if __name__ == "__main__":
    unittest.main()
