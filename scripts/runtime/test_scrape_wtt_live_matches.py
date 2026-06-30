import sys
import unittest
from pathlib import Path
from unittest.mock import patch


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import scrape_wtt_live_matches as live


class ScrapeWttLiveMatchesTests(unittest.TestCase):
    def test_dom_empty_falls_back_to_live_api_snapshot(self):
        api_matches = [
            {
                "match_code": "TTEMSINGLES-----------R64-002100",
                "source_status": "Start List",
                "sub_event": "Men's Singles",
                "round": "R64-",
                "scheduled_start": "2026-06-29T18:35:00",
                "table_no": "T01",
                "session_label": "Men's Singles - R64 - M 21",
                "score": None,
                "games": [],
                "winner_side": None,
                "sides": [
                    {"organization": "JPN", "display_name": "TOGAMI Shunsuke", "players": [{"name": "TOGAMI Shunsuke"}]},
                    {"organization": "USA", "display_name": "JHA Kanak", "players": [{"name": "JHA Kanak"}]},
                ],
            }
        ]
        api_summary = {"event_id": 3242, "matches": 1, "detail_rich_matches": 0}

        with patch.object(live, "scrape_live_page", return_value=([], "<html></html>")), patch.object(
            live, "build_live_results_snapshot", return_value=(api_summary, api_matches, [])
        ):
            cards, normalized, page_html, source = live.scrape_live_matches_with_fallback(
                3242,
                schedule_payload=[],
                use_cdp=False,
                cdp_port=9222,
                headless=True,
                timeout_ms=30000,
            )

        self.assertEqual([], cards)
        self.assertEqual(api_matches, normalized)
        self.assertEqual("<html></html>", page_html)
        self.assertEqual("api_live_result", source)


if __name__ == "__main__":
    unittest.main()
