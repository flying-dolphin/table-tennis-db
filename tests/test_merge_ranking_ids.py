import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from merge_ranking_ids import merge_payloads, merge_rankings_with_results_ids


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

    def test_matches_partial_names_when_one_source_omits_given_name_tokens(self):
        weekly_rows = [
            {"rank": 50, "name": "GREEN Anna Lillian", "country_code": "AUS", "points": 300},
            {"rank": 51, "name": "NGUYEN Minh Bao Chau Elisa", "country_code": "VIE", "points": 299},
        ]
        results_rows = [
            {"rank": 50, "name": "GREEN Anna", "country_code": "AUS", "points": 300, "player_id": "green"},
            {"rank": 51, "name": "NGUYEN Elisa", "country_code": "VIE", "points": 299, "player_id": "nguyen"},
        ]

        merged, unresolved = merge_rankings_with_results_ids(weekly_rows, results_rows)

        self.assertEqual(unresolved, [])
        self.assertEqual(merged[0]["player_id"], "green")
        self.assertEqual(merged[0]["id_resolution_status"], "partial_name")
        self.assertEqual(merged[1]["player_id"], "nguyen")
        self.assertEqual(merged[1]["id_resolution_status"], "partial_name")

    def test_matches_partial_names_without_requiring_surname_position(self):
        weekly_rows = [{"rank": 88, "name": "Anna GREEN Lillian", "country_code": "AUS", "points": 200}]
        results_rows = [
            {"rank": 88, "name": "GREEN Anna", "country_code": "AUS", "points": 200, "player_id": "green"}
        ]

        merged, unresolved = merge_rankings_with_results_ids(weekly_rows, results_rows)

        self.assertEqual(unresolved, [])
        self.assertEqual(merged[0]["player_id"], "green")
        self.assertEqual(merged[0]["id_resolution_status"], "partial_name")

    def test_does_not_match_partial_names_without_token_subset(self):
        weekly_rows = [{"rank": 60, "name": "GREEN Anna Lillian", "country_code": "AUS", "points": 300}]
        results_rows = [
            {"rank": 60, "name": "GREEN Emily", "country_code": "AUS", "points": 300, "player_id": "wrong"}
        ]

        merged, unresolved = merge_rankings_with_results_ids(weekly_rows, results_rows)

        self.assertIsNone(merged[0]["player_id"])
        self.assertEqual(merged[0]["id_resolution_status"], "unmatched")
        self.assertEqual(len(unresolved), 1)

    def test_marks_partial_name_match_ambiguous_when_rank_distance_ties(self):
        weekly_rows = [{"rank": 100, "name": "NGUYEN Minh Bao Chau Elisa", "country_code": "VIE", "points": 100}]
        results_rows = [
            {"rank": 99, "name": "NGUYEN Elisa", "country_code": "VIE", "points": 100, "player_id": "1"},
            {"rank": 101, "name": "Elisa NGUYEN", "country_code": "VIE", "points": 100, "player_id": "2"},
        ]

        merged, unresolved = merge_rankings_with_results_ids(weekly_rows, results_rows)

        self.assertEqual(merged[0]["id_resolution_status"], "ambiguous")
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["candidate_count"], 2)

    def test_counts_partial_name_resolutions_as_matched(self):
        weekly_payload = {
            "rankings": [{"rank": 50, "name": "GREEN Anna Lillian", "country_code": "AUS", "points": 300}]
        }
        results_payload = {
            "rankings": [
                {"rank": 50, "name": "GREEN Anna", "country_code": "AUS", "points": 300, "player_id": "green"}
            ]
        }

        merged_payload, unresolved_payload = merge_payloads(weekly_payload, results_payload)

        self.assertEqual(unresolved_payload["total_unresolved"], 0)
        self.assertEqual(merged_payload["player_id_resolution"]["matched"], 1)

    def test_matches_manual_alias_by_player_id_for_spelling_differences(self):
        weekly_rows = [{"rank": 70, "name": "MISMATCHED Name", "country_code": "AAA", "points": 250}]
        results_rows = [
            {"rank": 70, "name": "MISMACTHED Name", "country_code": "AAA", "points": 250, "player_id": "777"},
            {"rank": 71, "name": "Different Name", "country_code": "AAA", "points": 249, "player_id": "888"},
        ]
        aliases = [
            {
                "weekly_name": "MISMATCHED Name",
                "results_name": "MISMACTHED Name",
                "country_code": "AAA",
                "player_id": "777",
            }
        ]

        merged, unresolved = merge_rankings_with_results_ids(weekly_rows, results_rows, aliases=aliases)

        self.assertEqual(unresolved, [])
        self.assertEqual(merged[0]["player_id"], "777")
        self.assertEqual(merged[0]["id_resolution_status"], "manual_alias")

    def test_manual_alias_does_not_cross_country(self):
        weekly_rows = [{"rank": 70, "name": "MISMATCHED Name", "country_code": "AAA", "points": 250}]
        results_rows = [
            {"rank": 70, "name": "MISMACTHED Name", "country_code": "BBB", "points": 250, "player_id": "777"}
        ]
        aliases = [
            {
                "weekly_name": "MISMATCHED Name",
                "results_name": "MISMACTHED Name",
                "country_code": "AAA",
                "player_id": "777",
            }
        ]

        merged, unresolved = merge_rankings_with_results_ids(weekly_rows, results_rows, aliases=aliases)

        self.assertIsNone(merged[0]["player_id"])
        self.assertEqual(merged[0]["id_resolution_status"], "unmatched")
        self.assertEqual(len(unresolved), 1)

    def test_marks_manual_alias_ambiguous_without_player_id_when_rank_distance_ties(self):
        weekly_rows = [{"rank": 100, "name": "MISMATCHED Name", "country_code": "AAA", "points": 100}]
        results_rows = [
            {"rank": 99, "name": "MISMACTHED Name", "country_code": "AAA", "points": 100, "player_id": "1"},
            {"rank": 101, "name": "MISMACTHED Name", "country_code": "AAA", "points": 100, "player_id": "2"},
        ]
        aliases = [
            {
                "weekly_name": "MISMATCHED Name",
                "results_name": "MISMACTHED Name",
                "country_code": "AAA",
            }
        ]

        merged, unresolved = merge_rankings_with_results_ids(weekly_rows, results_rows, aliases=aliases)

        self.assertEqual(merged[0]["id_resolution_status"], "ambiguous")
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["candidate_count"], 2)

    def test_counts_manual_alias_resolutions_as_matched(self):
        weekly_payload = {
            "rankings": [{"rank": 70, "name": "MISMATCHED Name", "country_code": "AAA", "points": 250}]
        }
        results_payload = {
            "rankings": [
                {"rank": 70, "name": "MISMACTHED Name", "country_code": "AAA", "points": 250, "player_id": "777"}
            ]
        }
        aliases = [
            {
                "weekly_name": "MISMATCHED Name",
                "results_name": "MISMACTHED Name",
                "country_code": "AAA",
                "player_id": "777",
            }
        ]

        merged_payload, unresolved_payload = merge_payloads(weekly_payload, results_payload, aliases=aliases)

        self.assertEqual(unresolved_payload["total_unresolved"], 0)
        self.assertEqual(merged_payload["player_id_resolution"]["matched"], 1)

    def test_preserves_database_profile_rank_resolution_status(self):
        weekly_payload = {
            "rankings": [{"rank": 770, "name": "YEUNG Yee Lam", "country_code": "HKG", "points": 3}]
        }
        results_payload = {
            "rankings": [
                {
                    "rank": 770,
                    "name": "YEUNG Yee Lam",
                    "country_code": "HKG",
                    "points": 3,
                    "player_id": "205829",
                    "profile_url": "https://results.ittf.link/profile/205829",
                    "id_resolution_hint": "db_profile_rank",
                }
            ]
        }

        merged_payload, unresolved_payload = merge_payloads(weekly_payload, results_payload)

        self.assertEqual(unresolved_payload["total_unresolved"], 0)
        self.assertEqual(merged_payload["rankings"][0]["id_resolution_status"], "db_profile_rank")
        self.assertEqual(merged_payload["player_id_resolution"]["matched"], 1)


if __name__ == "__main__":
    unittest.main()
