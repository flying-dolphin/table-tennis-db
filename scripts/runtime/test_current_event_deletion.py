import sqlite3
import sys
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from import_current_event_completed import reset_tie_matches
from import_current_event_live import delete_current_event_team_tie


SCHEMA = """
CREATE TABLE current_event_team_ties (
    current_team_tie_id INTEGER PRIMARY KEY
);
CREATE TABLE current_event_team_tie_sides (
    current_team_tie_side_id INTEGER PRIMARY KEY,
    current_team_tie_id INTEGER NOT NULL
);
CREATE TABLE current_event_team_tie_side_players (
    current_team_tie_side_player_id INTEGER PRIMARY KEY,
    current_team_tie_side_id INTEGER NOT NULL
);
CREATE TABLE current_event_matches (
    current_match_id INTEGER PRIMARY KEY,
    current_team_tie_id INTEGER
);
CREATE TABLE current_event_match_sides (
    current_match_side_id INTEGER PRIMARY KEY,
    current_match_id INTEGER NOT NULL
);
CREATE TABLE current_event_match_side_players (
    current_match_side_player_id INTEGER PRIMARY KEY,
    current_match_side_id INTEGER NOT NULL
);
"""


class CurrentEventDeletionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(SCHEMA)
        self._insert_tree(1, 10, 100, 1000)
        self._insert_tree(2, 20, 200, 2000)

    def tearDown(self):
        self.conn.close()

    def _insert_tree(self, tie_id, tie_side_id, match_id, match_side_id):
        self.conn.execute(
            "INSERT INTO current_event_team_ties (current_team_tie_id) VALUES (?)",
            (tie_id,),
        )
        self.conn.execute(
            """
            INSERT INTO current_event_team_tie_sides (
                current_team_tie_side_id, current_team_tie_id
            ) VALUES (?, ?)
            """,
            (tie_side_id, tie_id),
        )
        self.conn.execute(
            """
            INSERT INTO current_event_team_tie_side_players (
                current_team_tie_side_player_id, current_team_tie_side_id
            ) VALUES (?, ?)
            """,
            (tie_side_id, tie_side_id),
        )
        self.conn.execute(
            """
            INSERT INTO current_event_matches (
                current_match_id, current_team_tie_id
            ) VALUES (?, ?)
            """,
            (match_id, tie_id),
        )
        self.conn.execute(
            """
            INSERT INTO current_event_match_sides (
                current_match_side_id, current_match_id
            ) VALUES (?, ?)
            """,
            (match_side_id, match_id),
        )
        self.conn.execute(
            """
            INSERT INTO current_event_match_side_players (
                current_match_side_player_id, current_match_side_id
            ) VALUES (?, ?)
            """,
            (match_side_id, match_side_id),
        )
        self.conn.commit()

    def count(self, table, column, value):
        return self.conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} = ?",
            (value,),
        ).fetchone()[0]

    def test_reset_tie_matches_deletes_match_children_only(self):
        reset_tie_matches(self.conn.cursor(), 1)

        self.assertEqual(0, self.count("current_event_matches", "current_team_tie_id", 1))
        self.assertEqual(0, self.count("current_event_match_sides", "current_match_id", 100))
        self.assertEqual(
            0,
            self.count(
                "current_event_match_side_players",
                "current_match_side_id",
                1000,
            ),
        )
        self.assertEqual(1, self.count("current_event_team_ties", "current_team_tie_id", 1))
        self.assertEqual(1, self.count("current_event_matches", "current_team_tie_id", 2))

    def test_delete_team_tie_deletes_full_tree(self):
        delete_current_event_team_tie(self.conn.cursor(), 1)

        self.assertEqual(0, self.count("current_event_team_ties", "current_team_tie_id", 1))
        self.assertEqual(
            0,
            self.count(
                "current_event_team_tie_sides",
                "current_team_tie_id",
                1,
            ),
        )
        self.assertEqual(
            0,
            self.count(
                "current_event_team_tie_side_players",
                "current_team_tie_side_id",
                10,
            ),
        )
        self.assertEqual(0, self.count("current_event_matches", "current_team_tie_id", 1))
        self.assertEqual(0, self.count("current_event_match_sides", "current_match_id", 100))
        self.assertEqual(
            0,
            self.count(
                "current_event_match_side_players",
                "current_match_side_id",
                1000,
            ),
        )
        self.assertEqual(1, self.count("current_event_team_ties", "current_team_tie_id", 2))


if __name__ == "__main__":
    unittest.main()
