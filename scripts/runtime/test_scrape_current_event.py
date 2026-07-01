import sys
import unittest
from pathlib import Path
from unittest.mock import patch


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import scrape_current_event


class ScrapeCurrentEventTests(unittest.TestCase):
    def test_cdp_port_implies_use_cdp_for_browser_sources(self):
        commands = []

        def capture_step(cmd):
            commands.append(cmd)
            return 0

        argv = [
            "scrape_current_event.py",
            "--event-id",
            "3242",
            "--sources",
            "live",
            "--cdp-port",
            "9223",
        ]
        with patch.object(sys, "argv", argv), patch.object(scrape_current_event, "run_step", side_effect=capture_step):
            self.assertEqual(0, scrape_current_event.main())

        self.assertEqual(1, len(commands))
        self.assertIn("--cdp-port", commands[0])
        self.assertIn("9223", commands[0])
        self.assertIn("--use-cdp", commands[0])

    def test_match_details_source_runs_scraper(self):
        commands = []

        def capture_step(cmd):
            commands.append(cmd)
            return 0

        argv = [
            "scrape_current_event.py",
            "--event-id",
            "3242",
            "--sources",
            "match_details",
            "--db-path",
            "/tmp/ittf.db",
        ]
        with patch.object(sys, "argv", argv), patch.object(scrape_current_event, "run_step", side_effect=capture_step):
            self.assertEqual(0, scrape_current_event.main())

        self.assertEqual(1, len(commands))
        self.assertTrue(any(str(part).endswith("scrape_wtt_match_details.py") for part in commands[0]))
        self.assertIn("--db-path", commands[0])
        self.assertIn("/tmp/ittf.db", commands[0])


if __name__ == "__main__":
    unittest.main()
