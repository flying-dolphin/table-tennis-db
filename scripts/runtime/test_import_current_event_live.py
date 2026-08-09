import sqlite3
import sys
import unittest
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from import_current_event_live import (
    sync_team_tie_from_live_match,
    upsert_live_individual_match,
    upsert_live_rubber,
    upsert_live_team_tie,
)
from wtt_scrape_shared import normalize_live_result_item


SCHEMA = """
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

    def insert_official_individual_match(self, external_match_code="OFFICIAL-INDIVIDUAL"):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO current_event_matches (
                event_id, sub_event_type_code, external_match_code, status, source_status,
                match_score, games, winner_side, winner_name, raw_source_payload
            ) VALUES (3242, 'MS', ?, 'completed', 'Official', '3-1', '["11-8", "11-7"]',
                      'A', 'Official Winner', '{"source": "official"}')
            """,
            (external_match_code,),
        )
        current_match_id = int(cursor.lastrowid)
        for side_no, name, is_winner in (
            (1, "Official Winner", 1),
            (2, "Official Runner-up", 0),
        ):
            cursor.execute(
                """
                INSERT INTO current_event_match_sides (
                    current_match_id, side_no, team_code, is_winner
                ) VALUES (?, ?, ?, ?)
                """,
                (current_match_id, side_no, "AAA" if side_no == 1 else "BBB", is_winner),
            )
            cursor.execute(
                """
                INSERT INTO current_event_match_side_players (
                    current_match_side_id, player_order, player_name, player_country
                ) VALUES (?, 1, ?, ?)
                """,
                (int(cursor.lastrowid), name, "AAA" if side_no == 1 else "BBB"),
            )
        return current_match_id

    def insert_official_team_tie(self, external_match_code="OFFICIAL-TEAM-TIE"):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO current_event_team_ties (
                event_id, sub_event_type_code, stage_label, stage_code, round_label, round_code,
                external_match_code, session_label, table_no, status, source_status, match_score,
                winner_side, winner_team_code
            ) VALUES (3242, 'MT', 'Main Draw', 'MAIN_DRAW', 'Final', 'F', ?, 'Match 1',
                      'T01', 'completed', 'Official', '3-1', 'A', 'AAA')
            """,
            (external_match_code,),
        )
        current_team_tie_id = int(cursor.lastrowid)
        for side_no, team_code, player_name, is_winner in (
            (1, "AAA", "Official A", 1),
            (2, "BBB", "Official B", 0),
        ):
            cursor.execute(
                """
                INSERT INTO current_event_team_tie_sides (
                    current_team_tie_id, side_no, team_code, team_name, is_winner
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (current_team_tie_id, side_no, team_code, team_code, is_winner),
            )
            cursor.execute(
                """
                INSERT INTO current_event_team_tie_side_players (
                    current_team_tie_side_id, player_order, player_name, player_country
                ) VALUES (?, 1, ?, ?)
                """,
                (int(cursor.lastrowid), player_name, team_code),
            )
        return self.conn.execute(
            "SELECT * FROM current_event_team_ties WHERE current_team_tie_id = ?",
            (current_team_tie_id,),
        ).fetchone()

    def insert_official_rubber(self, tie_row, rubber_order=1):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO current_event_matches (
                event_id, current_team_tie_id, sub_event_type_code, external_match_code,
                status, source_status, match_score, games, winner_side, raw_source_payload
            ) VALUES (3242, ?, 'MT', ?, 'completed', 'Completed', '3-0', '["11-8", "11-7"]',
                      'A', '{"source": "official"}')
            """,
            (int(tie_row["current_team_tie_id"]), f'{tie_row["external_match_code"]}::R{rubber_order}'),
        )
        current_match_id = int(cursor.lastrowid)
        for side_no, name, is_winner in (
            (1, "Official A", 1),
            (2, "Official B", 0),
        ):
            cursor.execute(
                """
                INSERT INTO current_event_match_sides (
                    current_match_id, side_no, team_code, is_winner
                ) VALUES (?, ?, ?, ?)
                """,
                (current_match_id, side_no, "AAA" if side_no == 1 else "BBB", is_winner),
            )
            cursor.execute(
                """
                INSERT INTO current_event_match_side_players (
                    current_match_side_id, player_order, player_name, player_country
                ) VALUES (?, 1, ?, ?)
                """,
                (int(cursor.lastrowid), name, "AAA" if side_no == 1 else "BBB"),
            )
        return current_match_id

    def live_individual_item(self, external_match_code, source_status="Start List"):
        return {
            "match_code": external_match_code,
            "source_status": source_status,
            "sub_event": "Men's Singles",
            "round": "RND1",
            "score": None if source_status == "Start List" else "1-0",
            "games": [] if source_status == "Start List" else ["11-5"],
            "winner_side": None,
            "sides": [
                {"organization": "AAA", "display_name": "Live A", "players": [{"name": "Live A"}]},
                {"organization": "BBB", "display_name": "Live B", "players": [{"name": "Live B"}]},
            ],
        }

    def live_team_item(self, external_match_code, source_status="Start List"):
        return {
            "match_code": external_match_code,
            "source_status": source_status,
            "sub_event": "Men's Teams",
            "sub_event_name": "Men's Teams - Final - Match 1",
            "round": "FNL",
            "table_no": "T01",
            "session_label": "Match 1",
            "score": None if source_status == "Start List" else "1-0",
            "games": [],
            "winner_side": None,
            "sides": [
                {"organization": "AAA", "display_name": "AAA", "players": [{"name": "Live A"}]},
                {"organization": "BBB", "display_name": "BBB", "players": [{"name": "Live B"}]},
            ],
        }

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

    def test_live_individual_update_preserves_existing_official_final_result(self):
        current_match_id = self.insert_official_individual_match()
        before_match = tuple(
            self.conn.execute(
                """
                SELECT status, source_status, match_score, games, winner_side, winner_name, raw_source_payload
                FROM current_event_matches WHERE current_match_id = ?
                """,
                (current_match_id,),
            ).fetchone()
        )
        before_players = self.conn.execute(
            """
            SELECT s.side_no, s.is_winner, p.player_name
            FROM current_event_match_sides s
            JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
            WHERE s.current_match_id = ? ORDER BY s.side_no
            """,
            (current_match_id,),
        ).fetchall()

        result = upsert_live_individual_match(
            self.conn.cursor(),
            event_id=3242,
            item=self.live_individual_item("OFFICIAL-INDIVIDUAL"),
            now="2026-07-02T03:00:00+00:00",
        )

        self.assertTrue(result)
        after_match = tuple(
            self.conn.execute(
                """
                SELECT status, source_status, match_score, games, winner_side, winner_name, raw_source_payload
                FROM current_event_matches WHERE current_match_id = ?
                """,
                (current_match_id,),
            ).fetchone()
        )
        after_players = self.conn.execute(
            """
            SELECT s.side_no, s.is_winner, p.player_name
            FROM current_event_match_sides s
            JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
            WHERE s.current_match_id = ? ORDER BY s.side_no
            """,
            (current_match_id,),
        ).fetchall()
        self.assertEqual(before_match, after_match)
        self.assertEqual([tuple(row) for row in before_players], [tuple(row) for row in after_players])

    def test_official_individual_update_can_correct_existing_official_final_result(self):
        current_match_id = self.insert_official_individual_match()
        self.conn.execute(
            """
            UPDATE current_event_matches
            SET match_score = '3-0', games = '["11-8", "11-7", "11-6"]'
            WHERE current_match_id = ?
            """,
            (current_match_id,),
        )
        official = self.live_individual_item("OFFICIAL-INDIVIDUAL", source_status="oFfIcIaL")
        official.update(
            {
                "score": "3-1",
                "games": ["11-8", "8-11", "11-6", "11-7"],
                "winner_side": "A",
                "sides": [
                    {
                        "organization": "AAA",
                        "display_name": "Corrected Winner",
                        "players": [{"name": "Corrected Winner"}],
                    },
                    {
                        "organization": "BBB",
                        "display_name": "Corrected Runner-up",
                        "players": [{"name": "Corrected Runner-up"}],
                    },
                ],
            }
        )

        result = upsert_live_individual_match(
            self.conn.cursor(),
            event_id=3242,
            item=official,
            now="2026-07-02T03:01:00+00:00",
        )

        self.assertTrue(result)
        match = self.conn.execute(
            """
            SELECT status, source_status, match_score, games, winner_side, winner_name
            FROM current_event_matches WHERE current_match_id = ?
            """,
            (current_match_id,),
        ).fetchone()
        self.assertEqual(
            ("completed", "oFfIcIaL", "3-1", '["11-8", "8-11", "11-6", "11-7"]', "A", "Corrected Winner"),
            tuple(match),
        )
        players = self.conn.execute(
            """
            SELECT s.side_no, s.is_winner, p.player_name
            FROM current_event_match_sides s
            JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
            WHERE s.current_match_id = ? ORDER BY s.side_no
            """,
            (current_match_id,),
        ).fetchall()
        self.assertEqual(
            [(1, 1, "Corrected Winner"), (2, 0, "Corrected Runner-up")],
            [tuple(row) for row in players],
        )

    def test_live_team_tie_update_preserves_official_tie_and_completed_child(self):
        tie_row = self.insert_official_team_tie()
        current_match_id = self.insert_official_rubber(tie_row)

        updated_tie = upsert_live_team_tie(
            self.conn.cursor(),
            event_id=3242,
            item=self.live_team_item("OFFICIAL-TEAM-TIE"),
            now="2026-07-02T03:00:00+00:00",
        )

        self.assertEqual(
            ("completed", "Official", "3-1", "A", "AAA"),
            tuple(updated_tie[key] for key in ("status", "source_status", "match_score", "winner_side", "winner_team_code")),
        )
        self.assertEqual(
            [(1, 1), (2, 0)],
            [tuple(row) for row in self.conn.execute(
                "SELECT side_no, is_winner FROM current_event_team_tie_sides WHERE current_team_tie_id = ? ORDER BY side_no",
                (int(tie_row["current_team_tie_id"]),),
            )],
        )
        child = self.conn.execute(
            "SELECT status, source_status, match_score, games, winner_side FROM current_event_matches WHERE current_match_id = ?",
            (current_match_id,),
        ).fetchone()
        self.assertEqual(("completed", "Completed", "3-0", '["11-8", "11-7"]', "A"), tuple(child))

    def test_official_team_tie_update_can_correct_existing_official_final_result(self):
        tie_row = self.insert_official_team_tie()
        self.conn.execute(
            "UPDATE current_event_team_ties SET match_score = '3-0' WHERE current_team_tie_id = ?",
            (int(tie_row["current_team_tie_id"]),),
        )
        official = self.live_team_item("OFFICIAL-TEAM-TIE", source_status="OFFICIAL")
        official["score"] = "2-3"

        updated_tie = upsert_live_team_tie(
            self.conn.cursor(),
            event_id=3242,
            item=official,
            now="2026-07-02T03:01:00+00:00",
        )
        sync_team_tie_from_live_match(
            self.conn.cursor(), int(updated_tie["current_team_tie_id"]), official
        )

        updated_tie = self.conn.execute(
            "SELECT * FROM current_event_team_ties WHERE current_team_tie_id = ?",
            (int(tie_row["current_team_tie_id"]),),
        ).fetchone()
        self.assertEqual(
            ("completed", "OFFICIAL", "2-3", "B", "BBB"),
            tuple(updated_tie[key] for key in ("status", "source_status", "match_score", "winner_side", "winner_team_code")),
        )
        sides = self.conn.execute(
            """
            SELECT s.side_no, s.is_winner, p.player_name
            FROM current_event_team_tie_sides s
            JOIN current_event_team_tie_side_players p
              ON p.current_team_tie_side_id = s.current_team_tie_side_id
            WHERE s.current_team_tie_id = ? ORDER BY s.side_no
            """,
            (int(tie_row["current_team_tie_id"]),),
        ).fetchall()
        self.assertEqual(
            [(1, 0, "Live A"), (2, 1, "Live B")],
            [tuple(row) for row in sides],
        )

    def test_live_rubber_and_parent_sync_preserve_official_completed_rubber(self):
        tie_row = self.insert_official_team_tie()
        current_match_id = self.insert_official_rubber(tie_row)
        before_players = self.conn.execute(
            """
            SELECT s.side_no, s.is_winner, p.player_name
            FROM current_event_match_sides s
            JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
            WHERE s.current_match_id = ? ORDER BY s.side_no
            """,
            (current_match_id,),
        ).fetchall()
        live_match = self.live_team_item("OFFICIAL-TEAM-TIE", source_status="Live")

        upsert_live_rubber(
            self.conn.cursor(),
            event_id=3242,
            tie_row=tie_row,
            live_match=live_match,
            individual_match={
                "player_a": "Live A",
                "player_b": "Live B",
                "match_score": "1-0",
                "games": ["11-5"],
            },
            rubber_order=1,
        )
        sync_team_tie_from_live_match(
            self.conn.cursor(), int(tie_row["current_team_tie_id"]), live_match
        )

        rubber = self.conn.execute(
            """
            SELECT status, source_status, match_score, games, winner_side, raw_source_payload
            FROM current_event_matches WHERE current_match_id = ?
            """,
            (current_match_id,),
        ).fetchone()
        self.assertEqual(
            ("completed", "Completed", "3-0", '["11-8", "11-7"]', "A", '{"source": "official"}'),
            tuple(rubber),
        )
        after_players = self.conn.execute(
            """
            SELECT s.side_no, s.is_winner, p.player_name
            FROM current_event_match_sides s
            JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
            WHERE s.current_match_id = ? ORDER BY s.side_no
            """,
            (current_match_id,),
        ).fetchall()
        self.assertEqual([tuple(row) for row in before_players], [tuple(row) for row in after_players])

    def test_official_rubber_update_can_correct_existing_official_final_result(self):
        tie_row = self.insert_official_team_tie()
        current_match_id = self.insert_official_rubber(tie_row)
        official = self.live_team_item("OFFICIAL-TEAM-TIE", source_status="Completed")

        upsert_live_rubber(
            self.conn.cursor(),
            event_id=3242,
            tie_row=tie_row,
            live_match=official,
            individual_match={
                "player_a": "Corrected A",
                "player_b": "Corrected B",
                "match_score": "3-1",
                "games": ["11-8", "8-11", "11-6", "11-7"],
            },
            rubber_order=1,
        )

        rubber = self.conn.execute(
            """
            SELECT status, source_status, match_score, games, winner_side
            FROM current_event_matches WHERE current_match_id = ?
            """,
            (current_match_id,),
        ).fetchone()
        self.assertEqual(
            ("completed", "Completed", "3-1", '["11-8", "8-11", "11-6", "11-7"]', "A"),
            tuple(rubber),
        )
        players = self.conn.execute(
            """
            SELECT s.side_no, s.is_winner, p.player_name
            FROM current_event_match_sides s
            JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
            WHERE s.current_match_id = ? ORDER BY s.side_no
            """,
            (current_match_id,),
        ).fetchall()
        self.assertEqual(
            [(1, 1, "Corrected A"), (2, 0, "Corrected B")],
            [tuple(row) for row in players],
        )

    def test_live_rubber_inserts_missing_child_under_official_completed_tie(self):
        tie_row = self.insert_official_team_tie()
        live_match = self.live_team_item("OFFICIAL-TEAM-TIE", source_status="Live")

        upsert_live_rubber(
            self.conn.cursor(),
            event_id=3242,
            tie_row=tie_row,
            live_match=live_match,
            individual_match={
                "player_a": "Live A",
                "player_b": "Live B",
                "match_score": "1-0",
                "games": ["11-5"],
            },
            rubber_order=1,
        )

        rubber = self.conn.execute(
            """
            SELECT status, source_status, match_score, games, winner_side
            FROM current_event_matches
            WHERE event_id = 3242 AND external_match_code = 'OFFICIAL-TEAM-TIE::R1'
            """
        ).fetchone()
        self.assertIsNotNone(rubber)
        self.assertEqual(("live", "Live", "1-0", '["11-5"]', "A"), tuple(rubber))

    def test_live_rubber_updates_non_final_child_under_official_completed_tie(self):
        tie_row = self.insert_official_team_tie()
        self.conn.execute(
            """
            INSERT INTO current_event_matches (
                event_id, current_team_tie_id, sub_event_type_code, external_match_code,
                status, source_status, games
            ) VALUES (3242, ?, 'MT', 'OFFICIAL-TEAM-TIE::R1', 'scheduled', 'Start List', '[]')
            """,
            (int(tie_row["current_team_tie_id"]),),
        )
        live_match = self.live_team_item("OFFICIAL-TEAM-TIE", source_status="Live")

        upsert_live_rubber(
            self.conn.cursor(),
            event_id=3242,
            tie_row=tie_row,
            live_match=live_match,
            individual_match={
                "player_a": "Live A",
                "player_b": "Live B",
                "match_score": "1-0",
                "games": ["11-5"],
            },
            rubber_order=1,
        )

        rubber = self.conn.execute(
            """
            SELECT status, source_status, match_score, games, winner_side
            FROM current_event_matches
            WHERE event_id = 3242 AND external_match_code = 'OFFICIAL-TEAM-TIE::R1'
            """
        ).fetchone()
        self.assertEqual(("live", "Live", "1-0", '["11-5"]', "A"), tuple(rubber))

    def test_official_tie_update_writes_rubber_before_parent_child_sync(self):
        start_list = self.live_team_item("TEAM-TIE-ORDER", source_status="Start List")
        tie_row = upsert_live_team_tie(
            self.conn.cursor(),
            event_id=3242,
            item=start_list,
            now="2026-07-02T03:00:00+00:00",
        )
        upsert_live_rubber(
            self.conn.cursor(),
            event_id=3242,
            tie_row=tie_row,
            live_match=start_list,
            individual_match={
                "player_a": "Live A",
                "player_b": "Live B",
                "match_score": None,
                "games": [],
            },
            rubber_order=1,
        )

        official = self.live_team_item("TEAM-TIE-ORDER", source_status="Official")
        official["individual_matches"] = [
            {
                "player_a": "Official A",
                "player_b": "Official B",
                "match_score": "3-1",
                "games": ["11-8", "8-11", "11-6", "11-7"],
            }
        ]
        tie_row = upsert_live_team_tie(
            self.conn.cursor(),
            event_id=3242,
            item=official,
            now="2026-07-02T03:01:00+00:00",
        )
        for rubber_order, individual_match in enumerate(official["individual_matches"], start=1):
            upsert_live_rubber(
                self.conn.cursor(),
                event_id=3242,
                tie_row=tie_row,
                live_match=official,
                individual_match=individual_match,
                rubber_order=rubber_order,
            )
        sync_team_tie_from_live_match(
            self.conn.cursor(), int(tie_row["current_team_tie_id"]), official
        )

        rubber = self.conn.execute(
            """
            SELECT status, source_status, match_score, games, winner_side
            FROM current_event_matches
            WHERE event_id = 3242 AND external_match_code = 'TEAM-TIE-ORDER::R1'
            """
        ).fetchone()
        self.assertEqual(
            ("completed", "Official", "3-1", '["11-8", "8-11", "11-6", "11-7"]', "A"),
            tuple(rubber),
        )
        players = self.conn.execute(
            """
            SELECT s.side_no, s.is_winner, p.player_name
            FROM current_event_match_sides s
            JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
            JOIN current_event_matches m ON m.current_match_id = s.current_match_id
            WHERE m.external_match_code = 'TEAM-TIE-ORDER::R1'
            ORDER BY s.side_no
            """
        ).fetchall()
        self.assertEqual(
            [(1, 1, "Official A"), (2, 0, "Official B")],
            [tuple(row) for row in players],
        )

    def test_official_parent_sync_preserves_completed_walkover_child_without_rubber_details(self):
        tie_row = self.insert_official_team_tie()
        current_match_id = self.insert_official_rubber(tie_row)
        self.conn.execute(
            """
            UPDATE current_event_matches
            SET status = 'walkover', source_status = 'Completed', match_score = 'WO',
                games = '["WO"]', winner_side = 'A', raw_source_payload = '{"result": "walkover"}'
            WHERE current_match_id = ?
            """,
            (current_match_id,),
        )
        before_players = self.conn.execute(
            """
            SELECT s.side_no, s.is_winner, p.player_name
            FROM current_event_match_sides s
            JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
            WHERE s.current_match_id = ? ORDER BY s.side_no
            """,
            (current_match_id,),
        ).fetchall()
        official = self.live_team_item("OFFICIAL-TEAM-TIE", source_status="Official")
        official["individual_matches"] = []

        tie_row = upsert_live_team_tie(
            self.conn.cursor(),
            event_id=3242,
            item=official,
            now="2026-07-02T03:01:00+00:00",
        )
        for rubber_order, individual_match in enumerate(official["individual_matches"], start=1):
            upsert_live_rubber(
                self.conn.cursor(),
                event_id=3242,
                tie_row=tie_row,
                live_match=official,
                individual_match=individual_match,
                rubber_order=rubber_order,
            )
        sync_team_tie_from_live_match(
            self.conn.cursor(), int(tie_row["current_team_tie_id"]), official
        )

        rubber = self.conn.execute(
            """
            SELECT status, source_status, match_score, games, winner_side, raw_source_payload
            FROM current_event_matches WHERE current_match_id = ?
            """,
            (current_match_id,),
        ).fetchone()
        self.assertEqual(
            ("walkover", "Completed", "WO", '["WO"]', "A", '{"result": "walkover"}'),
            tuple(rubber),
        )
        after_players = self.conn.execute(
            """
            SELECT s.side_no, s.is_winner, p.player_name
            FROM current_event_match_sides s
            JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
            WHERE s.current_match_id = ? ORDER BY s.side_no
            """,
            (current_match_id,),
        ).fetchall()
        self.assertEqual([tuple(row) for row in before_players], [tuple(row) for row in after_players])

    def test_existing_non_final_live_individual_match_still_updates(self):
        first = self.live_individual_item("NORMAL-LIVE")
        upsert_live_individual_match(
            self.conn.cursor(), event_id=3242, item=first, now="2026-07-02T03:00:00+00:00"
        )
        update = self.live_individual_item("NORMAL-LIVE", source_status="Live")

        result = upsert_live_individual_match(
            self.conn.cursor(), event_id=3242, item=update, now="2026-07-02T03:01:00+00:00"
        )

        self.assertTrue(result)
        match = self.conn.execute(
            "SELECT status, source_status, match_score, games FROM current_event_matches WHERE external_match_code = 'NORMAL-LIVE'"
        ).fetchone()
        self.assertEqual(("live", "Live", "1-0", '["11-5"]'), tuple(match))

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
