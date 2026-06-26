import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "server" / "update_events_calendar.sh"


class EventsCalendarDeployConfigTests(unittest.TestCase):
    def test_update_script_exists_is_executable_and_has_valid_shell_syntax(self):
        self.assertTrue(SCRIPT.exists(), f"missing script: {SCRIPT}")
        self.assertTrue(os.access(SCRIPT, os.X_OK), f"script is not executable: {SCRIPT}")

        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_update_script_publishes_calendar_runtime_dependencies(self):
        script = SCRIPT.read_text(encoding="utf-8")

        required_paths = [
            "scripts/db/config.py",
            "scripts/db/import_events_calendar.py",
            "scripts/db/event_classification_overrides.py",
            "data/event_category_mapping.json",
        ]

        for required_path in required_paths:
            self.assertIn(required_path, script)

    def test_update_script_dry_runs_backs_up_imports_and_verifies_in_order(self):
        script = SCRIPT.read_text(encoding="utf-8")

        preflight_pos = script.index("\n    run_remote_preflight")
        backup_pos = script.index("\n    backup_remote_database\n")
        import_pos = script.index("==> Running remote events calendar import")
        verify_pos = script.index("\n    verify_remote_import")

        self.assertLess(preflight_pos, backup_pos)
        self.assertLess(backup_pos, import_pos)
        self.assertLess(import_pos, verify_pos)
        self.assertIn("import_events_calendar.py --year '${YEAR}' --dry-run", script)
        self.assertIn("import_events_calendar.py --year '${YEAR}'", script)
        self.assertIn("ittf-before-events-calendar-", script)
        self.assertIn("events_calendar", script)
        self.assertIn("COUNT(*)", script)

    def test_update_script_publishes_payload_to_data_before_remote_dry_run(self):
        script = SCRIPT.read_text(encoding="utf-8")

        publish_pos = script.index("\n    publish_remote_payload_data")
        dry_run_pos = script.index("\n    run_remote_dry_run")

        self.assertLess(publish_pos, dry_run_pos)
        self.assertIn("import_events_calendar.py --year '${YEAR}' --dry-run", script)


if __name__ == "__main__":
    unittest.main()
