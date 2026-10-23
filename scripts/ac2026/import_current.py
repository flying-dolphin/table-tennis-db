"""Transactional, idempotent import of this championship's normalized batch."""
from __future__ import annotations

import argparse
import copy
import json
import re
import sqlite3
import unicodedata
from datetime import datetime

from .common import (BASE_URL, EVENT_ID, EVENT_NAME, EVENT_NAME_ZH, PROJECT_NAMES,
                     PROJECTS, ROUND_NAMES, STAGE_NAMES, SOURCE_ZONE, add_options, read_json)


def name_key(value: str) -> str:
    return " ".join(sorted(re.findall(r"[A-Z0-9]+", unicodedata.normalize("NFKD", value).upper())))


def player_resolver(conn, unresolved: set):
    records = [dict(row) for row in conn.execute("SELECT player_id,name,country_code,gender FROM players")]
    by_id = {row["player_id"]: row for row in records}

    def resolve(player: dict, code: str):
        source = str(player.get("source_id") or "")
        country, name = player.get("country"), player.get("name") or ""
        gender = {"MS": "Male", "MD": "Male", "MT": "Male", "WS": "Female", "WD": "Female", "WT": "Female"}.get(code)

        def matches(row):
            return (row["country_code"] == country and name_key(row["name"]) == name_key(name)
                    and (not gender or not row["gender"] or row["gender"] == gender))

        candidate = by_id.get(int(source)) if source.isdigit() else None
        if candidate and matches(candidate):
            return candidate["player_id"]
        # An existing source ID with conflicting identity must not be remapped.
        if candidate is None:
            candidates = [row["player_id"] for row in records if matches(row)]
            if len(candidates) == 1:
                return candidates[0]
        unresolved.add((source, country or "", name))
        return None
    return resolve


def initialize_event(conn, snapshot: dict) -> None:
    for code, (name, zh) in STAGE_NAMES.items():
        conn.execute("INSERT OR IGNORE INTO stage_codes(code,name,name_zh,sort_order) VALUES (?,?,?,0)", (code, name, zh))
    for order, (code, (name, zh)) in enumerate(ROUND_NAMES.items(), 1):
        conn.execute("INSERT OR IGNORE INTO round_codes(code,name,name_zh,kind,sort_order) VALUES (?,?,?,'unknown',?)", (code, name, zh, order))
    calendar = conn.execute("SELECT calendar_id,event_category_id,start_date,end_date FROM events_calendar WHERE year=2026 AND name=?", (EVENT_NAME,)).fetchall()
    if len(calendar) > 1:
        raise ValueError("multiple Asian Championships calendar rows")
    dates = calendar[0] if calendar else None
    category = conn.execute("SELECT id,category_id,category_name_zh FROM event_categories WHERE id=?", (dates[1],)).fetchone() if dates and dates[1] else None
    if category is None:
        category = conn.execute("SELECT id,category_id,category_name_zh FROM event_categories WHERE category_id='CONTINENTAL_CHAMPS'").fetchone()
    conn.execute("""INSERT INTO events(event_id,year,name,name_zh,event_type_name,event_kind,event_category_id,
        category_code,category_name_zh,start_date,end_date,location,time_zone,href,lifecycle_status)
        VALUES (?,2026,?,?,'Continental','Senior Championships',?,?,?,?,?,'Tashkent, Uzbekistan',?,?,'in_progress')
        ON CONFLICT(event_id) DO NOTHING""",
        (EVENT_ID, EVENT_NAME, EVENT_NAME_ZH, category[0] if category else None,
         category[1] if category else None, category[2] if category else None,
         dates[2] if dates else "2026-10-19", dates[3] if dates else "2026-10-25", SOURCE_ZONE, BASE_URL + "results.html"))
    if dates:
        current = conn.execute("SELECT event_id FROM events_calendar WHERE calendar_id=?", (dates[0],)).fetchone()[0]
        if current not in (None, EVENT_ID):
            raise ValueError("calendar already linked to another event")
        conn.execute("UPDATE events_calendar SET event_id=? WHERE calendar_id=?", (EVENT_ID, dates[0]))
    for project in snapshot["champ"]["events"]:
        code = PROJECTS[project["Key"]]
        name, zh = PROJECT_NAMES[code]
        conn.execute("INSERT OR IGNORE INTO sub_event_types(code,name,name_zh) VALUES (?,?,?)", (code, name, zh))
        conn.execute("INSERT OR IGNORE INTO sub_events(event_id,sub_event_type_code) VALUES (?,?)", (EVENT_ID, code))


COMMON_COLUMNS = ("sub_event_type_code", "stage_label", "stage_code", "round_label", "round_code", "group_code",
                  "scheduled_local_at", "scheduled_utc_at", "table_no", "session_label", "status", "source_status",
                  "match_score", "winner_side")


