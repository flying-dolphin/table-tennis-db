#!/usr/bin/env bash
#
# Publish the one-off Asian Games 2026 scraper/data bundle and import it on the
# production server. This remains separate from the WTT updater.
#
# Safe default: print the deployment plan only. Pass --apply explicitly when
# the maintainer wants this script to perform SSH/SCP and production writes.
#
# Usage:
#   deploy/server/update_asian_games_2026.sh              # plan only
#   deploy/server/update_asian_games_2026.sh --apply      # publish + import
#   deploy/server/update_asian_games_2026.sh --apply --skip-cron
#
# Optional environment:
#   REMOTE_HOST=flyingfox@xiaodoubao.site
#   REMOTE_PROJECT_DIR=doubao_tt
#   REMOTE_PYTHON=/home/flyingfox/.pyenv/shims/python3.11
#   REMOTE_PYTHON_BIN=/home/flyingfox/.pyenv/shims/python3.11
#   REMOTE_TMP_DIR=/tmp/ittf-asian-games-2026
#   REMOTE_DB_BACKUPS_KEEP=5

set -euo pipefail

REMOTE_HOST=${REMOTE_HOST:-flyingfox@xiaodoubao.site}
REMOTE_PROJECT_DIR=${REMOTE_PROJECT_DIR:-doubao_tt}
REMOTE_PYTHON=${REMOTE_PYTHON:-/home/flyingfox/.pyenv/shims/python3.11}
REMOTE_PYTHON_BIN=${REMOTE_PYTHON_BIN:-${REMOTE_PYTHON}}
REMOTE_TMP_DIR=${REMOTE_TMP_DIR:-/tmp/ittf-asian-games-2026}
REMOTE_DB_BACKUPS_KEEP=${REMOTE_DB_BACKUPS_KEEP:-5}

EVENT_ID=6666
EVENT_YEAR=2026
EVENT_NAME='Asian Games Aichi-Nagoya 2026'
EVENT_NAME_ZH='爱知·名古屋亚洲运动会'
EVENT_TYPE='Continental Games'
EVENT_KIND='--'
EVENT_CATEGORY_ID=6
EVENT_CATEGORY_CODE='CONTINENTAL_GAMES'
EVENT_CATEGORY_NAME_ZH='洲际运动会'
EVENT_START_DATE=2026-09-20
EVENT_END_DATE=2026-09-28
EVENT_LOCATION=JPN
EVENT_HREF='https://www.aichi-nagoya2026.org/en/'
EVENT_TIME_ZONE='Asia/Tokyo'
EVENT_LIFECYCLE='in_progress'

APPLY=0
SKIP_CRON=0

usage() {
    sed -n '2,28p' "$0"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --apply)
            APPLY=1
            shift
            ;;
        --skip-cron)
            SKIP_CRON=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if ! [[ "$REMOTE_DB_BACKUPS_KEEP" =~ ^[0-9]+$ ]] || [ "$REMOTE_DB_BACKUPS_KEEP" -lt 1 ]; then
    echo "ERROR: REMOTE_DB_BACKUPS_KEEP must be a positive integer" >&2
    exit 2
fi

cd "$(dirname "$0")/../.."
ROOT_DIR=$(pwd)

require_file() {
    if [ ! -f "$1" ]; then
        echo "ERROR: required file not found: $1" >&2
        exit 1
    fi
}

require_dir() {
    if [ ! -d "$1" ]; then
        echo "ERROR: required directory not found: $1" >&2
        exit 1
    fi
}

require_dir scripts/asian_games_2026
require_dir data/asian_games/2026
require_file data/event_schedule/${EVENT_ID}.json
require_file data/asian_games/2026/normalized/current_matches.json
require_file data/asian_games/2026/normalized/current_brackets.json

