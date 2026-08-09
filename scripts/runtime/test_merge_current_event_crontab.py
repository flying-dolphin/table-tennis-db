import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_current_event_crontab as merge


class MergeCurrentEventCrontabTests(unittest.TestCase):
    def test_installing_second_event_preserves_first_event(self):
        existing = """MAILTO=ops@example.com
# ITTF current-event refresh begin
# Generated for event 3245: Yokohama 2026
CRON_TZ=Asia/Shanghai
10 1 * * * run-3245
# ITTF current-event refresh end
"""
        generated = """# Generated for event 3246: Sweden 2026
CRON_TZ=Asia/Shanghai
20 2 * * * run-3246
"""

        result = merge.merge_crontab(existing, generated, 3246)

        self.assertIn("MAILTO=ops@example.com", result)
        self.assertIn("# ITTF current-event event 3245 begin", result)
        self.assertIn("10 1 * * * run-3245", result)
        self.assertIn("# ITTF current-event event 3246 begin", result)
        self.assertIn("20 2 * * * run-3246", result)
        self.assertFalse(result.startswith("\n"))
        self.assertEqual(1, result.count("# ITTF current-event refresh begin"))
        self.assertEqual(1, result.count("# ITTF current-event refresh end"))

    def test_reinstalling_event_replaces_only_that_event(self):
        existing = """# ITTF current-event refresh begin
# ITTF current-event event 3245 begin
# Generated for event 3245: Old
10 1 * * * old-3245
# ITTF current-event event 3245 end
# ITTF current-event event 3246 begin
# Generated for event 3246: Sweden
20 2 * * * run-3246
# ITTF current-event event 3246 end
# ITTF current-event refresh end
"""
        generated = """# Generated for event 3245: New
30 3 * * * new-3245
"""

        result = merge.merge_crontab(existing, generated, 3245)

        self.assertIn("30 3 * * * new-3245", result)
        self.assertNotIn("10 1 * * * old-3245", result)
        self.assertIn("20 2 * * * run-3246", result)
        self.assertEqual(1, result.count("# ITTF current-event event 3245 begin"))

    def test_empty_generated_jobs_removes_only_target_event(self):
        existing = """# ITTF current-event refresh begin
# ITTF current-event event 3245 begin
# Generated for event 3245: Yokohama
10 1 * * * run-3245
# ITTF current-event event 3245 end
# ITTF current-event event 3246 begin
# Generated for event 3246: Sweden
20 2 * * * run-3246
# ITTF current-event event 3246 end
# ITTF current-event refresh end
"""

        result = merge.merge_crontab(existing, "# Generated for event 3245: Yokohama\n# No future jobs\n", 3245)

        self.assertNotIn("run-3245", result)
        self.assertIn("run-3246", result)

    def test_first_install_without_existing_crontab_has_no_leading_blank_line(self):
        result = merge.merge_crontab(
            "",
            "# Generated for event 3245: Yokohama\n10 1 * * * run-3245\n",
            3245,
        )

        self.assertTrue(result.startswith("# ITTF current-event refresh begin\n"))


if __name__ == "__main__":
    unittest.main()
