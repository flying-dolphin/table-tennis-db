import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import scrape_wtt_live_matches as live


class FetchCdnJsonResultTests(unittest.TestCase):
    @staticmethod
    def response(status: int, body: bytes) -> MagicMock:
        response = MagicMock()
        response.status = status
        response.headers = {}
        response.read.return_value = body
        response.__enter__.return_value = response
        return response

    def test_returns_immutable_result_for_successful_json(self):
        self.assertTrue(hasattr(live, "JsonFetchResult"))
        response = self.response(200, b'{"status": "ok"}')

        with patch.object(live.urllib.request, "urlopen", return_value=response):
            result = live.fetch_cdn_json_result("/success.json", retries=1)

        self.assertTrue(result.ok)
        self.assertEqual(result.payload, {"status": "ok"})
        with self.assertRaises(AttributeError):
            result.ok = False

    def test_reports_http_204_as_unavailable(self):
        self.assertTrue(hasattr(live, "fetch_cdn_json_result"))
        response = self.response(204, b"")

        with patch.object(live.urllib.request, "urlopen", return_value=response):
            result = live.fetch_cdn_json_result("/empty.json", retries=1)

        self.assertFalse(result.ok)
        self.assertIsNone(result.payload)
        self.assertEqual(result.error, "HTTP 204 No Content")

    def test_reports_network_exception(self):
        self.assertTrue(hasattr(live, "fetch_cdn_json_result"))

        with patch.object(live.urllib.request, "urlopen", side_effect=OSError("offline")):
            result = live.fetch_cdn_json_result("/offline.json", retries=1)

        self.assertFalse(result.ok)
        self.assertIn("OSError: offline", result.error)

    def test_reports_decode_and_json_exceptions(self):
        self.assertTrue(hasattr(live, "fetch_cdn_json_result"))
        response = self.response(200, b"unreadable")

        with patch.object(live, "decode_response_body", side_effect=ValueError("bad gzip")):
            with patch.object(live.urllib.request, "urlopen", return_value=response):
                decode_result = live.fetch_cdn_json_result("/compressed.json", retries=1)

        json_response = self.response(200, b"not json")
        with patch.object(live.urllib.request, "urlopen", return_value=json_response):
            json_result = live.fetch_cdn_json_result("/invalid.json", retries=1)

        self.assertFalse(decode_result.ok)
        self.assertIn("ValueError: bad gzip", decode_result.error)
        self.assertFalse(json_result.ok)
        self.assertIn("JSONDecodeError", json_result.error)


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