print_plan() {
    local cron_note=""
    if [ "$SKIP_CRON" -eq 1 ]; then
        cron_note=" (skipped by --skip-cron)"
    fi
    cat <<PLAN
Asian Games 2026 deployment plan (no remote commands will run without --apply)

Target: ${REMOTE_HOST}:${REMOTE_PROJECT_DIR}
Python: ${REMOTE_PYTHON}
Event:  ${EVENT_ID} (${EVENT_TIME_ZONE}, lifecycle=${EVENT_LIFECYCLE})

1. Stage and upload scripts/asian_games_2026, data/asian_games/2026,
   and data/event_schedule/${EVENT_ID}.json.
2. Back up data/db/ittf.db on the server and retain the newest
   ${REMOTE_DB_BACKUPS_KEEP} Asian Games backups.
3. Idempotently create/update events.${EVENT_ID}; this does not depend on
   events_calendar, which is absent for this one-off event on the server.
4. Import current_event_session_schedule plus the Asian Games normalized
   match and individual-bracket snapshots.
5. Verify the event row, Asia/Tokyo timezone, session schedule count, team-tie
   count, match count, all five individual brackets, and roster/player rows.
6. Replace only the marked Asian Games crontab block${cron_note}.

To execute this plan: $0 --apply$([ "$SKIP_CRON" -eq 1 ] && printf ' --skip-cron')
PLAN
}

if [ "$APPLY" -eq 0 ]; then
    print_plan
    exit 0
fi

check_remote_python() {
    echo "==> Checking remote Python: ${REMOTE_PYTHON}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && test -x '${REMOTE_PYTHON}' && '${REMOTE_PYTHON}' --version && '${REMOTE_PYTHON}' - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit('Python 3.10+ is required: ' + sys.version)
print('Remote Python OK: ' + sys.version.split()[0])
PY"
}

stage_bundle() {
    local staging_dir archive_path remote_archive
    staging_dir=$(mktemp -d)
    archive_path=$(mktemp -p /tmp ittf-asian-games-2026.XXXXXX.tar.gz)
    remote_archive="${REMOTE_TMP_DIR}/asian-games-2026-bundle.tar.gz"
    trap 'rm -rf "$staging_dir" "$archive_path"' RETURN

    echo "==> Staging Asian Games 2026 files"
    mkdir -p "${staging_dir}/scripts/asian_games_2026"
    mkdir -p "${staging_dir}/data/asian_games/2026"
    mkdir -p "${staging_dir}/data/event_schedule"
    tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.swp' \
        -cf - -C scripts/asian_games_2026 . \
        | tar -xf - -C "${staging_dir}/scripts/asian_games_2026"
    tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.swp' \
        -cf - -C data/asian_games/2026 . \
        | tar -xf - -C "${staging_dir}/data/asian_games/2026"
    cp "data/event_schedule/${EVENT_ID}.json" \
        "${staging_dir}/data/event_schedule/${EVENT_ID}.json"
    tar -czf "$archive_path" -C "$staging_dir" .

    echo "==> Uploading bundle to ${REMOTE_HOST}:${remote_archive}"
    ssh "$REMOTE_HOST" "mkdir -p '${REMOTE_TMP_DIR}' '${REMOTE_PROJECT_DIR}'"
    scp "$archive_path" "${REMOTE_HOST}:${remote_archive}"
    echo "==> Extracting bundle under ${REMOTE_PROJECT_DIR}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && tar -xzf '${remote_archive}' && rm -f '${remote_archive}' && chmod +x scripts/asian_games_2026/*.sh"
}

backup_remote_database() {
    echo "==> Backing up remote database before Asian Games import"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && mkdir -p data/db/backups && backup_path=\"data/db/backups/ittf-before-asian-games-2026-\$(date +%Y%m%d_%H%M%S).db\" && '${REMOTE_PYTHON}' -c \"import sqlite3,sys; src=sqlite3.connect('data/db/ittf.db'); dst=sqlite3.connect(sys.argv[1]); src.backup(dst); dst.close(); src.close()\" \"\$backup_path\" && echo \"Remote backup path: \$backup_path\" && '${REMOTE_PYTHON}' -c \"from pathlib import Path; keep=int('${REMOTE_DB_BACKUPS_KEEP}'); files=sorted(Path('data/db/backups').glob('ittf-before-asian-games-2026-*.db'), key=lambda p:p.stat().st_mtime, reverse=True); [p.unlink() for p in files[keep:]]; print('Asian Games backup retention: kept {}'.format(min(len(files),keep)))\""
}

