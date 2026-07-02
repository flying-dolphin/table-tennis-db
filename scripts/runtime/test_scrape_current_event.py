import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch


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

    def test_run_step_logs_command_timing_and_return_code(self):
        completed = Mock()
        completed.returncode = 7
        stdout = StringIO()

        with patch.object(scrape_current_event.subprocess, "run", return_value=completed), patch("sys.stdout", stdout):
            rc = scrape_current_event.run_step(["python", "child.py", "--flag"])

        output = stdout.getvalue()
        self.assertEqual(7, rc)
        self.assertIn("[current-event] START", output)
        self.assertIn("python child.py --flag", output)
        self.assertIn("[current-event] END", output)
        self.assertIn("rc=7", output)
        self.assertIn("duration=", output)


if __name__ == "__main__":
    unittest.main()
