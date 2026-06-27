import sqlite3
import sys
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from import_current_event_live import upsert_live_individual_match


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


if __name__ == "__main__":
    unittest.main()
