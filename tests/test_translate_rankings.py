import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import translate_rankings


class FakeTranslator:
    def translate(self, value, category):
        translations = {
            ("known player", "players"): "Known Player CN",
            ("WTT Test Event", "events"): "Translated Event",
        }
        return translations.get((value, category), value)


class TranslateRankingsTests(unittest.TestCase):
    def test_does_not_translate_or_log_missing_point_breakdown_events(self):
        data = {
            "rankings": [
                {
                    "name": "Known Player",
                    "points_breakdown": [
                        {
                            "event": "WTT Test Event",
                            "category": "Untranslated Category",
                        }
                    ],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)
            with patch.object(translate_rankings, "LOGS_DIR", logs_dir):
                translated = translate_rankings.translate_rankings(data, FakeTranslator(), "sample")
                log_text = (logs_dir / "translate_ranks.log").read_text(encoding="utf-8")

        breakdown = translated["rankings"][0]["points_breakdown"][0]
        self.assertEqual(breakdown["event"], "WTT Test Event")
        self.assertNotIn("event_zh", breakdown)
        self.assertNotIn("--- event", log_text)
        self.assertNotIn("WTT Test Event", log_text)
        self.assertIn("--- category (1) ---", log_text)
        self.assertIn("Untranslated Category", log_text)


if __name__ == "__main__":
    unittest.main()
