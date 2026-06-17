import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from apply_ranking_profile_review import apply_review
from review_ranking_profile_outputs import build_review


class ReviewRankingProfileOutputsTests(unittest.TestCase):
    def test_builds_review_from_unresolved_and_translation_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            unresolved = tmp / "ranking_unresolved.json"
            unresolved.write_text(
                json.dumps(
                    {
                        "total_unresolved": 1,
                        "unresolved": [
                            {
                                "reason": "unmatched",
                                "weekly": {"rank": 184, "name": "WU Ying Syuan", "country_code": "TPE", "points": 117},
                                "candidates": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            rank_log = tmp / "translate_ranks.log"
            rank_log.write_text("--- name (1) ---\nWU Ying Syuan\n\n--- event (1) ---\nWTT Contender Test\n", encoding="utf-8")
            profile_log = tmp / "translate_profiles.log"
            profile_log.write_text(
                "2026-06-16 - ERROR - Missing translation [style] in player_201874_WU_Ying_Syuan.json: 'Right-handed shakehand'\n",
                encoding="utf-8",
            )

            review = build_review(unresolved, rank_log, profile_log)

        self.assertEqual(review["unresolved_player_ids"][0]["weekly"]["name"], "WU Ying Syuan")
        self.assertEqual(
            {(entry["scope"], entry["field"], entry["original"]) for entry in review["missing_translations"]},
            {
                ("ranking", "name", "WU Ying Syuan"),
                ("ranking", "event", "WTT Contender Test"),
                ("profile", "style", "Right-handed shakehand"),
            },
        )
        self.assertIsNone(review["missing_translations"][0]["translated"])

    def test_apply_review_updates_dictionary_and_ranking_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dict_path = tmp / "translation_dict_v2.json"
            dict_path.write_text(json.dumps({"metadata": {}, "entries": {}}), encoding="utf-8")
            ranking_path = tmp / "ranking_with_ids.json"
            ranking_path.write_text(
                json.dumps(
                    {
                        "rankings": [
                            {"rank": 184, "name": "WU Ying Syuan", "country_code": "TPE", "points": 117, "player_id": None}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            review = {
                "unresolved_player_ids": [
                    {
                        "weekly": {"rank": 184, "name": "WU Ying Syuan", "country_code": "TPE", "points": 117},
                        "resolution": {"player_id": "201874", "profile_url": "https://results.ittf.link/profile/201874"},
                    }
                ],
                "missing_translations": [
                    {
                        "scope": "ranking",
                        "field": "name",
                        "original": "WU Ying Syuan",
                        "translated": "吴颖萱",
                        "categories": ["players"],
                    }
                ],
            }
            review_path = tmp / "review.json"
            review_path.write_text(json.dumps(review), encoding="utf-8")

            summary = apply_review(review_path, dict_path=dict_path, ranking_file=ranking_path)

            dictionary = json.loads(dict_path.read_text(encoding="utf-8"))
            ranking = json.loads(ranking_path.read_text(encoding="utf-8"))

        self.assertEqual(summary["translations_added"], 1)
        self.assertEqual(summary["ranking_ids_applied"], 1)
        self.assertEqual(dictionary["entries"]["wu ying syuan"]["translated"], "吴颖萱")
        self.assertEqual(ranking["rankings"][0]["player_id"], "201874")


if __name__ == "__main__":
    unittest.main()
