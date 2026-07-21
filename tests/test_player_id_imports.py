import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "db"
sys.path.insert(0, str(SCRIPTS_DB_DIR))

import import_players as import_players_module
from import_players import import_players
from import_rankings import import_rankings
from import_sub_events import import_sub_events
from promote_current_event import promote_team_ties


def create_players_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE players (
            player_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            name_zh TEXT,
            slug TEXT UNIQUE NOT NULL,
            country TEXT,
            country_code TEXT NOT NULL,
            gender TEXT NOT NULL DEFAULT 'Female',
            birth_year INTEGER,
            age INTEGER,
            style TEXT,
            style_zh TEXT,
            playing_hand TEXT,
            playing_hand_zh TEXT,
            grip TEXT,
            grip_zh TEXT,
            avatar_url TEXT,
            avatar_file TEXT,
            career_events INTEGER DEFAULT 0,
            career_matches INTEGER DEFAULT 0,
            career_wins INTEGER DEFAULT 0,
            career_losses INTEGER DEFAULT 0,
            career_wtt_titles INTEGER DEFAULT 0,
            career_all_titles INTEGER DEFAULT 0,
            career_best_rank INTEGER,
            career_best_month TEXT,
            year_events INTEGER DEFAULT 0,
            year_matches INTEGER DEFAULT 0,
            year_wins INTEGER DEFAULT 0,
            year_losses INTEGER DEFAULT 0,
            year_games INTEGER DEFAULT 0,
            year_games_won INTEGER DEFAULT 0,
            year_games_lost INTEGER DEFAULT 0,
            year_wtt_titles INTEGER DEFAULT 0,
            year_all_titles INTEGER DEFAULT 0,
            scraped_at TEXT
        )
        """
    )


class PlayerIdImportTests(unittest.TestCase):
    def test_validate_player_profiles_reports_missing_gender_without_database_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            profiles_dir.mkdir()
            (profiles_dir / "player_2.json").write_text(
                json.dumps(
                    {
                        "player_id": "2",
                        "name": "Incomplete Player",
                        "country_code": "TST",
                    }
                ),
                encoding="utf-8",
            )

            _profiles, errors = import_players_module.validate_player_profiles(str(profiles_dir))

        self.assertEqual(len(errors), 1)
        self.assertIn("player_2.json: missing required fields: gender", errors[0])

    def test_validate_player_profiles_accepts_country_code_from_existing_player(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "test.sqlite"
            profiles_dir = root / "profiles"
            profiles_dir.mkdir()

            conn = sqlite3.connect(db_path)
            create_players_table(conn)
            conn.execute(
                "INSERT INTO players (player_id, name, slug, country_code, gender) VALUES (2, 'Legacy Player', '2', 'TST', 'Female')"
            )
            conn.commit()
            conn.close()
            (profiles_dir / "player_2.json").write_text(
                json.dumps(
                    {
                        "player_id": "2",
                        "name": "Legacy Player",
                        "gender": "Female",
                    }
                ),
                encoding="utf-8",
            )

            profiles, errors = import_players_module.validate_player_profiles(
                str(profiles_dir),
                str(db_path),
            )

        self.assertEqual(errors, [])
        self.assertEqual(len(profiles), 1)

    def test_import_players_rolls_back_entire_batch_when_one_profile_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "test.sqlite"
            profiles_dir = root / "profiles"
            profiles_dir.mkdir()

            conn = sqlite3.connect(db_path)
            create_players_table(conn)
            conn.commit()
            conn.close()

            (profiles_dir / "player_1.json").write_text(
                json.dumps(
                    {
                        "player_id": "1",
                        "name": "Valid Player",
                        "country_code": "TST",
                        "gender": "Female",
                    }
                ),
                encoding="utf-8",
            )
            (profiles_dir / "player_2.json").write_text(
                json.dumps(
                    {
                        "player_id": "2",
                        "name": "Incomplete Player",
                        "country_code": "TST",
                    }
                ),
                encoding="utf-8",
            )

            result = import_players(str(db_path), str(profiles_dir))

            self.assertEqual(result["inserted"], 0)
            self.assertEqual(len(result["errors"]), 1)
            conn = sqlite3.connect(db_path)
            player_count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
            conn.close()
            self.assertEqual(player_count, 0)

    def test_import_players_validate_only_exits_nonzero_for_invalid_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            profiles_dir.mkdir()
            (profiles_dir / "player_2.json").write_text(
                json.dumps(
                    {
                        "player_id": "2",
                        "name": "Incomplete Player",
                        "country_code": "TST",
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DB_DIR / "import_players.py"),
                    "--dir",
                    str(profiles_dir),
                    "--validate-only",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("Validation errors: 1", completed.stdout)
        self.assertIn("player_2.json: missing required fields: gender", completed.stdout)

    def test_import_players_rolls_back_valid_rows_after_sql_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "test.sqlite"
            profiles_dir = root / "profiles"
            profiles_dir.mkdir()

            conn = sqlite3.connect(db_path)
            create_players_table(conn)
            conn.commit()
            conn.close()

            for filename, player_id in (("player_1.json", "1"), ("player_invalid.json", "invalid")):
                (profiles_dir / filename).write_text(
                    json.dumps(
                        {
                            "player_id": player_id,
                            "name": "Test Player",
                            "country_code": "TST",
                            "gender": "Female",
                        }
                    ),
                    encoding="utf-8",
                )

            result = import_players(str(db_path), str(profiles_dir))

            self.assertEqual(result["inserted"], 0)
            self.assertEqual(len(result["errors"]), 1)
            conn = sqlite3.connect(db_path)
            player_count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
            conn.close()
            self.assertEqual(player_count, 0)

    def test_import_players_uses_player_id_slug_for_duplicate_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "test.sqlite"
            profiles_dir = root / "profiles"
            profiles_dir.mkdir()

            conn = sqlite3.connect(db_path)
            create_players_table(conn)
            conn.commit()
            conn.close()

            for player_id in (145463, 145296):
                (profiles_dir / f"player_{player_id}.json").write_text(
                    json.dumps(
                        {
                            "player_id": str(player_id),
                            "name": "STOJANOVSKA Sara",
                            "country_code": "MKD",
                            "country_zh": "北马其顿",
                            "gender": "Female",
                        }
                    ),
                    encoding="utf-8",
                )

            result = import_players(str(db_path), str(profiles_dir))

            self.assertEqual(result["errors"], [])
            conn = sqlite3.connect(db_path)
            rows = conn.execute("SELECT player_id, name, slug FROM players ORDER BY player_id").fetchall()
            conn.close()
            self.assertEqual(rows, [(145296, "STOJANOVSKA Sara", "145296"), (145463, "STOJANOVSKA Sara", "145463")])

    def test_import_rankings_requires_valid_player_id_without_name_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "test.sqlite"
            rankings_dir = root / "rankings"
            rankings_dir.mkdir()

            conn = sqlite3.connect(db_path)
            create_players_table(conn)
            conn.execute(
                "INSERT INTO players (player_id, name, slug, country_code) VALUES (1, 'DUP Name', '1', 'AAA')"
            )
            conn.execute(
                """
                CREATE TABLE ranking_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    ranking_week TEXT NOT NULL,
                    ranking_date TEXT NOT NULL,
                    total_players INTEGER,
                    scraped_at TEXT,
                    UNIQUE(category, ranking_week)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE ranking_entries (
                    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    rank INTEGER NOT NULL,
                    points INTEGER NOT NULL,
                    rank_change INTEGER DEFAULT 0,
                    UNIQUE(snapshot_id, player_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE points_breakdown (
                    breakdown_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    event_name TEXT NOT NULL,
                    event_name_zh TEXT,
                    event_type_code TEXT,
                    category_name_zh TEXT,
                    position TEXT,
                    position_zh TEXT,
                    points INTEGER NOT NULL,
                    expires_on TEXT
                )
                """
            )
            conn.commit()
            conn.close()

            ranking_file = rankings_dir / "ranking.json"
            ranking_file.write_text(
                json.dumps(
                    {
                        "category": "women",
                        "ranking_week": "25",
                        "ranking_date": "2026-06-16",
                        "total_players": 1,
                        "rankings": [{"rank": 1, "name": "DUP Name", "country_code": "AAA", "points": 10}],
                    }
                ),
                encoding="utf-8",
            )

            result = import_rankings(str(db_path), str(rankings_dir), str(ranking_file))

            self.assertEqual(result["entries"], 0)
            self.assertEqual(len(result["unmatched_player_ids"]), 1)
            conn = sqlite3.connect(db_path)
            entry_count = conn.execute("SELECT COUNT(*) FROM ranking_entries").fetchone()[0]
            conn.close()
            self.assertEqual(entry_count, 0)

    def test_promote_team_ties_does_not_name_fallback_player_id(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE stage_codes (code TEXT PRIMARY KEY, name TEXT, name_zh TEXT)")
        conn.execute("CREATE TABLE round_codes (code TEXT PRIMARY KEY, name_zh TEXT)")
        conn.execute(
            """
            CREATE TABLE current_event_team_ties (
                current_team_tie_id INTEGER PRIMARY KEY,
                event_id INTEGER,
                sub_event_type_code TEXT,
                stage_label TEXT,
                stage_code TEXT,
                round_label TEXT,
                round_code TEXT,
                group_code TEXT,
                match_score TEXT,
                winner_side TEXT,
                winner_team_code TEXT,
                external_match_code TEXT,
                status TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE current_event_team_tie_sides (
                current_team_tie_side_id INTEGER PRIMARY KEY,
                current_team_tie_id INTEGER,
                side_no INTEGER,
                team_code TEXT,
                team_name TEXT,
                seed INTEGER,
                qualifier INTEGER,
                is_winner INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE current_event_team_tie_side_players (
                current_team_tie_side_player_id INTEGER PRIMARY KEY,
                current_team_tie_side_id INTEGER,
                player_order INTEGER,
                player_id INTEGER,
                player_name TEXT,
                player_country TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE team_ties (
                team_tie_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                sub_event_type_code TEXT,
                stage TEXT,
                stage_zh TEXT,
                stage_code TEXT,
                round TEXT,
                round_zh TEXT,
                round_code TEXT,
                group_code TEXT,
                match_score TEXT,
                winner_side TEXT,
                winner_team_code TEXT,
                status TEXT,
                source_type TEXT,
                source_key TEXT,
                promoted_from_event_id INTEGER,
                promoted_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE team_tie_sides (
                team_tie_side_id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_tie_id INTEGER,
                side_no INTEGER,
                team_code TEXT,
                team_name TEXT,
                seed INTEGER,
                qualifier INTEGER,
                is_winner INTEGER,
                UNIQUE(team_tie_id, side_no)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE team_tie_side_players (
                team_tie_side_player_id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_tie_side_id INTEGER,
                player_order INTEGER,
                player_id INTEGER,
                player_name TEXT,
                player_country TEXT,
                UNIQUE(team_tie_side_id, player_order)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO current_event_team_ties
            VALUES (1, 100, 'MT', 'Main Draw', NULL, 'Final', NULL, NULL, '1-0', 'A', 'AAA', 'tie-1', 'completed')
            """
        )
        conn.execute("INSERT INTO current_event_team_tie_sides VALUES (1, 1, 1, 'AAA', 'AAA', NULL, NULL, 1)")
        conn.execute("INSERT INTO current_event_team_tie_sides VALUES (2, 1, 2, 'BBB', 'BBB', NULL, NULL, 0)")
        conn.execute("INSERT INTO current_event_team_tie_side_players VALUES (1, 1, 1, NULL, 'DUP Name', 'AAA')")
        conn.execute("INSERT INTO current_event_team_tie_side_players VALUES (2, 2, 1, NULL, 'Other Name', 'BBB')")

        miss_log = []
        promote_team_ties(conn.cursor(), 100, miss_log)

        rows = conn.execute(
            "SELECT player_id, player_name, player_country FROM team_tie_side_players ORDER BY team_tie_side_player_id"
        ).fetchall()
        conn.close()
        self.assertEqual(rows[0], (None, "DUP Name", "AAA"))
        self.assertIn(("DUP Name", "AAA"), miss_log)

    def test_import_sub_events_uses_match_side_player_id_for_champion(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE event_categories (id INTEGER PRIMARY KEY, points_eligible INTEGER)")
        conn.execute(
            """
            CREATE TABLE events (
                event_id INTEGER PRIMARY KEY,
                event_category_id INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY,
                event_id INTEGER,
                sub_event_type_code TEXT,
                winner_side TEXT,
                winner_name TEXT,
                match_score TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE match_sides (
                match_side_id INTEGER PRIMARY KEY,
                match_id INTEGER,
                side_no INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE match_side_players (
                match_side_player_id INTEGER PRIMARY KEY,
                match_side_id INTEGER,
                player_order INTEGER,
                player_id INTEGER,
                player_name TEXT,
                player_country TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE event_draw_matches (
                draw_match_id INTEGER PRIMARY KEY,
                match_id INTEGER,
                event_id INTEGER,
                sub_event_type_code TEXT,
                draw_stage TEXT,
                draw_round TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE sub_events (
                sub_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                sub_event_type_code TEXT,
                champion_player_ids TEXT,
                champion_name TEXT,
                champion_country_code TEXT
            )
            """
        )
        conn.execute("INSERT INTO event_categories VALUES (1, 1)")
        conn.execute("INSERT INTO events VALUES (100, 1)")
        conn.execute("INSERT INTO matches VALUES (10, 100, 'WS', 'A', 'DUP Name', '4-0')")
        conn.execute("INSERT INTO match_sides VALUES (1, 10, 1)")
        conn.execute("INSERT INTO match_sides VALUES (2, 10, 2)")
        conn.execute("INSERT INTO match_side_players VALUES (1, 1, 1, 222, 'DUP Name', 'AAA')")
        conn.execute("INSERT INTO match_side_players VALUES (2, 2, 1, 111, 'DUP Name', 'AAA')")
        conn.execute("INSERT INTO event_draw_matches VALUES (1, 10, 100, 'WS', 'Main Draw', 'Final')")

        result = import_sub_events("", conn=conn)

        self.assertEqual(result["sub_events_inserted"], 1)
        row = conn.execute(
            "SELECT champion_player_ids, champion_name, champion_country_code FROM sub_events"
        ).fetchone()
        conn.close()
        self.assertEqual(row, ("222", "DUP Name", "AAA"))


if __name__ == "__main__":
    unittest.main()
