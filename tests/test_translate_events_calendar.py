import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import translate_events_calendar


class FakeCalendarTranslator:
    def __init__(self):
        self.batch_calls = []
        self.one_calls = []
        self.stopped = False

    def translate_batch(self, items, data_type):
        self.batch_calls.append((dict(items), data_type))
        return {key: f"新译名:{value}" for key, value in items.items()}

    def translate_one(self, value, data_type):
        self.one_calls.append((value, data_type))
        if data_type == "locations" and value == "Doha, Qatar":
            return "卡塔尔多哈"
        return value


class TranslateEventsCalendarTests(unittest.TestCase):
    def test_parser_defaults_to_both_and_confirm_for_llm_modes(self):
        parser = translate_events_calendar.build_parser()

        args = parser.parse_args([])
        translate_events_calendar.normalize_args(args)
        self.assertEqual(args.mode, "both")
        self.assertTrue(args.confirm)
        self.assertIsNone(args.provider)
        self.assertIsNone(args.model)

        args = parser.parse_args(["--mode", "dict"])
        translate_events_calendar.normalize_args(args)
        self.assertFalse(args.confirm)

        args = parser.parse_args(["--mode", "llm", "--no-confirm"])
        translate_events_calendar.normalize_args(args)
        self.assertFalse(args.confirm)

    def test_translate_file_retranslates_name_instead_of_reusing_existing_cn_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            orig_file = tmp / "events_calendar_2026.json"
            cn_file = tmp / "cn" / "events_calendar_2026.json"
            orig_file.write_text(
                json.dumps(
                    {
                        "year": 2026,
                        "events": [
                            {
                                "name": "WTT Champions Doha 2026",
                                "date": "02-05 Jan",
                                "location": "Doha, Qatar",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            cn_file.parent.mkdir()
            cn_file.write_text(
                json.dumps(
                    {
                        "year": 2026,
                        "events": [
                            {
                                "name": "WTT Champions Doha 2026",
                                "name_zh": "旧译名",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            translator = FakeCalendarTranslator()
            args = argparse.Namespace(force=False)
            rc = translate_events_calendar.translate_file(orig_file, cn_file, args, translator)
            saved = json.loads(cn_file.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertEqual(
            translator.batch_calls,
            [({"event_1.name": "WTT Champions Doha 2026"}, "events")],
        )
        event = saved["events"][0]
        self.assertEqual(event["name_zh"], "新译名:WTT Champions Doha 2026")
        self.assertEqual(event["location_zh"], "卡塔尔多哈")
        self.assertEqual(event["date_zh"], "01-02至01-05")


class TranslatorDefaultEnvTests(unittest.TestCase):
    def test_translator_uses_default_provider_and_model_from_environment(self):
        from lib import translator as translator_module

        captured = {}

        class FakeDictTranslator:
            def __init__(self, *args, **kwargs):
                pass

        class FakeLLMTranslator:
            def __init__(self, provider="minimax", model=None, api_key=None):
                captured["provider"] = provider
                captured["model"] = model
                captured["api_key"] = api_key

        with patch.dict(
            translator_module.os.environ,
            {"DEFAULT_PROVIDER": "qwen", "DEFAULT_MODEL": "qwen-test"},
            clear=False,
        ), patch.object(translator_module, "DictTranslator", FakeDictTranslator), patch.object(
            translator_module, "LLMTranslator", FakeLLMTranslator
        ):
            translator_module.Translator(mode="both", provider=None, model=None)

        self.assertEqual(captured["provider"], "qwen")
        self.assertEqual(captured["model"], "qwen-test")


if __name__ == "__main__":
    unittest.main()
