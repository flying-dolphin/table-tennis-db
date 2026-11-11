import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.anti_bot import DelayConfig, RiskControlTriggered
from lib.checkpoint import CheckpointStore
from scrape_profiles import (
    IncompleteProfileError,
    _bootstrap_profiles_checkpoint_from_orig,
    extract_player_id_from_href,
    extract_profile_info,
    scrape_player_profile,
    validate_scraped_profile,
)


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


class FakeHtmlPage:
    def __init__(self, html: str):
        self._html = html

    def content(self) -> str:
        return self._html


def redesigned_profile_html(year: str) -> str:
    return f"""
    <section class="pp-hero" aria-label="Player">
      <div class="pp-photo">
        <img src="https://wttsimfiles.blob.core.windows.net/wtt-media/photos/400px/121411_Headshot_R_WANG_Manyu.png">
      </div>
      <div class="pp-id">
        <h1 class="pp-name">WANG <span>Manyu</span> <small class="pp-name__id">(ITTF ID #121411)</small></h1>
        <div class="pp-meta">
          <span><span class="pp-flag"><img src="/images/stories/flags/CHN.png" alt="">CHN</span> - CHINA</span>
          <span>Female</span>
          <span>Born 1999 (27)</span>
        </div>
        <div class="pp-meta"><span>Right-hand attack - shakehand</span></div>
      </div>
      <div class="pp-rank">
        <div><small>World ranking</small><b>#1</b><em>Week 46/2026 - 9 Nov 2026</em></div>
        <div><small>Career best</small><b>#1</b><em>Week 38/2026, held 8 weeks</em></div>
        <div><small>History</small><a href="#">Ranking History</a></div>
      </div>
    </section>
    <section class="pp-kpis" data-pp-scope="career" aria-label="Key numbers - career">
      <div class="pp-kpi"><small>Matches</small><b>516</b><span>444 won - 72 lost</span></div>
      <div class="pp-kpi"><small>Win rate</small><b>86.0%</b></div>
      <div class="pp-kpi"><small>Events</small><b>106</b></div>
      <div class="pp-kpi"><small>Titles</small><button type="button"><b>20</b></button><span>WTT 10 - all 20</span></div>
      <div class="pp-kpi"><small>Games won</small><b>74.2%</b><span>1,627 won - 567 lost</span></div>
      <div class="pp-kpi"><small>Points won</small><b>57.5%</b><span>22,577 won - 16,667 lost</span></div>
    </section>
    <section class="pp-kpis" data-pp-scope="{year}" hidden aria-label="Key numbers - {year}">
      <div class="pp-kpi"><small>Matches</small><b>54</b><span>45 won - 9 lost</span></div>
      <div class="pp-kpi"><small>Win rate</small><b>83.3%</b></div>
      <div class="pp-kpi"><small>Events</small><b>11</b></div>
      <div class="pp-kpi"><small>Titles</small><button type="button"><b>3</b></button><span>WTT 2 - all 3</span></div>
      <div class="pp-kpi"><small>Games won</small><b>74.3%</b><span>165 won - 57 lost</span></div>
      <div class="pp-kpi"><small>Points won</small><b>58.1%</b><span>2,333 won - 1,684 lost</span></div>
    </section>
    <section class="pp-card" aria-label="Recent singles matches">
      <div class="pp-mgrid">
        <div class="pp-m">
          <div class="ev"><a href="#">WTT Champions Montpellier 2026</a> - R16</div>
          <div class="op"><span class="pp-mbadge pp-mbadge--l">L</span><a href="#">CHEN Yi</a>
            <span class="pp-flag"><img src="/images/stories/flags/CHN.png" alt="">CHN</span></div>
          <div class="sc"><b>0-3</b> - 11-13 8-11 9-11</div>
        </div>
      </div>
    </section>
    """


class RedesignedProfileExtractionTests(unittest.TestCase):
    def test_extract_player_id_supports_legacy_and_pid_urls(self):
        self.assertEqual(extract_player_id_from_href("/index.php?player_id_raw=121411"), "121411")
        self.assertEqual(extract_player_id_from_href("/../index.php/player-profile?pid=121411"), "121411")
        self.assertIsNone(extract_player_id_from_href("/index.php/player-profile?pid=abc"))

    def test_extracts_profile_from_pp_dom(self):
        player = {
            "player_id": "121411",
            "name": "WANG Manyu",
            "english_name": "WANG Manyu",
            "country_code": "CHN",
            "rank": 1,
            "points": 9265,
            "change": 0,
        }
        profile = extract_profile_info(
            FakeHtmlPage(redesigned_profile_html(str(datetime.now().year))),
            player,
            "https://results.ittf.link/index.php/player-profile?pid=121411",
        )

        validate_scraped_profile(profile, "121411")
        self.assertEqual(profile["name"], "WANG Manyu")
        self.assertEqual(profile["player_id"], "121411")
        self.assertEqual(profile["country_code"], "CHN")
        self.assertEqual(profile["country"], "CHINA")
        self.assertEqual(profile["gender"], "Female")
        self.assertEqual(profile["birth_year"], 1999)
        self.assertEqual(profile["age"], 27)
        self.assertEqual(profile["style"], "right-hand attack (shakehand)")
        self.assertEqual(profile["playing_hand"], "Right")
        self.assertEqual(profile["grip"], "ShakeHand")
        self.assertEqual(profile["current_rank"], 1)
        self.assertEqual(profile["ranking_week"], "Week 46/2026 - 9 Nov 2026")
        self.assertEqual(profile["career_best_rank"], 1)
        self.assertEqual(profile["career_best_month"], "2026-09")
        self.assertEqual(
            profile["career_stats"],
            {
                "events": 106,
                "matches": 516,
                "wins": 444,
                "loses": 72,
                "wtt_senior_titles": 10,
                "all_senior_titles": 20,
                "games": 2194,
                "games_won": 1627,
                "games_lost": 567,
                "points_played": 39244,
                "points_won": 22577,
                "points_lost": 16667,
            },
        )
        self.assertEqual(profile["current_year_stats"]["events"], 11)
        self.assertEqual(profile["current_year_stats"]["matches"], 54)
        self.assertEqual(profile["current_year_stats"]["wins"], 45)
        self.assertEqual(profile["current_year_stats"]["loses"], 9)
        self.assertEqual(profile["current_year_stats"]["games"], 222)
        self.assertEqual(profile["current_year_stats"]["points_played"], 4017)
        self.assertEqual(profile["current_year_stats"]["wtt_senior_titles"], 2)
        self.assertEqual(profile["current_year_stats"]["all_senior_titles"], 3)
        self.assertEqual(profile["recent_matches_count"], 1)
        self.assertEqual(
            profile["recent_matches"][0],
            {
                "event": "WTT Champions Montpellier 2026",
                "player": "WANG Manyu",
                "player_country": "CHN",
                "opponent": "CHEN Yi",
                "opponent_country": "CHN",
                "stage": "R16",
                "score": "0-3 - 11-13 8-11 9-11",
                "result": "LOST",
            },
        )

    def test_raises_when_redesigned_hero_is_missing(self):
        with self.assertRaises(IncompleteProfileError) as raised:
            extract_profile_info(
                FakeHtmlPage("<html><body><main>login</main></body></html>"),
                {"player_id": "121411", "name": "WANG Manyu"},
                "https://results.ittf.link/index.php/player-profile?pid=121411",
            )
        self.assertIn("profile hero not found", str(raised.exception))


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