upsert_event_row() {
    echo "==> Ensuring events row for event ${EVENT_ID} (independent of events_calendar)"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && EVENT_ID='${EVENT_ID}' EVENT_YEAR='${EVENT_YEAR}' EVENT_NAME='${EVENT_NAME}' EVENT_NAME_ZH='${EVENT_NAME_ZH}' EVENT_TYPE='${EVENT_TYPE}' EVENT_KIND='${EVENT_KIND}' EVENT_CATEGORY_ID='${EVENT_CATEGORY_ID}' EVENT_CATEGORY_CODE='${EVENT_CATEGORY_CODE}' EVENT_CATEGORY_NAME_ZH='${EVENT_CATEGORY_NAME_ZH}' EVENT_START_DATE='${EVENT_START_DATE}' EVENT_END_DATE='${EVENT_END_DATE}' EVENT_LOCATION='${EVENT_LOCATION}' EVENT_HREF='${EVENT_HREF}' EVENT_TIME_ZONE='${EVENT_TIME_ZONE}' EVENT_LIFECYCLE='${EVENT_LIFECYCLE}' '${REMOTE_PYTHON}' - <<'PY'
import os
import sqlite3
from zoneinfo import ZoneInfo

event_id = int(os.environ['EVENT_ID'])
category_id = int(os.environ['EVENT_CATEGORY_ID'])
ZoneInfo(os.environ['EVENT_TIME_ZONE'])
conn = sqlite3.connect('data/db/ittf.db')
conn.execute('PRAGMA foreign_keys = ON')
try:
    category = conn.execute('SELECT 1 FROM event_categories WHERE id=?', (category_id,)).fetchone()
    if not category:
        raise SystemExit('event_categories.id={} is missing'.format(category_id))
    conn.execute('''
        INSERT INTO events (
            event_id, year, name, name_zh, event_type_name, event_kind,
            event_category_id, category_code, category_name_zh, total_matches,
            start_date, end_date, location, href, lifecycle_status, time_zone
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            year=excluded.year, name=excluded.name, name_zh=excluded.name_zh,
            event_type_name=excluded.event_type_name, event_kind=excluded.event_kind,
            event_category_id=excluded.event_category_id, category_code=excluded.category_code,
            category_name_zh=excluded.category_name_zh, start_date=excluded.start_date,
            end_date=excluded.end_date, location=excluded.location, href=excluded.href,
            time_zone=excluded.time_zone,
            lifecycle_status=CASE WHEN events.lifecycle_status='completed'
                THEN events.lifecycle_status ELSE excluded.lifecycle_status END
    ''', (
        event_id, int(os.environ['EVENT_YEAR']), os.environ['EVENT_NAME'],
        os.environ['EVENT_NAME_ZH'], os.environ['EVENT_TYPE'], os.environ['EVENT_KIND'],
        category_id, os.environ['EVENT_CATEGORY_CODE'], os.environ['EVENT_CATEGORY_NAME_ZH'],
        os.environ['EVENT_START_DATE'], os.environ['EVENT_END_DATE'],
        os.environ['EVENT_LOCATION'], os.environ['EVENT_HREF'],
        os.environ['EVENT_LIFECYCLE'], os.environ['EVENT_TIME_ZONE'],
    ))
    conn.commit()
    row = conn.execute(
        'SELECT event_id, year, name, lifecycle_status, time_zone, start_date, end_date '
        'FROM events WHERE event_id=?', (event_id,)
    ).fetchone()
    print('events[{}]: {}'.format(event_id, row))
finally:
    conn.close()
PY"
}

import_schedule_and_snapshot() {
    echo "==> Importing session schedule and Asian Games current snapshot"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && '${REMOTE_PYTHON}' scripts/runtime/import_current_event_session_schedule.py --db data/db/ittf.db --dir data/event_schedule --event '${EVENT_ID}' --verbose && '${REMOTE_PYTHON}' -m scripts.asian_games_2026.import_current --db-path data/db/ittf.db --input data/asian_games/2026/normalized/current_matches.json --brackets-input data/asian_games/2026/normalized/current_brackets.json"
}

