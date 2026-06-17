import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.event_translation import (
    translate_event_name_dict_only,
    translate_event_names_dict_then_llm,
    translate_event_names_llm_only,
)
from translate_event_names import main as translate_event_names_main


class FakeDictTranslator:
    def __init__(self):
        self.events = {
            "wtt champions doha": "WTT冠军赛多哈站",
            "wtt feeder dusseldorf ii": "WTT支线赛杜塞尔多夫站II",
            "world championships": "世界锦标赛",
        }

    def translate(self, value, category):
        if category != "events":
            return value
        return self.events.get(value.lower(), value)


class FakeLLMTranslator:
    def __init__(self):
        self.calls = []

    def translate_event_batch(self, items):
        self.calls.append(dict(items))
        return {key: f"LLM:{value}" for key, value in items.items()}


class EventTranslationTests(unittest.TestCase):
    def test_dict_only_strips_year_and_formats_year_first(self):
        result = translate_event_name_dict_only(
            "WTT Champions Doha 2026",
            dict_translator=FakeDictTranslator(),
        )

        self.assertEqual(result, "2026年WTT冠军赛多哈站")

    def test_dict_only_strips_presented_by_suffix(self):
        result = translate_event_name_dict_only(
            "World Championships 2026 Presented by Sponsor",
            dict_translator=FakeDictTranslator(),
        )

        self.assertEqual(result, "2026年世界锦标赛")

    def test_dict_only_folds_accents_for_lookup(self):
        result = translate_event_name_dict_only(
            "WTT Feeder Düsseldorf II 2026",
            dict_translator=FakeDictTranslator(),
        )

        self.assertEqual(result, "2026年WTT支线赛杜塞尔多夫站II")

    def test_dict_only_returns_none_on_miss(self):
        result = translate_event_name_dict_only(
            "Unknown Event 2026",
            dict_translator=FakeDictTranslator(),
        )

        self.assertIsNone(result)

    def test_llm_only_skips_dictionary_and_formats_year(self):
        llm = FakeLLMTranslator()
        result = translate_event_names_llm_only(
            {"a": "WTT Champions Doha 2026"},
            llm_translator=llm,
        )

        self.assertEqual(llm.calls, [{"a": "WTT Champions Doha"}])
        self.assertEqual(result, {"a": "2026年LLM:WTT Champions Doha"})

    def test_dict_then_llm_only_sends_misses_to_llm(self):
        llm = FakeLLMTranslator()
        result = translate_event_names_dict_then_llm(
            {
                "hit": "WTT Champions Doha 2026",
                "miss": "Unknown Event 2026",
            },
            dict_translator=FakeDictTranslator(),
            llm_translator=llm,
        )

        self.assertEqual(llm.calls, [{"miss": "Unknown Event"}])
        self.assertEqual(
            result,
            {
                "hit": "2026年WTT冠军赛多哈站",
                "miss": "2026年LLM:Unknown Event",
            },
        )


class TranslateEventNamesCliTests(unittest.TestCase):
    def test_cli_dict_mode_prints_translation(self):
        argv = [
            "translate_event_names.py",
            "--mode",
            "dict",
            "WTT Champions Doha 2026",
        ]
        stdout = io.StringIO()

        with patch.object(sys, "argv", argv), redirect_stdout(stdout):
            rc = translate_event_names_main()

        self.assertEqual(rc, 0)
        self.assertIn("2026年WTT冠军赛多哈站", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
