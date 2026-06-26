#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "prepare_same_name_player_matches.py"


def load_module():
    spec = importlib.util.spec_from_file_location("prepare_same_name_player_matches_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PrepareSameNamePlayerMatchesTests(unittest.TestCase):
    def test_plan_includes_all_same_name_candidates_and_marks_existing_cn_files(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "event_matches" / "cn"
            source_dir.mkdir(parents=True)
            same_name_path = root / "same_name_players.txt"
            matches_complete_dir = root / "matches_complete"
            (matches_complete_dir / "cn").mkdir(parents=True)

            same_name_path.write_text(
                "4,Same Name,CHN\n"
                "5,Same Name,CHN\n"
                "6,Other Name,JPN\n"
                "7,Other Name,JPN\n",
                encoding="utf-8",
            )
            payload = {
                "schema_version": "event_match.v1",
                "event_id": 1001,
                "event_year": 2024,
                "event": "Alpha Event",
                "matches": [
                    {
                        "side_a": ["Same Name (CHN)"],
                        "side_b": ["Opponent (JPN)"],
                        "raw_row_text": "2024 | Alpha Event | Same Name (CHN) | Opponent (JPN)",
                    }
                ],
            }
            (source_dir / "Alpha_Event_1001.json").write_text(json.dumps(payload), encoding="utf-8")
            (matches_complete_dir / "cn" / "player_4_Same_Name.json").write_text("{}", encoding="utf-8")

            plan = module.build_preparation_plan(
                source_dir=source_dir,
                event_ids=[1001],
                same_name_players_path=same_name_path,
                matches_complete_dir=matches_complete_dir,
                from_date=None,
                force=False,
            )

            self.assertEqual([1001], plan["event_ids"])
            self.assertEqual("2024-01-01", plan["from_date"])
            self.assertEqual(
                [
                    {
                        "player_id": 4,
                        "player_name": "Same Name",
                        "country_code": "CHN",
                        "cn_exists": True,
                        "needs_scrape": False,
                    },
                    {
                        "player_id": 5,
                        "player_name": "Same Name",
                        "country_code": "CHN",
                        "cn_exists": False,
                        "needs_scrape": True,
                    },
                ],
                plan["targets"],
            )

    def test_plan_ignores_non_selected_event_files(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "event_matches" / "cn"
            source_dir.mkdir(parents=True)
            same_name_path = root / "same_name_players.txt"
            matches_complete_dir = root / "matches_complete"

            same_name_path.write_text("4,Same Name,CHN\n5,Same Name,CHN\n", encoding="utf-8")
            payload = {
                "schema_version": "event_match.v1",
                "event_id": 1002,
                "event_year": 2024,
                "matches": [{"side_a": ["Same Name (CHN)"], "side_b": ["Opponent (JPN)"]}],
            }
            (source_dir / "Beta_Event_1002.json").write_text(json.dumps(payload), encoding="utf-8")

            plan = module.build_preparation_plan(
                source_dir=source_dir,
                event_ids=[1001],
                same_name_players_path=same_name_path,
                matches_complete_dir=matches_complete_dir,
                from_date="2020-01-01",
                force=False,
            )

            self.assertEqual([], plan["targets"])


if __name__ == "__main__":
    unittest.main()
