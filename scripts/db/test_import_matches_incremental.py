#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from import_matches import import_matches


def write_event_file(
    directory: Path,
    event_id: int,
    event_name: str,
    year: int,
    winner: str,
    *,
    side_a: list[str] | None = None,
    side_b: list[str] | None = None,
    sub_event: str = "MS",
    stage: str = "Main Draw",
    round_: str = "Final",
    match_score: str = "4-2",
) -> None:
    side_a = side_a or [f"{winner} (CHN)"]
    side_b = side_b or ["Opponent (JPN)"]
    payload = {
        "schema_version": "event_match.v1",
        "event_id": event_id,
        "event": event_name,
        "event_year": year,
        "matches": [
            {
                "sub_event": sub_event,
                "stage": stage,
                "round": round_,
                "side_a": side_a,
                "side_b": side_b,
                "match_score": match_score,
                "winner": winner,
                "raw_row_text": f"{year} | {event_name} | {' | '.join(side_a)} | {' | '.join(side_b)} | {sub_event} | {stage} | {round_} | {match_score} | {winner}",
            }
        ],
    }
    (directory / f"{event_name.replace(' ', '_')}_{event_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


class ImportMatchesIncrementalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "test.db"
        self.matches_dir = self.root / "matches"
        self.player_matches_dir = self.root / "player_matches"
        self.same_name_players_path = self.root / "same_name_players.txt"
        self.country_history_path = self.root / "player_country_history.json"
        self.matches_dir.mkdir()
        self.player_matches_dir.mkdir()
        self.same_name_players_path.write_text("", encoding="utf-8")
        self.country_history_path.write_text("[]\n", encoding="utf-8")

        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE events (
                event_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                name_zh TEXT,
                year INTEGER,
                event_category_id INTEGER
            );
            CREATE TABLE sub_event_types (
                code TEXT PRIMARY KEY,
                name TEXT,
                name_zh TEXT
            );
            CREATE TABLE event_categories (
                id INTEGER PRIMARY KEY,
                filtering_only INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE players (
                player_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                name_zh TEXT,
                country_code TEXT NOT NULL
            );
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                event_name TEXT,
                event_name_zh TEXT,
                event_year INTEGER,
                sub_event_type_code TEXT NOT NULL,
                stage TEXT,
                stage_zh TEXT,
                round TEXT,
                round_zh TEXT,
                side_a_key TEXT NOT NULL,
                side_b_key TEXT NOT NULL,
                match_score TEXT,
                games TEXT,
                winner_side TEXT,
                winner_name TEXT NOT NULL,
                raw_row_text TEXT NOT NULL,
                scraped_at TEXT
            );
            CREATE TABLE match_sides (
                match_side_id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                side_no INTEGER NOT NULL,
                side_key TEXT NOT NULL,
                is_winner INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE match_side_players (
                match_side_player_id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_side_id INTEGER NOT NULL,
                player_order INTEGER NOT NULL,
                player_id INTEGER,
                player_name TEXT NOT NULL,
                player_country TEXT
            );
            CREATE TABLE event_draw_matches (
                draw_match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL
            );
            CREATE TABLE sub_events (
                sub_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL
            );
            """
        )
        conn.executemany(
            "INSERT INTO events (event_id, name, year) VALUES (?, ?, ?)",
            [(1001, "Alpha Event", 2024), (1002, "Beta Event", 2024)],
        )
        conn.executemany(
            "INSERT INTO sub_event_types (code, name, name_zh) VALUES (?, ?, ?)",
            [("MS", "MS", "MS")],
        )
        conn.executemany(
            "INSERT INTO players (player_id, name, name_zh, country_code) VALUES (?, ?, ?, ?)",
            [
                (1, "Alpha Winner", "阿尔法", "CHN"),
                (2, "Opponent", "对手", "JPN"),
                (3, "Traveler", "旅行者", "MAC"),
                (4, "Same Name", "同名甲", "CHN"),
                (5, "Same Name", "同名乙", "CHN"),
            ],
        )
        for event_id, event_name in ((1001, "Alpha Event"), (1002, "Beta Event")):
            conn.execute(
                """
                INSERT INTO matches (
                    event_id, event_name, event_year, sub_event_type_code,
                    side_a_key, side_b_key, match_score, winner_side, winner_name, raw_row_text
                ) VALUES (?, ?, 2024, 'MS', 'OLD_A', 'OLD_B', '1-0', 'A', 'Old Winner', 'old')
                """,
                (event_id, event_name),
            )
            old_match_id = conn.execute(
                "SELECT match_id FROM matches WHERE event_id = ?",
                (event_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO match_sides (match_id, side_no, side_key, is_winner) VALUES (?, 1, 'OLD_A', 1)",
                (old_match_id,),
            )
            old_side_id = conn.execute(
                "SELECT match_side_id FROM match_sides WHERE match_id = ?",
                (old_match_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO match_side_players (match_side_id, player_order, player_name, player_country) VALUES (?, 1, 'Old Winner', 'CHN')",
                (old_side_id,),
            )
            conn.execute("INSERT INTO event_draw_matches (match_id, event_id) VALUES (?, ?)", (old_match_id, event_id))
            conn.execute("INSERT INTO sub_events (event_id) VALUES (?)", (event_id,))
        conn.commit()
        conn.close()

        write_event_file(self.matches_dir, 1001, "Alpha Event", 2024, "Alpha Winner")
        write_event_file(self.matches_dir, 1002, "Beta Event", 2024, "Beta Winner")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def count(self, table: str, event_id: int) -> int:
        conn = sqlite3.connect(self.db_path)
        value = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE event_id = ?", (event_id,)).fetchone()[0]
        conn.close()
        return value

    def test_event_id_import_replaces_only_selected_event(self) -> None:
        result = import_matches(
            str(self.db_path),
            str(self.matches_dir),
            event_ids=[1001],
            same_name_players_path=self.same_name_players_path,
            player_matches_dir=self.player_matches_dir,
            country_history_path=self.country_history_path,
        )

        self.assertFalse(result["full_refresh"])
        self.assertEqual([1001], result["event_ids"])
        self.assertEqual(1, self.count("matches", 1001))
        self.assertEqual(1, self.count("matches", 1002))
        self.assertEqual(0, self.count("event_draw_matches", 1001))
        self.assertEqual(1, self.count("event_draw_matches", 1002))
        self.assertEqual(0, self.count("sub_events", 1001))
        self.assertEqual(1, self.count("sub_events", 1002))

        conn = sqlite3.connect(self.db_path)
        beta_winner = conn.execute("SELECT winner_name FROM matches WHERE event_id = 1002").fetchone()[0]
        alpha_winner = conn.execute("SELECT winner_name FROM matches WHERE event_id = 1001").fetchone()[0]
        conn.close()

        self.assertEqual("Old Winner", beta_winner)
        self.assertEqual("Alpha Winner", alpha_winner)

    def import_event(self, event_id: int) -> dict:
        return import_matches(
            str(self.db_path),
            str(self.matches_dir),
            event_ids=[event_id],
            same_name_players_path=self.same_name_players_path,
            player_matches_dir=self.player_matches_dir,
            country_history_path=self.country_history_path,
        )

    def side_player_ids(self, event_id: int) -> list[tuple[str, str, int | None]]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """
            SELECT msp.player_name, msp.player_country, msp.player_id
              FROM matches m
              JOIN match_sides ms ON ms.match_id = m.match_id
              JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
             WHERE m.event_id = ?
             ORDER BY ms.side_no, msp.player_order
            """,
            (event_id,),
        ).fetchall()
        conn.close()
        return rows

    def test_unique_name_country_match_writes_player_id(self) -> None:
        self.import_event(1001)

        self.assertEqual(
            [("Alpha Winner", "CHN", 1), ("Opponent", "JPN", 2)],
            self.side_player_ids(1001),
        )

    def test_historical_country_match_writes_current_player_id(self) -> None:
        self.country_history_path.write_text(
            json.dumps(
                [
                    {
                        "player_name": "Traveler",
                        "current_country": "MAC",
                        "historical_country": "CHN",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        write_event_file(
            self.matches_dir,
            1001,
            "Alpha Event",
            2024,
            "Traveler",
            side_a=["Traveler (CHN)"],
            side_b=["Opponent (JPN)"],
        )

        self.import_event(1001)

        self.assertEqual(
            [("Traveler", "CHN", 3), ("Opponent", "JPN", 2)],
            self.side_player_ids(1001),
        )

    def test_same_name_without_player_matches_keeps_null(self) -> None:
        self.same_name_players_path.write_text(
            "4,Same Name,CHN\n5,Same Name,CHN\n",
            encoding="utf-8",
        )
        write_event_file(
            self.matches_dir,
            1001,
            "Alpha Event",
            2024,
            "Same Name",
            side_a=["Same Name (CHN)"],
            side_b=["Opponent (JPN)"],
        )

        result = self.import_event(1001)

        self.assertEqual(
            [("Same Name", "CHN", None), ("Opponent", "JPN", 2)],
            self.side_player_ids(1001),
        )
        self.assertIn("Same Name (CHN)", result["unresolved_same_name_players"])

    def test_same_name_with_player_matches_unique_evidence_writes_player_id(self) -> None:
        self.same_name_players_path.write_text(
            "4,Same Name,CHN\n5,Same Name,CHN\n",
            encoding="utf-8",
        )
        write_event_file(
            self.matches_dir,
            1001,
            "Alpha Event",
            2024,
            "Same Name",
            side_a=["Same Name (CHN)"],
            side_b=["Opponent (JPN)"],
            match_score="3-1",
        )
        player_payload = {
            "schema_version": "match.v2",
            "player_id": 4,
            "player_name": "Same Name",
            "country_code": "CHN",
            "years": {
                "2024": {
                    "events": [
                        {
                            "event_name": "Alpha Event",
                            "event_year": "2024",
                            "matches": [
                                {
                                    "sub_event": "MS",
                                    "stage": "Main Draw",
                                    "round": "Final",
                                    "side_a": ["Same Name (CHN)"],
                                    "side_b": ["Opponent (JPN)"],
                                    "match_score": "3-1",
                                    "perspective": "side_a",
                                    "result_for_player": "win",
                                    "winner": "Same Name",
                                }
                            ],
                        }
                    ]
                }
            },
        }
        (self.player_matches_dir / "player_4_Same_Name.json").write_text(
            json.dumps(player_payload, ensure_ascii=False),
            encoding="utf-8",
        )

        self.import_event(1001)

        self.assertEqual(
            [("Same Name", "CHN", 4), ("Opponent", "JPN", 2)],
            self.side_player_ids(1001),
        )

    def test_same_name_historical_country_uses_player_match_evidence(self) -> None:
        self.same_name_players_path.write_text(
            "4,Same Name,CHN\n5,Same Name,CHN\n",
            encoding="utf-8",
        )
        self.country_history_path.write_text(
            json.dumps(
                [
                    {
                        "player_name": "Same Name",
                        "current_country": "CHN",
                        "historical_country": "MAC",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        write_event_file(
            self.matches_dir,
            1001,
            "Alpha Event",
            2024,
            "Same Name",
            side_a=["Same Name (MAC)"],
            side_b=["Opponent (JPN)"],
            match_score="3-2",
        )
        player_payload = {
            "schema_version": "match.v2",
            "player_id": 5,
            "player_name": "Same Name",
            "country_code": "CHN",
            "years": {
                "2024": {
                    "events": [
                        {
                            "event_name": "Alpha Event",
                            "event_year": "2024",
                            "matches": [
                                {
                                    "sub_event": "MS",
                                    "stage": "Main Draw",
                                    "round": "Final",
                                    "side_a": ["Same Name (MAC)"],
                                    "side_b": ["Opponent (JPN)"],
                                    "match_score": "3-2",
                                    "winner": "Same Name",
                                }
                            ],
                        }
                    ]
                }
            },
        }
        (self.player_matches_dir / "player_5_Same_Name.json").write_text(
            json.dumps(player_payload, ensure_ascii=False),
            encoding="utf-8",
        )

        self.import_event(1001)

        self.assertEqual(
            [("Same Name", "MAC", 5), ("Opponent", "JPN", 2)],
            self.side_player_ids(1001),
        )

    def test_same_name_multiple_player_match_evidence_keeps_null(self) -> None:
        self.same_name_players_path.write_text(
            "4,Same Name,CHN\n5,Same Name,CHN\n",
            encoding="utf-8",
        )
        write_event_file(
            self.matches_dir,
            1001,
            "Alpha Event",
            2024,
            "Same Name",
            side_a=["Same Name (CHN)"],
            side_b=["Opponent (JPN)"],
            match_score="3-0",
        )
        for player_id in (4, 5):
            player_payload = {
                "schema_version": "match.v2",
                "player_id": player_id,
                "player_name": "Same Name",
                "country_code": "CHN",
                "years": {
                    "2024": {
                        "events": [
                            {
                                "event_name": "Alpha Event",
                                "event_year": "2024",
                                "matches": [
                                    {
                                        "sub_event": "MS",
                                        "stage": "Main Draw",
                                        "round": "Final",
                                        "side_a": ["Same Name (CHN)"],
                                        "side_b": ["Opponent (JPN)"],
                                        "match_score": "3-0",
                                        "winner": "Same Name",
                                    }
                                ],
                            }
                        ]
                    }
                },
            }
            (self.player_matches_dir / f"player_{player_id}_Same_Name.json").write_text(
                json.dumps(player_payload, ensure_ascii=False),
                encoding="utf-8",
            )

        result = self.import_event(1001)

        self.assertEqual(
            [("Same Name", "CHN", None), ("Opponent", "JPN", 2)],
            self.side_player_ids(1001),
        )
        self.assertIn("Same Name (CHN)", result["ambiguous_same_name_players"])


if __name__ == "__main__":
    unittest.main()
