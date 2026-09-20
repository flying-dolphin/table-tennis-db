from __future__ import annotations

import unittest

from scripts.asian_games_2026.scrape_matches import (
    normalize_detail,
    select_detail_units,
)


def competitor(name: str, org: str, result: str, *, wlt: str = "", members=None):
    value = {"Name": name, "Org": org, "Result": result, "WLT": wlt, "Reg": name}
    if members is not None:
        value["Members"] = members
    return value


class ScrapeMatchesTests(unittest.TestCase):
    def test_selects_linked_parent_results(self) -> None:
        rows = [
            {"Key": "running", "isH2H": True, "ShowLink": True, "Status": "RUNNING"},
            {"Key": "official", "isH2H": True, "ShowLink": True, "Status": "OFFICIAL"},
            {"Key": "future", "isH2H": True, "ShowLink": True, "Status": "START_LIST"},
            {"Key": "child", "isH2H": False, "ShowLink": True, "Status": "RUNNING"},
        ]
        self.assertEqual([x["Key"] for x in select_detail_units(rows)], ["running", "official"])
        self.assertEqual(
            [x["Key"] for x in select_detail_units(rows, all_linked=True)],
            ["running", "official", "future"],
        )

    def test_team_detail_keeps_roster_separate_from_rubbers(self) -> None:
        detail = {
            "Info": {
                "Key": "WT.GPA.1",
                "EventDesc": "Women's Team",
                "PhaseDesc": "Women's Team Group A",
                "DateTimeRaw": "2026-09-20T10:00:00+09:00",
                "Status": "OFFICIAL",
                "LocDesc": "Table 1",
                "UnitDescA": "Match 1",
            },
            "Results": {"ResDetail": "3-1"},
            "Competitors": [
                competitor(
                    "Japan", "JPN", "3", wlt="W",
                    members=[
                        {"Reg": "ag-1", "Name": "PLAYER One", "Org": "JPN", "Order": 1},
                        {"Reg": "ag-2", "Name": "PLAYER Bench", "Org": "JPN", "Order": 2},
                    ],
                ),
                competitor("Korea", "KOR", "1", wlt="L", members=[]),
            ],
            "SubUnits": [
                {
                    "Info": {
                        "Key": "WT.GPA.11",
                        "EventDesc": "Women's Team",
                        "PhaseDesc": "Women's Team Group A",
                        "DateTimeRaw": "2026-09-20T10:00:00+09:00",
                        "Status": "OFFICIAL",
                    },
                    "Results": {
                        "CurrentPeriod": 3,
                        "ResDetail": "11:4, 8:11, 11:6",
                        "Periods": [
                            {"Order": 1, "ResHome": "11", "ResAway": "4"},
                            {"Order": 2, "ResHome": "8", "ResAway": "11"},
                            {"Order": 3, "ResHome": "11", "ResAway": "6"},
                        ],
                    },
                    "Competitors": [
                        competitor("PLAYER One", "JPN", "2", wlt="W"),
                        competitor("PLAYER Other", "KOR", "1", wlt="L"),
                    ],
                }
            ],
        }

        normalized = normalize_detail(detail)
        self.assertEqual(normalized["kind"], "team_tie")
        self.assertEqual([p["name"] for p in normalized["sides"][0]["nominated_players"]], ["PLAYER One", "PLAYER Bench"])
        self.assertEqual([p["name"] for p in normalized["rubbers"][0]["sides"][0]["players"]], ["PLAYER One"])
        self.assertEqual(normalized["scheduled_utc_at"], "2026-09-20T01:00:00Z")
        self.assertEqual(normalized["scheduled_beijing_at"], "2026-09-20T09:00:00+08:00")
        self.assertEqual(
            normalized["rubbers"][0]["games"],
            [
                {"player": 11, "opponent": 4},
                {"player": 8, "opponent": 11},
                {"player": 11, "opponent": 6},
            ],
        )

    def test_individual_detail_becomes_match(self) -> None:
        detail = {
            "Info": {
                "Key": "MS.R64.1", "EventDesc": "Men's Singles",
                "PhaseDesc": "Men's Singles Round of 64",
                "DateTimeRaw": "2026-09-24T10:00:00+09:00", "Status": "RUNNING",
            },
            "Results": {"CurrentPeriod": 1, "Periods": [{"Order": 1, "ResHome": "5", "ResAway": "4"}]},
            "Competitors": [
                competitor("A One", "CHN", "0"), competitor("B Two", "JPN", "0")
            ],
        }
        normalized = normalize_detail(detail)
        self.assertEqual(normalized["kind"], "match")
        self.assertEqual(normalized["sub_event_type_code"], "MS")
        self.assertEqual(len(normalized["sides"]), 2)
        self.assertNotIn("rubbers", normalized)


if __name__ == "__main__":
    unittest.main()
