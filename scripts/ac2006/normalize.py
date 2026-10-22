"""Translate only TTE3474's Bornan files into the existing current model."""
from __future__ import annotations

import argparse
import copy
import re
from pathlib import Path

from .common import BASE_URL, EVENT_ID, PROJECTS, ROUND_NAMES, add_options, timestamp, write_json
from .scrape import load_capture

STATUS = {1: "completed", 2: "live", 4: "scheduled", "OFFICIAL": "completed",
          "FINISHED": "completed", "START_LIST": "scheduled", "SCHEDULED": "scheduled",
          "PROVISIONAL": "scheduled", "RUNNING": "live", "LIVE": "live",
          "CANCELLED": "cancelled", "": "scheduled"}


def round_meta(key: str, draw: str | None = None) -> dict:
    phase = key.split(".")[2].rstrip("-")
    stages = {"MAIN": "MAIN_DRAW", "PREL": "PRELIMINARY", "5-8": "POSITION_DRAW"}
    if draw and draw not in stages:
        raise ValueError(f"unsupported draw: {draw}")
    stage = stages.get(draw or "MAIN", "MAIN_DRAW")
    group = None
    order = 0
    if re.fullmatch(r"GP\d+", phase):
        stage, code, group = "PRELIMINARY", "RR", str(int(phase[2:]))
        label = "Groups"
    elif re.fullmatch(r"RND\d+", phase):
        stage, code = "PRELIMINARY", f"R{int(phase[3:])}"
        order, label = int(phase[3:]) * 10, "Preliminary"
    elif phase == "58":
        stage, code, order, label = "POSITION_DRAW", "R1", 10, "Pos 5-8"
    elif phase in ("1732", "2532", "2528", "2728", "2526"):
        low, high = int(phase[:2]), int(phase[2:])
        stage, code = "POSITION_DRAW", f"P{low}_{high}"
        order, label = 100 - (high - low), f"Pos. {low}-{high}"
    else:
        code = {"8FNL": "R16", "QFNL": "QF", "SFNL": "SF", "FNL": "F"}.get(phase, phase)
        orders = {"R256": 10, "R128": 20, "R64": 30, "R32": 40, "R16": 50, "QF": 60, "SF": 70, "F": 80}
        if code not in orders:
            raise ValueError(f"unsupported phase: {key}")
        order, label = orders[code], "Main Draw"
    return {"stage_code": stage, "stage_label": label, "round_code": code,
            "round_label": ROUND_NAMES[code][0], "round_order": order, "group_code": group}


def competitor_players(comp: dict) -> list[dict]:
    if not comp or comp.get("Org") == "BYE":
        return []
    values = comp.get("Members") or [comp]
    return [{"source_id": str(v.get("Reg") or ""), "name": v.get("Name") or v.get("Desc") or "",
             "country": v.get("Org") or comp.get("Org"), "order": i}
            for i, v in enumerate(values, 1) if v.get("Name") or v.get("Desc")]


def compat_payload(value):
    """Add the display aliases expected by the existing Bornan bracket reader."""
    if isinstance(value, list):
        return [compat_payload(v) for v in value]
    if isinstance(value, dict):
        result = {k: compat_payload(v) for k, v in value.items()}
        if "Reg" in value and "Desc" in value:
            result["Name"] = value["Desc"]
        return result
    return value


def clock_parts(text: str, date: str | None = None) -> tuple[str | None, str | None]:
    if date is None:
        match = re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2}),", text)
        date = f"2026-10-{int(match[1]):02d}" if match else None
    match = re.search(r"\b(\d{1,2}:\d{2})\b", text)
    return timestamp(date, match[1] if match else None)


def games_for(home: dict, away: dict) -> list[dict]:
    result = []
    hs, aws = home.get("Splits") or [], away.get("Splits") or []
    if len(hs) != len(aws):
        raise ValueError("unequal split lengths")
    for h, a in zip(hs, aws):
        hv, av = str(h.get("Res", "")), str(a.get("Res", ""))
        if not hv and not av:
            continue
        if not hv.isdigit() or not av.isdigit():
            raise ValueError("invalid or one-sided game score")
        if int(hv) or int(av):
            result.append({"player": int(hv), "opponent": int(av)})
    return result


