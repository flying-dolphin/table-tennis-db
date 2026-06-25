import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from scrape_events import build_parser, wait_for_events_table_ready


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector
        self.first = self

    def count(self):
        return self.page.counts[self.page.step].get(self.selector, 0)

    def is_visible(self):
        return self.count() > 0


class FakePage:
    def __init__(self):
        self.url = "https://results.ittf.link/index.php/events"
        self.step = 0
        self.counts = [
            {
                "table tbody tr": 0,
                "table tr": 0,
                ".limit p": 0,
                ".limit.row p": 0,
                ".pagination-info": 0,
            },
            {
                "table tbody tr": 2,
                "table tr": 3,
                ".limit p": 1,
                ".limit.row p": 0,
                ".pagination-info": 0,
            },
        ]

    def locator(self, selector):
        return FakeLocator(self, selector)

    def inner_text(self, _selector):
        return ""

    def title(self):
        return "Events"


class WaitForEventsTableReadyTests(unittest.TestCase):
    def test_waits_until_rows_and_pagination_are_ready(self):
        page = FakePage()

        def advance(_seconds):
            page.step = 1

        with patch("scrape_events.time.sleep", side_effect=advance):
            wait_for_events_table_ready(page, timeout_sec=1.0, poll_sec=0.1)

        self.assertEqual(page.step, 1)

    def test_raises_when_table_never_becomes_ready(self):
        page = FakePage()
        page.counts = [page.counts[0]]

        with (
            patch("scrape_events.time.sleep", return_value=None),
            self.assertRaisesRegex(RuntimeError, "Events table did not become ready"),
        ):
            wait_for_events_table_ready(page, timeout_sec=0.1, poll_sec=0.01)


class BuildParserTests(unittest.TestCase):
    def test_accepts_initial_delay_range(self):
        args = build_parser().parse_args(["--initial-min-delay", "1", "--initial-max-delay", "3"])

        self.assertEqual(args.initial_min_delay, 1)
        self.assertEqual(args.initial_max_delay, 3)


if __name__ == "__main__":
    unittest.main()
