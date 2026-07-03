import sqlite3
import sys
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from import_current_event_live import upsert_live_individual_match
from wtt_scrape_shared import normalize_live_result_item


SCHEMA = """
CREATE TABLE current_event_team_ties (
    current_team_tie_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    sub_event_type_code TEXT NOT NULL
);
CREATE TABLE current_event_matches (
    current_match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    current_team_tie_id INTEGER,
    sub_event_type_code TEXT NOT NULL,
    stage_label TEXT,
    stage_code TEXT,
    round_label TEXT,
    round_code TEXT,
    group_code TEXT,
    external_match_code TEXT,
    scheduled_local_at TEXT,
    scheduled_utc_at TEXT,
    table_no TEXT,
    session_label TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled',
    source_status TEXT,
    source_schedule_status TEXT,
    match_score TEXT,
    games TEXT,
    winner_side TEXT,
    winner_name TEXT,
    raw_source_payload TEXT,
    last_synced_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE current_event_match_sides (
    current_match_side_id INTEGER PRIMARY KEY AUTOINCREMENT,
    current_match_id INTEGER NOT NULL,
    side_no INTEGER NOT NULL,
    team_code TEXT,
    seed INTEGER,
    qualifier INTEGER,
    placeholder_text TEXT,
    is_winner INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE current_event_match_side_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    current_match_side_id INTEGER NOT NULL,
    player_order INTEGER NOT NULL,
    player_id INTEGER,
    player_name TEXT NOT NULL,
    player_country TEXT
);
CREATE TABLE players (
    player_id INTEGER PRIMARY KEY,
    name TEXT,
    name_zh TEXT
);
"""


class ImportCurrentEventLiveTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def tearDown(self):
        self.conn.close()

    def test_live_singles_result_imports_as_current_match(self):
        item = {
            "match_code": "TTEMSINGLES-----------RND1000100--",
            "source_status": "Live",
            "sub_event": "Men's Singles",
            "sub_event_name": "Men's Singles - Qualifying Round 1 - Match 1",
            "round": "RND1",
            "scheduled_start": "2026-06-26T10:00:00",
            "table_no": "Table 2",
            "session_label": "Match 1",
            "score": "2-1",
            "games": ["11-8", "8-11", "11-6"],
            "winner_side": None,
            "sides": [
                {
                    "organization": "USA",
                    "display_name": "LEFT Player",
                    "players": [{"name": "LEFT Player"}],
                },
                {
                    "organization": "IND",
                    "display_name": "RIGHT Player",
                    "players": [{"name": "RIGHT Player"}],
                },
            ],
        }

        result = upsert_live_individual_match(
            self.conn.cursor(),
            event_id=3242,
            item=item,
            now="2026-06-27T00:00:00+00:00",
        )

        self.assertTrue(result)
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM current_event_team_ties").fetchone()[0])
        match = self.conn.execute("SELECT * FROM current_event_matches").fetchone()
        self.assertEqual("MS", match["sub_event_type_code"])
        self.assertEqual("live", match["status"])
        self.assertEqual("Live", match["source_status"])
        self.assertEqual("2-1", match["match_score"])
        self.assertIsNone(match["winner_side"])
        self.assertIsNone(match["winner_name"])
        self.assertEqual("T02", match["table_no"])
        self.assertEqual(2, self.conn.execute("SELECT COUNT(*) FROM current_event_match_sides").fetchone()[0])
        self.assertEqual(2, self.conn.execute("SELECT COUNT(*) FROM current_event_match_side_players").fetchone()[0])

    def test_live_start_list_preserves_all_doubles_players(self):
        self.conn.executemany(
            "INSERT INTO players (player_id, name, name_zh) VALUES (?, ?, ?)",
            [
                (123682, "THAKKAR Manav", "萨卡尔·马纳夫"),
                (131879, "SHAH Manush", "沙·马努什"),
                (135996, "MATSUSHIMA Sora", "松岛辉空"),
                (133694, "TOGAMI Shunsuke", "户上隼辅"),
            ],
        )
        item = {
            "match_code": "TTEMDOUBLES-----------8FNL000700",
            "source_status": "Start List",
            "sub_event": "Men's Doubles",
            "round": "8FNL",
            "scheduled_start": "2026-06-30T20:55:00",
            "table_no": "T01",
            "session_label": "Men's Doubles - R16 - M 7",
            "score": None,
            "games": [],
            "winner_side": None,
            "sides": [
                {
                    "organization": "IND",
                    "display_name": "THAKKAR Manav/SHAH Manush",
                    "players": [
                        {"name": "THAKKAR Manav", "if_id": "123682", "organization": "IND"},
                        {"name": "SHAH Manush", "if_id": "131879", "organization": "IND"},
                    ],
                },
                {
                    "organization": "JPN",
                    "display_name": "MATSUSHIMA Sora/TOGAMI Shunsuke",
                    "players": [
                        {"name": "MATSUSHIMA Sora", "if_id": "135996", "organization": "JPN"},
                        {"name": "TOGAMI Shunsuke", "if_id": "133694", "organization": "JPN"},
                    ],
                },
            ],
        }

        result = upsert_live_individual_match(
            self.conn.cursor(),
            event_id=3242,
            item=item,
            now="2026-07-01T04:30:24+00:00",
        )

        self.assertTrue(result)
        match = self.conn.execute("SELECT * FROM current_event_matches").fetchone()
        self.assertEqual("scheduled", match["status"])
        players = self.conn.execute(
            """
            SELECT s.side_no, p.player_order, p.player_id, p.player_name, p.player_country
            FROM current_event_match_sides s
            JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
            ORDER BY s.side_no, p.player_order
            """
        ).fetchall()
        self.assertEqual(
            [
                (1, 1, 123682, "THAKKAR Manav", "IND"),
                (1, 2, 131879, "SHAH Manush", "IND"),
                (2, 1, 135996, "MATSUSHIMA Sora", "JPN"),
                (2, 2, 133694, "TOGAMI Shunsuke", "JPN"),
            ],
            [tuple(row) for row in players],
        )

    def test_live_result_normalization_preserves_match_card_player_ids(self):
        item = {
            "documentCode": "TTEMDOUBLES-----------QFNL000100----------",
            "status": "OFFICIAL",
            "match_card": {
                "documentCode": "TTEMDOUBLES-----------QFNL000100----------",
                "subEventName": "Men's Doubles",
                "resultStatus": "OFFICIAL",
                "competitiors": [
                    {
                        "competitiorName": "LIN Shidong/HUANG Youzheng",
                        "competitiorOrg": "CHN",
                        "players": [
                            {"playerId": "137237", "playerName": "LIN Shidong", "playerOrgCode": "CHN"},
                            {"playerId": "137238", "playerName": "HUANG Youzheng", "playerOrgCode": "CHN"},
                        ],
                    },
                    {
                        "competitiorName": "QUEK Izaac/PANG Koen",
                        "competitiorOrg": "SGP",
                        "players": [
                            {"playerId": "133713", "playerName": "QUEK Izaac", "playerOrgCode": "SGP"},
                            {"playerId": "131912", "playerName": "PANG Koen", "playerOrgCode": "SGP"},
                        ],
                    },
                ],
            },
        }

        normalized = normalize_live_result_item(item, {})

        self.assertEqual(
            [
                {"player_id": "137237", "name": "LIN Shidong", "organization": "CHN"},
                {"player_id": "137238", "name": "HUANG Youzheng", "organization": "CHN"},
            ],
            normalized["sides"][0]["players"],
        )
        self.assertEqual(
            [
                {"player_id": "133713", "name": "QUEK Izaac", "organization": "SGP"},
                {"player_id": "131912", "name": "PANG Koen", "organization": "SGP"},
            ],
            normalized["sides"][1]["players"],
        )

    def test_live_individual_import_uses_raw_match_card_player_ids_when_sides_are_empty(self):
        self.conn.executemany(
            "INSERT INTO players (player_id, name, name_zh) VALUES (?, ?, ?)",
            [
                (137237, "LIN Shidong", "林诗栋"),
                (137238, "HUANG Youzheng", "黄友政"),
                (133713, "QUEK Izaac", "郭以撒"),
                (131912, "PANG Koen", "庞 昆"),
            ],
        )
        item = {
            "match_code": "TTEMDOUBLES-----------QFNL000100",
            "source_status": "OFFICIAL",
            "sub_event": "MD",
            "sub_event_name": "Men's Doubles",
            "round": "QFNL",
            "scheduled_start": "07/02/2026 02:10:00",
            "table_no": "Table 1",
            "session_label": "Men's Doubles - QF - M 1",
            "score": "3-1",
            "games": ["11-9", "11-7", "4-11", "11-4", "0-0"],
            "winner_side": "A",
            "sides": [
                {"organization": "CHN", "display_name": "LIN Shidong/HUANG Youzheng", "players": []},
                {"organization": "SGP", "display_name": "QUEK Izaac/PANG Koen", "players": []},
            ],
            "raw_match_card": {
                "competitiors": [
                    {
                        "competitiorOrg": "CHN",
                        "players": [
                            {"playerId": "137237", "playerName": "LIN Shidong", "playerOrgCode": "CHN"},
                            {"playerId": "137238", "playerName": "HUANG Youzheng", "playerOrgCode": "CHN"},
                        ],
                    },
                    {
                        "competitiorOrg": "SGP",
                        "players": [
                            {"playerId": "133713", "playerName": "QUEK Izaac", "playerOrgCode": "SGP"},
                            {"playerId": "131912", "playerName": "PANG Koen", "playerOrgCode": "SGP"},
                        ],
                    },
                ],
            },
        }

        result = upsert_live_individual_match(
            self.conn.cursor(),
            event_id=3242,
            item=item,
            now="2026-07-02T03:00:00+00:00",
        )

        self.assertTrue(result)
        players = self.conn.execute(
            """
            SELECT s.side_no, p.player_order, p.player_id, p.player_name, p.player_country
            FROM current_event_match_sides s
            JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
            ORDER BY s.side_no, p.player_order
            """
        ).fetchall()
        self.assertEqual(
            [
                (1, 1, 137237, "LIN Shidong", "CHN"),
                (1, 2, 137238, "HUANG Youzheng", "CHN"),
                (2, 1, 133713, "QUEK Izaac", "SGP"),
                (2, 2, 131912, "PANG Koen", "SGP"),
            ],
            [tuple(row) for row in players],
        )


if __name__ == "__main__":
    unittest.main()
