import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.anti_bot import DelayConfig
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
                patch("scrape_profiles.extract_profile_info", return_value={"player_id": "136712", "name": "Test Player"}),
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


if __name__ == "__main__":
    unittest.main()
