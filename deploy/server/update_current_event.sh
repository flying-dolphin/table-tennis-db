#!/usr/bin/env bash
#
# Single production entry for current-event data updates.
#
# This is the one command a maintainer runs to onboard / refresh an in-progress
# (or upcoming / just-finished) event on the production server. It mirrors the
# rankings / calendar / historical deploy scripts (remote backup + preflight +
# verify) but, because live-event data is scraped ON the server, it triggers the
# scrape+import remotely instead of uploading data.
#
# Defaults target:
#   flyingfox@xiaodoubao.site:doubao_tt   (the DB the website reads:
#                                          doubao_tt/data/db/ittf.db)
#
# What one run does (for --event-id <id>):
#   1. (unless --skip-publish) publish the current-event runtime code, mirrored
#      under REMOTE_PROJECT_DIR (scripts/runtime, schedule scraper + translation
#      stack, promote + its deps, install_current_event_crontab.sh).
#   2. ensure the events row exists/updated for <id> from events_calendar
#      (insert if missing; refresh descriptive fields for not-yet-finalized
#      events). Use --time-zone <IANA> to set events.time_zone (the calendar
#      carries no zone, but cron generation + preflight require it). lifecycle_status
#      is auto-derived from start_date in the event's time zone (in_progress once
#      started, else upcoming); pass --lifecycle to override. 'completed' is never
#      auto-set or modified here -- only promote sets it.
#   3. preflight: events row present, time_zone is valid IANA, lifecycle ok;
#      with --install-crontab also require session-schedule rows.
#   4. back up the production SQLite (kept: REMOTE_DB_BACKUPS_KEEP).
#   5. (unless --no-refresh) scrape + import the event on the server (default
#      sources, or --sources), writing the production DB.
#   6. verify current_event_* row counts for <id>.
#   7. (with --install-crontab) install/replace the high-frequency refresh cron
#      for ongoing automatic refresh + post-event promote.
#
# Relationship to the cron: once --install-crontab is run, the server cron
# handles routine in-event refresh and post-event promote automatically; you do
# NOT need to re-run this for routine updates. Re-run it for setup, a manual
# safe refresh, or after the event ends if no cron was installed.
#
# NOT published / must already exist on the server:
#   - data/db/ittf.db
#   - .env with DEFAULT_PROVIDER + its matching API key (e.g. minimax ->
#     MINIMAX_API_KEY, qwen -> DASHSCOPE_API_KEY); used by scrape_event_schedule.py
#   - data/event_schedule/{event_id}.json (human session schedule; place manually)
#
# Usage:
#   deploy/server/update_current_event.sh --event-id 3216 --time-zone Europe/London
#   deploy/server/update_current_event.sh --event-id 3216 --install-crontab
#   deploy/server/update_current_event.sh --event-id 3216 --sources live completed
#   deploy/server/update_current_event.sh --event-id 3216 --no-refresh --install-crontab
#   deploy/server/update_current_event.sh --publish-only
#   deploy/server/update_current_event.sh --event-id 3216 --skip-publish
#
# Optional env:
#   REMOTE_HOST=flyingfox@xiaodoubao.site
#   REMOTE_PROJECT_DIR=doubao_tt
#   REMOTE_PYTHON=/home/flyingfox/.pyenv/shims/python3.11   # light remote ops
#   REMOTE_PYENV_ENV_NAME=venv        # browser env for scrape + cron (recommended)
#   REMOTE_PYTHON_BIN=/path/to/venv/bin/python  # browser interpreter if not pyenv
#   REMOTE_TMP_DIR=/tmp/ittf-current-event-update
#   REMOTE_DB_BACKUPS_KEEP=5
#   REMOTE_LOG_DIR=doubao_tt/data/logs
#   RUN_ID / LOG_FILE

set -euo pipefail

