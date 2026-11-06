import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

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


class HtmlLocator:
    """Small DOM adapter: exercises production extraction using nested HTML."""

    def __init__(self, nodes):
        self.nodes = nodes

    def locator(self, selector):
        return HtmlLocator([child for node in self.nodes for child in node.select(selector)])

    def count(self):
        return len(self.nodes)

    def nth(self, index):
        return HtmlLocator([self.nodes[index]])

    @property
    def first(self):
        return self.nth(0)

    def inner_text(self):
        node = copy.deepcopy(self.nodes[0])
        for hidden in node.select("dialog:not([open]), style, script"):
            hidden.decompose()
        return node.get_text("\n", strip=True)

    def all_inner_texts(self):
        return [self.nth(i).inner_text() for i in range(self.count())]


def profile_page(recent="", year_text=None):
    data = complete_profile()
    career = "\n".join(f"{label}: {data['career_stats'][key]}" for label, key in [
        ("Events", "events"), ("Matches", "matches"), ("Wins", "wins"), ("Loses", "loses"),
        ("WTT Senior Titles", "wtt_senior_titles"), ("All Senior Titles", "all_senior_titles")])
    year_text = year_text if year_text is not None else """Events: 11
Matches: 54
Wins: 45
Loses: 9
Games: 222 (W: 165 , L: 57)
Points: 4017 (W: 2333 , L: 1684)
WTT Senior Titles: 2
All Senior Titles: 3"""
    soup = BeautifulSoup(f"""<body><main><table>
<thead><tr><th></th><th>Name</th><th>Profile</th><th>Career *</th><th>Current Year *</th></tr></thead>
<tbody><tr><td></td><td>WANG Manyu (#121411)</td>
<td>CHINA\nGender: Female\nAge: 27</td><td>{career}
<dialog><table><tr><td>China Smash 2026</td><td>WS</td></tr></table></dialog></td>
<td>{year_text}</td></tr></tbody></table>
<div>Recent Singles Matches:\n{recent}\nRecent Results in Singles Matches in WTT Events:</div>
</main></body>""", "html.parser")
    return HtmlLocator([soup])


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

    def test_nested_title_table_does_not_replace_year_statistics(self):
        data = extract_profile_info(profile_page(), complete_profile(), "https://example.test/profile")
        self.assertEqual(data["current_year_stats"]["events"], 11)
        self.assertEqual(data["current_year_stats"]["matches"], 54)
        validate_scraped_profile(data, "121411")

    def test_recent_matches_accept_all_event_prefixes_and_unicode_names(self):
        recent = "\n\n".join(
            f"{event}\n{left} (CHN) vs {right} (GER)\nWS Main Draw - R32 | 3 - 1\nResult: WON"
            for event, left, right in [
                ("WTT Champions Montpellier 2026", "WANG Manyu", "MITTELHAM Nina"),
                ("China Smash 2026", "WANG Manyu", "O’BRIEN Zoë"),
                ("Asian Games Aichi-Nagoya 2026", "DIAZ Adriana", "WANG Manyu"),
                ("Europe Smash - Sweden 2026", "WANG Manyu", "HAN Ying"),
            ]
        )
        data = extract_profile_info(profile_page(recent), complete_profile(), "https://example.test/profile")
        self.assertEqual(len(data.get("recent_matches", [])), 4)
        self.assertEqual(data["recent_matches"][1]["event"], "China Smash 2026")
        self.assertEqual(data["recent_matches"][1]["opponent"], "O’BRIEN Zoë")
        self.assertEqual(data["recent_matches"][2]["player"], "DIAZ Adriana")
        self.assertEqual(data["recent_matches_count"], 4)

    def test_unparsed_recent_match_is_rejected(self):
        recent = "China Smash 2026\nchanged match format\nResult: LOST"
        with self.assertRaisesRegex(IncompleteProfileError, "recent"):
            data = extract_profile_info(profile_page(recent), complete_profile(), "https://example.test/profile")
            validate_scraped_profile(data, "121411")

    def test_truncated_recent_match_is_rejected_even_after_a_complete_match(self):
        recent = """China Smash 2026
WANG Manyu (CHN) vs HAN Ying (GER)
WS Main Draw - R32 | 3 - 1
Result: WON
Asian Games 2026
WANG Manyu (CHN) vs HAN Ying (GER)
WS Main Draw - R16 | 3 - 0"""
        with self.assertRaisesRegex(IncompleteProfileError, "recent"):
            extract_profile_info(profile_page(recent), complete_profile(), "https://example.test/profile")

    def test_player_id_substring_cannot_match_wrong_source_player(self):
        player = complete_profile()
        player["player_id"] = "12141"
        with self.assertRaisesRegex(IncompleteProfileError, "profile row not found"):
            extract_profile_info(profile_page(), player, "https://example.test/profile")

    def test_country_label_can_be_an_existing_country_code(self):
        page = profile_page()
        label = page.nodes[0].find(string=lambda text: text and text.startswith("CHINA\n"))
        label.replace_with(str(label).replace("CHINA", "USA", 1))
        player = complete_profile()
        player.pop("country_code")
        data = extract_profile_info(page, player, "https://example.test/profile", {"UNITED STATES": "USA"})
        self.assertEqual(data["country_code"], "USA")
        self.assertEqual(data["country"], "UNITED STATES")
        validate_scraped_profile(data, "121411")

    def test_country_label_can_contain_punctuation(self):
        page = profile_page()
        label = page.nodes[0].find(string=lambda text: text and text.startswith("CHINA\n"))
        label.replace_with(str(label).replace("CHINA", "HONG KONG, CHINA", 1))
        player = complete_profile()
        player.pop("country_code")
        data = extract_profile_info(page, player, "https://example.test/profile", {"HONG KONG, CHINA": "HKG"})
        self.assertEqual(data["country_code"], "HKG")
        validate_scraped_profile(data, "121411")

    def test_batch_file_preserves_known_country_and_accepts_legacy_two_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "players.txt"
            path.write_text("131231,ABRAAMIAN Elizabet,rus\n121411,WANG Manyu\n")
            self.assertEqual(load_player_file(str(path)), [
                {"player_id": "131231", "player_name": "ABRAAMIAN Elizabet", "country_code": "RUS"},
                {"player_id": "121411", "player_name": "WANG Manyu"},
            ])

    def test_known_country_is_retained_when_reverse_map_lacks_it(self):
        page = profile_page()
        label = page.nodes[0].find(string=lambda text: text and text.startswith("CHINA\n"))
        label.replace_with(str(label).replace("CHINA", "RUSSIA", 1))
        player = complete_profile()
        player["country_code"] = "RUS"
        data = extract_profile_info(page, player, "https://example.test/profile", {"CHINA": "CHN"})
        self.assertEqual(data["country_code"], "RUS")
        self.assertEqual(data["country"], "RUSSIA")
        validate_scraped_profile(data, "121411")

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
