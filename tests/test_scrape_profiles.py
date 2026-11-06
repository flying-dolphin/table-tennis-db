import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.anti_bot import DelayConfig, RiskControlTriggered
from lib.checkpoint import CheckpointStore
from scrape_profiles import IncompleteProfileError, _bootstrap_profiles_checkpoint_from_orig, scrape_player_profile


def complete_profile():
    career_fields = ("events", "matches", "wins", "loses", "wtt_senior_titles", "all_senior_titles")
    year_fields = career_fields + ("games", "games_won", "games_lost", "points_played", "points_won", "points_lost")
    return {
        "player_id": "136712", "name": "Test Player", "gender": "Male", "country_code": "CHN",
        "career_stats": dict.fromkeys(career_fields, 0),
        "current_year_stats": dict.fromkeys(year_fields, 0),
        "recent_matches": [], "recent_matches_count": 0,
    }


class FakePage:
    def wait_for_load_state(self, *_args, **_kwargs):
        return None


class ScrapePlayerProfileTests(unittest.TestCase):
    def test_saves_profile_json_without_writing_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            player = {
                "player_id": "136712",
                "name": "Test Player",
                "english_name": "Test Player",
                "profile_url": "https://results.ittf.link/index.php/player-profile/list/60?x=1",
            }
            with (
                patch("scrape_profiles.guarded_goto"),
                patch(
                    "scrape_profiles.extract_profile_info",
                    return_value=complete_profile(),
                ),
                patch("scrape_profiles.download_player_avatar", return_value=None),
                patch("scrape_profiles.save_json") as save_profile_json,
            ):
                result = scrape_player_profile(
                    FakePage(),
                    str(player["profile_url"]),
                    player,
                    DelayConfig(
                        min_request_sec=0,
                        max_request_sec=0,
                        min_player_gap_sec=0,
                        max_player_gap_sec=0,
                    ),
                    tmp / "profiles" / "orig",
                    tmp / "avatars",
                )

        self.assertEqual(result[0]["player_id"], "136712")
        self.assertTrue(result[1])
        save_profile_json.assert_called_once()

    def test_retries_incomplete_profile_before_saving(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            player = {
                "player_id": "136712",
                "name": "Test Player",
                "profile_url": "https://results.ittf.link/profile?id=136712",
            }
            incomplete = {"player_id": "136712", "name": "Test Player"}
            complete = complete_profile()

            with (
                patch("scrape_profiles.guarded_goto") as goto,
                patch("scrape_profiles.extract_profile_info", side_effect=[incomplete, complete]) as extract,
                patch("scrape_profiles.download_player_avatar", return_value=None),
                patch("scrape_profiles.save_json") as save_profile_json,
            ):
                result = scrape_player_profile(
                    FakePage(),
                    str(player["profile_url"]),
                    player,
                    DelayConfig(0, 0, 0, 0),
                    tmp / "profiles" / "orig",
                    tmp / "avatars",
                )

        self.assertEqual(result, (complete, True))
        self.assertEqual(goto.call_count, 2)
        self.assertEqual(extract.call_count, 2)
        save_profile_json.assert_called_once_with(
            tmp / "profiles" / "orig" / "player_136712_Test_Player.json",
            complete,
        )

    def test_does_not_save_or_complete_checkpoint_for_incomplete_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            checkpoint = CheckpointStore(tmp / "checkpoint.json")
            player = {
                "player_id": "136712",
                "name": "Test Player",
                "profile_url": "https://results.ittf.link/profile?id=136712",
            }
            incomplete = {"player_id": "136712", "name": "Test Player"}

            with (
                patch("scrape_profiles.guarded_goto") as goto,
                patch("scrape_profiles.extract_profile_info", return_value=incomplete) as extract,
                patch("scrape_profiles.download_player_avatar", return_value=None),
                patch("scrape_profiles.save_json") as save_profile_json,
            ):
                result = scrape_player_profile(
                    FakePage(),
                    str(player["profile_url"]),
                    player,
                    DelayConfig(0, 0, 0, 0),
                    tmp / "profiles" / "orig",
                    tmp / "avatars",
                    checkpoint=checkpoint,
                    category="women",
                )

        self.assertEqual(result, (None, False))
        self.assertEqual(goto.call_count, 2)
        self.assertEqual(extract.call_count, 2)
        save_profile_json.assert_not_called()
        key = "profile|women|player:136712|scrape"
        self.assertNotIn(key, checkpoint.data["completed"])
        self.assertIn("missing required fields: gender", checkpoint.data["failed"][key]["reason"])

    def test_invalid_statistics_preserve_previous_file_and_clear_done_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            orig = tmp / "player_136712_Test_Player.json"
            previous = json.dumps(complete_profile())
            orig.write_text(previous)
            checkpoint = CheckpointStore(tmp / "checkpoint.json")
            key = "profile|women|player:136712|scrape"
            checkpoint.mark_done(key)
            invalid = complete_profile()
            invalid["current_year_stats"] = {}
            with (
                patch("scrape_profiles.guarded_goto") as goto,
                patch("scrape_profiles.extract_profile_info", return_value=invalid),
                patch("scrape_profiles.download_player_avatar") as avatar,
            ):
                result = scrape_player_profile(
                    FakePage(), "https://example.test/profile", complete_profile(), DelayConfig(0, 0, 0, 0),
                    tmp, tmp / "avatars", checkpoint=checkpoint, category="women",
                )
            self.assertEqual(result, (None, False))
            self.assertEqual(goto.call_count, 2)
            self.assertEqual(orig.read_text(), previous)
            avatar.assert_not_called()
            self.assertFalse(checkpoint.is_done(key))
            self.assertIn("current_year_stats.events", checkpoint.data["failed"][key]["reason"])

    def test_resume_revalidates_cached_profile_before_skipping(self):
        for valid_cache in (False, True):
            with self.subTest(valid_cache=valid_cache), tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                cached = complete_profile()
                if not valid_cache:
                    cached["current_year_stats"] = {}
                (tmp / "player_136712_Test_Player.json").write_text(json.dumps(cached))
                checkpoint = CheckpointStore(tmp / "checkpoint.json")
                checkpoint.mark_done("profile|women|player:136712|scrape")
                with (
                    patch("scrape_profiles.guarded_goto") as goto,
                    patch("scrape_profiles.extract_profile_info", return_value=complete_profile()),
                    patch("scrape_profiles.download_player_avatar", return_value=None),
                    patch("scrape_profiles.save_json") as save,
                ):
                    result = scrape_player_profile(
                        FakePage(), "https://example.test/profile", complete_profile(), DelayConfig(0, 0, 0, 0),
                        tmp, tmp / "avatars", checkpoint=checkpoint, category="women", resume=True,
                    )
                self.assertEqual(result, (complete_profile(), not valid_cache))
                self.assertEqual(goto.call_count, 0 if valid_cache else 1)
                self.assertEqual(save.call_count, 0 if valid_cache else 1)

    def test_extraction_failure_is_retried_before_saving(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("scrape_profiles.guarded_goto") as goto,
                patch("scrape_profiles.extract_profile_info", side_effect=[
                    IncompleteProfileError("incomplete recent matches"), complete_profile(),
                ]),
                patch("scrape_profiles.download_player_avatar", return_value=None),
                patch("scrape_profiles.save_json") as save,
            ):
                result = scrape_player_profile(
                    FakePage(), "https://example.test/profile", complete_profile(), DelayConfig(0, 0, 0, 0),
                    Path(tmpdir), Path(tmpdir) / "avatars",
                )
            self.assertEqual(result, (complete_profile(), True))
            self.assertEqual(goto.call_count, 2)
            save.assert_called_once()

    def test_bootstrap_ignores_incomplete_profile_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            invalid = complete_profile()
            invalid["career_stats"] = {}
            (tmp / "player_136712_Test_Player.json").write_text(json.dumps(invalid))
            checkpoint = CheckpointStore(tmp / "checkpoint.json")
            _bootstrap_profiles_checkpoint_from_orig(checkpoint, "women", tmp)
            self.assertFalse(checkpoint.has_any_completed())

    def test_profile_429_is_not_swallowed_or_retried(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            checkpoint = CheckpointStore(tmp / "checkpoint.json")
            player = {
                "player_id": "136712",
                "name": "Test Player",
                "profile_url": "https://results.ittf.link/profile?id=136712",
            }
            page = FakePage()
            page.url = "https://results.ittf.link/ranking"
            risk = RiskControlTriggered("HTTP 429", status=429, retry_after_sec=420)

            with patch("scrape_profiles.guarded_goto", side_effect=risk) as goto:
                with self.assertRaises(RiskControlTriggered) as raised:
                    scrape_player_profile(
                        page,
                        str(player["profile_url"]),
                        player,
                        DelayConfig(0, 0, 0, 0),
                        tmp / "profiles" / "orig",
                        tmp / "avatars",
                        checkpoint=checkpoint,
                        category="women",
                    )

        self.assertEqual(raised.exception.retry_after_sec, 420)
        self.assertEqual(goto.call_count, 1)
        self.assertEqual(goto.call_args.kwargs["retries"], 0)
        self.assertFalse(goto.call_args.kwargs["retry_risk_responses"])
        failed = checkpoint.data["failed"]["profile|women|player:136712|scrape"]
        self.assertEqual(failed["meta"]["retry_after_sec"], 420)


if __name__ == "__main__":
    unittest.main()
