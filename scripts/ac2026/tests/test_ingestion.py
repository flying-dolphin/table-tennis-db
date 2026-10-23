from __future__ import annotations

import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from scripts.ac2026.common import EVENT_NAME, ROOT, PROJECTS, ROUND_NAMES, read_json, timestamp, write_json
from scripts.ac2026.finalize import validate_current
from scripts.ac2026.import_current import import_snapshot
from scripts.ac2026.normalize import (build_snapshot, competitor_players, normalize_brackets,
    normalize_match, normalize_team, result_fields, round_meta)
from scripts.ac2026.scrape import capture, load_capture
from scripts.ac2026.refresh import event_lock
from scripts.ac2026.generate_crontab import generate_crontab

FIXTURE = Path(__file__).parent / "fixtures/official_samples.json"
REVERSED = "M.TEAM--------------.QFNL.00020000"
RETIRED = "W.TEAM--------------.GP04.00050000"
DOUBLE = "W.DOUBLES-----------.R64-.000200--"


def samples():
    return read_json(FIXTURE)


def snapshot():
    f = samples()
    rosters = {e["Reg"]: competitor_players(e) for e in f["entries"]}
    issues = []
    return {"event_id": 3474, "captured_at": "2026-10-22T01:00:00.000000Z", "batch_id": "test-batch", "full": True,
            "champ": {"events": [{"Key": k} for k in PROJECTS], "isFinished": False},
            "team_ties": [normalize_team(f[REVERSED], "2026-10-21", rosters, issues)],
            "matches": [normalize_match(f[DOUBLE], "2026-10-21")],
            "brackets": normalize_brackets(f["brackets"], "WS"), "standings": [], "issues": issues}


