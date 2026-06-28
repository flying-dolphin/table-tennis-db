import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("infer_event_time_zone.py")
spec = importlib.util.spec_from_file_location("infer_event_time_zone_under_test", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class InferEventTimeZoneTests(unittest.TestCase):
    def test_city_name_takes_precedence_for_multi_zone_country(self):
        event = module.EventTimezoneInput(
            event_id=3274,
            name="WTT Youth Contender San Francisco 2026",
            calendar_location="USA",
            event_location=None,
        )

        result = module.infer_time_zone(event)

        self.assertEqual(result.time_zone, "America/Los_Angeles")
        self.assertEqual(result.source, "city")

    def test_single_timezone_country_code_is_used_as_fallback(self):
        event = module.EventTimezoneInput(
            event_id=3231,
            name="WTT Champions 2026",
            calendar_location="QAT",
            event_location=None,
        )

        result = module.infer_time_zone(event)

        self.assertEqual(result.time_zone, "Asia/Qatar")
        self.assertEqual(result.source, "country")

    def test_multi_zone_country_without_known_city_is_ambiguous(self):
        event = module.EventTimezoneInput(
            event_id=4000,
            name="Example Table Tennis Event 2026",
            calendar_location="USA",
            event_location=None,
        )

        result = module.infer_time_zone(event)

        self.assertIsNone(result.time_zone)
        self.assertIn("multi-zone country", result.reason)


if __name__ == "__main__":
    unittest.main()
