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

from audit_same_name_players import audit_same_name_players


class AuditSameNamePlayersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "ittf.db"
        self.output_path = self.root / "same_name_players.txt"
        self.history_path = self.root / "player_country_history.json"

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE players (
                player_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                name_zh TEXT,
                country_code TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT INTO players (player_id, name, name_zh, country_code) VALUES (?, ?, ?, ?)",
            [
                (10, "Same Name", "同名甲", "CHN"),
                (11, "Name Same", "同名乙", "CHN"),
                (12, "Solo Player", "单人", "JPN"),
                (13, "Traveler", "旅行者", "MAC"),
                (14, "Traveler", "旅行者二", "CHN"),
                (99, "Existing Person", "已有", "KOR"),
            ],
        )
        conn.commit()
        conn.close()

        self.output_path.write_text("99,Existing Person,KOR\n", encoding="utf-8")
        self.history_path.write_text(
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

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_audit_merges_current_and_historical_same_name_groups(self) -> None:
        summary = audit_same_name_players(
            db_path=self.db_path,
            output_path=self.output_path,
            country_history_path=self.history_path,
            update=True,
        )

        self.assertEqual(4, summary["discovered_entries"])
        self.assertEqual(4, summary["added_entries"])
        self.assertEqual(
            [
                "99,Existing Person,KOR",
                "10,Same Name,CHN",
                "11,Name Same,CHN",
                "13,Traveler,CHN",
                "14,Traveler,CHN",
            ],
            self.output_path.read_text(encoding="utf-8").strip().splitlines(),
        )

    def test_audit_discovers_same_name_groups_from_profile_json_and_preserves_existing(self) -> None:
        profile_dir = self.root / "profiles"
        profile_dir.mkdir()
        (profile_dir / "player_201_Same_Profile.json").write_text(
            json.dumps({"player_id": 201, "name": "Same Profile", "country_code": "CHN"}),
            encoding="utf-8",
        )
        (profile_dir / "player_202_Profile_Same.json").write_text(
            json.dumps({"player_id": 202, "english_name": "Profile Same", "country_code": "CHN"}),
            encoding="utf-8",
        )
        (profile_dir / "player_203_Solo_Profile.json").write_text(
            json.dumps({"player_id": 203, "name": "Solo Profile", "country_code": "JPN"}),
            encoding="utf-8",
        )

        summary = audit_same_name_players(
            db_path=self.db_path,
            output_path=self.output_path,
            country_history_path=self.history_path,
            profile_dir=profile_dir,
            update=True,
        )

        lines = self.output_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertIn("99,Existing Person,KOR", lines)
        self.assertIn("201,Same Profile,CHN", lines)
        self.assertIn("202,Profile Same,CHN", lines)
        self.assertNotIn("203,Solo Profile,JPN", lines)
        self.assertGreaterEqual(summary["added_entries"], 2)


if __name__ == "__main__":
    unittest.main()
