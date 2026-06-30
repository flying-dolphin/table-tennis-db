import argparse
import sys
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import generate_current_event_crontab as cron


class GenerateCurrentEventCrontabTests(unittest.TestCase):
    def test_completed_refresh_scrapes_match_details_without_import_source(self):
        args = argparse.Namespace(
            python_bin="/venv/bin/python",
            project_root="/srv/ittf",
            live_event_data_root="data/live_event_data",
            emit_db_path=None,
            db_path=Path("data/db/ittf.db"),
            runtime_python_dir="scripts/runtime",
            event_id=3242,
            headless=True,
            use_cdp=False,
            cdp_port=9223,
            log_dir=None,
        )

        command = cron.build_refresh_command(args, {"completed"})

        self.assertIn("--sources completed match_details", command)
        self.assertIn("--sources completed --db-path", command)
        self.assertNotIn("--sources completed match_details --db-path", command)


if __name__ == "__main__":
    unittest.main()
