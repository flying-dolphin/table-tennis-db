from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from scripts.asian_games_2026.import_current import (
    collect_missing_player_translations,
    collect_unresolved_players,
    import_snapshot,
)


ROOT = Path(__file__).resolve().parents[3]


class ImportCurrentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript((ROOT / "scripts/db/schema.sql").read_text(encoding="utf-8"))
        self.conn.execute("INSERT INTO events(event_id, year, name) VALUES (6666, 2026, 'Asian Games')")
        for code in ("MT", "WT", "MS", "WS", "MD", "WD", "XD"):
            self.conn.execute("INSERT OR IGNORE INTO sub_event_types(code,name,name_zh) VALUES (?,?,?)", (code, code, code))
        self.conn.execute(
            "INSERT INTO players(player_id,name,slug,country_code) VALUES (136711,'HARIMOTO Miwa','harimoto-miwa','JPN')"
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_idempotent_import_roster_players_and_status_priority(self) -> None:
        tie = {
            "external_match_code": "WT.1", "sub_event_type_code": "WT", "stage_label": "Group A",
            "stage_code": "MAIN_DRAW", "round_label": "Women's Team Group A", "round_code": "RR",
            "group_code": "A", "session_label": "Match 1", "scheduled_local_at": "2026-09-20T10:00:00",
            "scheduled_utc_at": "2026-09-20T01:00:00Z", "table_no": "Table 1", "status": "completed",
            "source_status": "OFFICIAL", "match_score": "3-0", "winner_side": "A", "winner_team_code": "JPN",
            "sides": [{"side_no": 1, "team_code": "JPN", "team_name": "Japan", "is_winner": True,
                       "nominated_players": [{"order": 1, "name": "HARIMOTO Miwa", "country": "JPN"},
                                               {"order": 2, "name": "UNKNOWN Player", "country": "JPN"}]},
                      {"side_no": 2, "team_code": "KOR", "team_name": "Korea", "is_winner": False,
                       "nominated_players": []}],
            "rubbers": [],
        }
        snapshot = {"team_ties": [tie], "matches": []}
        import_snapshot(self.conn, snapshot)
        tie["status"] = "scheduled"
        tie["source_status"] = "START_LIST"
        import_snapshot(self.conn, snapshot)

        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM current_event_team_ties").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT status FROM current_event_team_ties").fetchone()[0], "completed")
        players = self.conn.execute(
            "SELECT player_name,player_id FROM current_event_team_tie_side_players ORDER BY player_order"
        ).fetchall()
        self.assertEqual([tuple(row) for row in players], [("HARIMOTO Miwa", 136711), ("UNKNOWN Player", None)])
        self.assertEqual(["JPN:HARIMOTO Miwa (1)"], collect_missing_player_translations(self.conn))
        event = self.conn.execute("SELECT time_zone,lifecycle_status FROM events WHERE event_id=6666").fetchone()
        self.assertEqual(tuple(event), ("Asia/Tokyo", "in_progress"))

    def test_imports_match_sides_and_games(self) -> None:
        match = {
            "external_match_code": "WS.1", "sub_event_type_code": "WS", "stage_label": "Round of 64",
            "stage_code": "MAIN_DRAW", "round_label": "Women's Singles Round of 64", "round_code": "R64",
            "group_code": None, "session_label": "Match 1", "scheduled_local_at": "2026-09-24T10:00:00",
            "scheduled_utc_at": "2026-09-24T01:00:00Z", "table_no": "Table 1", "status": "completed",
            "source_status": "OFFICIAL", "match_score": "4-1", "winner_side": "A", "winner_name": "HARIMOTO Miwa",
            "games": [{"game": 1, "side_a": "11", "side_b": "7"}], "raw_source_payload": {"Info": {}},
            "sides": [{"side_no": 1, "team_code": "JPN", "is_winner": True,
                       "players": [{"order": 1, "name": "HARIMOTO Miwa", "country": "JPN"}]},
                      {"side_no": 2, "team_code": "KOR", "is_winner": False,
                       "players": [{"order": 1, "name": "OTHER Player", "country": "KOR"}]}],
        }
        import_snapshot(self.conn, {"team_ties": [], "matches": [match]})
        match["status"] = "scheduled"
        match["source_status"] = "START_LIST"
        import_snapshot(self.conn, {"team_ties": [], "matches": [match]})
        row = self.conn.execute("SELECT games,winner_name FROM current_event_matches").fetchone()
        self.assertIn('"side_a": "11"', row[0])
        self.assertEqual(row[1], "HARIMOTO Miwa")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM current_event_match_sides").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT status FROM current_event_matches").fetchone()[0], "completed")

    def test_import_resolves_variant_roster_names_and_preserves_ambiguous_match_names(self) -> None:
        self.conn.executemany(
            "INSERT INTO players(player_id,name,slug,country_code,gender) VALUES (?,?,?,?,?)",
            [
                (117332, "ZHU Yuling", "zhu-yuling", "MAC", "Female"),
                (207486, "KUAN Cheok Lam", "kuan-cheok-lam", "MAC", "Female"),
                (131966, "TAN Zhao Yun", "tan-zhao-yun", "SGP", "Female"),
                (133601, "TAN Zhao Ray", "tan-zhao-ray", "SGP", "Male"),
            ],
        )
        self.conn.commit()

        tie = {
            "external_match_code": "WT.VARIANTS",
            "sub_event_type_code": "WT",
            "stage_label": "Group A",
            "stage_code": "MAIN_DRAW",
            "round_label": "Women's Team Group A",
            "round_code": "RR",
            "group_code": "A",
            "session_label": "Match 1",
            "scheduled_local_at": "2026-09-20T10:00:00",
            "scheduled_utc_at": "2026-09-20T01:00:00Z",
            "table_no": "Table 1",
            "status": "scheduled",
            "source_status": "SCHEDULED",
            "match_score": None,
            "winner_side": None,
            "winner_team_code": None,
            "sides": [
                {
                    "side_no": 1,
                    "team_code": "MAC",
                    "team_name": "Macau",
                    "is_winner": False,
                    "nominated_players": [
                        {"order": 1, "name": "ZHU Yu Ling", "country": "MAC"},
                        {"order": 2, "name": "KUAN Cheok", "country": "MAC"},
                    ],
                },
                {"side_no": 2, "team_code": "CHN", "team_name": "China", "is_winner": False, "nominated_players": []},
            ],
            "rubbers": [],
        }
        ambiguous_match = {
            "external_match_code": "XD.AMBIGUOUS",
            "sub_event_type_code": "XD",
            "stage_label": "Round 1",
            "stage_code": "MAIN_DRAW",
            "round_label": "Mixed Doubles Round 1",
            "round_code": "R1",
            "group_code": None,
            "session_label": "Match 1",
            "scheduled_local_at": "2026-09-20T10:00:00",
            "scheduled_utc_at": "2026-09-20T01:00:00Z",
            "table_no": "Table 2",
            "status": "scheduled",
            "source_status": "SCHEDULED",
            "match_score": None,
            "winner_side": None,
            "winner_name": None,
            "games": [],
            "raw_source_payload": {},
            "sides": [
                {
                    "side_no": 1,
                    "team_code": "SGP",
                    "is_winner": False,
                    "players": [{"order": 1, "name": "TAN Zhao", "country": "SGP"}],
                },
                {"side_no": 2, "team_code": "MAC", "is_winner": False, "players": []},
            ],
        }

        import_snapshot(self.conn, {"team_ties": [tie], "matches": [ambiguous_match]})

        roster_rows = self.conn.execute(
            "SELECT player_name,player_id FROM current_event_team_tie_side_players ORDER BY player_order"
        ).fetchall()
        self.assertEqual([tuple(row) for row in roster_rows], [("ZHU Yu Ling", 117332), ("KUAN Cheok", 207486)])
        ambiguous_id = self.conn.execute(
            "SELECT player_id FROM current_event_match_side_players WHERE player_name='TAN Zhao'"
        ).fetchone()[0]
        self.assertIsNone(ambiguous_id)
        self.assertEqual(["SGP:TAN Zhao (1)"], collect_unresolved_players(self.conn))

    def test_imports_brackets_idempotently_and_only_replaces_supplied_sub_events(self) -> None:
        self.conn.execute(
            """INSERT INTO current_event_brackets
               (event_id,sub_event_type_code,external_unit_code,round_code,bracket_position)
               VALUES (6666,'MS','stale-ms','R64',1), (6666,'MT','keep-mt','QF',1)"""
        )
        self.conn.commit()
        row = {
            "event_id": 6666,
            "sub_event_type_code": "MS",
            "draw_code": "MAIN",
            "bracket_code": "M.SINGLES-----------.R64-",
            "stage_code": "MAIN_DRAW",
            "round_code": "R64",
            "round_order": 20,
            "bracket_position": 1,
            "external_unit_code": "M.SINGLES-----------.R64-.000100--",
            "scheduled_date": None,
            "scheduled_time": None,
            "match_score": None,
            "winner_side": "A",
            "status": "completed",
            "side_a_previous_unit": None,
            "side_b_previous_unit": None,
            "side_a_team_code": "CHN",
            "side_b_team_code": "BYE",
            "side_a_placeholder": None,
            "side_b_placeholder": "BYE",
            "raw_source_payload": {
                "Home": {"Reg": "16273238", "Name": "WANG Chuqin", "Org": "CHN", "Win": True},
                "Away": {"Reg": "7", "Name": "", "Org": "BYE", "Win": False},
                "Info": {"Key": "M.SINGLES-----------.R64-.000100--", "IsBye": True},
            },
        }
        brackets = {"event_id": 6666, "sub_events": ["MS"], "brackets": [row]}

        counts = import_snapshot(self.conn, {"team_ties": [], "matches": []}, brackets)
        second_counts = import_snapshot(self.conn, {"team_ties": [], "matches": []}, brackets)

        self.assertEqual(counts["brackets"], 1)
        self.assertEqual(second_counts["brackets"], 1)
        self.assertEqual(
            [tuple(item) for item in self.conn.execute(
                "SELECT external_unit_code FROM current_event_brackets WHERE sub_event_type_code='MS'"
            ).fetchall()],
            [("M.SINGLES-----------.R64-.000100--",)],
        )
        self.assertEqual(
            [tuple(item) for item in self.conn.execute(
                "SELECT external_unit_code FROM current_event_brackets WHERE sub_event_type_code='MT'"
            ).fetchall()],
            [("keep-mt",)],
        )
        raw = self.conn.execute(
            "SELECT raw_source_payload FROM current_event_brackets WHERE sub_event_type_code='MS'"
        ).fetchone()[0]
        self.assertIn('"WANG Chuqin"', raw)


if __name__ == "__main__":
    unittest.main()
