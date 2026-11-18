import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scrape_matches_from_events as scraper


def stats_data():
    return {
        "n": {"1": "TAULER Norbert", "2": "GUNDUZ Ibrahim", "3": "PARTNER One", "4": "PARTNER Two"},
        "m": {"10667994": {
            "e": "MS", "r": "Preliminary", "k": 100, "gn": 0,
            "a": [[1, "ESP"]], "x": [[2, "TUR"]],
            "ra": 2, "rx": 3, "w": "X",
            "g": [[2, 11], [4, 11], [14, 12], [11, 9], [4, 11]],
        }},
    }


class EventStatsTests(unittest.TestCase):
    def test_new_and_legacy_event_ids(self):
        self.assertEqual(scraper.event_id_from_url("https://results.ittf.link/index.php/event-stats?tid=3257"), "3257")
        self.assertEqual(scraper.event_id_from_url("https://results.ittf.link/index.php/event-matches/list/68?abc=460"), "460")

    def test_preserves_original_sides_scores_and_winner(self):
        match = scraper.parse_event_stats_data(stats_data(), "Event 2026")[0]
        self.assertEqual(match["source_row_id"], "10667994")
        self.assertEqual(match["side_a"], ["TAULER Norbert (ESP)"])
        self.assertEqual(match["side_b"], ["GUNDUZ Ibrahim (TUR)"])
        self.assertEqual(match["match_score"], "2-3")
        self.assertEqual(match["games"][0], {"player": 2, "opponent": 11})
        self.assertEqual(match["games_display"][0], "2:11")
        self.assertEqual(match["winner"], "GUNDUZ Ibrahim (TUR)")
        self.assertEqual(match["round"], "Preliminary")
        self.assertEqual(match["stage"], "")
        self.assertEqual(match["event"], "Event 2026")

    def test_doubles_keep_both_players_per_side(self):
        data = stats_data()
        m = data["m"]["10667994"]
        m.update(e="XD", a=[[1, "ESP"], [3, "ESP"]], x=[[2, "TUR"], [4, "TUR"]])
        match = scraper.parse_event_stats_data(data, "Event 2026")[0]
        self.assertEqual(len(match["side_a"]), 2)
        self.assertEqual(len(match["side_b"]), 2)
        self.assertEqual(match["winner"], "GUNDUZ Ibrahim (TUR) / PARTNER Two (TUR)")

    def test_rejects_missing_names_or_incomplete_match_data(self):
        for field in ("a", "ra", "g", "w"):
            data = stats_data()
            del data["m"]["10667994"][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                scraper.parse_event_stats_data(data, "Event 2026")
        data = stats_data()
        del data["n"]["1"]
        with self.assertRaises(ValueError):
            scraper.parse_event_stats_data(data, "Event 2026")

    def test_empty_matches_are_valid_but_missing_map_is_not(self):
        data = stats_data()
        data["m"] = {}
        self.assertEqual(scraper.parse_event_stats_data(data, "Event 2026"), [])
        with self.assertRaises(ValueError):
            scraper.parse_event_stats_data({}, "Event 2026")

    def test_rejects_inconsistent_winner_and_game_scores(self):
        for change in ({"w": "A"}, {"ra": 1}, {"g": [[11, 2]]}):
            data = stats_data()
            data["m"]["10667994"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                scraper.parse_event_stats_data(data, "Event 2026")

    def test_stats_path_bypasses_legacy_pagination_and_checks_total(self):
        page = MagicMock()
        page.url = "https://results.ittf.link/index.php/event-stats?tid=3257"
        page.locator.return_value.count.return_value = 1
        page.locator.return_value.first.inner_text.return_value = "1"
        page.locator.return_value.first.text_content.return_value = json.dumps(stats_data())
        with tempfile.TemporaryDirectory() as directory, patch.object(scraper, "guarded_goto"), patch.object(
            scraper, "get_event_title_from_page", return_value="Event 2026"
        ), patch.object(scraper, "read_initial_page_info") as legacy:
            payload = scraper.scrape_event_url(page, page.url, Path(directory), scraper.DelayConfig(0, 0, 0, 0), 500)
            self.assertEqual(len(payload["matches"]), 1)
            self.assertTrue(Path(payload["output_file"]).exists())
            legacy.assert_not_called()
            page.locator.return_value.first.inner_text.return_value = "2"
            with patch.object(scraper, "DEFAULT_PROBLEMATIC_OUTPUT_DIR", directory), self.assertRaisesRegex(RuntimeError, "Record count mismatch"):
                scraper.scrape_event_url(page, page.url, Path(directory), scraper.DelayConfig(0, 0, 0, 0), 500)


if __name__ == "__main__":
    unittest.main()
