import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from merge_ranking_ids import merge_rankings_with_results_ids


class MergeRankingIdsTests(unittest.TestCase):
    def test_uses_name_country_and_points_to_disambiguate_duplicate_names(self):
        weekly_rows = [
            {"rank": 140, "name": "LEE Daeun", "country_code": "KOR", "points": 188},
            {"rank": 233, "name": "LEE Daeun", "country_code": "KOR", "points": 79},
        ]
        results_rows = [
            {
                "rank": 139,
                "name": "LEE Daeun",
                "country_code": "KOR",
                "points": 79,
                "player_id": "222",
                "profile_url": "https://results.ittf.link/player/222",
            },
            {
                "rank": 141,
                "name": "LEE Daeun",
                "country_code": "KOR",
                "points": 188,
                "player_id": "111",
                "profile_url": "https://results.ittf.link/player/111",
            },
        ]

        merged, unresolved = merge_rankings_with_results_ids(weekly_rows, results_rows)

        self.assertEqual(unresolved, [])
        self.assertEqual(merged[0]["player_id"], "111")
        self.assertEqual(merged[0]["id_resolution_status"], "matched")
        self.assertEqual(merged[1]["player_id"], "222")

    def test_marks_ambiguous_when_multiple_candidates_have_same_identity_fields(self):
        weekly_rows = [{"rank": 10, "name": "SAME Name", "country_code": "AAA", "points": 100}]
        results_rows = [
            {"rank": 9, "name": "SAME Name", "country_code": "AAA", "points": 100, "player_id": "1"},
            {"rank": 11, "name": "SAME Name", "country_code": "AAA", "points": 100, "player_id": "2"},
        ]

        merged, unresolved = merge_rankings_with_results_ids(weekly_rows, results_rows)

        self.assertEqual(merged[0]["id_resolution_status"], "ambiguous")
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["reason"], "ambiguous")

    def test_disambiguates_duplicate_weekly_names_when_results_name_has_birth_year(self):
        weekly_rows = [
            {"rank": 775, "name": "STOJANOVSKA Sara", "country_code": "MKD", "points": 2},
            {"rank": 830, "name": "STOJANOVSKA Sara", "country_code": "MKD", "points": 2},
        ]
        results_rows = [
            {
                "rank": 775,
                "name": "STOJANOVSKA Sara (2008)",
                "country_code": "MKD",
                "points": 2,
                "player_id": "145463",
                "profile_url": "https://results.ittf.link/player/145463",
            },
            {
                "rank": 830,
                "name": "STOJANOVSKA Sara",
                "country_code": "MKD",
                "points": 2,
                "player_id": "145296",
                "profile_url": "https://results.ittf.link/player/145296",
            },
        ]

        merged, unresolved = merge_rankings_with_results_ids(weekly_rows, results_rows)

        self.assertEqual(unresolved, [])
        self.assertEqual(merged[0]["player_id"], "145463")
        self.assertEqual(merged[0]["results_rank"], 775)
        self.assertEqual(merged[1]["player_id"], "145296")
        self.assertEqual(merged[1]["results_rank"], 830)


if __name__ == "__main__":
    unittest.main()