def upsert_unit(conn, item: dict, captured: str, *, tie_id=None, team=False) -> int | None:
    table = "current_event_team_ties" if team else "current_event_matches"
    id_col = "current_team_tie_id" if team else "current_match_id"
    old = conn.execute(f"SELECT * FROM {table} WHERE event_id=? AND external_match_code=?",
                       (EVENT_ID, item["external_match_code"])).fetchone()
    if old:
        if old["last_synced_at"] and old["last_synced_at"] > captured:
            return None
        if old["status"] in ("completed", "walkover") and item["status"] in ("scheduled", "live"):
            return None
        if old["status"] == "live" and item["status"] == "scheduled":
            return None
    values = {column: item.get(column) for column in COMMON_COLUMNS}
    # Absent fields in partial sources must not erase previously recorded data.
    if old:
        for column, value in list(values.items()):
            if value is None:
                values[column] = old[column]
    values["last_synced_at"] = captured
    values["source_schedule_status"] = item.get("source_status")
    if team:
        values["winner_team_code"] = item.get("winner_team_code") or (old["winner_team_code"] if old else None)
    else:
        values["current_team_tie_id"] = tie_id
        values["winner_name"] = item.get("winner_name") or (old["winner_name"] if old else None)
        values["raw_source_payload"] = json.dumps(item.get("raw_source_payload"), ensure_ascii=False)
        values["games"] = json.dumps(item.get("games") or [], ensure_ascii=False) if item.get("games") else (old["games"] if old else "[]")
    if old:
        conn.execute(f"UPDATE {table} SET {','.join(c+'=?' for c in values)},updated_at=datetime('now') WHERE {id_col}=?",
                     (*values.values(), old[id_col]))
        return old[id_col]
    values = {"event_id": EVENT_ID, "external_match_code": item["external_match_code"], **values}
    cursor = conn.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
    return cursor.lastrowid


