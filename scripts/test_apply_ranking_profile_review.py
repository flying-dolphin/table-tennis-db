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

from apply_ranking_profile_review import apply_review


class ApplyRankingProfileReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.review_path = self.root / "review.json"
        self.dict_path = self.root / "translation_dict.json"
        self.ranking_path = self.root / "ranking.json"
        self.same_name_path = self.root / "same_name_players.txt"
        self.db_path = self.root / "ittf.db"

        self.dict_path.write_text('{"metadata": {}, "entries": {}}\n', encoding="utf-8")
        self.ranking_path.write_text('{"rankings": []}\n', encoding="utf-8")

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
                (4, "Same Name", "同名甲", "CHN"),
                (5, "Name Same", "同名乙", "CHN"),
                (6, "Same Name", "其他国家", "JPN"),
            ],
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_manual_player_id_resolution_adds_same_name_country_group(self) -> None:
        self.review_path.write_text(
            json.dumps(
                {
                    "missing_translations": [],
                    "unresolved_player_ids": [
                        {
                            "weekly": {
                                "name": "Same Name",
                                "country_code": "CHN",
                            },
                            "resolution": {
                                "player_id": 4,
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        summary = apply_review(
            self.review_path,
            dict_path=self.dict_path,
            ranking_file=self.ranking_path,
            same_name_players_path=self.same_name_path,
            db_path=self.db_path,
        )

        self.assertEqual(2, summary["same_name_players_added"])
        self.assertEqual(
            ["4,Same Name,CHN", "5,Name Same,CHN"],
            self.same_name_path.read_text(encoding="utf-8").strip().splitlines(),
        )


if __name__ == "__main__":
    unittest.main()
