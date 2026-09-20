from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from scripts.asian_games_2026.finalize import FinalizeError, validate_current

ROOT = Path(__file__).resolve().parents[3]


class FinalizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript((ROOT / "scripts/db/schema.sql").read_text(encoding="utf-8"))
        self.conn.execute("INSERT INTO events(event_id,year,name,lifecycle_status) VALUES(6666,2026,'AG','in_progress')")
        for code in ("WT", "MS", "WS", "MD", "WD", "XD"):
            self.conn.execute("INSERT INTO sub_event_types(code,name,name_zh) VALUES(?,?,?)", (code, code, code))
        for code in ("MS", "WS", "MD", "WD", "XD"):
            self.conn.execute(
                """INSERT INTO current_event_brackets
                   (event_id,sub_event_type_code,external_unit_code,round_code,bracket_position)
                   VALUES(6666,?,?, 'F',1)""",
                (code, f"{code}.F"),
            )
        self.conn.execute("INSERT INTO current_event_team_ties(event_id,sub_event_type_code,status) VALUES(6666,'WT','completed')")
        tie_id = self.conn.execute("SELECT current_team_tie_id FROM current_event_team_ties").fetchone()[0]
        side_id = self.conn.execute(
            "INSERT INTO current_event_team_tie_sides(current_team_tie_id,side_no) VALUES(?,1)", (tie_id,)
        ).lastrowid
        self.conn.execute(
            "INSERT INTO current_event_team_tie_side_players(current_team_tie_side_id,player_order,player_name) VALUES(?,1,'A')",
            (side_id,),
        )
        side_id = self.conn.execute(
            "INSERT INTO current_event_team_tie_sides(current_team_tie_id,side_no) VALUES(?,2)", (tie_id,)
        ).lastrowid
        self.conn.execute(
            "INSERT INTO current_event_team_tie_side_players(current_team_tie_side_id,player_order,player_name) VALUES(?,1,'B')",
            (side_id,),
        )
        match_id = self.conn.execute(
            """INSERT INTO current_event_matches(event_id,current_team_tie_id,sub_event_type_code,status,winner_side,external_match_code)
               VALUES(6666,?,'WT','completed','A','WT.1')""", (tie_id,)
        ).lastrowid
        side_a = self.conn.execute("INSERT INTO current_event_match_sides(current_match_id,side_no) VALUES(?,1)", (match_id,)).lastrowid
        side_b = self.conn.execute("INSERT INTO current_event_match_sides(current_match_id,side_no) VALUES(?,2)", (match_id,)).lastrowid
        self.conn.execute("INSERT INTO current_event_match_side_players(current_match_side_id,player_order,player_name) VALUES(?,1,'A')", (side_a,))
        self.conn.execute("INSERT INTO current_event_match_side_players(current_match_side_id,player_order,player_name) VALUES(?,1,'B')", (side_b,))
        # An unplayed fourth/fifth rubber under an already completed tie is valid.
        self.conn.execute(
            "INSERT INTO current_event_matches(event_id,current_team_tie_id,sub_event_type_code,status,external_match_code) VALUES(6666,?,'WT','scheduled','WT.2')",
            (tie_id,),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_allows_unplayed_planned_rubber_in_completed_tie(self) -> None:
        self.assertEqual(validate_current(self.conn)["pending_units"], 0)

    def test_rejects_live_standalone_match(self) -> None:
        self.conn.execute("INSERT INTO current_event_matches(event_id,sub_event_type_code,status,external_match_code) VALUES(6666,'WT','live','WT.3')")
        with self.assertRaises(FinalizeError):
            validate_current(self.conn)

    def test_rejects_missing_individual_bracket(self) -> None:
        self.conn.execute("DELETE FROM current_event_brackets WHERE sub_event_type_code='XD'")

        with self.assertRaisesRegex(FinalizeError, "missing individual brackets: XD"):
            validate_current(self.conn)

        report = validate_current(self.conn, force=True)
        self.assertEqual(report["individual_bracket_nodes"], 4)
        self.assertEqual(report["missing_individual_brackets"], ["XD"])


if __name__ == "__main__":
    unittest.main()