class NormalizeTests(unittest.TestCase):
    def test_position_draw_9_to_16(self):
        phase = copy.deepcopy(samples()["brackets"][0]["Phases"][0])
        phase["Code"] = "X.DOUBLES-----------.916-"
        rows = normalize_brackets([{"Code": "9-16", "Phases": [phase]}], "XD")
        self.assertEqual(len(rows), len(phase["Matches"]))
        for row in rows:
            self.assertEqual(row["draw_code"], "9-16")
            self.assertEqual(row["stage_code"], "POSITION_DRAW")
            self.assertEqual(row["round_code"], "P9_16")
            self.assertIsNone(row["side_a_previous_unit"])
            self.assertIsNone(row["side_b_previous_unit"])
        self.assertEqual(round_meta("X.DOUBLES-----------.FNL-", "9-16")["stage_label"], "Position Draw")

    def test_consolation_projects_build_complete_snapshot(self):
        projects = {"M.DOUBLES-----------": ("MD", ["916-", "1616", "1314"]),
                    "W.DOUBLES-----------": ("WD", ["916-", "1616", "1516"]),
                    "X.DOUBLES-----------": ("XD", ["1616", "1314"])}
        payloads = {"champ.json": {"events": [{"Key": k} for k in PROJECTS], "dates": []},
                    "match/live.json": []}
        for pk in PROJECTS:
            for section in ("entries", "groups", "brackets"):
                payloads[f"{section}/{pk}.json"] = []
        expected = {"916-": "P9_16", "1616": "P13_16", "1314": "P13_14", "1516": "P15_16"}
        for pk, (code, phases) in projects.items():
            draws = []
            for phase_code in reversed(phases):
                phase = copy.deepcopy(samples()["brackets"][0]["Phases"][0])
                phase["Code"] = f"{pk}.{phase_code}"
                for index, match in enumerate(phase["Matches"], 1):
                    match["Info"]["Code"] = f"{pk}.{phase_code}.{index:04d}00--"
                draws.append(phase)
            payloads[f"brackets/{pk}.json"] = [{"Code": "CONS", "Phases": draws}]
        result = build_snapshot({"batch_id": "cons", "captured_at": "2026-10-23T00:00:00Z",
                                 "full": True, "files": {}}, payloads)
        self.assertEqual(result["issues"], [])
        self.assertEqual(set(result["bracket_projects"]), {"MD", "WD", "XD"})
        for pk, (code, phases) in projects.items():
            rows = [r for r in result["brackets"] if r["sub_event_type_code"] == code]
            count = len(samples()["brackets"][0]["Phases"][0]["Matches"])
            self.assertEqual([r["round_code"] for r in rows],
                             [expected[p] for p in phases for _ in range(count)])
            for row in rows:
                self.assertEqual(row["draw_code"], "CONS")
                self.assertEqual(row["stage_code"], "POSITION_DRAW")
                self.assertIsNone(row["side_a_previous_unit"])
                self.assertIsNone(row["side_b_previous_unit"])
                self.assertEqual(row["raw_source_payload"]["_original"]["Info"]["Code"],
                                 row["external_unit_code"])

    def test_consolation_round_semantics_and_parallel_finals(self):
        for phase, code in (("1616", "P13_16"), ("1314", "P13_14"), ("1516", "P15_16")):
            for draw in (None, "CONS"):
                meta = round_meta(f"X.DOUBLES-----------.{phase}", draw)
                self.assertEqual(meta["round_code"], code)
                self.assertEqual(meta["stage_code"], "POSITION_DRAW")
                self.assertEqual(meta["round_label"], ROUND_NAMES[code][0])
        first = round_meta("X.DOUBLES-----------.1616", "CONS")
        finals = [round_meta(f"X.DOUBLES-----------.{p}", "CONS") for p in ("1314", "1516")]
        self.assertLess(first["round_order"], finals[0]["round_order"])
        self.assertEqual(finals[0]["round_order"], finals[1]["round_order"])
        self.assertEqual(ROUND_NAMES["P13_16"], ("Pos. 13-16", "第13至16名排位赛"))
        self.assertEqual(round_meta("X.DOUBLES-----------.FNL-", "CONS")["stage_label"], "Position Draw")
        with self.assertRaisesRegex(ValueError, "unsupported draw"):
            round_meta("X.DOUBLES-----------.FNL-", "UNKNOWN")
        with self.assertRaisesRegex(ValueError, "unsupported phase"):
            round_meta("X.DOUBLES-----------.9999", "CONS")

    def test_first_live_game_is_not_skipped_at_zero_sets(self):
        f = samples()
        row = f[REVERSED]
        row["Status"] = 2
        row["SubMatches"] = row["SubMatches"][:1]
        for key, score in (("Home", "5"), ("Away", "3")):
            row["SubMatches"][0][key]["Res"] = "0"
            row["SubMatches"][0][key]["Splits"] = [{"Res": score}] + [{"Res": ""}] * 4
        rosters = {e["Reg"]: competitor_players(e) for e in f["entries"]}
        tie = normalize_team(row, "2026-10-21", rosters, [])
        self.assertEqual(len(tie["rubbers"]), 1)
        self.assertEqual(tie["rubbers"][0]["status"], "live")
        self.assertEqual(tie["rubbers"][0]["games"], [{"player": 3, "opponent": 5}])

    def test_official_reversed_rubbers_align_scores_games_players(self):
        s = snapshot()
        tie = s["team_ties"][0]
        self.assertEqual(tie["match_score"], "0-3")
        self.assertEqual(len(tie["rubbers"]), 3)
        child = tie["rubbers"][0]
        self.assertEqual(child["winner_side"], "B")
        self.assertEqual(child["match_score"], "1-3")
        self.assertEqual(child["games"][0], {"player": 11, "opponent": 8})
        self.assertEqual([v["team_code"] for v in child["sides"]], ["HKG", "TPE"])
        self.assertEqual(child["sides"][0]["players"][0]["source_id"], "112620")
        self.assertEqual(len(s["issues"]), 3)
        self.assertTrue(all(i["severity"] == "warning" for i in s["issues"]))

    def test_retirement_is_played_match_not_walkover(self):
        f = samples()
        issues = []
        rosters = {e["Reg"]: competitor_players(e) for e in f["entries"]}
        tie = normalize_team(f[RETIRED], "2026-10-19", rosters, issues)
        self.assertEqual(issues, [])
        child = tie["rubbers"][2]
        self.assertEqual((child["status"], child["match_score"], child["source_status"]), ("completed", "0-3", "RET"))
        self.assertEqual(len(tie["rubbers"]), 3)

    def test_wo_is_not_normal_win(self):
        fields = result_fields({"Res": "WO"}, {"Res": "3"}, "completed")
        self.assertEqual((fields["status"], fields["winner_side"]), ("walkover", "B"))

    def test_doubles_members_and_source_ids(self):
        match = snapshot()["matches"][0]
        self.assertEqual([len(s["players"]) for s in match["sides"]], [2, 2])
        self.assertEqual(match["sides"][0]["players"][0]["source_id"], "108526")

    def test_bye_kept_in_bracket_with_name_alias_and_feeders(self):
        rows = snapshot()["brackets"]
        self.assertEqual(rows[0]["side_b_placeholder"], "BYE")
        self.assertIsNone(rows[0]["match_score"])
        self.assertEqual(rows[0]["raw_source_payload"]["Home"]["Name"], "HARIMOTO Miwa")
        self.assertEqual(rows[2]["side_a_previous_unit"], rows[0]["external_unit_code"])
        self.assertEqual(rows[0]["raw_source_payload"]["_original"], samples()["brackets"][0]["Phases"][0]["Matches"][0])

    def test_round_classification(self):
        self.assertEqual(round_meta("M.TEAM--------------.GP07")["group_code"], "7")
        self.assertEqual(round_meta("M.TEAM--------------.RND2")["stage_code"], "PRELIMINARY")
        self.assertEqual(round_meta("M.TEAM--------------.58--")["stage_code"], "POSITION_DRAW")
        self.assertEqual(round_meta("M.SINGLES-----------.1732", "PREL")["round_code"], "P17_32")
        with self.assertRaises(ValueError):
            round_meta("M.SINGLES-----------.NEW")

    def test_mixed_doubles_position_round_9_to_16(self):
        for draw in (None, "PREL", "MAIN"):
            with self.subTest(draw=draw):
                meta = round_meta("X.DOUBLES-----------.916-", draw)
                self.assertEqual(meta["stage_code"], "POSITION_DRAW")
                self.assertEqual(meta["round_code"], "P9_16")
                self.assertEqual(meta["round_label"], "Pos. 9-16")
                self.assertEqual(meta["round_order"], 93)
        self.assertEqual(ROUND_NAMES["P9_16"], ("Pos. 9-16", "第9至16名排位赛"))

    def test_brackets_sort_and_preserve_position_round_9_to_16(self):
        phase = copy.deepcopy(samples()["brackets"][0]["Phases"][0])
        phase["Code"] = "X.DOUBLES-----------.916-"
        for index, match in enumerate(phase["Matches"], 1):
            match["Info"]["Code"] = f"X.DOUBLES-----------.916-.{index:04d}00--"
        earlier = copy.deepcopy(phase)
        earlier["Code"] = "X.DOUBLES-----------.1732"
        for match in earlier["Matches"]:
            match["Info"]["Code"] = match["Info"]["Code"].replace(".916-.", ".1732.")
        rows = normalize_brackets([{"Code": "PREL", "Phases": [phase, earlier]}], "XD")
        count = len(phase["Matches"])
        self.assertEqual([row["round_code"] for row in rows], ["P17_32"] * count + ["P9_16"] * count)
        for row, source in zip(rows[count:], phase["Matches"]):
            self.assertEqual(row["stage_code"], "POSITION_DRAW")
            self.assertEqual(row["sub_event_type_code"], "XD")
            self.assertEqual(row["external_unit_code"], source["Info"]["Code"])
            self.assertEqual(row["raw_source_payload"]["_original"], source)
            self.assertIsNone(row["side_a_previous_unit"])
            self.assertIsNone(row["side_b_previous_unit"])

    def test_time_zone_and_tbd(self):
        self.assertEqual(timestamp("2026-10-21", "10:00"), ("2026-10-21T10:00:00", "2026-10-21T05:00:00Z"))
        self.assertEqual(timestamp(None, "TBD"), (None, None))

    def test_unknown_status_and_inconsistent_games_rejected(self):
        row = samples()[DOUBLE]
        row["Status"] = 999
        with self.assertRaises(ValueError):
            normalize_match(row, "2026-10-21")
        row = samples()[DOUBLE]
        row["Home"]["Res"] = "2"
        row["Away"]["Res"] = "3"
        with self.assertRaises(ValueError):
            normalize_match(row, "2026-10-21")


