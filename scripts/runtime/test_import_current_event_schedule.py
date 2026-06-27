import sqlite3
import sys
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from import_current_event_schedule import (
    cleanup_non_team_ties,
    load_existing_matches,
    load_existing_ties,
    load_player_ids_for_units,
    upsert_schedule_unit,
)


SCHEMA = """
CREATE TABLE players (
    player_id INTEGER PRIMARY KEY,
    name TEXT,
    country_code TEXT
);
CREATE TABLE current_event_team_ties (
    current_team_tie_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    sub_event_type_code TEXT NOT NULL,
    stage_label TEXT,
    stage_code TEXT,
    round_label TEXT,
    round_code TEXT,
    group_code TEXT,
    external_match_code TEXT,
    session_label TEXT,
    scheduled_local_at TEXT,
    scheduled_utc_at TEXT,
    table_no TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled',
    source_status TEXT,
    source_schedule_status TEXT,
    match_score TEXT,
    winner_side TEXT,
    winner_team_code TEXT,
    last_synced_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE current_event_team_tie_sides (
    current_team_tie_side_id INTEGER PRIMARY KEY AUTOINCREMENT,
    current_team_tie_id INTEGER NOT NULL,
    side_no INTEGER NOT NULL,
    team_code TEXT,
    team_name TEXT,
    seed INTEGER,
    qualifier INTEGER,
    is_winner INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE current_event_team_tie_side_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    current_team_tie_side_id INTEGER NOT NULL,
    player_order INTEGER NOT NULL,
    player_id INTEGER,
    player_name TEXT NOT NULL,
    player_country TEXT
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


def unit(sub_event: str, code: str, starts: list[dict]) -> dict:
    return {
        "Code": code,
        "SubEvent": sub_event,
        "Round": "RND1",
        "StartDate": "2026-06-26T10:00:00",
        "ScheduleStatus": "Scheduled",
        "Location": "T02",
        "ItemName": [{"Language": "ENG", "Value": f"{sub_event} - Qual. 1 - M 1"}],
        "StartList": {"Start": starts},
    }


def start(code: str, org: str, name: str, if_id: str, *, seed: int = 1) -> dict:
    family, _, given = name.partition(" ")
    return {
        "Competitor": {
            "Code": code,
            "Organization": org,
            "Seed": seed,
            "Qualifier": True,
            "Description": {"TeamName": name, "IfId": if_id},
            "Composition": {
                "Athlete": [
                    {
                        "Code": if_id,
                        "Order": 1,
                        "Description": {
                            "GivenName": given,
                            "FamilyName": family,
                            "Organization": org,
                            "IfId": if_id,
                        },
                    }
                ]
            },
        }
    }


def qualifier_placeholder(code: str, label: str, *, seed: int = 62) -> dict:
    return {
        "Competitor": {
            "Code": code,
            "Organization": "DEF",
            "Seed": seed,
            "Qualifier": True,
            "Description": {"TeamName": label, "IfId": code},
            "Composition": {
                "Athlete": [
                    {
                        "Code": code,
                        "Order": 1,
                        "Description": {
                            "GivenName": "",
                            "FamilyName": "",
                            "Organization": "DEF",
                            "IfId": code,
                        },
                    }
                ]
            },
        }
    }


class ImportCurrentEventScheduleTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def tearDown(self):
        self.conn.close()

    def test_singles_schedule_unit_imports_as_current_match(self):
        match_unit = unit(
            "Men's Singles",
            "TTEMSINGLES-----------RND1000100--",
            [
                start("101", "USA", "LEFT Player", "1001"),
                start("102", "IND", "RIGHT Player", "1002", seed=2),
            ],
        )
        player_ids = load_player_ids_for_units(self.conn.cursor(), [match_unit])

        result = upsert_schedule_unit(
            self.conn.cursor(),
            event_id=3242,
            event_time_zone=None,
            unit=match_unit,
            existing_rows=load_existing_ties(self.conn.cursor(), 3242),
            existing_matches=load_existing_matches(self.conn.cursor(), 3242),
            player_ids=player_ids,
        )

        self.assertEqual((True, "match", 2, 2), result)
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM current_event_team_ties").fetchone()[0])
        row = self.conn.execute("SELECT * FROM current_event_matches").fetchone()
        self.assertEqual("MS", row["sub_event_type_code"])
        self.assertIsNone(row["current_team_tie_id"])
        self.assertEqual("T02", row["table_no"])
        self.assertEqual(2, self.conn.execute("SELECT COUNT(*) FROM current_event_match_sides").fetchone()[0])
        self.assertEqual(2, self.conn.execute("SELECT COUNT(*) FROM current_event_match_side_players").fetchone()[0])

    def test_qualifier_placeholder_does_not_import_numeric_player_name(self):
        match_unit = unit(
            "Women's Singles",
            "TTEWSINGLES-----------R64-002500--",
            [
                start("135049", "CHN", "KUAI Man", "135049"),
                qualifier_placeholder("100258767", "Qualifier 6"),
            ],
        )
        player_ids = load_player_ids_for_units(self.conn.cursor(), [match_unit])

        result = upsert_schedule_unit(
            self.conn.cursor(),
            event_id=3242,
            event_time_zone=None,
            unit=match_unit,
            existing_rows=load_existing_ties(self.conn.cursor(), 3242),
            existing_matches=load_existing_matches(self.conn.cursor(), 3242),
            player_ids=player_ids,
        )

        self.assertEqual((True, "match", 2, 1), result)
        side = self.conn.execute(
            "SELECT * FROM current_event_match_sides WHERE side_no = 2",
        ).fetchone()
        self.assertEqual("资格赛晋级位 6", side["placeholder_text"])
        self.assertIsNone(side["team_code"])
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM current_event_match_side_players WHERE player_name = '100258767'",
            ).fetchone()[0],
        )

    def test_team_schedule_unit_imports_as_team_tie(self):
        team_unit = unit(
            "Men's Teams",
            "TTEMTEAM-------------GP01000100--",
            [
                start("CHN", "CHN", "China", "2001"),
                start("JPN", "JPN", "Japan", "2002", seed=2),
            ],
        )
        player_ids = load_player_ids_for_units(self.conn.cursor(), [team_unit])

        result = upsert_schedule_unit(
            self.conn.cursor(),
            event_id=3216,
            event_time_zone=None,
            unit=team_unit,
            existing_rows=load_existing_ties(self.conn.cursor(), 3216),
            existing_matches=load_existing_matches(self.conn.cursor(), 3216),
            player_ids=player_ids,
        )

        self.assertEqual((True, "team_tie", 2, 2), result)
        self.assertEqual(1, self.conn.execute("SELECT COUNT(*) FROM current_event_team_ties").fetchone()[0])
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM current_event_matches").fetchone()[0])

    def test_cleanup_non_team_ties_removes_bad_schedule_imports(self):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO current_event_team_ties (event_id, sub_event_type_code, external_match_code) VALUES (3242, 'MS', 'BAD')"
        )
        bad_tie_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO current_event_team_tie_sides (current_team_tie_id, side_no) VALUES (?, 1)",
            (bad_tie_id,),
        )
        bad_side_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO current_event_team_tie_side_players (current_team_tie_side_id, player_order, player_name) VALUES (?, 1, 'Bad Player')",
            (bad_side_id,),
        )
        cursor.execute(
            "INSERT INTO current_event_matches (event_id, current_team_tie_id, sub_event_type_code) VALUES (3242, ?, 'MS')",
            (bad_tie_id,),
        )
        bad_match_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO current_event_match_sides (current_match_id, side_no) VALUES (?, 1)",
            (bad_match_id,),
        )
        bad_match_side_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO current_event_match_side_players (current_match_side_id, player_order, player_name) VALUES (?, 1, 'Bad Player')",
            (bad_match_side_id,),
        )

        removed = cleanup_non_team_ties(cursor, 3242)

        self.assertEqual(1, removed)
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM current_event_team_ties").fetchone()[0])
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM current_event_team_tie_sides").fetchone()[0])
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM current_event_team_tie_side_players").fetchone()[0])
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM current_event_matches").fetchone()[0])
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM current_event_match_sides").fetchone()[0])
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM current_event_match_side_players").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
