from __future__ import annotations

import unittest

from scripts.asian_games_2026.scrape_schedule import build_schedule


class ScrapeScheduleTests(unittest.TestCase):
    def test_groups_source_instants_and_outputs_beijing_time(self) -> None:
        rows_by_date = {
            "2026-09-20": [
                {
                    "isH2H": True,
                    "DateTimeRaw": "2026-09-20T10:00:00+09:00",
                    "EventDesc": "Women's Team",
                    "PhaseDesc": "Women's Team First Stage -Group A",
                    "VenueDesc": "SKY HALL TOYOTA",
                },
                {
                    "isH2H": True,
                    "DateTimeRaw": "2026-09-20T10:00:00+09:00",
                    "EventDesc": "Men's Team",
                    "PhaseDesc": "Men's Team First Stage -Group B",
                    "VenueDesc": "SKY HALL TOYOTA",
                },
                {
                    "isH2H": False,
                    "DateTimeRaw": "2026-09-20T10:00:00+09:00",
                    "EventDesc": "Women's Team",
                    "PhaseDesc": "Women's Team First Stage -Group A",
                    "VenueDesc": "SKY HALL TOYOTA",
                },
            ]
        }

        self.assertEqual(
            build_schedule(rows_by_date),
            [
                {
                    "日期": "9月20日",
                    "场次": "",
                    "时间": "09:00",
                    "赛事": ["女团小组赛A组", "男团小组赛B组"],
                    "球台": "",
                    "场馆": "SKY HALL TOYOTA",
                    "_parsed": [
                        {
                            "sub_event_code": "WT",
                            "stage_code": "MAIN_DRAW",
                            "round_code": "RR",
                        },
                        {
                            "sub_event_code": "MT",
                            "stage_code": "MAIN_DRAW",
                            "round_code": "RR",
                        },
                    ],
                }
            ],
        )

    def test_beijing_date_is_derived_from_converted_instant(self) -> None:
        rows = {
            "2026-09-21": [
                {
                    "isH2H": True,
                    "DateTimeRaw": "2026-09-21T00:30:00+09:00",
                    "EventDesc": "Men's Singles",
                    "PhaseDesc": "Men's Singles Round of 64",
                    "VenueDesc": "SKY HALL TOYOTA",
                }
            ]
        }

        item = build_schedule(rows)[0]
        self.assertEqual(item["日期"], "9月20日")
        self.assertEqual(item["时间"], "23:30")

    def test_round_one_uses_structured_phase_code(self) -> None:
        rows = {
            "2026-09-21": [
                {
                    "isH2H": True,
                    "DateTimeRaw": "2026-09-21T18:30:00+09:00",
                    "EventDesc": "Women's Doubles",
                    "Phase": "W.DOUBLES-----------.R64-",
                    "PhaseDesc": "Women's Doubles Round 1",
                    "VenueDesc": "SKY HALL TOYOTA",
                }
            ]
        }

        item = build_schedule(rows)[0]

        self.assertEqual(
            item["_parsed"],
            [{"sub_event_code": "WD", "stage_code": "MAIN_DRAW", "round_code": "R64"}],
        )


if __name__ == "__main__":
    unittest.main()