REMOTE_HOST=${REMOTE_HOST:-flyingfox@xiaodoubao.site}
REMOTE_PROJECT_DIR=${REMOTE_PROJECT_DIR:-doubao_tt}
REMOTE_PYTHON=${REMOTE_PYTHON:-/home/flyingfox/.pyenv/shims/python3.11}
REMOTE_PYENV_ENV_NAME=${REMOTE_PYENV_ENV_NAME:-${PYENV_ENV_NAME:-}}
REMOTE_PYTHON_BIN=${REMOTE_PYTHON_BIN:-}
REMOTE_TMP_DIR=${REMOTE_TMP_DIR:-/tmp/ittf-current-event-update}
REMOTE_DB_BACKUPS_KEEP=${REMOTE_DB_BACKUPS_KEEP:-5}
REMOTE_LOG_DIR=${REMOTE_LOG_DIR:-}
RUN_ID=${RUN_ID:-$(date +%Y%m%d_%H%M%S)}
LOCAL_LOG_DIR=${LOCAL_LOG_DIR:-logs/deploy}
LOG_FILE=${LOG_FILE:-${LOCAL_LOG_DIR}/current-event-${RUN_ID}.log}

EVENT_ID=""
EVENT_SOURCES=()
EVENT_TIME_ZONE=""
EVENT_LIFECYCLE=""
SKIP_PUBLISH=0
PUBLISH_ONLY=0
INSTALL_CRONTAB=0
NO_REFRESH=0

usage() {
    sed -n '2,63p' "$0"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --event-id)
            if [ "$#" -lt 2 ]; then
                echo "ERROR: --event-id requires a value" >&2
                exit 2
            fi
            EVENT_ID="$2"
            shift 2
            ;;
        --sources)
            shift
            while [ "$#" -gt 0 ] && [[ "$1" != --* ]]; do
                EVENT_SOURCES+=("$1")
                shift
            done
            ;;
        --time-zone)
            if [ "$#" -lt 2 ]; then
                echo "ERROR: --time-zone requires an IANA zone value (e.g. Europe/London)" >&2
                exit 2
            fi
            EVENT_TIME_ZONE="$2"
            shift 2
            ;;
        --lifecycle)
            if [ "$#" -lt 2 ]; then
                echo "ERROR: --lifecycle requires a value" >&2
                exit 2
            fi
            EVENT_LIFECYCLE="$2"
            shift 2
            ;;
        --skip-publish)
            SKIP_PUBLISH=1
            shift
            ;;
        --publish-only)
            PUBLISH_ONLY=1
            shift
            ;;
        --install-crontab)
            INSTALL_CRONTAB=1
            shift
            ;;
        --no-refresh)
            NO_REFRESH=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ "$SKIP_PUBLISH" -eq 1 ] && [ "$PUBLISH_ONLY" -eq 1 ]; then
    echo "ERROR: --skip-publish and --publish-only cannot be used together" >&2
    exit 2
fi
if [ "$PUBLISH_ONLY" -eq 0 ] && [ -z "$EVENT_ID" ]; then
    echo "ERROR: --event-id is required (unless --publish-only)" >&2
    usage >&2
    exit 2
fi
if [ -n "$EVENT_ID" ] && ! [[ "$EVENT_ID" =~ ^[0-9]+$ ]]; then
    echo "ERROR: event_id must be numeric: ${EVENT_ID}" >&2
    exit 2
fi
if [ -n "$EVENT_LIFECYCLE" ] && [[ ! "$EVENT_LIFECYCLE" =~ ^(upcoming|draw_published|in_progress)$ ]]; then
    echo "ERROR: --lifecycle must be one of: upcoming draw_published in_progress (completed is set only by promote)" >&2
    exit 2
fi
if ! [[ "$REMOTE_DB_BACKUPS_KEEP" =~ ^[0-9]+$ ]] || [ "$REMOTE_DB_BACKUPS_KEEP" -lt 1 ]; then
    echo "ERROR: REMOTE_DB_BACKUPS_KEEP must be a positive integer: ${REMOTE_DB_BACKUPS_KEEP}" >&2
    exit 2
