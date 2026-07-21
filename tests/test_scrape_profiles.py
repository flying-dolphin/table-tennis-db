import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.anti_bot import DelayConfig, RiskControlTriggered
from lib.checkpoint import CheckpointStore
from scrape_profiles import scrape_player_profile


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
                    return_value={"player_id": "136712", "name": "Test Player", "gender": "Male"},
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
            complete = {"player_id": "136712", "name": "Test Player", "gender": "Male"}

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
