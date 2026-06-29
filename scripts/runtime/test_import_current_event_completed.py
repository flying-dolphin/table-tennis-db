import sqlite3
import sys
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import wtt_import_shared as shared
from import_current_event_completed import (
    normalize_round_from_category,
    replace_match_children,
    split_rubber_player_names,
)


SCHEMA = """
CREATE TABLE current_event_team_ties (
    current_team_tie_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL
);
CREATE TABLE current_event_team_tie_sides (
    current_team_tie_side_id INTEGER PRIMARY KEY AUTOINCREMENT,
    current_team_tie_id INTEGER NOT NULL,
    side_no INTEGER NOT NULL,
    team_code TEXT
);
CREATE TABLE current_event_team_tie_side_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    current_team_tie_side_id INTEGER NOT NULL,
    player_order INTEGER NOT NULL,
    player_id INTEGER,
    player_name TEXT NOT NULL,
    player_country TEXT
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


class CompletedRubberRosterTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        cur = self.conn.cursor()
        cur.execute("INSERT INTO current_event_team_ties (current_team_tie_id, event_id) VALUES (1, 3216)")
        # Side 1 = FRA, side 2 = SWE; only some roster members have a player_id.
        cur.execute(
            "INSERT INTO current_event_team_tie_sides (current_team_tie_side_id, current_team_tie_id, side_no, team_code) VALUES (10, 1, 1, 'FRA')"
        )
        cur.execute(
            "INSERT INTO current_event_team_tie_sides (current_team_tie_side_id, current_team_tie_id, side_no, team_code) VALUES (20, 1, 2, 'SWE')"
        )
        roster = [
            (10, 1, 5001, "LEBRUN Alexis", "FRA"),
            (10, 2, 5002, "LEBRUN Felix", "FRA"),
            (10, 3, None, "COTON Flavien", "FRA"),  # not in players table
            (20, 1, 6001, "MOREGARD Truls", "SWE"),
            (20, 2, 6002, "KARLSSON Kristian", "SWE"),
        ]
        cur.executemany(
            "INSERT INTO current_event_team_tie_side_players (current_team_tie_side_id, player_order, player_id, player_name, player_country) VALUES (?, ?, ?, ?, ?)",
            roster,
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_load_roster_only_keeps_resolved_ids(self):
        roster = shared.load_event_roster_player_ids(self.conn.cursor(), 3216)
        self.assertEqual(5001, roster[("FRA", "LEBRUN ALEXIS")])
        self.assertEqual(6001, roster[("SWE", "MOREGARD TRULS")])
        # COTON has no player_id, so it is absent from the map.
        self.assertNotIn(("FRA", "COTON FLAVIEN"), roster)

    def test_resolve_is_team_scoped_and_case_insensitive(self):
        roster = shared.load_event_roster_player_ids(self.conn.cursor(), 3216)
        self.assertEqual(5002, shared.resolve_roster_player_id(roster, "fra", "lebrun felix"))
        # Same name attributed to the wrong team must not resolve.
        self.assertIsNone(shared.resolve_roster_player_id(roster, "SWE", "LEBRUN Felix"))
        self.assertIsNone(shared.resolve_roster_player_id(roster, "FRA", "COTON Flavien"))

    def test_replace_match_children_resolves_singles_rubber(self):
        roster = shared.load_event_roster_player_ids(self.conn.cursor(), 3216)
        cur = self.conn.cursor()
        replace_match_children(
            cur,
            current_match_id=100,
            side_a={"team_code": "FRA", "player_name": "LEBRUN Alexis", "player_country": "FRA", "is_winner": True},
            side_b={"team_code": "SWE", "player_name": "COTON Flavien", "player_country": "SWE", "is_winner": False},
            roster=roster,
        )
        rows = cur.execute(
            "SELECT player_name, player_id, player_order FROM current_event_match_side_players ORDER BY player_name"
        ).fetchall()
        resolved = {r["player_name"]: r["player_id"] for r in rows}
        self.assertEqual(5001, resolved["LEBRUN Alexis"])
        # Not in roster (no id) -> NULL fallback, name still stored.
        self.assertIsNone(resolved["COTON Flavien"])

    def test_replace_match_children_splits_doubles_rubber(self):
        roster = shared.load_event_roster_player_ids(self.conn.cursor(), 3216)
        cur = self.conn.cursor()
        replace_match_children(
            cur,
            current_match_id=101,
            side_a={"team_code": "FRA", "player_name": "LEBRUN Alexis / LEBRUN Felix", "player_country": "FRA", "is_winner": True},
            side_b={"team_code": "SWE", "player_name": "MOREGARD Truls / KARLSSON Kristian", "player_country": "SWE", "is_winner": False},
            roster=roster,
        )
        side_a_id = cur.execute(
            "SELECT current_match_side_id FROM current_event_match_sides WHERE current_match_id = 101 AND side_no = 1"
        ).fetchone()[0]
        players = cur.execute(
            "SELECT player_order, player_name, player_id FROM current_event_match_side_players WHERE current_match_side_id = ? ORDER BY player_order",
            (side_a_id,),
        ).fetchall()
        self.assertEqual(2, len(players))
        self.assertEqual((1, "LEBRUN Alexis", 5001), tuple(players[0]))
        self.assertEqual((2, "LEBRUN Felix", 5002), tuple(players[1]))

    def test_split_rubber_player_names(self):
        self.assertEqual(["A", "B"], split_rubber_player_names("A / B"))
        self.assertEqual(["Solo"], split_rubber_player_names("Solo"))
        self.assertEqual([], split_rubber_player_names(""))
        self.assertEqual([], split_rubber_player_names(None))


class NormalizeRoundFromCategoryTests(unittest.TestCase):
    def test_maps_main_draw_rounds(self):
        # Round of 64 / 128 / 256 previously fell through to (None, None), so the
        # completed/official-results path showed the raw English category label.
        cases = {
            "Women's Singles - Round of 256": ("MAIN_DRAW", "R256"),
            "Men's Singles - Round of 128": ("MAIN_DRAW", "R128"),
            "Women's Singles - Round of 64": ("MAIN_DRAW", "R64"),
            "Men's Singles - Round of 32": ("MAIN_DRAW", "R32"),
            "Women's Singles - Round of 16": ("MAIN_DRAW", "R16"),
            "Men's Singles - Quarter-Final": ("MAIN_DRAW", "QF"),
            "Women's Singles - Semi-Final": ("MAIN_DRAW", "SF"),
            "Men's Singles - Final": ("MAIN_DRAW", "F"),
        }
        for category, expected in cases.items():
            self.assertEqual(expected, normalize_round_from_category(category), category)

    def test_maps_qualifying_rounds(self):
        for n in (1, 2, 3):
            self.assertEqual(
                ("PRELIMINARY", f"R{n}"),
                normalize_round_from_category(f"Men's Singles - Qualifying Round {n}"),
            )

    def test_unknown_category_falls_back(self):
        self.assertEqual((None, None), normalize_round_from_category("Mixed Doubles - Something Odd"))


if __name__ == "__main__":
    unittest.main()