def replace_sides(conn, item: dict, parent_id: int, resolve, *, team=False):
    prefix = "current_event_team_tie" if team else "current_event_match"
    parent_col = "current_team_tie_id" if team else "current_match_id"
    side_col = "current_team_tie_side_id" if team else "current_match_side_id"
    for side in item.get("sides") or []:
        side_no = side["side_no"]
        old = conn.execute(f"SELECT * FROM {prefix}_sides WHERE {parent_col}=? AND side_no=?", (parent_id, side_no)).fetchone()
        players = side.get("nominated_players" if team else "players") or []
        # A TBD source is not evidence to discard already known competitors.
        if old and not side.get("team_code") and not players:
            continue
        values = {"team_code": side.get("team_code"), "is_winner": int(bool(side.get("is_winner")))}
        if team:
            values["team_name"] = side.get("team_name")
        if old:
            side_id = old[side_col]
            conn.execute(f"UPDATE {prefix}_sides SET {','.join(k+'=?' for k in values)} WHERE {side_col}=?", (*values.values(), side_id))
        else:
            values = {parent_col: parent_id, "side_no": side_no, **values}
            side_id = conn.execute(f"INSERT INTO {prefix}_sides ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values())).lastrowid
        if players:
            prior_players = [dict(p) for p in conn.execute(f"SELECT player_id,player_name,player_country FROM {prefix}_side_players WHERE {side_col}=? ORDER BY player_order", (side_id,))]
            if len(players) < len(prior_players):
                # A truncated source list does not establish a roster removal.
                continue
            conn.execute(f"DELETE FROM {prefix}_side_players WHERE {side_col}=?", (side_id,))
            for order, player in enumerate(players, 1):
                conn.execute(f"INSERT INTO {prefix}_side_players ({side_col},player_order,player_id,player_name,player_country) VALUES (?,?,?,?,?)",
                             (side_id, order, resolve(player, item["sub_event_type_code"]), player["name"], player.get("country")))


def bracket_payload(item: dict, resolve) -> str:
    from .normalize import competitor_players
    payload = copy.deepcopy(item["raw_source_payload"])
    code = item["sub_event_type_code"]
    sides = []
    for number, key in enumerate(("Home", "Away"), 1):
        players = [] if code in ("MT", "WT") else competitor_players(payload.get(key) or {})
        sides.append({"side_no": number, "players": [{"source_name": p["name"], "source_country": p["country"],
                      "source_registration_id": p["source_id"], "player_id": resolve(p, code)} for p in players]})
    payload["_resolved_players"] = {"version": 1, "sides": sides}
    return json.dumps(payload, ensure_ascii=False)


def import_snapshot(conn: sqlite3.Connection, snapshot: dict, *, dry_run=False) -> dict:
    if snapshot.get("event_id") != EVENT_ID:
        raise ValueError("snapshot must be event 3474")
    captured = snapshot["captured_at"]
    datetime.fromisoformat(captured.replace("Z", "+00:00"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    unresolved: set = set()
    counts = {"team_ties": 0, "matches": 0, "brackets": 0, "standings": 0}
    conn.execute("BEGIN IMMEDIATE")
    try:
        old = conn.execute("SELECT last_synced_at,lifecycle_status FROM events WHERE event_id=?", (EVENT_ID,)).fetchone()
        if old and old["last_synced_at"] and old["last_synced_at"] > captured:
            conn.rollback()
            return {**counts, "skipped": "older snapshot"}
        if old and old["lifecycle_status"] == "completed":
            raise ValueError("event already archived; current refresh is disabled")
        initialize_event(conn, snapshot)
        resolve = player_resolver(conn, unresolved)
        for tie in snapshot["team_ties"]:
            tie_id = upsert_unit(conn, tie, captured, team=True)
            if tie_id is None:
                continue
            replace_sides(conn, tie, tie_id, resolve, team=True)
            counts["team_ties"] += 1
            for child in tie["rubbers"]:
                match_id = upsert_unit(conn, child, captured, tie_id=tie_id)
                if match_id:
                    replace_sides(conn, child, match_id, resolve)
                    counts["matches"] += 1
        for item in snapshot["matches"]:
            match_id = upsert_unit(conn, item, captured)
            if match_id:
                replace_sides(conn, item, match_id, resolve)
                counts["matches"] += 1
        for item in snapshot["brackets"]:
            values = {k: v for k, v in item.items() if k != "raw_source_payload"}
            values.update(raw_source_payload=bracket_payload(item, resolve), last_synced_at=captured)
            existing = conn.execute("SELECT * FROM current_event_brackets WHERE event_id=? AND sub_event_type_code=? AND external_unit_code=?",
                                    (EVENT_ID, item["sub_event_type_code"], item["external_unit_code"])).fetchone()
            if existing and existing["status"] in ("completed", "walkover") and item["status"] in ("scheduled", "live"):
                continue
            if existing:
                # Empty placeholder updates cannot erase a known participant.
                for key, value in list(values.items()):
                    if value is None:
                        values[key] = existing[key]
                previous_payload = json.loads(existing["raw_source_payload"])
                new_payload = json.loads(values["raw_source_payload"])
                for side, number in (("Home", 1), ("Away", 2)):
                    if not (new_payload.get(side) or {}).get("Reg") and (previous_payload.get(side) or {}).get("Reg"):
                        new_payload[side] = previous_payload[side]
                        new_payload["_resolved_players"]["sides"][number-1] = previous_payload["_resolved_players"]["sides"][number-1]
                        for suffix in ("team_code", "placeholder"):
                            field = f"side_{'a' if number == 1 else 'b'}_{suffix}"
                            values[field] = existing[field]
                values["raw_source_payload"] = json.dumps(new_payload, ensure_ascii=False)
                conn.execute(f"UPDATE current_event_brackets SET {','.join(k+'=?' for k in values)},updated_at=datetime('now') WHERE current_bracket_id=?", (*values.values(), existing["current_bracket_id"]))
            else:
                conn.execute(f"INSERT INTO current_event_brackets ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
            counts["brackets"] += 1
        for item in snapshot["standings"]:
            values = {"event_id": EVENT_ID, **item, "updated_at": captured}
            values["players_json"] = json.dumps(item["players_json"], ensure_ascii=False)
            existing = conn.execute("SELECT * FROM current_event_group_standings WHERE event_id=? AND stage_label=? AND team_code=? AND group_code=? AND organization_code=?",
                (EVENT_ID, item["stage_label"], item["team_code"], item["group_code"], item["organization_code"])).fetchone()
            if existing:
                for field, value in list(values.items()):
                    if value is None or (field == "players_json" and len(item["players_json"]) < len(json.loads(existing[field] or "[]"))):
                        values[field] = existing[field]
            columns = list(values)
            conn.execute(f"INSERT INTO current_event_group_standings ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
                         "ON CONFLICT(event_id,stage_label,team_code,group_code,organization_code) DO UPDATE SET " +
                         ",".join(f"{c}=excluded.{c}" for c in columns if c not in ("event_id", "stage_label", "team_code", "group_code", "organization_code")), tuple(values.values()))
            counts["standings"] += 1
        conn.execute("UPDATE events SET time_zone=?,last_synced_at=? WHERE event_id=?", (SOURCE_ZONE, captured, EVENT_ID))
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {**counts, "dry_run": dry_run, "source_errors": sum(i["severity"] == "error" for i in snapshot["issues"]),
            "unresolved_players": [{"source_id": i, "country": c, "name": n} for i, c, n in sorted(unresolved)]}


def main() -> int:
    parser = argparse.ArgumentParser(description="事务导入亚锦赛当前数据")
    add_options(parser, database=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    from .refresh import event_lock
    with event_lock(args.data_root):
        with sqlite3.connect(f"{args.db_path.resolve().as_uri()}?mode=rw", uri=True) as conn:
            report = import_snapshot(conn, read_json(args.data_root / "normalized/current.json"), dry_run=args.dry_run)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
