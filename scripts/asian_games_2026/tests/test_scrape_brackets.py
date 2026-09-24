from __future__ import annotations

import unittest

from scripts.asian_games_2026.scrape_brackets import BRACKET_EVENTS, normalize_bracket_payload


def competitor(name: str, org: str, *, reg: str = "", win: bool = False, members=None):
    value = {
        "Reg": reg,
        "Name": name,
        "Org": org,
        "Res": "",
        "Win": win,
    }
    if members is not None:
        value["Members"] = members
    return value


def bracket_match(key: str, home: dict, away: dict, *, status: str = "", is_bye: bool = False):
    return {
        "Home": home,
        "Away": away,
        "Info": {
            "Key": key,
            "Status": status,
            "IsBye": is_bye,
            "DateTimeRaw": "",
        },
    }


class ScrapeBracketsTests(unittest.TestCase):
    def test_team_brackets_include_byes_without_scheduled_matches(self):
        for code, official in [('WT', 'W.TEAM--------------'), ('MT', 'M.TEAM--------------')]:
            self.assertEqual(BRACKET_EVENTS.get(code), official)
            payload = [{'Code': 'MAINDRAW', 'Phases': [{
                'Code': official + '.8FNL', 'Matches': [bracket_match(
                    official + '.8FNL.00010000', competitor('China', 'CHN', win=True),
                    competitor('', 'BYE'), status='OFFICIAL', is_bye=True)]}]}]
            row = normalize_bracket_payload(payload, sub_event_type_code=code)[0]
            self.assertEqual(row['round_code'], 'R16')
            self.assertEqual(row['side_b_team_code'], 'BYE')
            self.assertEqual(row['winner_side'], 'A')
            self.assertIsNone(row['scheduled_date'])
            self.assertIsNone(row['match_score'])

    def test_normalizes_rounds_byes_and_feeder_links(self) -> None:
        payload = [
            {
                "Code": "MAINDRAW",
                "Desc": "Main Draw",
                "isDoubles": False,
                "Phases": [
                    {
                        "Code": "M.SINGLES-----------.R64-",
                        "Desc": "Round 1",
                        "Matches": [
                            bracket_match(
                                "M.SINGLES-----------.R64-.000100--",
                                competitor("WANG Chuqin", "CHN", reg="16273238", win=True),
                                competitor("", "BYE", reg="7"),
                                status="OFFICIAL",
                                is_bye=True,
                            ),
                            bracket_match(
                                "M.SINGLES-----------.R64-.000200--",
                                competitor("A Player", "JPN", reg="1"),
                                competitor("B Player", "KOR", reg="2"),
                            ),
                        ],
                    },
                    {
                        "Code": "M.SINGLES-----------.R32-",
                        "Desc": "Round 2",
                        "Matches": [
                            bracket_match(
                                "M.SINGLES-----------.R32-.000100--",
                                competitor("WANG Chuqin", "CHN", reg="16273238"),
                                competitor("", ""),
                            )
                        ],
                    },
                ],
            }
        ]

        rows = normalize_bracket_payload(payload, sub_event_type_code="MS")

        self.assertEqual(len(rows), 3)
        first, second, next_round = rows
        self.assertEqual(
            (first["stage_code"], first["round_code"], first["round_order"], first["bracket_position"]),
            ("MAIN_DRAW", "R64", 20, 1),
        )
        self.assertEqual(first["status"], "completed")
        self.assertEqual(first["winner_side"], "A")
        self.assertEqual(first["side_b_team_code"], "BYE")
        self.assertEqual(first["side_b_placeholder"], "BYE")
        self.assertEqual(second["bracket_position"], 2)
        self.assertEqual(next_round["round_code"], "R32")
        self.assertEqual(next_round["side_a_previous_unit"], first["external_unit_code"])
        self.assertEqual(next_round["side_b_previous_unit"], second["external_unit_code"])
        self.assertEqual(next_round["raw_source_payload"]["Home"]["Name"], "WANG Chuqin")

    def test_preserves_doubles_members_and_score(self) -> None:
        payload = [
            {
                "Code": "MAINDRAW",
                "Desc": "Main Draw",
                "isDoubles": True,
                "Phases": [
                    {
                        "Code": "X.DOUBLES-----------.FNL-",
                        "Desc": "Final",
                        "Matches": [
                            {
                                **bracket_match(
                                    "X.DOUBLES-----------.FNL-.000100--",
                                    competitor(
                                        "WANG Chuqin / SUN Yingsha",
                                        "CHN",
                                        win=True,
                                        members=[
                                            {"Reg": "16273238", "Name": "WANG Chuqin", "Org": "CHN"},
                                            {"Reg": "16277232", "Name": "SUN Yingsha", "Org": "CHN"},
                                        ],
                                    ),
                                    competitor(
                                        "LIM Jonghoon / SHIN Yubin",
                                        "KOR",
                                        members=[
                                            {"Reg": "16562726", "Name": "LIM Jonghoon", "Org": "KOR"},
                                            {"Reg": "16564280", "Name": "SHIN Yubin", "Org": "KOR"},
                                        ],
                                    ),
                                    status="OFFICIAL",
                                ),
                                "Home": {
                                    **competitor(
                                        "WANG Chuqin / SUN Yingsha",
                                        "CHN",
                                        win=True,
                                        members=[
                                            {"Reg": "16273238", "Name": "WANG Chuqin", "Org": "CHN"},
                                            {"Reg": "16277232", "Name": "SUN Yingsha", "Org": "CHN"},
                                        ],
                                    ),
                                    "Res": "4",
                                },
                                "Away": {
                                    **competitor(
                                        "LIM Jonghoon / SHIN Yubin",
                                        "KOR",
                                        members=[
                                            {"Reg": "16562726", "Name": "LIM Jonghoon", "Org": "KOR"},
                                            {"Reg": "16564280", "Name": "SHIN Yubin", "Org": "KOR"},
                                        ],
                                    ),
                                    "Res": "2",
                                },
                            }
                        ],
                    }
                ],
            }
        ]

        row = normalize_bracket_payload(payload, sub_event_type_code="XD")[0]

        self.assertEqual((row["round_code"], row["round_order"]), ("F", 80))
        self.assertEqual(row["match_score"], "4-2")
        self.assertEqual(row["winner_side"], "A")
        self.assertEqual(
            [member["Name"] for member in row["raw_source_payload"]["Home"]["Members"]],
            ["WANG Chuqin", "SUN Yingsha"],
        )

    def test_rejects_payload_without_main_draw(self) -> None:
        with self.assertRaisesRegex(ValueError, "no bracket phases"):
            normalize_bracket_payload([], sub_event_type_code="WS")


if __name__ == "__main__":
    unittest.main()