class FetchRecentOfficialTests(unittest.TestCase):
    def test_uses_nonempty_take_10_without_full_official_fallback(self):
        self.assertTrue(hasattr(live, "fetch_recent_official"))
        take_10 = SimpleNamespace(
            url="https://cdn.test/take-10.json",
            ok=True,
            payload=[{"documentCode": "MATCH-1"}],
            error=None,
        )

        with (
            patch.object(live, "fetch_cdn_json_result", return_value=take_10, create=True),
            patch.object(live, "fetch_all_official_results", create=True) as fallback,
        ):
            result = live.fetch_recent_official(3242)

        self.assertEqual(result.items, take_10.payload)
        self.assertEqual(result.selected_source, "take_10")
        self.assertFalse(result.degraded)
        self.assertEqual(result.sources["take_10"]["count"], 1)
        fallback.assert_not_called()

    def test_uses_empty_take_10_without_full_official_fallback(self):
        self.assertTrue(hasattr(live, "fetch_recent_official"))
        take_10 = SimpleNamespace(
            url="https://cdn.test/take-10.json",
            ok=True,
            payload=[],
            error=None,
        )

        with (
            patch.object(live, "fetch_cdn_json_result", return_value=take_10, create=True),
            patch.object(live, "fetch_all_official_results", create=True) as fallback,
        ):
            result = live.fetch_recent_official(3242)

        self.assertEqual(result.items, [])
        self.assertEqual(result.selected_source, "take_10")
        self.assertFalse(result.degraded)
        self.assertEqual(result.sources["take_10"]["count"], 0)
        fallback.assert_not_called()

    def test_unavailable_take_10_uses_full_official_fallback(self):
        self.assertTrue(hasattr(live, "fetch_recent_official"))
        take_10 = SimpleNamespace(
            url="https://cdn.test/take-10.json",
            ok=False,
            payload=None,
            error="HTTP 204 No Content",
        )
        fallback_meta = {
            "url": "https://api.test/official-results",
            "ok": True,
            "count": 2,
            "pages": 1,
        }
        fallback_items = [{"documentCode": "MATCH-1"}, {"documentCode": "MATCH-2"}]

        with (
            patch.object(live, "fetch_cdn_json_result", return_value=take_10, create=True),
            patch.object(
                live,
                "fetch_all_official_results",
                return_value=(fallback_meta, fallback_items),
                create=True,
            ) as fallback,
        ):
            result = live.fetch_recent_official(3242)

        self.assertEqual(result.items, fallback_items)
        self.assertEqual(result.selected_source, "full_official_fallback")
        self.assertFalse(result.degraded)
        self.assertEqual(result.sources["full_official_fallback"]["pages"], 1)
        fallback.assert_called_once_with(3242)

    def test_invalid_take_10_uses_full_official_fallback(self):
        self.assertTrue(hasattr(live, "fetch_recent_official"))
        take_10 = SimpleNamespace(
            url="https://cdn.test/take-10.json",
            ok=True,
            payload={"unexpected": "object"},
            error=None,
        )
        fallback_meta = {
            "url": "https://api.test/official-results",
            "ok": True,
            "count": 1,
            "pages": 1,
        }
        fallback_items = [{"documentCode": "MATCH-1"}]

        with (
            patch.object(live, "fetch_cdn_json_result", return_value=take_10, create=True),
            patch.object(
                live,
                "fetch_all_official_results",
                return_value=(fallback_meta, fallback_items),
                create=True,
            ) as fallback,
        ):
            result = live.fetch_recent_official(3242)

        self.assertEqual(result.items, fallback_items)
        self.assertEqual(result.selected_source, "full_official_fallback")
        self.assertIn("expected list", result.sources["take_10"]["error"])
        fallback.assert_called_once_with(3242)

    def test_marks_result_degraded_when_take_10_and_full_official_fail(self):
        self.assertTrue(hasattr(live, "fetch_recent_official"))
        take_10 = SimpleNamespace(
            url="https://cdn.test/take-10.json",
            ok=False,
            payload=None,
            error="JSONDecodeError: invalid JSON",
        )
        fallback_meta = {
            "url": "https://api.test/official-results",
            "ok": False,
            "count": 0,
            "pages": 0,
            "error": "upstream unavailable",
        }

        with (
            patch.object(live, "fetch_cdn_json_result", return_value=take_10, create=True),
            patch.object(
                live,
                "fetch_all_official_results",
                return_value=(fallback_meta, []),
                create=True,
            ),
        ):
            result = live.fetch_recent_official(3242)

        self.assertEqual(result.items, [])
        self.assertIsNone(result.selected_source)
        self.assertTrue(result.degraded)
        self.assertEqual(result.sources["full_official_fallback"]["error"], "upstream unavailable")


