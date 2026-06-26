#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "scrape_event_schedule.py"


def load_module():
    if "dotenv" not in sys.modules:
        dotenv_stub = types.ModuleType("dotenv")
        dotenv_stub.load_dotenv = lambda *args, **kwargs: None
        sys.modules["dotenv"] = dotenv_stub

    spec = importlib.util.spec_from_file_location("scrape_event_schedule_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ScrapeEventScheduleTests(unittest.TestCase):
    def test_default_provider_defers_to_translator_environment(self) -> None:
        module = load_module()

        args = module.build_parser().parse_args(["--event-id", "3242"])

        self.assertIsNone(args.provider)


if __name__ == "__main__":
    unittest.main()