class ImportTests(unittest.TestCase):
    def test_consolation_rounds_import_without_schema_change(self):
        s = snapshot()
        s["brackets"] = []
        for phase_code, round_code in (("1616", "P13_16"), ("1314", "P13_14"), ("1516", "P15_16")):
            phase = copy.deepcopy(samples()["brackets"][0]["Phases"][0])
            phase["Code"] = f"X.DOUBLES-----------.{phase_code}"
            for index, match in enumerate(phase["Matches"], 1):
                match["Info"]["Code"] = f"X.DOUBLES-----------.{phase_code}.{index:04d}00--"
            s["brackets"].extend(normalize_brackets([{"Code": "CONS", "Phases": [phase]}], "XD"))
        import_snapshot(self.conn, s)
        stored = self.conn.execute("SELECT DISTINCT draw_code,stage_code,round_code FROM current_event_brackets").fetchall()
        self.assertEqual({tuple(r) for r in stored},
                         {("CONS", "POSITION_DRAW", r) for r in ("P13_16", "P13_14", "P15_16")})
        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript((ROOT / "scripts/db/schema.sql").read_text())
        self.conn.execute("INSERT INTO events_calendar(year,name,start_date,end_date) VALUES (2026,?,'2026-10-19','2026-10-25')", (EVENT_NAME,))
        for pid, name, org, gender in ((112620, "WONG Chun Ting", "HKG", "Male"),
                                      (200044, "KUO Guan-Hong", "TPE", "Male"),
                                      (136711, "HARIMOTO Miwa", "JPN", "Female")):
            self.conn.execute("INSERT INTO players(player_id,name,slug,country_code,gender) VALUES (?,?,?,?,?)", (pid, name, str(pid), org, gender))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_replay_is_idempotent_and_calendar_is_linked(self):
        s = snapshot()
        first = import_snapshot(self.conn, s)
        import_snapshot(self.conn, s)
        self.assertEqual(first["matches"], 4)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM current_event_matches").fetchone()[0], 4)
        self.assertEqual(self.conn.execute("SELECT event_id FROM events_calendar").fetchone()[0], 3474)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM events_calendar").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        pid = self.conn.execute("SELECT player_id FROM current_event_match_side_players WHERE player_name='WONG Chun Ting'").fetchone()[0]
        self.assertEqual(pid, 112620)

    def test_dry_run_rolls_back_initialization_and_data(self):
        report = import_snapshot(self.conn, snapshot(), dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertEqual(self.conn.execute("SELECT count(*) FROM events").fetchone()[0], 0)
        self.assertIsNone(self.conn.execute("SELECT event_id FROM events_calendar").fetchone()[0])

    def test_failure_rolls_back_entire_batch(self):
        s = snapshot()
        s["matches"][0]["sides"][0]["side_no"] = 3
        with self.assertRaises(sqlite3.IntegrityError):
            import_snapshot(self.conn, s)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM current_event_team_ties").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM events").fetchone()[0], 0)

    def test_older_snapshot_cannot_change_results_or_brackets(self):
        s = snapshot()
        import_snapshot(self.conn, s)
        s["captured_at"] = "2026-10-21T01:00:00.000000Z"
        s["matches"][0]["match_score"] = "0-3"
        self.assertEqual(import_snapshot(self.conn, s)["skipped"], "older snapshot")
        self.assertEqual(self.conn.execute("SELECT match_score FROM current_event_matches WHERE external_match_code=?", (s["matches"][0]["external_match_code"],)).fetchone()[0], "3-2")

    def test_partial_source_cannot_clear_terminal_result(self):
        s = snapshot()
        import_snapshot(self.conn, s)
        s["captured_at"] = "2026-10-22T02:00:00.000000Z"
        match = s["matches"][0]
        match.update(status="scheduled", match_score=None, games=[], winner_side=None, sides=[])
        import_snapshot(self.conn, s)
        row = self.conn.execute("SELECT status,match_score,games FROM current_event_matches WHERE external_match_code=?", (match["external_match_code"],)).fetchone()
        self.assertEqual(tuple(row)[:2], ("completed", "3-2"))
        self.assertEqual(len(json.loads(row["games"])), 5)

    def test_official_terminal_correction_is_applied(self):
        s = snapshot()
        import_snapshot(self.conn, s)
        s["captured_at"] = "2026-10-22T02:00:00.000000Z"
        s["matches"][0].update(match_score="2-3", winner_side="B")
        import_snapshot(self.conn, s)
        self.assertEqual(self.conn.execute("SELECT match_score FROM current_event_matches WHERE external_match_code=?", (s["matches"][0]["external_match_code"],)).fetchone()[0], "2-3")

    def test_wrong_identity_for_existing_source_id_stays_unresolved(self):
        s = snapshot()
        s["team_ties"][0]["rubbers"][0]["sides"][0]["players"][0]["name"] = "WRONG Person"
        report = import_snapshot(self.conn, s)
        self.assertIn("WRONG Person", [p["name"] for p in report["unresolved_players"]])
        self.assertIsNone(self.conn.execute("SELECT player_id FROM current_event_match_side_players WHERE player_name='WRONG Person'").fetchone()[0])

    def test_bracket_resolved_identity_and_bye_never_resolved(self):
        import_snapshot(self.conn, snapshot())
        payload = json.loads(self.conn.execute("SELECT raw_source_payload FROM current_event_brackets ORDER BY current_bracket_id").fetchone()[0])
        self.assertEqual(payload["_resolved_players"]["sides"][0]["players"][0]["player_id"], 136711)
        self.assertEqual(payload["_resolved_players"]["sides"][1]["players"], [])

    def test_unfinished_event_cannot_be_archived(self):
        s = snapshot()
        import_snapshot(self.conn, s)
        with self.assertRaisesRegex(ValueError, "not finished"):
            validate_current(self.conn, s)

    def test_shorter_member_and_roster_lists_keep_known_players(self):
        s = snapshot()
        import_snapshot(self.conn, s)
        original = self.conn.execute("SELECT count(*) FROM current_event_team_tie_side_players").fetchone()[0]
        s["captured_at"] = "2026-10-22T02:00:00.000000Z"
        s["team_ties"][0]["sides"][0]["nominated_players"] = s["team_ties"][0]["sides"][0]["nominated_players"][:1]
        s["matches"][0]["sides"][0]["players"] = s["matches"][0]["sides"][0]["players"][:1]
        import_snapshot(self.conn, s)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM current_event_team_tie_side_players").fetchone()[0], original)
        match_id = self.conn.execute("SELECT current_match_id FROM current_event_matches WHERE external_match_code=?", (s["matches"][0]["external_match_code"],)).fetchone()[0]
        count = self.conn.execute("SELECT count(*) FROM current_event_match_side_players p JOIN current_event_match_sides s USING(current_match_side_id) WHERE s.current_match_id=?", (match_id,)).fetchone()[0]
        self.assertEqual(count, 4)

    def test_missing_standings_fields_keep_prior_values(self):
        s = snapshot()
        s["standings"] = [{"stage_label": "Groups", "team_code": "MTEAM", "group_code": "1", "organization_code": "TPE", "team_name": "Chinese Taipei", "rank": 1, "won": 2, "lost": 0, "result": 4, "players_json": [{"name": "Player"}]}]
        import_snapshot(self.conn, s)
        s["standings"][0].update(rank=None, won=None, players_json=[])
        import_snapshot(self.conn, s)
        row = self.conn.execute("SELECT rank,won,players_json FROM current_event_group_standings").fetchone()
        self.assertEqual((row[0], row[1]), (1, 2))
        self.assertEqual(json.loads(row[2]), [{"name": "Player"}])

    def finished_snapshot(self):
        s = snapshot()
        s["champ"]["isFinished"] = True
        s["champ"]["dates"] = [{"raw": f"2026-10-{d}"} for d in range(19, 26)]
        s["bracket_projects"] = list(PROJECTS.values())
        s["standings_projects"] = ["MT", "WT"]
        paths = ["champ.json", "match/live.json"] + [f"match/d2026-10-{d}.json" for d in range(19, 26)]
        paths += [f"{section}/{project}.json" for project in PROJECTS for section in ("entries", "brackets", "groups")]
        s["resources"] = dict.fromkeys(paths, True)
        final = s["brackets"][2]
        s["brackets"] = []
        for pk, code in PROJECTS.items():
            item = copy.deepcopy(final)
            key = pk + (".FNL-.00010000" if code in ("MT", "WT") else ".FNL-.000100--")
            item.update(sub_event_type_code=code, external_unit_code=key, round_code="F", draw_code="MAIN", status="completed", winner_side="A")
            if code in ("MT", "WT"):
                tie = copy.deepcopy(s["team_ties"][0])
                tie.update(external_match_code=key, sub_event_type_code=code, round_code="F")
                for i, rubber in enumerate(tie["rubbers"], 1):
                    rubber.update(external_match_code=f"{key}:rubber:{i}", sub_event_type_code=code, round_code="F")
                s["team_ties"].append(tie)
                item["winner_side"] = tie["winner_side"]
            else:
                match = copy.deepcopy(s["matches"][0])
                match.update(external_match_code=key, sub_event_type_code=code, round_code="F")
                if code in ("MS", "WS"):
                    for side in match["sides"]:
                        side["players"] = side["players"][:1]
                s["matches"].append(match)
            s["brackets"].append(item)
        return s

    def test_complete_reconciled_snapshot_passes_archive_checks(self):
        s = self.finished_snapshot()
        import_snapshot(self.conn, s)
        counts = validate_current(self.conn, s)
        self.assertEqual(counts["current_event_matches"], 15)

    def test_stale_database_finals_cannot_cover_missing_latest_final(self):
        s = self.finished_snapshot()
        import_snapshot(self.conn, s)
        s["brackets"].pop()
        with self.assertRaisesRegex(ValueError, "unfinished finals"):
            validate_current(self.conn, s)

    def test_unpublished_resource_blocks_archiving(self):
        s = self.finished_snapshot()
        import_snapshot(self.conn, s)
        s["resources"]["entries/M.TEAM--------------.json"] = False
        with self.assertRaisesRegex(ValueError, "missing required"):
            validate_current(self.conn, s)

    def test_unresolved_source_error_blocks_archiving(self):
        s = self.finished_snapshot()
        import_snapshot(self.conn, s)
        s["issues"].append({"severity": "error", "reason": "contradictory result"})
        with self.assertRaisesRegex(ValueError, "source errors"):
            validate_current(self.conn, s)

    def test_archived_replace_checks_preserved_current_batch_timestamps(self):
        s = self.finished_snapshot()
        import_snapshot(self.conn, s)
        self.conn.execute("UPDATE events SET lifecycle_status='completed',last_synced_at='2026-10-26 10:00:00' WHERE event_id=3474")
        with self.assertRaisesRegex(ValueError, "exact captured batch"):
            validate_current(self.conn, s)
        validate_current(self.conn, s, allow_archived=True)
        self.conn.execute("UPDATE current_event_matches SET last_synced_at='2026-10-27T00:00:00Z' WHERE current_match_id=1")
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            validate_current(self.conn, s, allow_archived=True)

    def test_final_bracket_without_actual_final_cannot_be_archived(self):
        s = self.finished_snapshot()
        import_snapshot(self.conn, s)
        self.conn.execute("DELETE FROM current_event_matches WHERE external_match_code=?", (s["brackets"][0]["external_unit_code"],))
        with self.assertRaisesRegex(ValueError, "actual final"):
            validate_current(self.conn, s)

    def test_shared_promoter_preview_archive_and_replace_preserve_played_retirement(self):
        s = self.finished_snapshot()
        f = samples()
        rosters = {e["Reg"]: competitor_players(e) for e in f["entries"]}
        s["team_ties"].append(normalize_team(f[RETIRED], "2026-10-19", rosters, s["issues"]))
        s["matches"][0].update(status="walkover", match_score="WO-3", winner_side="B")
        import_snapshot(self.conn, s)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "ittf.db"
            target = sqlite3.connect(path)
            self.conn.backup(target)
            target.close()
            write_json(root / "normalized/current.json", s)
            command = [sys.executable, "-m", "scripts.ac2026.finalize", "--skip-refresh", "--db-path", str(path), "--data-root", str(root)]
            for flags in (["--dry-run"], [], ["--replace"]):
                result = subprocess.run(command + flags, capture_output=True, text=True, cwd=ROOT)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                with sqlite3.connect(path) as check:
                    count = check.execute("SELECT count(*) FROM matches WHERE event_id=3474").fetchone()[0]
                    self.assertEqual(count, 0 if flags == ["--dry-run"] else 17)
                    if flags != ["--dry-run"]:
                        retired = check.execute("SELECT count(*) FROM matches WHERE event_id=3474 AND raw_row_text LIKE '%RET%'").fetchone()[0]
                        self.assertEqual(retired, 1)
                        self.assertEqual(check.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_default_finalize_preview_never_refreshes_or_changes_capture_artifacts(self):
        from scripts.ac2026.finalize import main
        s = self.finished_snapshot()
        import_snapshot(self.conn, s)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "ittf.db"
            target = sqlite3.connect(path)
            self.conn.backup(target)
            target.close()
            write_json(root / "normalized/current.json", s)
            original = (root / "normalized/current.json").read_bytes()
            argv = ["finalize", "--dry-run", "--db-path", str(path), "--data-root", str(root)]
            with patch.object(sys, "argv", argv), patch("scripts.ac2026.finalize.refresh", create=True, side_effect=AssertionError("归档不应刷新")) as refresh, patch("scripts.ac2026.finalize.subprocess.run") as promote:
                promote.return_value.returncode = 0
                self.assertEqual(main(), 0)
                self.assertIn(str(path), promote.call_args.args[0])
            refresh.assert_not_called()
            self.assertEqual((root / "normalized/current.json").read_bytes(), original)
            with sqlite3.connect(path) as check:
                self.assertEqual(check.execute("SELECT count(*) FROM matches").fetchone()[0], 0)


class CaptureTests(unittest.TestCase):
    def test_overlapping_refresh_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with event_lock(Path(tmp)):
                with self.assertRaisesRegex(RuntimeError, "another"):
                    with event_lock(Path(tmp)):
                        self.fail("second refresh acquired lock")

    def test_cron_creates_log_directory_before_python_redirection(self):
        text = generate_crontab(Path("/tmp/with space"), "/tmp/python")
        self.assertIn("mkdir -p data/ac2026/3474/logs", text)
        self.assertIn("[ \"$(TZ=Asia/Shanghai date +\\%Y)\" = 2026 ]", text)
        self.assertIn("cd '/tmp/with space'", text)

    def test_cron_separates_final_refresh_from_local_archive(self):
        lines = generate_crontab().splitlines()
        refresh = next(line for line in lines if line.startswith("55 4 26 10 *"))
        archive = next(line for line in lines if line.startswith("0 5 26 10 *"))
        self.assertIn("scripts.ac2026.refresh --full", refresh)
        self.assertIn("scripts.ac2026.finalize --skip-refresh", archive)
        self.assertNotIn("refresh --full", archive)

    def test_archive_can_wait_for_an_in_progress_final_refresh(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp:
            with patch("scripts.ac2026.refresh.fcntl.flock") as flock:
                with event_lock(Path(tmp), wait=True):
                    pass
                flock.assert_called_once()
                self.assertEqual(flock.call_args.args[1], fcntl.LOCK_EX)

    @staticmethod
    def fetch(path):
        if path == "champ.json":
            return {"champ": "TTE3474", "events": [{"Key": k} for k in PROJECTS], "dates": [{"raw": "2026-10-21"}]}
        return []

    def test_failed_capture_keeps_previous_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture(root, fetch=self.fetch)
            original = (root / "raw/latest.json").read_bytes()
            def fail(path):
                if path.startswith("brackets/"):
                    raise OSError("disconnected")
                return self.fetch(path)
            with self.assertRaises(OSError):
                capture(root, fetch=fail)
            self.assertEqual((root / "raw/latest.json").read_bytes(), original)

    def test_offline_replay_validates_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture(root, fetch=self.fetch)
            manifest, payloads = load_capture(root)
            self.assertEqual(payloads["match/live.json"], [])
            path = root / manifest["files"]["champ.json"]["file"]
            path.write_text("{}")
            with self.assertRaisesRegex(ValueError, "digest"):
                load_capture(root)

    def test_only_unpublished_project_files_allow_404(self):
        def fetch(path):
            if path.startswith("groups/"):
                raise urllib.error.HTTPError(path, 404, "not published", {}, None)
            return self.fetch(path)
        with tempfile.TemporaryDirectory() as tmp:
            capture(Path(tmp), fetch=fetch)
            manifest, _ = load_capture(Path(tmp))
            self.assertFalse(manifest["files"]["groups/M.TEAM--------------.json"]["available"])
            self.assertTrue(manifest["files"]["match/live.json"]["available"])
        def failure(path):
            if path.startswith("match/d"):
                raise urllib.error.HTTPError(path, 404, "not found", {}, None)
            return self.fetch(path)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(urllib.error.HTTPError):
                capture(Path(tmp), fetch=failure)


if __name__ == "__main__":
    unittest.main()
