import sys
import unittest
from pathlib import Path
from unittest.mock import patch


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import scrape_wtt_live_matches as live


class NormalizeCdnMatchTests(unittest.TestCase):
    def test_live_matchdata_normalizes_correctly(self):
        card = {
            "eventId": "3242",
            "documentCode": "TTEMSINGLES-----------R32-001100----------",
            "subEventName": "Men's Singles",
            "subEventDescription": "Men's Singles - Round of 32 - Match 11",
            "resultStatus": "LIVE",
            "overallScores": "2-1",
            "resultOverallScores": "2-1",
            "gameScores": "11-5,9-11,11-7,0-0,0-0",
            "tableNumber": "T01",
            "tableName": "Table 1",
            "competitiors": [
                {"competitiorId": "116021", "competitiorName": "JHA Kanak", "competitiorOrg": "USA"},
                {"competitiorId": "121684", "competitiorName": "JARVIS Tom", "competitiorOrg": "ENG"},
            ],
            "matchDateTime": {"startDateUTC": "2026-07-02T03:20:00"},
        }
        result = live.normalize_cdn_match(card, "LIVE", {})
        self.assertEqual(result["match_code"], "TTEMSINGLES-----------R32-001100")
        self.assertEqual(result["source_status"], "LIVE")
        self.assertEqual(result["score"], "2-1")
        self.assertEqual(result["sub_event"], "MS")
        self.assertEqual(result["round"], "R32-")
        self.assertEqual(result["table_no"], "Table 1")
        self.assertEqual(len(result["sides"]), 2)
        self.assertEqual(result["sides"][0]["display_name"], "JHA Kanak")
        self.assertEqual(result["sides"][1]["display_name"], "JARVIS Tom")
        self.assertEqual(result["winner_side"], "A")

    def test_official_match_has_no_winner_side_when_tied(self):
        card = {
            "documentCode": "TTEMSINGLES-----------R32-001100----------",
            "resultStatus": "OFFICIAL",
            "overallScores": "0-0",
        }
        result = live.normalize_cdn_match(card, "OFFICIAL", {})
        self.assertIsNone(result["winner_side"])

    def test_sub_event_code_mapping(self):
        self.assertEqual(live.sub_event_code_from_name("Men's Singles"), "MS")
        self.assertEqual(live.sub_event_code_from_name("Women's Doubles"), "WD")
        self.assertEqual(live.sub_event_code_from_name("Mixed Doubles"), "XD")
        self.assertEqual(live.sub_event_code_from_name("Men's Teams"), "MT")
        self.assertIsNone(live.sub_event_code_from_name(None))
        self.assertIsNone(live.sub_event_code_from_name("Unknown Event"))

    def test_round_code_from_description(self):
        self.assertEqual(live.round_code_from_description("Men's Singles - Quarterfinal - Match 1"), "QFNL")
        self.assertEqual(live.round_code_from_description("Mixed Doubles - Semifinal - Match 2"), "SFNL")
        self.assertEqual(live.round_code_from_description("Women's Singles - Round of 32 - Match 11"), "R32-")
        self.assertEqual(live.round_code_from_description("Men's Doubles - Final"), "FNL")
        self.assertIsNone(live.round_code_from_description(None))

    def test_build_sides_from_empty_competitors(self):
        self.assertEqual(live.build_sides_from_competitors({"competitiors": []}), [])
        self.assertEqual(live.build_sides_from_competitors({}), [])

    def test_full_document_code_pads_to_42_chars(self):
        code = "TTEMSINGLESR32001100"
        result = live.full_document_code(code)
        self.assertEqual(len(result), 42)
        self.assertTrue(result.startswith(code))
        self.assertTrue(result.endswith("--"))

    def test_cdn_matchdata_without_competitors_returns_empty_sides(self):
        card = {
            "documentCode": "TTEMSINGLES-----------R32-001100----------",
            "subEventName": "Men's Singles",
            "resultStatus": "LIVE",
        }
        result = live.normalize_cdn_match(card, "LIVE", {})
        self.assertEqual(result["sides"], [])

    def test_official_result_from_take_10_structure(self):
        payload = {
            "eventId": "3242",
            "documentCode": "TTEMSINGLES-----------R32-001100----------",
            "subEventName": "Men's Singles",
            "subEventDescription": "Men's Singles - Round of 32 - Match 11",
            "resultStatus": "OFFICIAL",
            "overallScores": "3-1",
            "resultOverallScores": "3-1",
            "gameScores": "11-2,11-3,6-11,11-4,0-0",
            "tableName": "Table 1",
            "competitiors": [
                {"competitiorId": "116021", "competitiorName": "JHA Kanak", "competitiorOrg": "USA"},
                {"competitiorId": "121684", "competitiorName": "JARVIS Tom", "competitiorOrg": "ENG"},
            ],
            "matchDateTime": {"startDateUTC": "2026-07-02T03:20:00"},
        }
        result = live.normalize_cdn_match(payload, "OFFICIAL", {})
        self.assertEqual(result["source_status"], "OFFICIAL")
        self.assertEqual(result["score"], "3-1")
        self.assertEqual(result["games"], ["11-2", "11-3", "6-11", "11-4", "0-0"])


if __name__ == "__main__":
    unittest.main()
