import sys
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import import_current_event


class ImportCurrentEventTests(unittest.TestCase):
    def test_lifecycle_advances_only_started_unfinished_events_in_event_timezone(self):
        now = datetime(2026, 10, 1, 0, 30, tzinfo=timezone.utc)
        cases = [
            ("upcoming", "2026-10-01", "Asia/Shanghai", "in_progress"),
            ("draw_published", "2026-10-01", "Asia/Shanghai", "in_progress"),
            ("upcoming", "2026-10-01", "America/Los_Angeles", "upcoming"),
            ("upcoming", "2026-10-02", "Asia/Shanghai", "upcoming"),
            ("upcoming", "2026-09-01", "Asia/Shanghai", "in_progress"),
            ("completed", "2026-09-01", "Asia/Shanghai", "completed"),
            ("in_progress", "2026-10-02", "Asia/Shanghai", "in_progress"),
            ("upcoming", None, "Asia/Shanghai", "upcoming"),
            ("upcoming", "invalid", "Asia/Shanghai", "upcoming"),
            ("upcoming", "2026-10-01", "Invalid/Zone", "upcoming"),
        ]
        for status, start, tz, expected in cases:
            with self.subTest(status=status, start=start, tz=tz), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "test.db"
                with closing(sqlite3.connect(db)) as conn, conn:
                    conn.execute("CREATE TABLE events (event_id INTEGER PRIMARY KEY, lifecycle_status TEXT, start_date TEXT, time_zone TEXT)")
                    conn.execute("INSERT INTO events VALUES (3249, ?, ?, ?)", (status, start, tz))
                    conn.execute("INSERT INTO events VALUES (999, 'upcoming', '2026-09-01', 'Asia/Shanghai')")
                import_current_event.advance_event_lifecycle(db, 3249, now=now)
                with closing(sqlite3.connect(db)) as conn, conn:
                    self.assertEqual(expected, conn.execute("SELECT lifecycle_status FROM events WHERE event_id=3249").fetchone()[0])
                    self.assertEqual("upcoming", conn.execute("SELECT lifecycle_status FROM events WHERE event_id=999").fetchone()[0])

    def test_main_advances_lifecycle_after_successful_import_only(self):
        for step_rc in (0, 9):
            with self.subTest(step_rc=step_rc), patch.object(sys, "argv", ["import_current_event.py", "--event-id", "3249", "--sources", "schedule"]), patch.object(import_current_event, "run_step", return_value=step_rc), patch.object(import_current_event, "advance_event_lifecycle", create=True) as advance:
                self.assertEqual(step_rc, import_current_event.main())
                self.assertEqual(1 if step_rc == 0 else 0, advance.call_count)

    def test_run_step_logs_command_timing_and_return_code(self):
        completed = Mock()
        completed.returncode = 9
        stdout = StringIO()

        with patch.object(import_current_event.subprocess, "run", return_value=completed), patch("sys.stdout", stdout):
            rc = import_current_event.run_step(["python", "import_child.py", "--event-id", "3242"])

        output = stdout.getvalue()
        self.assertEqual(9, rc)
        self.assertIn("[current-event] START", output)
        self.assertIn("python import_child.py --event-id 3242", output)
        self.assertIn("[current-event] END", output)
        self.assertIn("rc=9", output)
        self.assertIn("duration=", output)


if __name__ == "__main__":
    unittest.main()
