#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backfill_historical_data as backfill


class BackfillHistoricalDataTests(unittest.TestCase):
    def test_event_match_url_plan_includes_filtering_only_and_skips_existing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events_dir = root / "events"
            output_dir = root / "event_matches" / "orig"
            problematic_dir = root / "event_matches" / "problematic"
            events_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            problematic_dir.mkdir(parents=True)

            (events_dir / "events.json").write_text(
                json.dumps(
                    {
                        "events": [
                            {
                                "event_id": 1001,
                                "name": "Alpha Event",
                                "matches_href": "/index.php/event-matches/list/68?abc=1001",
                                "filtering_only": False,
                            },
                            {
                                "event_id": 1002,
                                "name": "Beta Event",
                                "matches_href": "/index.php/event-matches/list/68?abc=1002",
                                "filtering_only": True,
                            },
                            {
                                "event_id": 1003,
                                "name": "Gamma Event",
                                "matches_href": "/index.php/event-matches/list/68?abc=1003",
                                "filtering_only": False,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "Alpha_Event_1001.json").write_text(
                json.dumps({"event_id": "1001", "matches": []}),
                encoding="utf-8",
            )
            (problematic_dir / "Gamma_Event_1003.json").write_text(
                json.dumps({"event_id": "1003", "validation_error": "bad"}),
                encoding="utf-8",
            )

            plan = backfill.build_event_match_url_plan(
                events_dir=events_dir,
                output_dir=output_dir,
                problematic_dir=problematic_dir,
            )

            self.assertEqual(
                [
                    {
                        "event_id": "1002",
                        "event_name": "Beta Event",
                        "filtering_only": True,
                        "url": "https://results.ittf.link/index.php/event-matches/list/68?abc=1002",
                    }
                ],
                plan["pending"],
            )
            self.assertEqual(2, plan["completed_count"])
            self.assertEqual(1, plan["filtering_only_count"])

    def test_profile_search_names_merge_match_names_db_names_and_cache_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            matches_dir = root / "matches"
            cache_path = root / "profile_search_candidates.json"
            db_path = root / "ittf.db"
            matches_dir.mkdir()

            (matches_dir / "Alpha_1001.json").write_text(
                json.dumps(
                    {
                        "matches": [
                            {"side_a": ["Sun Yingsha (CHN)"], "side_b": ["Player New (JPN)"]},
                            {"side_a": ["WANG Chuqin (CHN)"], "side_b": ["Sun Yingsha (CHN)"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            cache_path.write_text(
                json.dumps(
                    {
                        "sun yingsha": {
                            "last_checked_at": "2026-01-01T00:00:00Z",
                            "candidates": [{"player_id": 1, "display_name": "Sun Yingsha", "country_code": "CHN"}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE players (player_id INTEGER PRIMARY KEY, name TEXT, country_code TEXT)")
            conn.executemany(
                "INSERT INTO players (player_id, name, country_code) VALUES (?, ?, ?)",
                [(1, "Sun Yingsha", "CHN"), (2, "DB Only", "KOR")],
            )
            conn.commit()
            conn.close()

            selected = backfill.build_profile_search_plan(
                event_matches_dir=matches_dir,
                db_path=db_path,
                cache_path=cache_path,
                refresh_names=["Sun Yingsha"],
            )

            self.assertEqual(
                ["DB Only", "Player New", "Sun Yingsha", "WANG Chuqin"],
                [item["name"] for item in selected["pending"]],
            )
            self.assertEqual(1, selected["cached_count"])


if __name__ == "__main__":
    unittest.main()
