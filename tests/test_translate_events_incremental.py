import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from translate_events import filter_files_since, parse_since


class TranslateEventsIncrementalTests(unittest.TestCase):
    def test_parse_since_accepts_date_and_datetime_values(self):
        self.assertEqual(parse_since("2026-06-25"), datetime(2026, 6, 25))
        self.assertEqual(parse_since("2026-06-25 10:30"), datetime(2026, 6, 25, 10, 30))
        self.assertEqual(parse_since("2026-06-25T10:30:05"), datetime(2026, 6, 25, 10, 30, 5))

    def test_filter_files_since_uses_source_file_mtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_file = tmp / "events_a.json"
            new_file = tmp / "events_b.json"
            old_file.write_text("{}", encoding="utf-8")
            new_file.write_text("{}", encoding="utf-8")

            old_ts = datetime(2026, 6, 24, 23, 59).timestamp()
            new_ts = datetime(2026, 6, 25, 10, 1).timestamp()
            old_file.touch()
            new_file.touch()
            import os

            os.utime(old_file, (old_ts, old_ts))
            os.utime(new_file, (new_ts, new_ts))

            selected = filter_files_since([old_file, new_file], datetime(2026, 6, 25, 10, 0))

        self.assertEqual(selected, [new_file])


if __name__ == "__main__":
    unittest.main()
