"""Conservative removal of withdrawn, empty provisional team slots."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.asian_games_2026.common import EVENT_ID, SOURCE_TIME_ZONE


def cleanup_placeholders(conn, snapshot):
    # These small integration-owned tables are created within the import transaction.
    conn.execute('''CREATE TABLE IF NOT EXISTS asian_games_cleanup_batches (
        batch_id TEXT PRIMARY KEY, completed_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS asian_games_placeholder_missing (
        tie_id INTEGER PRIMARY KEY REFERENCES current_event_team_ties(current_team_tie_id)
        ON DELETE CASCADE, batch_id TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS asian_games_placeholder_audit (
        id INTEGER PRIMARY KEY, tie_id INTEGER NOT NULL, batch_id TEXT NOT NULL,
        previous_batch_id TEXT NOT NULL, reason TEXT NOT NULL,
        original_json TEXT NOT NULL, deleted_at TEXT NOT NULL DEFAULT (datetime('now')))''')
    ties = snapshot.get('team_ties') or []
    present = {item['external_match_code'] for item in ties + (snapshot.get('matches') or [])}
    # Reappearance resets confirmation even when cleanup is disabled for this snapshot.
    for code in present:
        conn.execute('''DELETE FROM asian_games_placeholder_missing WHERE tie_id IN
            (SELECT current_team_tie_id FROM current_event_team_ties
             WHERE event_id=? AND external_match_code=?)''', (EVENT_ID, code))
    capture = snapshot.get('schedule_capture') or {}
    if (capture.get('complete') is not True or not capture.get('batch_id')
            or not capture.get('completed_at') or not capture.get('dates')
            or not capture.get('schedule_keys')):
        return 0
    batch = capture['batch_id']
    try:
        stamp = datetime.fromisoformat(capture['completed_at'].replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return 0
    if stamp.tzinfo is None:
        return 0
    if conn.execute('SELECT 1 FROM asian_games_cleanup_batches WHERE batch_id=?', (batch,)).fetchone():
        return 0
    previous = conn.execute('SELECT completed_at FROM asian_games_cleanup_batches').fetchall()
    if any(datetime.fromisoformat(row[0]) >= stamp for row in previous):
        return 0
    conn.execute('INSERT INTO asian_games_cleanup_batches VALUES (?,?)', (batch, stamp.isoformat()))
    today = min(datetime.now(ZoneInfo(SOURCE_TIME_ZONE)).date(), stamp.astimezone(ZoneInfo(SOURCE_TIME_ZONE)).date()).isoformat()
    keys = set(capture['schedule_keys'])
    present |= keys

    def scope(item):
        return (str(item.get('scheduled_local_at') or '')[:10], item.get('sub_event_type_code'),
                item.get('stage_code'), item.get('round_code'), item.get('group_code'))

    scopes = set()
    for tie in ties:
        sides = tie.get('sides') or []
        if (tie['external_match_code'] in keys
                and tie.get('source_status') in {'SCHEDULED', 'START_LIST', 'RUNNING', 'OFFICIAL', 'FINISHED'}
                and {s.get('side_no') for s in sides if s.get('team_code') and s['team_code'] != 'BYE'} == {1, 2}):
            key = scope(tie)
            if key[0] in capture['dates'] and key[0] <= today and key[2] and key[3]:
                scopes.add(key)
    candidates = conn.execute('''SELECT t.* FROM current_event_team_ties t
        WHERE event_id=? AND status='scheduled' AND source_status='PROVISIONAL'
        AND NULLIF(TRIM(match_score),'') IS NULL AND winner_side IS NULL
        AND NULLIF(TRIM(winner_team_code),'') IS NULL
        AND NOT EXISTS (SELECT 1 FROM current_event_team_tie_sides s
                        WHERE s.current_team_tie_id=t.current_team_tie_id)
        AND NOT EXISTS (SELECT 1 FROM current_event_matches m
                        WHERE m.current_team_tie_id=t.current_team_tie_id)''', (EVENT_ID,)).fetchall()
    eligible = {row['current_team_tie_id']: dict(row) for row in candidates
                if row['external_match_code'] not in present and scope(dict(row)) in scopes}
    # A successful intervening snapshot without qualifying evidence breaks the streak.
    for row in conn.execute('SELECT tie_id FROM asian_games_placeholder_missing').fetchall():
        if row[0] not in eligible:
            conn.execute('DELETE FROM asian_games_placeholder_missing WHERE tie_id=?', (row[0],))
    removed = 0
    for tie_id, original in eligible.items():
        prior = conn.execute('SELECT batch_id FROM asian_games_placeholder_missing WHERE tie_id=?', (tie_id,)).fetchone()
        if prior is None:
            conn.execute('INSERT INTO asian_games_placeholder_missing VALUES (?,?)', (tie_id, batch))
            continue
        conn.execute('''INSERT INTO asian_games_placeholder_audit
            (tie_id,batch_id,previous_batch_id,reason,original_json) VALUES (?,?,?,?,?)''',
            (tie_id, batch, prior[0], 'Empty provisional slot absent from two complete captures; '
             'same date/event/round has official opponents; no sides, score, winner or rubbers',
             json.dumps(original, ensure_ascii=False)))
        conn.execute('DELETE FROM current_event_team_ties WHERE current_team_tie_id=?', (tie_id,))
        removed += 1
    return removed
