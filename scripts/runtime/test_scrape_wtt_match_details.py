import json
import sys
import tempfile
import unittest
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import brotli


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import scrape_wtt_match_details as details


class ScrapeWttMatchDetailsTests(unittest.TestCase):
    def test_selects_official_missing_from_results_and_current_live_codes_only(self):
        schedule_payload = [
            {
                "Competition": {
                    "Unit": [
                        {
                            "Code": "TTEWSINGLES-----------R64-001300--",
                            "ScheduleStatus": "Official",
                        },
                        {
                            "Code": "TTEWSINGLES-----------R64-001400--",
                            "ScheduleStatus": "Official",
                        },
                        {
                            "Code": "TTEWSINGLES-----------R32-000900--",
                            "ScheduleStatus": "Scheduled",
                        },
                    ]
                }
            }
        ]
        official_results = [
            {"documentCode": "TTEWSINGLES-----------R64-001400----------"},
        ]
        live_payload = {
            "matches": [
                {"match_code": "TTEMSINGLES-----------R64-002200", "source_status": "Live"},
            ]
        }

        selected = details.select_match_detail_codes(schedule_payload, official_results, live_payload)

        self.assertEqual(
            [
                details.MatchDetailTarget("TTEWSINGLES-----------R64-001300", "missing_official"),
                details.MatchDetailTarget("TTEMSINGLES-----------R64-002200", "live"),
            ],
            selected,
        )

    def test_selects_upcoming_schedule_and_db_backlog_codes(self):
        schedule_payload = [
            {
                "Competition": {
                    "Unit": [
                        {
                            "Code": "TTEWSINGLES-----------R32-000900--",
                            "ScheduleStatus": "Scheduled",
                            "StartDate": "2026-07-01T12:10:00",
                        },
                        {
                            "Code": "TTEWSINGLES-----------R32-001000--",
                            "ScheduleStatus": "Scheduled",
                            "StartDate": "2026-07-01T12:20:00",
                        },
                    ]
                }
            }
        ]
        now = datetime(2026, 7, 1, 4, 0, tzinfo=timezone.utc)

        selected = details.select_match_detail_codes(
            schedule_payload,
            [],
            {"matches": []},
            now_utc=now,
            event_time_zone="Asia/Shanghai",
            db_codes=[
                details.MatchDetailTarget("TTEMSINGLES-----------R64-002200", "db_live"),
                details.MatchDetailTarget("TTEMDOUBLES-----------8FNL000700", "db_scheduled"),
            ],
        )

        self.assertEqual(
            [
                details.MatchDetailTarget("TTEWSINGLES-----------R32-000900", "upcoming"),
                details.MatchDetailTarget("TTEMSINGLES-----------R64-002200", "db_live"),
                details.MatchDetailTarget("TTEMDOUBLES-----------8FNL000700", "db_scheduled"),
            ],
            selected,
        )

    def test_load_db_match_detail_targets_selects_pending_live_and_incomplete_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ittf.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE current_event_matches (
                    event_id INTEGER,
                    external_match_code TEXT,
                    status TEXT,
                    match_score TEXT,
                    games TEXT
                )
                """
            )
            conn.executemany(
                "INSERT INTO current_event_matches VALUES (?, ?, ?, ?, ?)",
                [
                    (3242, "A----------", "scheduled", None, None),
                    (3242, "B----------", "live", "1-1", '["11-9"]'),
                    (3242, "C----------", "completed", None, "[]"),
                    (3242, "D----------", "completed", "3-0", '["11-8"]'),
                    (9999, "E----------", "scheduled", None, None),
                ],
            )
            conn.commit()
            conn.close()

            targets = details.load_db_match_detail_targets(db_path, 3242)

        self.assertEqual(
            [
                details.MatchDetailTarget("A", "db_scheduled"),
                details.MatchDetailTarget("B", "db_live"),
                details.MatchDetailTarget("C", "db_completed_missing_score"),
            ],
            targets,
        )

    def test_scrape_summary_counts_static_and_official_query_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp) / "3242"
            event_dir.mkdir()
            (event_dir / "GetEventSchedule.json").write_text("[]", encoding="utf-8")
            (event_dir / "GetOfficialResult.json").write_text("[]", encoding="utf-8")
            (event_dir / "GetLiveResult.json").write_text(
                json.dumps(
                    {
                        "summary": {"event_id": 3242},
                        "matches": [
                            {"match_code": "TTEWSINGLES-----------R64-001300", "source_status": "Live"},
                            {"match_code": "TTEMSINGLES-----------R64-002200", "source_status": "Live"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            cards = {
                "TTEWSINGLES-----------R64-001300": (
                    "https://static.example/card.json",
                    {
                        "eventId": "3242",
                        "documentCode": "TTEWSINGLES-----------R64-001300----------",
                        "subEventName": "Women's Singles",
                        "resultStatus": "LIVE",
                    },
                    "static_matchdata",
                ),
                "TTEMSINGLES-----------R64-002200": (
                    "https://api.example/card.json",
                    {
                        "eventId": "3242",
                        "documentCode": "TTEMSINGLES-----------R64-002200----------",
                        "subEventName": "Men's Singles",
                        "resultStatus": "OFFICIAL",
                    },
                    "official_query",
                ),
            }

            def fake_fetch(event_id, match_code):
                return cards[match_code]

            with patch.object(details, "fetch_match_card", side_effect=fake_fetch):
                summary = details.scrape_match_details_only(3242, event_dir, db_path=Path(tmp) / "missing.db")

        self.assertEqual(2, summary["fetched"])
        self.assertEqual(
            {"static_matchdata": 1, "official_query": 1},
            summary["source_counts"],
        )

    def test_full_document_code_pads_normalized_code(self):
        self.assertEqual(
            "TTEWSINGLES-----------R64-001300----------",
            details.full_document_code("TTEWSINGLES-----------R64-001300--"),
        )

    def test_decode_response_body_handles_brotli_json(self):
        response = Mock()
        response.headers = {"Content-Encoding": "br"}
        payload = {"documentCode": "TTEWSINGLES-----------R64-001300----------"}

        decoded = details.decode_response_body(response, brotli.compress(json.dumps(payload).encode("utf-8")))

        self.assertEqual(payload, json.loads(decoded.decode("utf-8")))

    def test_merge_match_cards_splits_official_and_live_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp) / "3242"
            event_dir.mkdir()
            (event_dir / "GetOfficialResult.json").write_text("[]", encoding="utf-8")
            (event_dir / "GetLiveResult.json").write_text(
                json.dumps({"summary": {"event_id": 3242}, "matches": []}),
                encoding="utf-8",
            )
            schedule_payload = [
                {
                    "Competition": {
                        "Unit": [
                            {
                                "Code": "TTEWSINGLES-----------R64-001300--",
                                "SubEvent": "Women's Singles",
                                "Round": "R64-",
                                "StartDate": "2026-06-29T19:10:00",
                                "Location": "T03",
                                "ItemName": [{"Language": "ENG", "Value": "Women's Singles - R64 - M 13"}],
                                "StartList": {"Start": []},
                            },
                            {
                                "Code": "TTEMSINGLES-----------R64-002200--",
                                "SubEvent": "Men's Singles",
                                "Round": "R64-",
                                "StartDate": "2026-06-29T19:45:00",
                                "Location": "T03",
                                "ItemName": [{"Language": "ENG", "Value": "Men's Singles - R64 - M 22"}],
                                "StartList": {"Start": []},
                            },
                        ]
                    }
                }
            ]
            completed_card = {
                "eventId": "3242",
                "documentCode": "TTEWSINGLES-----------R64-001300----------",
                "subEventName": "Women's Singles",
                "subEventDescription": "Women's Singles - Round of 64 - Match 13",
                "resultStatus": "OFFICIAL",
                "resultOverallScores": "3-0",
                "resultsGameScores": "11-8,16-14,11-3",
                "competitiors": [{"competitiorName": "ODO Satsuki"}, {"competitiorName": "LEE Eunhye"}],
            }
            live_card = {
                "eventId": "3242",
                "documentCode": "TTEMSINGLES-----------R64-002200----------",
                "subEventName": "Men's Singles",
                "subEventDescription": "Men's Singles - Round of 64 - Match 22",
                "resultStatus": "LIVE",
                "resultOverallScores": "2-1",
                "resultsGameScores": "11-7,8-11,11-6",
                "competitiors": [{"competitiorName": "JARVIS Tom"}, {"competitiorName": "OH Junsung"}],
            }

            report = details.merge_match_cards(
                event_dir,
                3242,
                schedule_payload,
                [completed_card, live_card],
            )

            self.assertEqual(1, report["official_added"])
            self.assertEqual(1, report["live_added"])
            official = json.loads((event_dir / "GetOfficialResult.json").read_text(encoding="utf-8"))
            live = json.loads((event_dir / "GetLiveResult.json").read_text(encoding="utf-8"))
            self.assertEqual("3-0", official[0]["match_card"]["resultOverallScores"])
            self.assertEqual("TTEMSINGLES-----------R64-002200", live["matches"][0]["match_code"])
            self.assertEqual("2-1", live["matches"][0]["score"])


if __name__ == "__main__":
    unittest.main()