class OfficialResultMergeTests(unittest.TestCase):
    @staticmethod
    def normalized_match(code: str, status: str, table: str = "Table 1") -> dict:
        return {
            "match_code": code,
            "source_status": status,
            "table_no": table,
            "score": "3-1" if status == "OFFICIAL" else "2-1",
        }

    def test_official_match_replaces_live_match_with_the_same_code(self):
        live_match = self.normalized_match("MATCH-1", "LIVE")
        official_match = self.normalized_match("MATCH-1", "OFFICIAL")

        self.assertTrue(hasattr(live, "merge_normalized_matches"))
        merged = live.merge_normalized_matches([live_match], [official_match])

        self.assertEqual(merged, [official_match])

    def test_keeps_different_match_codes_in_existing_deterministic_order(self):
        live_match = self.normalized_match("MATCH-2", "LIVE", "Table 2")
        official_match = self.normalized_match("MATCH-1", "OFFICIAL", "Table 1")

        self.assertTrue(hasattr(live, "merge_normalized_matches"))
        merged = live.merge_normalized_matches([live_match], [official_match])

        self.assertEqual(merged, [live_match, official_match])

    def test_scrape_uses_recent_official_and_normalizes_full_fallback_item(self):
        live_card = {
            "documentCode": "MATCH-1",
            "resultStatus": "LIVE",
            "overallScores": "2-1",
            "tableName": "Live Table",
        }
        fallback_item = {
            "documentCode": "MATCH-1",
            "fullResults": "OFFICIAL",
            "match_card": {
                "documentCode": "MATCH-1",
                "resultStatus": "OFFICIAL",
                "resultOverallScores": "3-1",
                "gameScores": "11-8,11-7,9-11,11-5",
                "tableName": "Official Table",
            },
        }
        official_result = live.RecentOfficialResult(
            items=[fallback_item],
            selected_source="full_official_fallback",
            sources={"full_official_fallback": {"ok": True, "count": 1}},
            degraded=False,
        )

        with (
            patch.object(live, "fetch_live_match_ids", return_value=[{"documentCode": "MATCH-1"}]),
            patch.object(live, "fetch_matchdata_card", return_value=live_card),
            patch.object(live, "fetch_recent_official", return_value=official_result) as fetch_official,
        ):
            scraped = live.scrape_event_matches(
                3242,
                include_official=True,
            )

        self.assertIsInstance(scraped, tuple)
        matches, returned_official_result = scraped
        fetch_official.assert_called_once_with(3242)
        self.assertIs(returned_official_result, official_result)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["source_status"], "OFFICIAL")
        self.assertEqual(matches[0]["score"], "3-1")
        self.assertEqual(matches[0]["table_no"], "Official Table")

    def test_failed_official_sources_leave_live_output_and_write_only_warning(self):
        live_card = {
            "documentCode": "MATCH-1",
            "resultStatus": "LIVE",
            "overallScores": "2-1",
        }
        official_result = live.RecentOfficialResult(
            items=[],
            selected_source=None,
            sources={
                "take_10": {"ok": False, "error": "HTTP 204 No Content"},
                "full_official_fallback": {"ok": False, "error": "upstream unavailable"},
            },
            degraded=True,
        )

        with (
            patch.object(live, "fetch_live_match_ids", return_value=[{"documentCode": "MATCH-1"}]),
            patch.object(live, "fetch_matchdata_card", return_value=live_card),
            patch.object(live, "fetch_recent_official", return_value=official_result),
            tempfile.TemporaryDirectory() as tmp_dir,
        ):
            scraped = live.scrape_event_matches(
                3242,
                include_official=True,
            )
            self.assertIsInstance(scraped, tuple)
            matches, returned_official_result = scraped
            live.write_outputs(
                Path(tmp_dir),
                3242,
                matches,
                official_result=returned_official_result,
                schedule_cache_used=False,
                with_debug_files=False,
            )
            summary = json.loads(
                (Path(tmp_dir) / "_scrape_summary_live.json").read_text(encoding="utf-8")
            )

        self.assertEqual([match["match_code"] for match in matches], ["MATCH-1"])
        self.assertEqual(summary["errors"], [])
        self.assertEqual(len(summary["warnings"]), 1)
        self.assertTrue(summary["degraded"])
        self.assertIsNone(summary["selected_official_source"])
        self.assertEqual(summary["official_sources"], official_result.sources)

    def test_scrape_without_official_returns_empty_official_result(self):
        with (
            patch.object(live, "fetch_live_match_ids", return_value=[]),
            patch.object(live, "fetch_recent_official") as fetch_official,
        ):
            scraped = live.scrape_event_matches(3242)

        self.assertIsInstance(scraped, tuple)
        matches, official_result = scraped
        self.assertEqual(matches, [])
        self.assertEqual(official_result, live.RecentOfficialResult([], None, {}, False))
        fetch_official.assert_not_called()


if __name__ == "__main__":
    unittest.main()
