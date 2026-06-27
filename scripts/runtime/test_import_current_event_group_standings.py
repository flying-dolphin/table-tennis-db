import json
import sys
import tempfile
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from import_current_event_group_standings import should_skip_missing_standings


class ImportCurrentEventGroupStandingsTests(unittest.TestCase):
    def test_skipped_capture_summary_allows_missing_standings_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp)
            (input_dir / "standings_capture_summary.json").write_text(
                json.dumps({"skipped": True, "skip_reason": "No team sub-events found"}),
                encoding="utf-8",
            )

            self.assertTrue(should_skip_missing_standings(input_dir))

    def test_missing_standings_without_skipped_summary_is_not_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(should_skip_missing_standings(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
