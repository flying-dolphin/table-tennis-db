import sys
import unittest
from pathlib import Path
from unittest.mock import patch


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import wtt_scrape_shared as shared


class WttScrapeSharedTests(unittest.TestCase):
    def test_default_official_results_page_size_covers_large_individual_events(self):
        self.assertGreaterEqual(shared.OFFICIAL_RESULTS_PAGE_SIZE, 5000)

    def test_official_results_falls_back_when_large_take_fails(self):
        calls = []

        def fake_fetch_json_value(url):
            calls.append(url)
            if "take=5000" in url:
                return None
            if "take=1000" in url:
                return [
                    {
                        "documentCode": "TTEWSINGLES-----------R64-001700----------",
                        "match_card": {"resultOverallScores": "2-3"},
                    }
                ]
            return []

        with patch.object(shared, "fetch_json_value", side_effect=fake_fetch_json_value):
            meta, results = shared.fetch_all_official_results(3242)

        self.assertTrue(meta["ok"])
        self.assertEqual(1, len(results))
        self.assertIn("take=5000", calls[0])
        self.assertTrue(any("take=1000" in call for call in calls))

    def test_fetch_json_value_returns_none_for_invalid_json(self):
        with patch.object(shared, "fetch_json", return_value=b"not json"):
            self.assertIsNone(shared.fetch_json_value("https://example.test/bad.json"))


if __name__ == "__main__":
    unittest.main()