verify_import() {
    echo "==> Verifying Asian Games import"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && '${REMOTE_PYTHON}' - <<'PY'
import sqlite3
from zoneinfo import ZoneInfo

event_id = ${EVENT_ID}
conn = sqlite3.connect('data/db/ittf.db')
try:
    event = conn.execute(
        'SELECT name, lifecycle_status, time_zone FROM events WHERE event_id=?', (event_id,)
    ).fetchone()
    if not event:
        raise SystemExit('verification failed: events row is missing')
    if event[2] != '${EVENT_TIME_ZONE}':
        raise SystemExit('verification failed: expected ${EVENT_TIME_ZONE}, got {}'.format(event[2]))
    ZoneInfo(event[2])
    counts = {
        'current_event_session_schedule': conn.execute(
            'SELECT COUNT(*) FROM current_event_session_schedule WHERE event_id=?', (event_id,)
        ).fetchone()[0],
        'current_event_team_ties': conn.execute(
            'SELECT COUNT(*) FROM current_event_team_ties WHERE event_id=?', (event_id,)
        ).fetchone()[0],
        'current_event_matches': conn.execute(
            'SELECT COUNT(*) FROM current_event_matches WHERE event_id=?', (event_id,)
        ).fetchone()[0],
        'current_event_brackets': conn.execute(
            'SELECT COUNT(*) FROM current_event_brackets WHERE event_id=?', (event_id,)
        ).fetchone()[0],
        # These two child tables intentionally do not carry event_id; follow
        # their foreign keys through the corresponding parent records.
        'current_event_team_tie_side_players': conn.execute(
            '''SELECT COUNT(*)
               FROM current_event_team_tie_side_players AS p
               JOIN current_event_team_tie_sides AS s
                 ON s.current_team_tie_side_id = p.current_team_tie_side_id
               JOIN current_event_team_ties AS t
                 ON t.current_team_tie_id = s.current_team_tie_id
               WHERE t.event_id=?''', (event_id,)
        ).fetchone()[0],
        'current_event_match_side_players': conn.execute(
            '''SELECT COUNT(*)
               FROM current_event_match_side_players AS p
               JOIN current_event_match_sides AS s
                 ON s.current_match_side_id = p.current_match_side_id
               JOIN current_event_matches AS m
                 ON m.current_match_id = s.current_match_id
               WHERE m.event_id=?''', (event_id,)
        ).fetchone()[0],
    }
    if counts['current_event_session_schedule'] == 0:
        raise SystemExit('verification failed: no session schedule rows')
    bracket_counts = dict(conn.execute(
        '''SELECT sub_event_type_code, COUNT(*)
           FROM current_event_brackets
           WHERE event_id=? AND sub_event_type_code IN ('MS','WS','MD','WD','XD')
           GROUP BY sub_event_type_code''', (event_id,)
    ))
    missing_brackets = [code for code in ('MS', 'WS', 'MD', 'WD', 'XD') if bracket_counts.get(code, 0) == 0]
    if missing_brackets:
        raise SystemExit('verification failed: missing individual brackets: {}'.format(', '.join(missing_brackets)))
    print('events[{}]: {}'.format(event_id, event))
    for table, count in counts.items():
        print('{}: {}'.format(table, count))
    print('individual brackets: {}'.format(bracket_counts))
finally:
    conn.close()
PY"
}

install_remote_crontab() {
    echo "==> Installing Asian Games 2026 crontab block"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && PYTHON_BIN='${REMOTE_PYTHON_BIN}' scripts/asian_games_2026/install_crontab.sh"
}

check_remote_python
stage_bundle
backup_remote_database
upsert_event_row
import_schedule_and_snapshot
verify_import
if [ "$SKIP_CRON" -eq 0 ]; then
    install_remote_crontab
fi

echo "==> Asian Games 2026 deployment completed"
