#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_event_to_dict import extract_entries


class UpdateEventToDictTests(unittest.TestCase):
    def test_events_list_reads_translated_fields_instead_of_english_source_fields(self) -> None:
        orig_data = {
            "events": [
                {
                    "event_id": 3241,
                    "name": "WTT Star Contender Ljubljana 2026",
                    "event_type": "WTT Contender Series",
                }
            ]
        }
        cn_data = {
            "events": [
                {
                    "event_id": 3241,
                    "name": "WTT Star Contender Ljubljana 2026",
                    "name_zh": "2026年WTT球星挑战赛卢布尔雅那站",
                    "event_type": "WTT Contender Series",
                    "event_type_zh": "WTT挑战赛系列",
                }
            ]
        }

        entries = extract_entries(orig_data, cn_data, "error")

        self.assertEqual(
            [
                (
                    "WTT Star Contender Ljubljana 2026",
                    "WTT球星挑战赛卢布尔雅那站",
                    "events",
                ),
                ("WTT Contender Series", "WTT挑战赛系列", "events"),
            ],
            entries,
        )


if __name__ == "__main__":
    unittest.main()
