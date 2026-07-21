import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.anti_bot import DelayConfig, RiskControlTriggered
from lib.page_ops import _retry_after_seconds, click_next_page_if_any, guarded_goto


class GuardedNavigationTests(unittest.TestCase):
    def setUp(self):
        self.delay = DelayConfig(0, 0, 0, 0)

    def test_guarded_goto_does_not_retry_429_when_risk_retries_disabled(self):
        response = MagicMock(status=429, status_text="Too Many Requests", headers={"retry-after": "300"})
        page = MagicMock()
        page.goto.return_value = response

        with patch("lib.page_ops.time.sleep") as sleep:
            with self.assertRaisesRegex(RiskControlTriggered, "HTTP 429") as raised:
                guarded_goto(
                    page,
                    "https://results.ittf.link/ranking",
                    self.delay,
                    "test",
                    retries=1,
                    sleep_first=False,
                    retry_risk_responses=False,
                )

        self.assertEqual(page.goto.call_count, 1)
        self.assertEqual(raised.exception.retry_after_sec, 300)
        sleep.assert_not_called()

    def test_retry_after_is_not_capped_below_server_instruction(self):
        self.assertEqual(_retry_after_seconds("600", attempt=0), 600)

    def test_next_page_propagates_risk_instead_of_reporting_end(self):
        page = MagicMock()
        locator = MagicMock()
        locator.count.return_value = 1
        locator.is_visible.return_value = True
        locator.get_attribute.side_effect = lambda name: {
            "class": "page-link",
            "aria-disabled": None,
            "href": "/ranking?limitstart58=825",
        }.get(name)
        locator.locator.return_value.get_attribute.return_value = "page-item"
        page.locator.return_value.first = locator
        page.url = "https://results.ittf.link/ranking?limitstart58=800"

        with patch("lib.page_ops._get_active_pagination_page", side_effect=[33, 34]), patch(
            "lib.page_ops.move_mouse_to_locator"
        ) as click, patch("lib.page_ops.guarded_goto") as goto:
            self.assertTrue(click_next_page_if_any(page, self.delay))

        click.assert_called_once_with(page, locator)
        goto.assert_not_called()

    def test_next_page_is_not_clicked_when_footer_reports_last_page(self):
        page = MagicMock()
        page.content.return_value = '<div class="list-footer">Page 10 of 10 Total: 958</div>'

        self.assertFalse(click_next_page_if_any(page, self.delay))

        page.locator.assert_not_called()


if __name__ == "__main__":
    unittest.main()
