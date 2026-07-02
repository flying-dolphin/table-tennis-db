import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import import_current_event


class ImportCurrentEventTests(unittest.TestCase):
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
