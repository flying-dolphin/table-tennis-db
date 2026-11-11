import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from scrape_profiles import IncompleteProfileError, extract_profile_info, load_player_file, validate_scraped_profile
from scrape_profiles_from_search import _load_existing_orig_keys, save_player_to_players_table


def complete_profile():
    return {
        "player_id": "121411", "name": "WANG Manyu", "gender": "Female", "country_code": "CHN",
        "career_stats": dict(events=106, matches=517, wins=444, loses=73,
                             wtt_senior_titles=10, all_senior_titles=20),
        "current_year_stats": dict(events=11, matches=54, wins=45, loses=9,
                                   games=222, games_won=165, games_lost=57,
                                   points_played=4017, points_won=2333, points_lost=1684,
                                   wtt_senior_titles=2, all_senior_titles=3),
        "recent_matches": [], "recent_matches_count": 0,
    }


class FakeHtmlPage:
    def __init__(self, html: str):
        self._html = html

    def content(self) -> str:
        return self._html


def default_recent_matches_html() -> str:
    return """
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


def profile_page(*, year: str | None = None, recent_matches: str | None = None) -> FakeHtmlPage:
    year = year or str(datetime.now().year)
    recent_matches = recent_matches if recent_matches is not None else default_recent_matches_html()
    return FakeHtmlPage(f"""
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
    {recent_matches}
    """)


class ProfileValidationTests(unittest.TestCase):
    def test_empty_statistics_are_rejected(self):
        for block in ("career_stats", "current_year_stats"):
            with self.subTest(block=block):
                data = complete_profile()
                data[block] = {}
                with self.assertRaisesRegex(IncompleteProfileError, block):
                    validate_scraped_profile(data, "121411")

    def test_missing_or_invalid_stat_is_rejected(self):
        for value in (None, -1, "11", True, 1.5):
            with self.subTest(value=value):
                data = complete_profile()
                data["current_year_stats"]["events"] = value
                with self.assertRaisesRegex(IncompleteProfileError, "current_year_stats.events"):
                    validate_scraped_profile(data, "121411")
        data = complete_profile()
        del data["current_year_stats"]["games_lost"]
        with self.assertRaisesRegex(IncompleteProfileError, "games_lost"):
            validate_scraped_profile(data, "121411")

    def test_real_zero_and_optional_personal_fields_are_allowed(self):
        data = complete_profile()
        for block in ("career_stats", "current_year_stats"):
            data[block] = dict.fromkeys(data[block], 0)
        validate_scraped_profile(data, "121411")

    def test_source_match_total_need_not_equal_wins_plus_losses(self):
        data = complete_profile()
        data["career_stats"]["matches"] += 1
        validate_scraped_profile(data, "121411")

    def test_recent_match_count_must_match_source(self):
        data = complete_profile()
        data["recent_matches_count"] = 6
        with self.assertRaisesRegex(IncompleteProfileError, "recent"):
            validate_scraped_profile(data, "121411")

    def test_legacy_cache_without_source_count_requires_rescraping(self):
        data = complete_profile()
        del data["recent_matches_count"]
        with self.assertRaisesRegex(IncompleteProfileError, "recent_matches_count"):
            validate_scraped_profile(data, "121411")


class RedesignedProfileExtractionTests(unittest.TestCase):
    def test_extracts_career_and_current_year_kpis(self):
        data = extract_profile_info(profile_page(), complete_profile(), "https://example.test/profile")

        self.assertEqual(data["current_year_stats"]["events"], 11)
        self.assertEqual(data["current_year_stats"]["matches"], 54)
        self.assertEqual(data["current_year_stats"]["games"], 222)
        self.assertEqual(data["current_year_stats"]["points_played"], 4017)
        self.assertEqual(data["current_year_stats"]["wtt_senior_titles"], 2)
        self.assertEqual(data["career_stats"]["matches"], 516)
        self.assertEqual(data["career_stats"]["wins"], 444)
        self.assertEqual(data["career_stats"]["loses"], 72)
        self.assertEqual(data["career_stats"]["all_senior_titles"], 20)
        validate_scraped_profile(data, "121411")

    def test_extracts_hero_country_style_and_ranking(self):
        data = extract_profile_info(profile_page(), complete_profile(), "https://example.test/profile")

        self.assertEqual(data["player_id"], "121411")
        self.assertEqual(data["name"], "WANG Manyu")
        self.assertEqual(data["country_code"], "CHN")
        self.assertEqual(data["country"], "CHINA")
        self.assertEqual(data["gender"], "Female")
        self.assertEqual(data["birth_year"], 1999)
        self.assertEqual(data["age"], 27)
        self.assertEqual(data["style"], "right-hand attack (shakehand)")
        self.assertEqual(data["playing_hand"], "Right")
        self.assertEqual(data["grip"], "ShakeHand")
        self.assertEqual(data["current_rank"], 1)
        self.assertEqual(data["ranking_week"], "Week 46/2026 - 9 Nov 2026")
        self.assertEqual(data["career_best_rank"], 1)
        self.assertEqual(data["career_best_month"], "2026-09")

    def test_recent_matches_accept_unicode_names_and_event_hyphens(self):
        recent = """
        <section class="pp-card"><div class="pp-mgrid">
          <div class="pp-m">
            <div class="ev"><a>Europe Smash - Sweden 2026</a> - R32</div>
            <div class="op"><span class="pp-mbadge pp-mbadge--w">W</span><a>O’BRIEN Zoë</a>
              <span class="pp-flag"><img src="/images/stories/flags/GER.png" alt="">GER</span></div>
            <div class="sc"><b>3-1</b> - 11-9 8-11 11-7 11-5</div>
          </div>
          <div class="pp-m">
            <div class="ev"><a>China Smash 2026</a> - F</div>
            <div class="op"><span class="pp-mbadge pp-mbadge--l">L</span><a>HAN Ying</a>
              <span class="pp-flag"><img src="/images/stories/flags/GER.png" alt="">GER</span></div>
            <div class="sc"><b>2-4</b> - 11-9 8-11 11-7 11-5 9-11 7-11</div>
          </div>
        </div></section>
        """
        data = extract_profile_info(
            profile_page(recent_matches=recent), complete_profile(), "https://example.test/profile"
        )

        self.assertEqual(data["recent_matches_count"], 2)
        self.assertEqual(data["recent_matches"][0]["event"], "Europe Smash - Sweden 2026")
        self.assertEqual(data["recent_matches"][0]["stage"], "R32")
        self.assertEqual(data["recent_matches"][0]["opponent"], "O’BRIEN Zoë")
        self.assertEqual(data["recent_matches"][0]["result"], "WON")
        self.assertEqual(data["recent_matches"][1]["event"], "China Smash 2026")
        self.assertEqual(data["recent_matches"][1]["stage"], "F")
        self.assertEqual(data["recent_matches"][1]["result"], "LOST")
        validate_scraped_profile(data, "121411")

    def test_team_tag_is_used_as_recent_match_stage(self):
        recent = """
        <section class="pp-card"><div class="pp-mgrid">
          <div class="pp-m">
            <div class="ev"><a>Asian Games Aichi-Nagoya 2026</a> <span class="pp-tag">Team</span></div>
            <div class="op"><span class="pp-mbadge pp-mbadge--l">L</span><a>HARIMOTO Tomokazu</a>
              <span class="pp-flag"><img src="/images/stories/flags/JPN.png" alt="">JPN</span></div>
            <div class="sc"><b>0-3</b> - 7-11 4-11 9-11</div>
          </div>
        </div></section>
        """
        data = extract_profile_info(
            profile_page(recent_matches=recent), complete_profile(), "https://example.test/profile"
        )

        self.assertEqual(data["recent_matches"][0]["event"], "Asian Games Aichi-Nagoya 2026")
        self.assertEqual(data["recent_matches"][0]["stage"], "Team")
        validate_scraped_profile(data, "121411")

    def test_current_year_section_is_optional(self):
        html = profile_page().content()
        year = str(datetime.now().year)
        html = html.replace(f'<section class="pp-kpis" data-pp-scope="{year}"', '<section class="pp-kpis" data-pp-scope="1999"')
        data = extract_profile_info(FakeHtmlPage(html), complete_profile(), "https://example.test/profile")

        self.assertEqual(data["current_year_stats"]["matches"], 0)
        self.assertEqual(data["current_year_stats"]["points_played"], 0)
        validate_scraped_profile(data, "121411")

    def test_player_id_mismatch_is_rejected(self):
        player = complete_profile()
        player["player_id"] = "12141"
        with self.assertRaisesRegex(IncompleteProfileError, "player_id mismatch"):
            extract_profile_info(profile_page(), player, "https://example.test/profile")

    def test_missing_career_kpis_are_rejected(self):
        html = profile_page().content().replace('data-pp-scope="career"', 'data-pp-scope="career-old"')
        with self.assertRaisesRegex(IncompleteProfileError, "career statistics not found"):
            extract_profile_info(FakeHtmlPage(html), complete_profile(), "https://example.test/profile")

    def test_missing_hero_is_rejected(self):
        with self.assertRaisesRegex(IncompleteProfileError, "profile hero not found"):
            extract_profile_info(
                FakeHtmlPage("<html><body><main>login</main></body></html>"),
                complete_profile(),
                "https://example.test/profile",
            )

    def test_batch_file_preserves_known_country_and_accepts_legacy_two_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "players.txt"
            path.write_text("131231,ABRAAMIAN Elizabet,rus\n121411,WANG Manyu\n")
            self.assertEqual(load_player_file(str(path)), [
                {"player_id": "131231", "player_name": "ABRAAMIAN Elizabet", "country_code": "RUS"},
                {"player_id": "121411", "player_name": "WANG Manyu"},
            ])

    def test_search_scraper_does_not_skip_invalid_existing_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "player_121411_WANG_Manyu.json"
            data = complete_profile()
            data["current_year_stats"] = {}
            path.write_text(json.dumps(data))
            self.assertEqual(_load_existing_orig_keys(Path(tmpdir)), set())
            path.write_text(json.dumps(complete_profile()))
            self.assertEqual(len(_load_existing_orig_keys(Path(tmpdir))), 1)

    def test_search_scraper_rejects_missing_statistics_before_opening_database(self):
        data = complete_profile()
        data["current_year_stats"] = {}
        with patch("scrape_profiles_from_search.sqlite3.connect") as connect:
            with self.assertRaisesRegex(IncompleteProfileError, "current_year_stats"):
                save_player_to_players_table(Path("unused.db"), data)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
