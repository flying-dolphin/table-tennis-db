import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.anti_bot import RiskControlTriggered
from scrape_matches_from_events import click_start_page_if_needed


class StartPageNavigationTests(unittest.TestCase):
    def test_clicks_start_control_without_goto(self):
        page = MagicMock()
        page.url = "https://results.ittf.link/event-matches/list/68?limitstart68=100"
        link = MagicMock()
        link.count.return_value = 1
        link.is_visible.return_value = True
        link.get_attribute.return_value = "/event-matches/list/68?limitstart68=0"
        page.locator.return_value.first = link

        with patch("scrape_matches_from_events.time.sleep"), patch(
            "scrape_matches_from_events.wait_for_pagination_info_after_retry", return_value=(1, 10, 997)
        ):
            reached = click_start_page_if_needed(page, current_page=2)

        self.assertTrue(reached)
        link.click.assert_called_once()
        page.goto.assert_not_called()

    def test_propagates_risk_after_start_click(self):
        page = MagicMock()
        link = MagicMock()
        link.count.return_value = 1
        link.is_visible.return_value = True
        link.get_attribute.return_value = "/event-matches/list/68?limitstart68=0"
        page.locator.return_value.first = link
        risk = RiskControlTriggered("HTTP 429", status=429)

        with patch("scrape_matches_from_events.time.sleep"), patch(
            "scrape_matches_from_events.wait_for_pagination_info_after_retry", side_effect=risk
        ):
            with self.assertRaises(RiskControlTriggered):
                click_start_page_if_needed(page, current_page=2)


if __name__ == "__main__":
    unittest.main()
