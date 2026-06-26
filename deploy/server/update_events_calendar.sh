#!/usr/bin/env bash
#
# Publish events calendar import code and a single year calendar JSON, then
# import it on the remote server.
#
# Defaults target:
#   flyingfox@xiaodoubao.site:doubao_tt/data
#
# Usage:
#   deploy/server/update_events_calendar.sh --year 2026
#   deploy/server/update_events_calendar.sh --year 2026 --publish-only
#   deploy/server/update_events_calendar.sh --year 2026 --skip-publish
#
# Optional env:
#   REMOTE_HOST=flyingfox@xiaodoubao.site
#   REMOTE_PROJECT_DIR=doubao_tt
#   REMOTE_DATA_DIR=doubao_tt/data
#   REMOTE_PYTHON=/home/flyingfox/.pyenv/shims/python3.11
#   REMOTE_TMP_DIR=/tmp/ittf-events-calendar-update
#   REMOTE_DB_BACKUPS_KEEP=5
#   RUN_ID=20260626_180000
#   LOG_FILE=logs/deploy/events-calendar-20260626_180000.log
#   REMOTE_IMPORT_LOG_DIR=doubao_tt/data/ittf_logs

set -euo pipefail

REMOTE_HOST=${REMOTE_HOST:-flyingfox@xiaodoubao.site}
REMOTE_PROJECT_DIR=${REMOTE_PROJECT_DIR:-doubao_tt}
REMOTE_DATA_DIR=${REMOTE_DATA_DIR:-${REMOTE_PROJECT_DIR}/data}
REMOTE_PYTHON=${REMOTE_PYTHON:-/home/flyingfox/.pyenv/shims/python3.11}
REMOTE_TMP_DIR=${REMOTE_TMP_DIR:-/tmp/ittf-events-calendar-update}
REMOTE_BUNDLE_NAME=${REMOTE_BUNDLE_NAME:-events_calendar_payload.tar.gz}
REMOTE_DB_BACKUPS_KEEP=${REMOTE_DB_BACKUPS_KEEP:-5}
RUN_ID=${RUN_ID:-$(date +%Y%m%d_%H%M%S)}
LOCAL_LOG_DIR=${LOCAL_LOG_DIR:-logs/deploy}
LOG_FILE=${LOG_FILE:-${LOCAL_LOG_DIR}/events-calendar-${RUN_ID}.log}
REMOTE_IMPORT_LOG_DIR=${REMOTE_IMPORT_LOG_DIR:-${REMOTE_DATA_DIR}/ittf_logs}

YEAR=${YEAR:-}
PUBLISH_ONLY=0
SKIP_PUBLISH=0

usage() {
    sed -n '2,21p' "$0"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --year|-y)
            if [ "$#" -lt 2 ]; then
                echo "ERROR: $1 requires a year value" >&2
                usage >&2
                exit 2
            fi
            YEAR="$2"
            shift
            ;;
        --publish-only)
            PUBLISH_ONLY=1
            ;;
        --skip-publish)
            SKIP_PUBLISH=1
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
    shift
done

if [ -z "$YEAR" ]; then
    echo "ERROR: --year or YEAR is required" >&2
    usage >&2
    exit 2
fi
if ! [[ "$YEAR" =~ ^[0-9]{4}$ ]]; then
    echo "ERROR: year must be a four-digit year: ${YEAR}" >&2
    exit 2
fi
if [ "$PUBLISH_ONLY" -eq 1 ] && [ "$SKIP_PUBLISH" -eq 1 ]; then
    echo "ERROR: --publish-only and --skip-publish cannot be used together" >&2
    exit 2
fi
if ! [[ "$REMOTE_DB_BACKUPS_KEEP" =~ ^[0-9]+$ ]] || [ "$REMOTE_DB_BACKUPS_KEEP" -lt 1 ]; then
    echo "ERROR: REMOTE_DB_BACKUPS_KEEP must be a positive integer: ${REMOTE_DB_BACKUPS_KEEP}" >&2
    exit 2
fi

cd "$(dirname "$0")/../.."