fi
if [ "$INSTALL_CRONTAB" -eq 1 ] && [ -z "$REMOTE_PYENV_ENV_NAME" ] && [ -z "$REMOTE_PYTHON_BIN" ]; then
    echo "ERROR: --install-crontab needs REMOTE_PYENV_ENV_NAME or REMOTE_PYTHON_BIN (browser-capable python for cron jobs)" >&2
    exit 2
fi
if [ "$NO_REFRESH" -eq 0 ] && [ "$PUBLISH_ONLY" -eq 0 ] && [ -z "$REMOTE_PYENV_ENV_NAME" ] && [ -z "$REMOTE_PYTHON_BIN" ]; then
    echo "ERROR: the refresh step needs REMOTE_PYENV_ENV_NAME or REMOTE_PYTHON_BIN (browser-capable python); pass --no-refresh to skip it" >&2
    exit 2
fi

cd "$(dirname "$0")/../.."

SOURCES_STR="${EVENT_SOURCES[*]:-}"

init_logging() {
    mkdir -p "$(dirname "$LOG_FILE")"
    touch "$LOG_FILE"
    exec > >(tee -a "$LOG_FILE") 2>&1
    echo "==> Run ID: ${RUN_ID}"
    echo "==> Remote: ${REMOTE_HOST}:${REMOTE_PROJECT_DIR}"
    [ -n "$EVENT_ID" ] && echo "==> Event id: ${EVENT_ID}"
    [ -n "$SOURCES_STR" ] && echo "==> Sources: ${SOURCES_STR}"
    echo "==> Logging to ${LOG_FILE}"
}

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

copy_file_to_staging() {
    local src="$1"
    local dest="$2"
    require_file "$src"
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
}

check_remote_python() {
    echo "==> Checking remote Python: ${REMOTE_PYTHON}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && command -v ${REMOTE_PYTHON} && ${REMOTE_PYTHON} --version && ${REMOTE_PYTHON} - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit(f'ERROR: Python 3.10+ required, got {sys.version.split()[0]}')
print(f'Remote Python OK: {sys.version.split()[0]}')
PY"
}

# Mirror scripts/runtime/** into the staging tree, excluding tests and bytecode.
copy_runtime_python_to_staging() {
    local staging_dir="$1"
    require_dir "scripts/runtime"
    mkdir -p "${staging_dir}/scripts/runtime"
    tar \
        --exclude='__pycache__' \
        --exclude='test_*.py' \
        -cf - \
        -C scripts/runtime . \
        | tar -xf - -C "${staging_dir}/scripts/runtime"
}