def result_fields(home: dict, away: dict, status: str, *, team: bool = False) -> dict:
    hs, aws = str(home.get("Res", "")), str(away.get("Res", ""))
    games = [] if team else games_for(home, away)
    if "WO" in (hs.upper(), aws.upper()):
        return {"status": "walkover", "match_score": f"{hs}-{aws}", "games": [],
                "winner_side": "B" if hs.upper() == "WO" else "A"}
    if "RET" in (hs.upper(), aws.upper()):
        if (hs.upper() == "RET") == (aws.upper() == "RET"):
            raise ValueError("both sides retired")
        wins = (sum(g["player"] > g["opponent"] and max(g.values()) >= 11 and abs(g["player"] - g["opponent"]) >= 2 for g in games),
                sum(g["opponent"] > g["player"] and max(g.values()) >= 11 and abs(g["player"] - g["opponent"]) >= 2 for g in games))
        a, b = (wins[0], int(aws)) if hs.upper() == "RET" else (int(hs), wins[1])
        return {"status": "completed", "match_score": f"{a}-{b}", "games": games,
                "winner_side": "B" if hs.upper() == "RET" else "A", "source_status": "RET"}
    winner = None
    score = None
    if hs.isdigit() and aws.isdigit():
        a, b = int(hs), int(aws)
        score = f"{a}-{b}" if a or b or status in ("live", "completed") else None
        if status == "completed":
            if a == b:
                raise ValueError("completed match has tied score")
            winner = "A" if a > b else "B"
            if not team and games:
                completed_games = [g for g in games if max(g.values()) >= 11 and abs(g["player"] - g["opponent"]) >= 2]
                wins = (sum(g["player"] > g["opponent"] for g in completed_games),
                        sum(g["opponent"] > g["player"] for g in completed_games))
                if wins != (a, b) or len(completed_games) != len(games):
                    raise ValueError("game scores disagree with final result")
    elif status == "completed":
        raise ValueError("completed match has no numeric result")
    return {"status": status, "match_score": score, "games": games, "winner_side": winner}


def base_match(row: dict, date: str | None) -> dict:
    key = row["Key"]
    project_key = ".".join(key.split(".")[:2])
    if project_key not in PROJECTS:
        raise ValueError(f"unknown project {key}")
    if row.get("Status", "") not in STATUS:
        raise ValueError(f"unknown match status: {row.get('Status')}")
    meta = round_meta(key)
    meta.pop("round_order")
    local, utc = clock_parts(row.get("RTime") or row.get("Time") or "", date)
    return {"event_id": EVENT_ID, "external_match_code": key,
            "sub_event_type_code": PROJECTS[project_key], **meta,
            "scheduled_local_at": local, "scheduled_utc_at": utc,
            "table_no": row.get("LocDesc") or row.get("Loc") or None,
            "session_label": row.get("Desc"), "status": STATUS[row.get("Status", "")],
            "source_status": str(row.get("Status", "")), "raw_source_payload": copy.deepcopy(row)}


def normalize_match(row: dict, date: str | None) -> dict:
    item = base_match(row, date)
    h, a = row.get("Home") or {}, row.get("Away") or {}
    item.update(result_fields(h, a, item["status"]))
    item["sides"] = [{"side_no": i, "team_code": v.get("Org") or None,
                      "is_winner": item["winner_side"] == ("A" if i == 1 else "B"),
                      "players": competitor_players(v)} for i, v in enumerate((h, a), 1)]
    if item["status"] in ("completed", "walkover"):
        expected = 2 if item["sub_event_type_code"] in ("MD", "WD", "XD") else 1
        if any(len(s["players"]) != expected for s in item["sides"]):
            raise ValueError("terminal match has missing competitors")
    item["winner_name"] = "/".join(p["name"] for s in item["sides"] if s["is_winner"] for p in s["players"]) or None
    return item


