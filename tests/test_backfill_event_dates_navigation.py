import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from backfill_event_dates import collect_events_with_pagination, select_and_load_player_events
from lib.anti_bot import DelayConfig, RiskControlTriggered


class BackfillNavigationTests(unittest.TestCase):
    def test_rate_limit_stops_without_direct_goto_retry(self):
        page = MagicMock()
        risk = RiskControlTriggered("HTTP 429", status=429, retry_after_sec=3525)

        with patch("backfill_event_dates.guarded_goto", side_effect=risk):
            with self.assertRaises(RiskControlTriggered):
                select_and_load_player_events(
                    page,
                    "Player",
                    "CHN",
                    DelayConfig(0, 0, 0, 0),
                )

        page.goto.assert_not_called()

    def test_pagination_stops_on_risk_page_before_parsing(self):
        page = MagicMock()
        with patch("backfill_event_dates.detect_risk", return_value="risk text detected: too many requests"), patch(
            "backfill_event_dates.parse_event_rows"
        ) as parse:
            with self.assertRaises(RiskControlTriggered):
                collect_events_with_pagination(page, from_date=None)

        parse.assert_not_called()


if __name__ == "__main__":
    unittest.main()
