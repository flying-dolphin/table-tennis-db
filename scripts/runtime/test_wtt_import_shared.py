import sys
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import wtt_import_shared as shared


class WttImportSharedTests(unittest.TestCase):
    def test_infers_united_states_smash_time_zone_from_event_name(self):
        event = {
            "name": "United States Smash 2026",
            "location": "USA",
            "href": "/eventInfo?eventId=3242",
            "time_zone": None,
        }

        self.assertEqual("America/Los_Angeles", shared.infer_time_zone(event))

    def test_normalize_round_maps_main_draw_codes(self):
        cases = {
            "R128-": ("MAIN_DRAW", "R128"),
            "R64-": ("MAIN_DRAW", "R64"),
            "R64": ("MAIN_DRAW", "R64"),
            "R32-": ("MAIN_DRAW", "R32"),
            "8FNL": ("MAIN_DRAW", "R16"),
            "QFNL": ("MAIN_DRAW", "QF"),
            "SFNL": ("MAIN_DRAW", "SF"),
            "FNL-": ("MAIN_DRAW", "F"),
        }
        for raw, (stage, round_code) in cases.items():
            info = shared.normalize_round(raw)
            self.assertEqual(stage, info.stage_code, raw)
            self.assertEqual(round_code, info.round_code, raw)

    def test_normalize_round_maps_all_qualifying_rounds(self):
        for n in (1, 2, 3):
            info = shared.normalize_round(f"RND{n}")
            self.assertEqual("PRELIMINARY", info.stage_code)
            self.assertEqual(f"R{n}", info.round_code)

    def test_normalize_round_unknown_falls_back(self):
        info = shared.normalize_round("WHAT")
        self.assertEqual("UNKNOWN", info.stage_code)
        self.assertEqual("UNKNOWN", info.round_code)


if __name__ == "__main__":
    unittest.main()
