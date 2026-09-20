from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from scripts.asian_games_2026.player_resolution import player_resolver


ROOT = Path(__file__).resolve().parents[3]


class PlayerResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript((ROOT / "scripts/db/schema.sql").read_text(encoding="utf-8"))
        self.conn.executemany(
            "INSERT INTO players(player_id,name,slug,country_code,gender) VALUES (?,?,?,?,?)",
            [
                (117332, "ZHU Yuling", "zhu-yuling", "MAC", "Female"),
                (207486, "KUAN Cheok Lam", "kuan-cheok-lam", "MAC", "Female"),
                (131966, "TAN Zhao Yun", "tan-zhao-yun", "SGP", "Female"),
                (133601, "TAN Zhao Ray", "tan-zhao-ray", "SGP", "Male"),
                (144488, "LE Ellsworth", "le-ellsworth", "SGP", "Male"),
                (300001, "DUP Name One", "dup-name-one", "JPN", "Female"),
                (300002, "DUP Name One", "dup-name-one-2", "JPN", "Female"),
            ],
        )
        self.conn.commit()
        self.resolve = player_resolver(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_compact_name_matches_internal_space_variant(self) -> None:
        self.assertEqual(117332, self.resolve("MAC", "ZHU Yu Ling", "WS"))

    def test_verified_alias_matches_truncated_source_name(self) -> None:
        self.assertEqual(207486, self.resolve("MAC", "KUAN Cheok", "WT"))

    def test_project_gender_disambiguates_same_source_name(self) -> None:
        self.assertEqual(131966, self.resolve("SGP", "TAN Zhao", "WT"))
        self.assertEqual(133601, self.resolve("SGP", "TAN Zhao", "MT"))
        self.assertIsNone(self.resolve("SGP", "TAN Zhao", "XD"))

    def test_token_order_variant_matches_when_unique(self) -> None:
        self.assertEqual(144488, self.resolve("SGP", "ELLSWORTH Le", "MT"))

    def test_ambiguous_candidate_is_not_guessed(self) -> None:
        self.assertIsNone(self.resolve("JPN", "DUP Name One", "WS"))
        self.assertIsNone(self.resolve("JPN", "UNKNOWN Player", "WS"))


if __name__ == "__main__":
    unittest.main()
