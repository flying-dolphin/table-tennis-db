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


if __name__ == "__main__":
    unittest.main()