init_logging() {
    mkdir -p "$(dirname "$LOG_FILE")"
    touch "$LOG_FILE"
    exec > >(tee -a "$LOG_FILE") 2>&1

    echo "==> Run ID: ${RUN_ID}"
    echo "==> Year: ${YEAR}"
    echo "==> Logging to ${LOG_FILE}"
}

require_file() {
    if [ ! -f "$1" ]; then
        echo "ERROR: required file not found: $1" >&2
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

file_mtime() {
    stat -c '%y' "$1"
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

publish_runtime() {
    local staging_dir archive_path remote_archive
    staging_dir="$(mktemp -d)"
    archive_path="$(mktemp -p /tmp ittf-events-calendar-runtime.XXXXXX.tar.gz)"
    remote_archive="${REMOTE_TMP_DIR}/events_calendar_runtime_bundle.tar.gz"
    trap 'rm -rf "$staging_dir" "$archive_path"' RETURN

    echo "==> Staging events calendar runtime/import files"
    copy_file_to_staging "scripts/db/config.py" "${staging_dir}/scripts/db/config.py"
    copy_file_to_staging "scripts/db/import_events_calendar.py" "${staging_dir}/scripts/db/import_events_calendar.py"
    copy_file_to_staging "scripts/db/event_classification_overrides.py" "${staging_dir}/scripts/db/event_classification_overrides.py"
    copy_file_to_staging "data/event_category_mapping.json" "${staging_dir}/data/event_category_mapping.json"

    tar -czf "$archive_path" -C "$staging_dir" .

    echo "==> Uploading runtime/import bundle to ${REMOTE_HOST}:${remote_archive}"
    ssh "$REMOTE_HOST" "mkdir -p '${REMOTE_TMP_DIR}' '${REMOTE_PROJECT_DIR}'"
    scp "$archive_path" "${REMOTE_HOST}:${remote_archive}"

    echo "==> Extracting runtime/import bundle under ${REMOTE_PROJECT_DIR}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && tar -xzf '${remote_archive}' && rm -f '${remote_archive}'"
}

backup_remote_database() {
    echo "==> Backing up remote database before events calendar import"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && mkdir -p data/db/backups && backup_path=\"data/db/backups/ittf-before-events-calendar-${YEAR}-\$(date +%Y%m%d_%H%M%S).db\" && ${REMOTE_PYTHON} -c \"import sqlite3, sys; src = sqlite3.connect('data/db/ittf.db'); dst = sqlite3.connect(sys.argv[1]); src.backup(dst); dst.close(); src.close()\" \"\$backup_path\" && echo \"Remote backup path: \$backup_path\" && ls -lh \"\$backup_path\" && ${REMOTE_PYTHON} -c \"from pathlib import Path; keep = int('${REMOTE_DB_BACKUPS_KEEP}'); backups = sorted(Path('data/db/backups').glob('ittf-before-events-calendar-*.db'), key=lambda p: p.stat().st_mtime, reverse=True); removed = backups[keep:]; [p.unlink() for p in removed]; print('Backup retention: kept {} of {} files, removed {}'.format(min(len(backups), keep), len(backups), len(removed)))\""
}

write_payload_manifest() {
    local manifest_path="$1"
    local calendar_file="$2"
    local remote_payload_dir="$3"
    local remote_calendar_path="$4"
    local remote_manifest_log_path="$5"

    {
        echo "run_id=${RUN_ID}"
        echo "created_at=$(date -Is)"
        echo "year=${YEAR}"
        echo "remote_host=${REMOTE_HOST}"
        echo "remote_project_dir=${REMOTE_PROJECT_DIR}"
        echo "remote_data_dir=${REMOTE_DATA_DIR}"
        echo "remote_tmp_dir=${REMOTE_TMP_DIR}"
        echo "remote_payload_dir=${remote_payload_dir}"
        echo "remote_import_log_dir=${REMOTE_IMPORT_LOG_DIR}"
        echo "remote_manifest_log_path=${remote_manifest_log_path}"
        echo "local_log_file=${LOG_FILE}"
        echo "calendar_file=${calendar_file}"
        echo "calendar_file_mtime=$(file_mtime "$calendar_file")"
        echo "remote_calendar_path=${remote_calendar_path}"
    } > "$manifest_path"
}

run_remote_preflight() {
    local remote_calendar_path="$1"

    echo "==> Running remote events calendar preflight checks"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && YEAR='${YEAR}' CALENDAR_FILE='${remote_calendar_path}' ${REMOTE_PYTHON} -" <<'PY'
import json
import os
import sys
from pathlib import Path

year = int(os.environ["YEAR"])
calendar_path = Path(os.environ["CALENDAR_FILE"])
errors = []

if not calendar_path.exists():
    errors.append(f"calendar_file_missing={calendar_path}")
    payload = {}
else:
    try:
        payload = json.loads(calendar_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"calendar_json_invalid={exc}")
        payload = {}

payload_year = payload.get("year")
events = payload.get("events") or []
missing_name_zh = [item.get("name") for item in events if not item.get("name_zh")]
missing_location_zh = [item.get("name") for item in events if item.get("location") and not item.get("location_zh")]
with_href = [item for item in events if item.get("href")]

if payload_year != year:
    errors.append(f"year_mismatch={payload_year} expected={year}")
if not events:
    errors.append("events_empty")
if missing_name_zh:
    errors.append(f"missing_name_zh={len(missing_name_zh)}")
if missing_location_zh:
    errors.append(f"missing_location_zh={len(missing_location_zh)}")

print("Remote events calendar preflight summary:")
print(f"  calendar_file: {calendar_path}")
print(f"  year: {payload_year}")
print(f"  events: {len(events)}")
print(f"  with_href: {len(with_href)}")
print(f"  missing_name_zh: {len(missing_name_zh)}")
print(f"  missing_location_zh: {len(missing_location_zh)}")

if errors:
    print("Remote events calendar preflight failed:")
    for error in errors:
        print(f"  - {error}")
    if missing_name_zh:
        print("  missing_name_zh samples:", missing_name_zh[:10])
    if missing_location_zh:
        print("  missing_location_zh samples:", missing_location_zh[:10])
    sys.exit(1)
PY
}

run_remote_dry_run() {
    echo "==> Running remote events calendar dry-run"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && test -f 'data/events_calendar/cn/events_calendar_${YEAR}.json' && ${REMOTE_PYTHON} scripts/db/import_events_calendar.py --year '${YEAR}' --dry-run"
}

verify_remote_import() {
    local remote_calendar_path="$1"

    echo "==> Verifying remote database after events calendar import"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && YEAR='${YEAR}' CALENDAR_FILE='${remote_calendar_path}' ${REMOTE_PYTHON} -" <<'PY'
import json
import os
import sqlite3
import sys
from pathlib import Path

year = int(os.environ["YEAR"])
calendar_path = Path(os.environ["CALENDAR_FILE"])
payload = json.loads(calendar_path.read_text(encoding="utf-8"))
expected = len(payload.get("events") or [])

conn = sqlite3.connect("data/db/ittf.db")
try:
    total = conn.execute("SELECT COUNT(*) FROM events_calendar WHERE year = ?", (year,)).fetchone()[0]
    with_start_date = conn.execute(
        "SELECT COUNT(*) FROM events_calendar WHERE year = ? AND start_date IS NOT NULL",
        (year,),
    ).fetchone()[0]
    with_event_id = conn.execute(
        "SELECT COUNT(*) FROM events_calendar WHERE year = ? AND event_id IS NOT NULL",
        (year,),
    ).fetchone()[0]
    with_category = conn.execute(
        "SELECT COUNT(*) FROM events_calendar WHERE year = ? AND event_category_id IS NOT NULL",
        (year,),
    ).fetchone()[0]
finally:
    conn.close()

errors = []
if total != expected:
    errors.append(f"events_calendar_count_mismatch={total} expected={expected}")

print("Remote events calendar import verification summary:")
print(f"  year: {year}")
print(f"  expected_events: {expected}")
print(f"  events_calendar rows: {total}")
print(f"  with_start_date: {with_start_date}")
print(f"  with_event_id: {with_event_id}")
print(f"  with_category: {with_category}")

if errors:
    print("Remote events calendar import verification failed:")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)
PY
}

publish_remote_payload_data() {
    local remote_payload_dir="$1"
    local calendar_basename="$2"

    echo "==> Publishing events calendar JSON into ${REMOTE_DATA_DIR}"
    ssh "$REMOTE_HOST" "mkdir -p '${REMOTE_DATA_DIR}/events_calendar/cn' && cp '${remote_payload_dir}/events_calendar/cn/${calendar_basename}' '${REMOTE_DATA_DIR}/events_calendar/cn/${calendar_basename}'"
}

upload_data_and_import() {
    local calendar_file calendar_basename staging_dir archive_path remote_archive
    local remote_payload_dir remote_calendar_path manifest_path remote_manifest_log_path

    calendar_file="data/events_calendar/cn/events_calendar_${YEAR}.json"
    calendar_basename="$(basename "$calendar_file")"
    require_file "$calendar_file"

    staging_dir="$(mktemp -d)"
    archive_path="$(mktemp -p /tmp ittf-events-calendar.XXXXXX.tar.gz)"
    remote_archive="${REMOTE_TMP_DIR}/${REMOTE_BUNDLE_NAME}"
    remote_payload_dir="${REMOTE_TMP_DIR}/payload-${YEAR}-$(date +%Y%m%d_%H%M%S)-$$"
    remote_calendar_path="${remote_payload_dir}/events_calendar/cn/${calendar_basename}"
    remote_manifest_log_path="${REMOTE_IMPORT_LOG_DIR}/events-calendar-${YEAR}-${RUN_ID}.manifest.txt"
    trap 'rm -rf "$staging_dir" "$archive_path"' RETURN

    echo "==> Packaging events calendar data"
    echo "    year:     ${YEAR}"
    echo "    calendar: ${calendar_file}"

    mkdir -p "${staging_dir}/events_calendar/cn"
    cp "$calendar_file" "${staging_dir}/events_calendar/cn/${calendar_basename}"

    manifest_path="${staging_dir}/import_manifest.txt"
    write_payload_manifest "$manifest_path" "$calendar_file" "$remote_payload_dir" "$remote_calendar_path" "$remote_manifest_log_path"

    echo "==> Payload manifest"
    cat "$manifest_path"

    tar -czf "$archive_path" -C "$staging_dir" .

    echo "==> Uploading data bundle to ${REMOTE_HOST}:${remote_archive}"
    ssh "$REMOTE_HOST" "mkdir -p '${REMOTE_TMP_DIR}' '${REMOTE_DATA_DIR}'"
    scp "$archive_path" "${REMOTE_HOST}:${remote_archive}"

    echo "==> Extracting data bundle under ${remote_payload_dir}"
    ssh "$REMOTE_HOST" "rm -rf '${remote_payload_dir}' && mkdir -p '${remote_payload_dir}' && tar -xzf '${remote_archive}' -C '${remote_payload_dir}' && rm -f '${remote_archive}'"

    run_remote_preflight "$remote_calendar_path"
    publish_remote_payload_data "$remote_payload_dir" "$calendar_basename"
    run_remote_dry_run
    backup_remote_database

    echo "==> Running remote events calendar import"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && ${REMOTE_PYTHON} scripts/db/import_events_calendar.py --year '${YEAR}'"

    verify_remote_import "data/events_calendar/cn/${calendar_basename}"

    echo "==> Saving import manifest to ${remote_manifest_log_path}"
    ssh "$REMOTE_HOST" "mkdir -p '${REMOTE_IMPORT_LOG_DIR}' && cp '${remote_payload_dir}/import_manifest.txt' '${remote_manifest_log_path}'"

    echo "==> Cleaning up remote payload directory"
    ssh "$REMOTE_HOST" "rm -rf '${remote_payload_dir}'"
}

init_logging
check_remote_python

if [ "$SKIP_PUBLISH" -eq 0 ]; then
    publish_runtime
fi

if [ "$PUBLISH_ONLY" -eq 0 ]; then
    upload_data_and_import
fi

echo "==> Done"
