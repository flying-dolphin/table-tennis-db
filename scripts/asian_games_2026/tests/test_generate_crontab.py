from __future__ import annotations

import unittest
from pathlib import Path

from scripts.asian_games_2026.generate_crontab import generate_crontab


class GenerateCrontabTests(unittest.TestCase):
    def test_beijing_cron_has_refresh_reconcile_finalize_and_guard(self) -> None:
        text = generate_crontab(project_root=Path("/srv/ittf"), python="/venv/python")
        self.assertIn("CRON_TZ=Asia/Shanghai", text)
        self.assertIn("*/5 * 20-28 9 *", text)
        self.assertIn("refresh --all-linked", text)
        self.assertIn("0 2 29 9 *", text)
        self.assertIn('date +\\%Y', text)
        self.assertIn("scripts.asian_games_2026.finalize", text)


if __name__ == "__main__":
    unittest.main()
