#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

fake_translator_module = types.ModuleType("lib.translator")
fake_translator_module.Translator = object
sys.modules["lib.translator"] = fake_translator_module

from translate_profiles import translate_profile


class FakeTranslator:
    stopped = False

    def translate_one(self, text: str, category: str) -> str | None:
        values = {
            ("Example Player", "players"): "示例球员",
            ("China", "locations"): "中国",
            ("Male", "terms"): "男",
            ("Right-handed", "terms"): "右手",
        }
        return values.get((text, category))


class TranslateProfilesTests(unittest.TestCase):
    def test_rank_threshold_skips_chinese_fields_but_preserves_profile(self) -> None:
        profile = {
            "player_id": 10,
            "name": "Example Player",
            "country": "China",
            "country_code": "CHN",
            "gender": "Male",
            "playing_hand": "Right-handed",
            "career_best_rank": 51,
            "recent_matches": [{"id": 1}],
        }

        translated = translate_profile(
            dict(profile),
            FakeTranslator(),
            "player_10_Example_Player.json",
            career_best_rank_lte=50,
        )

        self.assertNotIn("recent_matches", translated)
        self.assertEqual("Example Player", translated["name"])
        self.assertNotIn("name_zh", translated)
        self.assertNotIn("gender_zh", translated)

    def test_rank_threshold_translates_chinese_fields_for_eligible_profile(self) -> None:
        profile = {
            "player_id": 10,
            "name": "Example Player",
            "country": "China",
            "country_code": "CHN",
            "gender": "Male",
            "playing_hand": "Right-handed",
            "career_best_rank": 50,
        }

        translated = translate_profile(
            dict(profile),
            FakeTranslator(),
            "player_10_Example_Player.json",
            career_best_rank_lte=50,
        )

        self.assertEqual("示例球员", translated["name_zh"])
        self.assertEqual("男", translated["gender_zh"])


if __name__ == "__main__":
    unittest.main()