publish_runtime() {
    local staging_dir archive_path remote_archive
    staging_dir="$(mktemp -d)"
    archive_path="$(mktemp -p /tmp ittf-current-event-runtime.XXXXXX.tar.gz)"
    remote_archive="${REMOTE_TMP_DIR}/current_event_runtime_bundle.tar.gz"
    trap 'rm -rf "$staging_dir" "$archive_path"' RETURN

    echo "==> Staging current-event runtime files (mirrored under ${REMOTE_PROJECT_DIR})"
    copy_runtime_python_to_staging "$staging_dir"
    copy_file_to_staging "deploy/server/install_current_event_crontab.sh" "${staging_dir}/deploy/server/install_current_event_crontab.sh"
    # Per-session schedule scraper + translation stack.
    copy_file_to_staging "scripts/scrape_event_schedule.py" "${staging_dir}/scripts/scrape_event_schedule.py"
    copy_file_to_staging "scripts/lib/translator.py" "${staging_dir}/scripts/lib/translator.py"
    copy_file_to_staging "scripts/lib/dict_translator.py" "${staging_dir}/scripts/lib/dict_translator.py"
    copy_file_to_staging "scripts/lib/event_translation.py" "${staging_dir}/scripts/lib/event_translation.py"
    copy_file_to_staging "scripts/data/translation_dict_v2.json" "${staging_dir}/scripts/data/translation_dict_v2.json"
    copy_file_to_staging "docs/rules/TRANSLATION_RULES.md" "${staging_dir}/docs/rules/TRANSLATION_RULES.md"
    # Post-event promote + its local deps (closes the auto-promote cron loop).
    copy_file_to_staging "scripts/db/config.py" "${staging_dir}/scripts/db/config.py"
    copy_file_to_staging "scripts/db/_match_keys.py" "${staging_dir}/scripts/db/_match_keys.py"
    copy_file_to_staging "scripts/db/_import_summary.py" "${staging_dir}/scripts/db/_import_summary.py"
    copy_file_to_staging "scripts/db/import_event_draw_matches.py" "${staging_dir}/scripts/db/import_event_draw_matches.py"
    copy_file_to_staging "scripts/db/import_sub_events.py" "${staging_dir}/scripts/db/import_sub_events.py"
    copy_file_to_staging "scripts/db/promote_current_event.py" "${staging_dir}/scripts/db/promote_current_event.py"

    tar -czf "$archive_path" -C "$staging_dir" .

    echo "==> Uploading current-event runtime to ${REMOTE_HOST}:${remote_archive}"
    ssh "$REMOTE_HOST" "mkdir -p '${REMOTE_TMP_DIR}' '${REMOTE_PROJECT_DIR}'"
    scp "$archive_path" "${REMOTE_HOST}:${remote_archive}"

    echo "==> Extracting current-event runtime under ${REMOTE_PROJECT_DIR}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && tar -xzf '${remote_archive}' && rm -f '${remote_archive}' && chmod +x deploy/server/install_current_event_crontab.sh"
}