def normalize_team(row: dict, date: str | None, rosters: dict, issues: list) -> dict:
    item = base_match(row, date)
    h, a = row.get("Home") or {}, row.get("Away") or {}
    item.update(result_fields(h, a, item["status"], team=True))
    item["sides"] = []
    for i, comp in enumerate((h, a), 1):
        item["sides"].append({"side_no": i, "team_code": comp.get("Org"),
                              "team_name": comp.get("Desc"),
                              "is_winner": item["winner_side"] == ("A" if i == 1 else "B"),
                              "nominated_players": rosters.get(comp.get("Reg"), [])})
    item["winner_team_code"] = next((s["team_code"] for s in item["sides"] if s["is_winner"]), None)
    item["rubbers"] = []
    wins = {1: 0, 2: 0}
    for index, source in enumerate(row.get("SubMatches") or [], 1):
        key = f"{row['Key']}:rubber:{index}"
        rubber = copy.deepcopy(source)
        try:
            comps = [rubber.get("Home") or {}, rubber.get("Away") or {}]
            # No source key/status exists on rubbers. Array slot is stable even
            # when the source changes players; derive result from actual scores.
            has_points = any(str(g.get("Res") or "0").isdigit() and int(g.get("Res") or 0) > 0
                             for c in comps for g in c.get("Splits") or [])
            if all(str(c.get("Res") or "0") == "0" for c in comps) and not has_points:
                continue
            direction = []
            for comp in comps:
                owners = [s["side_no"] for s in item["sides"]
                          if any(p["source_id"] == str(comp.get("Reg")) for p in s["nominated_players"])]
                if len(owners) != 1:
                    owners = [s["side_no"] for s in item["sides"] if s["team_code"] == comp.get("Org")]
                if len(owners) != 1:
                    raise ValueError("cannot determine rubber team ownership")
                direction.append(owners[0])
            if sorted(direction) != [1, 2]:
                raise ValueError("rubber players belong to same team")
            if direction == [2, 1]:
                rubber["Home"], rubber["Away"] = comps[1], comps[0]
                issues.append({"severity": "warning", "key": key, "reason": "rubber sides aligned using roster/country"})
            split_count = max(len(c.get("Splits") or []) for c in comps)
            numeric = [int(c.get("Res") or 0) if str(c.get("Res") or "0").isdigit() else 0 for c in comps]
            terminal = any(str(c.get("Res")).upper() == "WO" for c in comps) or max(numeric) >= (split_count // 2 + 1 if split_count else 3)
            rubber.update({"Key": row["Key"], "Status": 1 if terminal else 2,
                           "RTime": row.get("RTime"), "Time": row.get("Time"),
                           "LocDesc": row.get("LocDesc"), "Desc": f"{row.get('Desc')} / Rubber {index}"})
            child = normalize_match(rubber, date)
            child["external_match_code"] = key
            child["raw_source_payload"] = {"source": source, "parent_key": row["Key"], "rubber_index": index}
            item["rubbers"].append(child)
            if child["winner_side"]:
                wins[1 if child["winner_side"] == "A" else 2] += 1
        except ValueError as exc:
            issues.append({"severity": "error", "key": key, "reason": str(exc)})
    if item["status"] == "completed":
        if any(not s["team_code"] or not s["nominated_players"] for s in item["sides"]):
            issues.append({"severity": "error", "key": row["Key"], "reason": "completed tie has no full roster"})
        expected = [int(c.get("Res") or 0) for c in (h, a)]
        if list(wins.values()) != expected:
            issues.append({"severity": "error", "key": row["Key"], "reason": "rubber wins disagree with tie score"})
    return item


def normalize_brackets(payload: list, code: str) -> list[dict]:
    rows = []
    for draw in payload:
        previous = []
        phases = sorted(draw["Phases"], key=lambda p: round_meta(p["Code"], draw["Code"])["round_order"])
        for phase in phases:
            meta = round_meta(phase["Code"], draw["Code"])
            matches = phase["Matches"]
            for index, source in enumerate(matches):
                info = source["Info"]
                key = info["Code"]
                h, a = source.get("Home") or {}, source.get("Away") or {}
                local, _ = clock_parts(info.get("Time") or "")
                status = STATUS.get(info.get("Status", ""))
                if status is None:
                    raise ValueError(f"unknown bracket status {info.get('Status')}")
                bye = info.get("IsBye") or h.get("Org") == "BYE" or a.get("Org") == "BYE"
                fields = ({"status": status, "match_score": None, "winner_side": "B" if h.get("Org") == "BYE" else "A"}
                          if bye else result_fields(h, a, status, team=True))
                feeders = len(previous) == 2 * len(matches) and draw["Code"] == "MAIN"
                rows.append({"event_id": EVENT_ID, "sub_event_type_code": code,
                             "draw_code": draw["Code"], "bracket_code": phase["Code"],
                             "stage_code": meta["stage_code"], "round_code": meta["round_code"],
                             "round_order": meta["round_order"], "bracket_position": index + 1,
                             "external_unit_code": key, "scheduled_date": local[:10] if local else None,
                             "scheduled_time": local[11:16] if local else None,
                             **{k: fields[k] for k in ("status", "match_score", "winner_side")},
                             "side_a_previous_unit": previous[index * 2]["Info"]["Code"] if feeders else None,
                             "side_b_previous_unit": previous[index * 2 + 1]["Info"]["Code"] if feeders else None,
                             "side_a_team_code": h.get("Org") or None, "side_b_team_code": a.get("Org") or None,
                             "side_a_placeholder": "BYE" if h.get("Org") == "BYE" else (None if h.get("Reg") else "TBD"),
                             "side_b_placeholder": "BYE" if a.get("Org") == "BYE" else (None if a.get("Reg") else "TBD"),
                             "raw_source_payload": {**compat_payload(source), "_original": source}})
            previous = matches
    return rows


def build_snapshot(manifest: dict, payloads: dict) -> dict:
    champ = payloads["champ.json"]
    issues: list = []
    snapshot = {"event_id": EVENT_ID, "batch_id": manifest["batch_id"],
                "captured_at": manifest["captured_at"], "full": manifest["full"],
                "champ": champ, "team_ties": [], "matches": [], "brackets": [],
                "standings": [], "bracket_projects": [], "standings_projects": [], "issues": issues}
    snapshot["resources"] = {path: item.get("available", True) for path, item in manifest["files"].items()}
    rosters = {}
    for project in champ["events"]:
        pk, code = project["Key"], PROJECTS[project["Key"]]
        for org in payloads[f"entries/{pk}.json"]:
            for entry in org["Entries"]:
                if code in ("MT", "WT"):
                    rosters[entry["Reg"]] = competitor_players(entry)
        brackets = payloads[f"brackets/{pk}.json"]
        if brackets:
            snapshot["brackets"].extend(normalize_brackets(brackets, code))
            snapshot["bracket_projects"].append(code)
        groups = payloads[f"groups/{pk}.json"]
        if groups and code in ("MT", "WT"):
            snapshot["standings_projects"].append(code)
            for group in groups:
                group_match = re.search(r"Group\s+(\d+)", group["Desc"])
                if not group_match:
                    raise ValueError(f"unknown group: {group['Desc']}")
                for comp in group["Competitors"]:
                    won, lost = comp.get("Won"), comp.get("Lost")
                    snapshot["standings"].append({"stage_label": "Groups", "team_code": "MTEAM" if code == "MT" else "WTEAM",
                        "group_code": str(int(group_match[1])), "organization_code": comp["Org"], "team_name": comp["Name"],
                        "played": won + lost if won is not None and lost is not None else None,
                        "won": won, "lost": lost, "result": comp.get("Points"), "rank": int(comp["Rk"]) if str(comp.get("Rk", "")).isdigit() else None,
                        "players_json": rosters.get(comp["Reg"], []), "source_url": BASE_URL + f"groups/{pk}.json"})
    by_key = {}
    for day in champ["dates"]:
        for row in payloads[f"match/d{day['raw']}.json"]:
            key = row["Key"]
            detail = payloads.get(f"match/{key}.json")
            if detail:
                matching = [v for v in detail if v.get("Key") == key]
                if len(matching) != 1:
                    raise ValueError(f"invalid match detail {key}")
                row = matching[0]
            by_key[key] = (day["raw"], row)
    for row in payloads["match/live.json"]:
        existing = by_key.get(row["Key"])
        if existing and existing[1].get("Status") == 1:
            continue
        if existing:
            by_key[row["Key"]] = (existing[0], {**existing[1], **row})
        else:
            by_key[row["Key"]] = (None, row)
    bye_keys = {b["external_unit_code"] for b in snapshot["brackets"] if b["raw_source_payload"]["Info"].get("IsBye")}
    for key, (date, row) in by_key.items():
        if key in bye_keys:
            continue
        try:
            if row.get("IsTeam"):
                snapshot["team_ties"].append(normalize_team(row, date, rosters, issues))
            else:
                snapshot["matches"].append(normalize_match(row, date))
        except (ValueError, KeyError) as exc:
            issues.append({"severity": "error", "key": key, "reason": str(exc)})
    return snapshot


def normalize_capture(data_root: Path, manifest_path: Path | None = None) -> dict:
    manifest, payloads = load_capture(data_root, manifest_path)
    snapshot = build_snapshot(manifest, payloads)
    write_json(data_root / "normalized" / f"{manifest['batch_id']}.json", snapshot)
    write_json(data_root / "normalized/current.json", snapshot)
    write_json(data_root / "normalized/issues.json", snapshot["issues"])
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="标准化亚锦赛数据（支持离线重放）")
    add_options(parser)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    snapshot = normalize_capture(args.data_root, args.manifest)
    print({k: len(snapshot[k]) for k in ("team_ties", "matches", "brackets", "standings", "issues")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
