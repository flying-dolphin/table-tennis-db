from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.asian_games_2026.refresh import run_refresh


class RefreshTests(unittest.TestCase):
    @patch("scripts.asian_games_2026.refresh.subprocess.run")
    def test_refresh_captures_brackets_before_import(self, run) -> None:
        run_refresh(db_path=Path("/tmp/asian-games-test.db"), all_linked=True)

        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(
            commands,
            [
                [sys.executable, "-m", "scripts.asian_games_2026.scrape_schedule"],
                [sys.executable, "-m", "scripts.asian_games_2026.scrape_brackets"],
                [sys.executable, "-m", "scripts.asian_games_2026.scrape_matches", "--all-linked"],
                [
                    sys.executable,
                    "-m",
                    "scripts.asian_games_2026.import_current",
                    "--db-path",
                    "/tmp/asian-games-test.db",
                ],
            ],
        )
        self.assertTrue(all(call.kwargs == {"check": True} for call in run.call_args_list))


if __name__ == "__main__":
    unittest.main()