# Insert the events row from events_calendar if missing; refresh descriptive
# fields while the event is not yet finalized. Never touches time_zone /
# lifecycle_status / scraped_at / total_matches, and never clobbers completed
# (historical / promoted) events — guarded by lifecycle_status != 'completed'
# (import_events.py / promote set 'completed' once an event is finalized).
ensure_events_row() {
    echo "==> Ensuring events row for event ${EVENT_ID} from events_calendar"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && EVENT_ID='${EVENT_ID}' EVENT_TIME_ZONE='${EVENT_TIME_ZONE}' EVENT_LIFECYCLE='${EVENT_LIFECYCLE}' ${REMOTE_PYTHON} - <<'PY'
import os
import sqlite3
import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

event_id = int(os.environ['EVENT_ID'])
tz = (os.environ.get('EVENT_TIME_ZONE') or '').strip()
lifecycle = (os.environ.get('EVENT_LIFECYCLE') or '').strip()
conn = sqlite3.connect('data/db/ittf.db')
conn.execute('PRAGMA foreign_keys = ON')
try:
    cur = conn.cursor()
    # Validate the time zone before any write, so a bad --time-zone fails fast.
    if tz:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise SystemExit('ERROR: --time-zone not a valid IANA zone: ' + tz)
    cal = cur.execute('SELECT 1 FROM events_calendar WHERE event_id = ?', (event_id,)).fetchone()
    if not cal:
        existing = cur.execute('SELECT 1 FROM events WHERE event_id = ?', (event_id,)).fetchone()
        print('  events_calendar has no row for {}; {}'.format(
            event_id,
            'events row already exists, leaving as-is.' if existing
            else 'and no events row exists either.'))
    else:
        cur.execute(
            '''
            INSERT INTO events (
                event_id, year, name, name_zh, event_type_name, event_kind,
                event_category_id, category_code, category_name_zh,
                total_matches, start_date, end_date, location, href,
                scraped_at, lifecycle_status
            )
            SELECT
                ec.event_id, ec.year, ec.name, ec.name_zh, ec.event_type, ec.event_kind,
                ec.event_category_id, cat.category_id, cat.category_name_zh,
                0, ec.start_date, ec.end_date, ec.location, ec.href,
                ec.scraped_at, 'upcoming'
            FROM events_calendar ec
            LEFT JOIN event_categories cat ON cat.id = ec.event_category_id
            WHERE ec.event_id = ?
            ON CONFLICT(event_id) DO UPDATE SET
                year = excluded.year,
                name = excluded.name,
                name_zh = excluded.name_zh,
                event_type_name = excluded.event_type_name,
                event_kind = excluded.event_kind,
                event_category_id = excluded.event_category_id,
                category_code = excluded.category_code,
                category_name_zh = excluded.category_name_zh,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                location = excluded.location,
                href = excluded.href
            WHERE events.lifecycle_status != 'completed'
            ''',
            (event_id,),
        )
        conn.commit()
    # Set events-only fields the calendar does not carry (time_zone / lifecycle),
    # only for not-yet-finalized events. promote owns the 'completed' transition.
    if tz:
        cur.execute(
            \"UPDATE events SET time_zone = ? WHERE event_id = ? AND lifecycle_status != 'completed'\",
            (tz, event_id),
        )
    # lifecycle: explicit --lifecycle wins; otherwise auto-derive upcoming/in_progress
    # from start_date in the event's time zone. Never auto-set 'completed' (promote owns it).
    cur_row = cur.execute(
        'SELECT lifecycle_status, time_zone, start_date FROM events WHERE event_id = ?',
        (event_id,),
    ).fetchone()
    if cur_row and cur_row[0] != 'completed':
        if lifecycle:
            cur.execute(
                \"UPDATE events SET lifecycle_status = ? WHERE event_id = ? AND lifecycle_status != 'completed'\",
                (lifecycle, event_id),
            )
        else:
            start_date = (cur_row[2] or '')[:10]
            if start_date:
                tzinfo = None
                if cur_row[1]:
                    try:
                        tzinfo = ZoneInfo(cur_row[1])
                    except (ZoneInfoNotFoundError, ValueError):
                        tzinfo = None
                today = datetime.datetime.now(tzinfo).date().isoformat()
                derived = 'in_progress' if today >= start_date else 'upcoming'
                cur.execute(
                    \"UPDATE events SET lifecycle_status = ? WHERE event_id = ? AND lifecycle_status != 'completed'\",
                    (derived, event_id),
                )
                print('  lifecycle 自动判定为 {} (start_date={}, tz={}, today={})'.format(
                    derived, start_date, cur_row[1] or '?', today))
            else:
                print('  start_date 缺失，未自动判定 lifecycle（保持现状；需要时显式传 --lifecycle）')
    conn.commit()
    row = cur.execute(
        'SELECT lifecycle_status, time_zone, scraped_at FROM events WHERE event_id = ?',
        (event_id,),
    ).fetchone()
    if row:
        print('  events[{}]: lifecycle={} time_zone={} scraped_at={}'.format(
            event_id, row[0], row[1], row[2]))
finally:
    conn.close()
PY"
}

run_preflight() {
    echo "==> Running current-event preflight"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && EVENT_ID='${EVENT_ID}' NEED_SCHEDULE='${INSTALL_CRONTAB}' ${REMOTE_PYTHON} - <<'PY'
import os
import sqlite3
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

event_id = int(os.environ['EVENT_ID'])
need_schedule = os.environ.get('NEED_SCHEDULE') == '1'
conn = sqlite3.connect('data/db/ittf.db')
errors = []
try:
    row = conn.execute(
        'SELECT lifecycle_status, time_zone FROM events WHERE event_id = ?',
        (event_id,),
    ).fetchone()
    if not row:
        errors.append('no events row for {} (not in events_calendar? set up base record first)'.format(event_id))
    else:
        lifecycle, tz = row
        if lifecycle not in ('upcoming', 'draw_published', 'in_progress', 'completed'):
            errors.append('invalid lifecycle_status={!r}'.format(lifecycle))
        if not tz:
            errors.append('time_zone is empty (pass --time-zone <IANA>, e.g. --time-zone Europe/London)')
        else:
            try:
                ZoneInfo(tz)
            except (ZoneInfoNotFoundError, ValueError):
                errors.append('time_zone not a valid IANA zone: {!r}'.format(tz))
    if need_schedule:
        n = conn.execute(
            'SELECT COUNT(*) FROM current_event_session_schedule WHERE event_id = ?',
            (event_id,),
        ).fetchone()[0]
        if not n:
            errors.append('no current_event_session_schedule rows (cron generation needs the session schedule; '
                          'import data/event_schedule/{id}.json first)')
    print('Current-event preflight summary:')
    print('  event_id: {}'.format(event_id))
    if row:
        print('  lifecycle_status: {}'.format(row[0]))
        print('  time_zone: {}'.format(row[1]))
finally:
    conn.close()

if errors:
    print('Current-event preflight failed:')
    for e in errors:
        print('  - {}'.format(e))
    sys.exit(1)
PY"
}

