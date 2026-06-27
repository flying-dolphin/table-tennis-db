import json
import sys
import tempfile
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from wtt_scrape_shared import (
    discover_event_sub_events,
    doc_code_for_sub,
    resolve_bracket_sub_events,
    resolve_standings_team_codes,
)


class EventSubEventDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.event_schedule_dir = self.root / "data" / "event_schedule"
        self.event_schedule_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write_event_schedule(self, event_id: int, parsed_codes: list[str]) -> None:
        payload = [
            {
                "赛事": parsed_codes,
                "_parsed": [
                    {
                        "sub_event_code": code,
                        "stage_code": "MAIN_DRAW",
                        "round_code": "R64",
                    }
                    for code in parsed_codes
                ],
            }
        ]
        (self.event_schedule_dir / f"{event_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_discovers_3242_individual_brackets_without_team_standings(self):
        self.write_event_schedule(3242, ["MS", "WS", "MD", "WD", "XD"])

        discovered = discover_event_sub_events(3242, project_root=self.root)

        self.assertEqual(["MS", "WS", "MD", "WD", "XD"], discovered.sub_event_codes)
        self.assertEqual(
            ["MSING", "WSING", "MDOUB", "WDOUB", "XDOUB"],
            resolve_bracket_sub_events(discovered),
        )
        self.assertEqual([], resolve_standings_team_codes(discovered))

    def test_discovers_team_standings_codes(self):
        self.write_event_schedule(3216, ["MT", "WT"])

        discovered = discover_event_sub_events(3216, project_root=self.root)

        self.assertEqual(["MTEAM", "WTEAM"], resolve_standings_team_codes(discovered))
        self.assertEqual(["MTEAM", "WTEAM"], resolve_bracket_sub_events(discovered))

    def test_bracket_document_code_uses_full_wtt_sub_event_name(self):
        self.assertEqual(
            "TTEMSINGLES-------------------------------",
            doc_code_for_sub("MSING"),
        )
        self.assertEqual(
            "TTEXDOUBLES-------------------------------",
            doc_code_for_sub("XDOUB"),
        )


if __name__ == "__main__":
    unittest.main()
