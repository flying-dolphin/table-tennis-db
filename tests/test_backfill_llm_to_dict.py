import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import backfill_llm_to_dict


class BackfillLlmToDictTests(unittest.TestCase):
    def test_extract_entries_strips_event_year_with_shared_event_name_logic(self):
        data = {
            "events": [
                {
                    "event_id": 1,
                    "name": "World Championships 2026 Presented by Sponsor",
                    "name_zh": "2026年世界锦标赛",
                }
            ]
        }

        entries = backfill_llm_to_dict.extract_entries(data)

        self.assertEqual(entries, [("World Championships", "世界锦标赛", "events")])

    def test_extract_entries_prompts_for_conflicting_translations_and_accepts_choice(self):
        data = {
            "events": [
                {"event_id": 1, "event_kind": "WTT Contender", "event_kind_zh": "WTT挑战赛"},
                {"event_id": 2, "event_kind": "WTT Contender", "event_kind_zh": "WTT竞争者赛"},
            ]
        }

        with patch("builtins.input", return_value="2"):
            entries = backfill_llm_to_dict.extract_entries(data)

        self.assertEqual(entries, [("WTT Contender", "WTT竞争者赛", "events")])

    def test_extract_entries_prompts_for_conflicting_translations_and_accepts_manual_input(self):
        data = {
            "events": [
                {"event_id": 1, "event_type": "Regional", "event_type_zh": "地区赛事"},
                {"event_id": 2, "event_type": "Regional", "event_type_zh": "区域赛"},
            ]
        }

        with patch("builtins.input", side_effect=["m", "地区赛"]):
            entries = backfill_llm_to_dict.extract_entries(data)

        self.assertEqual(entries, [("Regional", "地区赛", "events")])

    def test_update_dict_keeps_existing_different_translation_after_manual_reject(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dict_path = Path(tmpdir) / "dict.json"
            dict_path.write_text(
                json.dumps(
                    {
                        "metadata": {"total_entries": 1},
                        "entries": {
                            "wtt contender": {
                                "original": "WTT Contender",
                                "translated": "WTT挑战赛",
                                "categories": ["events"],
                                "source": "dict",
                                "review_status": "pending",
                                "validators": {"events": "event_name"},
                                "updated_at": "2026-01-01T00:00:00",
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("builtins.input", return_value="n"):
                backfill_llm_to_dict.update_dict(
                    [("WTT Contender", "WTT竞争者赛", "events")],
                    dict_path,
                )

            data = json.loads(dict_path.read_text(encoding="utf-8"))
            self.assertEqual(data["entries"]["wtt contender"]["translated"], "WTT挑战赛")
            self.assertNotIn("updated_at", data["metadata"])


if __name__ == "__main__":
    unittest.main()