backup_remote_database() {
    echo "==> Backing up remote database before current-event refresh"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && mkdir -p data/db/backups && backup_path=\"data/db/backups/ittf-before-current-event-\$(date +%Y%m%d_%H%M%S).db\" && ${REMOTE_PYTHON} -c \"import sqlite3, sys; src = sqlite3.connect('data/db/ittf.db'); dst = sqlite3.connect(sys.argv[1]); src.backup(dst); dst.close(); src.close()\" \"\$backup_path\" && echo \"Remote backup path: \$backup_path\" && ls -lh \"\$backup_path\" && ${REMOTE_PYTHON} -c \"from pathlib import Path; keep = int('${REMOTE_DB_BACKUPS_KEEP}'); backups = sorted(Path('data/db/backups').glob('ittf-before-current-event-*.db'), key=lambda p: p.stat().st_mtime, reverse=True); removed = backups[keep:]; [p.unlink() for p in removed]; print('Backup retention: kept {} of {} files, removed {}'.format(min(len(backups), keep), len(backups), len(removed)))\""
}

# Emit the remote shell prelude that resolves a browser-capable PYTHON_BIN.
remote_python_prelude() {
    if [ -n "$REMOTE_PYENV_ENV_NAME" ]; then
        cat <<PRELUDE
export PYENV_ROOT="\$HOME/.pyenv"
export PATH="\$PYENV_ROOT/bin:\$PATH"
eval "\$(pyenv init -)"
eval "\$(pyenv virtualenv-init -)"
pyenv activate "${REMOTE_PYENV_ENV_NAME}"
PYTHON_BIN="\$(pyenv which python)"
PRELUDE
    else
        echo "PYTHON_BIN='${REMOTE_PYTHON_BIN}'"
    fi
}

run_refresh() {
    # session_schedule 只能从 data/event_schedule/{id}.json 导入，不是 scrape source。
    # scrape 与 import 分别取 sources：scrape 过滤掉 session_schedule；若 --sources 只剩
    # session_schedule（无可抓取项）则跳过 scrape，仅导入。未指定 --sources 时两者各用
    # 自己的默认（scrape=schedule/standings/brackets/live/completed，import 含 session_schedule）。
    local import_arg="" scrape_arg="" scrape_sources=""
    if [ -n "$SOURCES_STR" ]; then
        import_arg="--sources ${SOURCES_STR}"
        local s
        for s in "${EVENT_SOURCES[@]}"; do
            [ "$s" = "session_schedule" ] && continue
            scrape_sources="${scrape_sources:+$scrape_sources }$s"
        done
        [ -n "$scrape_sources" ] && scrape_arg="--sources ${scrape_sources}"
    else
        # 默认与 cron 完全一致：scrape 和 import 都走相同的五类 source。显式指定
        # import 五类（而非依赖 import 自带的默认，那个还含 session_schedule），
        # 这样默认刷新不会因为服务器上缺该赛事的人工 session 日程文件而失败。
        # session_schedule 是人工日程，按第 4.1 节用 --sources session_schedule 单独导入。
        import_arg="--sources schedule standings brackets live completed"
        # scrape 不传 --sources，用其默认（同样的五类）。
    fi

    local scrape_line
    if [ -z "$SOURCES_STR" ] || [ -n "$scrape_sources" ]; then
        scrape_line="\"\$PYTHON_BIN\" scripts/runtime/scrape_current_event.py --event-id ${EVENT_ID} ${scrape_arg} --headless --live-event-data-root data/live_event_data"
    else
        scrape_line="echo '    (--sources 仅含 session_schedule：跳过 scrape，仅导入)'"
    fi

    echo "==> Scraping + importing event ${EVENT_ID} on the server"
    ssh "$REMOTE_HOST" bash -s <<REMOTE
set -euo pipefail
cd "${REMOTE_PROJECT_DIR}"
$(remote_python_prelude)
echo "    using python: \$PYTHON_BIN"
${scrape_line}
"\$PYTHON_BIN" scripts/runtime/import_current_event.py --event-id ${EVENT_ID} ${import_arg} --db-path data/db/ittf.db --live-event-data-root data/live_event_data --event-schedule-dir data/event_schedule
REMOTE
}

