import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.country_codes import normalize_profile_country
from translate_profiles import translate_profile


class CountryNormalizationTests(unittest.TestCase):
    def test_replaces_country_code_country_with_english_name_and_chinese_name(self):
        profile = {"country": "ROU", "country_code": "ROU"}

        normalized, changed = normalize_profile_country(profile, include_country_zh=True)

        self.assertTrue(changed)
        self.assertEqual(normalized["country_code"], "ROU")
        self.assertEqual(normalized["country"], "ROMANIA")
        self.assertEqual(normalized["country_en"], "ROMANIA")
        self.assertEqual(normalized["country_zh"], "罗马尼亚")

    def test_preserves_existing_full_country_name_when_code_matches(self):
        profile = {"country": "UKRAINE", "country_code": "UKR"}

        normalized, changed = normalize_profile_country(profile, include_country_zh=True)

        self.assertTrue(changed)
        self.assertEqual(normalized["country"], "UKRAINE")
        self.assertEqual(normalized["country_en"], "UKRAINE")
        self.assertEqual(normalized["country_zh"], "乌克兰")


class TranslateProfilesCountryTests(unittest.TestCase):
    def test_country_translation_falls_back_to_country_code_map(self):
        profile = {
            "name": "SAMARA Elizabeta",
            "country": "ROMANIA",
            "country_code": "ROU",
        }
        indexes = {
            "players": {"samara elizabeta": "萨马拉"},
            "locations": {},
            "terms": {},
            "others": {},
        }

        translated = translate_profile(profile, indexes, "player_108226_SAMARA_Elizabeta.json")

        self.assertEqual(translated["country"], "ROMANIA")
        self.assertEqual(translated["country_code"], "ROU")
        self.assertEqual(translated["country_en"], "ROMANIA")
        self.assertEqual(translated["country_zh"], "罗马尼亚")


if __name__ == "__main__":
    unittest.main()
