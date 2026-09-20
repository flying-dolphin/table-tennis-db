from __future__ import annotations

import json
import unittest
import zlib

from scripts.asian_games_2026 import common


class CommonTests(unittest.TestCase):
    def test_decode_utf8_wrapped_zlib(self) -> None:
        payload = [{"Status": "RUNNING", "Key": "TTE.1"}]
        compressed = zlib.compress(json.dumps(payload).encode())
        wrapped = compressed.decode("latin-1").encode("utf-8")
        self.assertEqual(common.decode_api_payload(wrapped), payload)

    def test_decode_plain_json(self) -> None:
        self.assertEqual(common.decode_api_payload(b'{"ok": true}'), {"ok": True})

    def test_tokyo_timestamp_conversions(self) -> None:
        converted = common.convert_source_timestamp("2026-09-20T10:00:00+09:00")
        self.assertEqual(converted.source_local, "2026-09-20T10:00:00")
        self.assertEqual(converted.utc, "2026-09-20T01:00:00Z")
        self.assertEqual(converted.beijing, "2026-09-20T09:00:00+08:00")

    def test_event_round_and_status_mappings(self) -> None:
        self.assertEqual(common.sub_event_code("Women's Team"), "WT")
        self.assertEqual(common.sub_event_code("Mixed Doubles"), "XD")
        self.assertEqual(common.round_meta("Women's Team Group B"), ("MAIN_DRAW", "RR", "B"))
        self.assertEqual(common.round_meta("Men's Singles Round of 32"), ("MAIN_DRAW", "R32", None))
        self.assertEqual(common.round_meta("Mixed Doubles Quarter-Finals"), ("MAIN_DRAW", "QF", None))
        self.assertEqual(
            common.round_meta(
                "Women's Doubles Round 1",
                phase_code="W.DOUBLES-----------.R64-",
            ),
            ("MAIN_DRAW", "R64", None),
        )
        self.assertEqual(common.normalize_status("START_LIST"), "scheduled")
        self.assertEqual(common.normalize_status("RUNNING"), "live")
        self.assertEqual(common.normalize_status("OFFICIAL"), "completed")


if __name__ == "__main__":
    unittest.main()
