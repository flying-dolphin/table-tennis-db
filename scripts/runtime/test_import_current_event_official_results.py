import sqlite3
import sys
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from import_current_event_official_results import upsert_official_individual_match


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
"""


def competitor(name: str, org: str, player_id: str) -> dict:
    return {
        "competitiorName": name,
        "competitiorOrg": org,
        "players": [
            {
                "playerId": player_id,
                "playerName": name,
                "playerOrgCode": org,
                "playerPosition": 1,
            }
        ],
    }


class ImportCurrentEventOfficialResultsTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def tearDown(self):
        self.conn.close()

    def test_official_singles_result_imports_as_current_match(self):
        item = {
            "documentCode": "TTEMSINGLES-----------RND1000100--",
            "subEventType": "Men's Singles",
            "match_card": {
                "documentCode": "TTEMSINGLES-----------RND1000100--",
                "subEventName": "Men's Singles",
                "subEventDescription": "Men's Singles - Qualifying Round 1 - Match 1",
                "tableName": "Table 2",
                "competitiors": [
                    competitor("LEFT Player", "USA", "1001"),
                    competitor("RIGHT Player", "IND", "1002"),
                ],
                "resultOverallScores": "3-1",
                "resultsGameScores": "11:8,8:11,11:6,11:5",
                "matchDateTime": {"startDateLocal": "06/26/2026 10:00:00"},
            },
        }

        upsert_official_individual_match(
            self.conn.cursor(),
            event_id=3242,
            item=item,
            sub_event_type_code="MS",
            category="Men's Singles - Qualifying Round 1",
            event_time_zone="America/Los_Angeles",
        )

        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM current_event_team_ties").fetchone()[0])
        match = self.conn.execute("SELECT * FROM current_event_matches").fetchone()
        self.assertEqual("MS", match["sub_event_type_code"])
        self.assertEqual("completed", match["status"])
        self.assertEqual("Official", match["source_status"])
        self.assertEqual("3-1", match["match_score"])
        self.assertEqual("A", match["winner_side"])
        self.assertEqual("LEFT Player", match["winner_name"])
        self.assertEqual("T02", match["table_no"])
        self.assertEqual("PRELIMINARY", match["stage_code"])
        self.assertEqual("R1", match["round_code"])
        self.assertEqual("2026-06-26T17:00:00+00:00", match["scheduled_utc_at"])
        self.assertEqual(2, self.conn.execute("SELECT COUNT(*) FROM current_event_match_sides").fetchone()[0])
        self.assertEqual(2, self.conn.execute("SELECT COUNT(*) FROM current_event_match_side_players").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