verify_refresh() {
    echo "==> Verifying current_event_* row counts for event ${EVENT_ID}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && EVENT_ID='${EVENT_ID}' ${REMOTE_PYTHON} - <<'PY'
import os
import sqlite3

event_id = int(os.environ['EVENT_ID'])
conn = sqlite3.connect('data/db/ittf.db')
tables = [
    'current_event_session_schedule',
    'current_event_group_standings',
    'current_event_brackets',
    'current_event_team_ties',
    'current_event_matches',
]
counts = {}
try:
    for t in tables:
        try:
            counts[t] = conn.execute('SELECT COUNT(*) FROM {} WHERE event_id = ?'.format(t), (event_id,)).fetchone()[0]
        except sqlite3.OperationalError as exc:
            counts[t] = 'ERR({})'.format(exc)
finally:
    conn.close()

print('Current-event verification summary:')
for t, c in counts.items():
    print('  {}: {}'.format(t, c))

numeric = [c for c in counts.values() if isinstance(c, int)]
if numeric and sum(numeric) == 0:
    # Not necessarily an error (e.g. an upcoming event with no data yet, or a
    # session_schedule-only import). Warn but do not fail the run.
    print('Current-event verification WARNING: all current_event_* counts are zero for this event; '
          'check the scrape output / raw files if data was expected.')
PY"
}

install_remote_crontab() {
    local remote_env=""
    if [ -n "$REMOTE_PYENV_ENV_NAME" ]; then
        remote_env="PYENV_ENV_NAME='${REMOTE_PYENV_ENV_NAME}'"
    fi
    if [ -n "$REMOTE_PYTHON_BIN" ]; then
        remote_env="${remote_env} PYTHON_BIN='${REMOTE_PYTHON_BIN}'"
    fi
    if [ -n "$REMOTE_LOG_DIR" ]; then
        remote_env="${remote_env} LOG_DIR='${REMOTE_LOG_DIR}'"
    fi

    echo "==> Installing current-event crontab for event ${EVENT_ID}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && ${remote_env} ./deploy/server/install_current_event_crontab.sh '${EVENT_ID}'"
}

init_logging
check_remote_python

if [ "$SKIP_PUBLISH" -eq 0 ]; then
    publish_runtime
fi

if [ "$PUBLISH_ONLY" -eq 1 ]; then
    echo "==> Done (publish-only)"
    exit 0
fi

# Back up first: ensure_events_row already writes the events row, so the backup
# must precede it to cover every production write.
backup_remote_database
ensure_events_row
run_preflight

if [ "$NO_REFRESH" -eq 0 ]; then
    run_refresh
    verify_refresh
fi

if [ "$INSTALL_CRONTAB" -eq 1 ]; then
    install_remote_crontab
fi

echo "==> Done"
