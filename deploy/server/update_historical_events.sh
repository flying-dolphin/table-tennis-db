#!/usr/bin/env bash
#
# Publish completed historical-event facts (events / matches / event_draw_matches /
# sub_events) to the remote production database.
#
# Use this AFTER you have already scraped + translated + imported a batch of
# completed events into the local dev database via:
#   scripts/run_import_wtt_events.sh --event-id <id...>
# (see docs/event-data-update-workflow.md section 7). This script ships the same
# already-translated JSON to the server and re-runs the importers there against
# the production SQLite, scoped strictly to the given event ids.
#
# It does NOT scrape on the server: the same-name player-centric evidence
# (data/matches_complete/cn/player_*.json) is uploaded from the dev machine and
# the server-side same-name preparation/scraping step is skipped.
#
# Defaults target:
#   flyingfox@xiaodoubao.site:doubao_tt/data
#
# Usage:
#   deploy/server/update_historical_events.sh --event-id 3391 3392
#   deploy/server/update_historical_events.sh --event-id 3391 --publish-only
#   deploy/server/update_historical_events.sh --event-id 3391 --skip-publish
#
# Optional env:
#   REMOTE_HOST=flyingfox@xiaodoubao.site
#   REMOTE_PROJECT_DIR=doubao_tt
#   REMOTE_DATA_DIR=doubao_tt/data
#   REMOTE_PYTHON=/home/flyingfox/.pyenv/shims/python3.11
#   REMOTE_TMP_DIR=/tmp/ittf-historical-events-update
#   REMOTE_DB_BACKUPS_KEEP=5
#   RUN_ID=20260627_180000
#   LOG_FILE=logs/deploy/historical-events-20260627_180000.log
#   REMOTE_IMPORT_LOG_DIR=doubao_tt/data/ittf_logs

set -euo pipefail

REMOTE_HOST=${REMOTE_HOST:-flyingfox@xiaodoubao.site}
REMOTE_PROJECT_DIR=${REMOTE_PROJECT_DIR:-doubao_tt}
REMOTE_DATA_DIR=${REMOTE_DATA_DIR:-${REMOTE_PROJECT_DIR}/data}
REMOTE_PYTHON=${REMOTE_PYTHON:-/home/flyingfox/.pyenv/shims/python3.11}
REMOTE_TMP_DIR=${REMOTE_TMP_DIR:-/tmp/ittf-historical-events-update}
REMOTE_BUNDLE_NAME=${REMOTE_BUNDLE_NAME:-historical_events_payload.tar.gz}
REMOTE_DB_BACKUPS_KEEP=${REMOTE_DB_BACKUPS_KEEP:-5}
RUN_ID=${RUN_ID:-$(date +%Y%m%d_%H%M%S)}
LOCAL_LOG_DIR=${LOCAL_LOG_DIR:-logs/deploy}
LOG_FILE=${LOG_FILE:-${LOCAL_LOG_DIR}/historical-events-${RUN_ID}.log}
REMOTE_IMPORT_LOG_DIR=${REMOTE_IMPORT_LOG_DIR:-${REMOTE_DATA_DIR}/ittf_logs}

EVENT_IDS=()
PUBLISH_ONLY=0
SKIP_PUBLISH=0

usage() {
    sed -n '2,34p' "$0"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --event-id)
            shift
            while [ "$#" -gt 0 ] && [[ "$1" != --* ]]; do
                EVENT_IDS+=("$1")
                shift
            done
            ;;
        --publish-only)
            PUBLISH_ONLY=1
            shift
            ;;
        --skip-publish)
            SKIP_PUBLISH=1
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

if [ "$PUBLISH_ONLY" -eq 1 ] && [ "$SKIP_PUBLISH" -eq 1 ]; then
    echo "ERROR: --publish-only and --skip-publish cannot be used together" >&2
    exit 2
fi
if [ "$PUBLISH_ONLY" -eq 0 ] && [ "${#EVENT_IDS[@]}" -eq 0 ]; then
    echo "ERROR: --event-id is required (unless --publish-only)" >&2
    usage >&2
    exit 2
fi
for eid in "${EVENT_IDS[@]:-}"; do
    if [ -n "$eid" ] && ! [[ "$eid" =~ ^[0-9]+$ ]]; then
        echo "ERROR: event_id must be numeric: ${eid}" >&2
        exit 2
    fi
done
if ! [[ "$REMOTE_DB_BACKUPS_KEEP" =~ ^[0-9]+$ ]] || [ "$REMOTE_DB_BACKUPS_KEEP" -lt 1 ]; then
    echo "ERROR: REMOTE_DB_BACKUPS_KEEP must be a positive integer: ${REMOTE_DB_BACKUPS_KEEP}" >&2
    exit 2
fi

cd "$(dirname "$0")/../.."

EVENT_IDS_STR="${EVENT_IDS[*]:-}"
HAS_2860=0
for eid in "${EVENT_IDS[@]:-}"; do
    if [ "$eid" = "2860" ]; then
        HAS_2860=1
    fi
done

init_logging() {
    mkdir -p "$(dirname "$LOG_FILE")"
    touch "$LOG_FILE"
    exec > >(tee -a "$LOG_FILE") 2>&1

    echo "==> Run ID: ${RUN_ID}"
    echo "==> Event ids: ${EVENT_IDS_STR:-<none>}"
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

check_remote_python() {
    echo "==> Checking remote Python: ${REMOTE_PYTHON}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && command -v ${REMOTE_PYTHON} && ${REMOTE_PYTHON} --version && ${REMOTE_PYTHON} - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit(f'ERROR: Python 3.10+ required, got {sys.version.split()[0]}')
print(f'Remote Python OK: {sys.version.split()[0]}')
PY"
}

# Upload the minimal historical-import runtime: the db importers and their local
# module dependencies. No browser/scrape code is shipped.
publish_runtime() {
    local staging_dir archive_path remote_archive
    staging_dir="$(mktemp -d)"
    archive_path="$(mktemp -p /tmp ittf-historical-events-runtime.XXXXXX.tar.gz)"
    remote_archive="${REMOTE_TMP_DIR}/historical_events_runtime_bundle.tar.gz"
    trap 'rm -rf "$staging_dir" "$archive_path"' RETURN

    echo "==> Staging historical-events runtime/import files"
    copy_file_to_staging "scripts/db/config.py" "${staging_dir}/scripts/db/config.py"
    copy_file_to_staging "scripts/db/_import_summary.py" "${staging_dir}/scripts/db/_import_summary.py"
    copy_file_to_staging "scripts/db/_match_keys.py" "${staging_dir}/scripts/db/_match_keys.py"
    copy_file_to_staging "scripts/db/event_classification_overrides.py" "${staging_dir}/scripts/db/event_classification_overrides.py"
    copy_file_to_staging "scripts/db/import_events.py" "${staging_dir}/scripts/db/import_events.py"
    copy_file_to_staging "scripts/db/import_matches.py" "${staging_dir}/scripts/db/import_matches.py"
    copy_file_to_staging "scripts/db/import_event_draw_matches.py" "${staging_dir}/scripts/db/import_event_draw_matches.py"
    copy_file_to_staging "scripts/db/import_sub_events.py" "${staging_dir}/scripts/db/import_sub_events.py"
    copy_file_to_staging "scripts/audit_same_name_players.py" "${staging_dir}/scripts/audit_same_name_players.py"
    copy_file_to_staging "scripts/fix_special_event_2860_stage_round.py" "${staging_dir}/scripts/fix_special_event_2860_stage_round.py"

    tar -czf "$archive_path" -C "$staging_dir" .

    echo "==> Uploading runtime/import bundle to ${REMOTE_HOST}:${remote_archive}"
    ssh "$REMOTE_HOST" "mkdir -p '${REMOTE_TMP_DIR}' '${REMOTE_PROJECT_DIR}'"
    scp "$archive_path" "${REMOTE_HOST}:${remote_archive}"

    echo "==> Extracting runtime/import bundle under ${REMOTE_PROJECT_DIR}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && tar -xzf '${remote_archive}' && rm -f '${remote_archive}'"
}

backup_remote_database() {
    echo "==> Backing up remote database before historical-events import"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && mkdir -p data/db/backups && backup_path=\"data/db/backups/ittf-before-historical-events-\$(date +%Y%m%d_%H%M%S).db\" && ${REMOTE_PYTHON} -c \"import sqlite3, sys; src = sqlite3.connect('data/db/ittf.db'); dst = sqlite3.connect(sys.argv[1]); src.backup(dst); dst.close(); src.close()\" \"\$backup_path\" && echo \"Remote backup path: \$backup_path\" && ls -lh \"\$backup_path\" && ${REMOTE_PYTHON} -c \"from pathlib import Path; keep = int('${REMOTE_DB_BACKUPS_KEEP}'); backups = sorted(Path('data/db/backups').glob('ittf-before-historical-events-*.db'), key=lambda p: p.stat().st_mtime, reverse=True); removed = backups[keep:]; [p.unlink() for p in removed]; print('Backup retention: kept {} of {} files, removed {}'.format(min(len(backups), keep), len(backups), len(removed)))\""
}

# Resolve each requested event id to its local match file and a filtered events
# list entry, then stage all payload files into staging_dir. Prints the resolved
# match-file basenames (one per line). Aborts on any unresolved id.
collect_local_payload() {
    local staging_dir="$1"
    local filtered_events_path="${staging_dir}/events_list/cn/events_publish_${RUN_ID}.json"
    mkdir -p "${staging_dir}/events_list/cn" "${staging_dir}/event_matches/cn" \
        "${staging_dir}/event_matches/orig" "${staging_dir}/matches_complete/cn" \
        "${staging_dir}/data"

    EVENT_IDS_STR="$EVENT_IDS_STR" FILTERED_EVENTS_PATH="$filtered_events_path" \
        STAGING_DIR="$staging_dir" python - <<'PY'
import json
import os
import re
import sys
import shutil
from pathlib import Path

root = Path.cwd()
staging = Path(os.environ["STAGING_DIR"])
event_ids = [int(x) for x in os.environ["EVENT_IDS_STR"].split()]

# event_id -> match file path (from event_matches/cn)
match_dir = root / "data" / "event_matches" / "cn"
match_by_id = {}
for path in match_dir.glob("*.json"):
    eid = None
    try:
        raw = json.loads(path.read_text(encoding="utf-8")).get("event_id")
        if raw not in (None, ""):
            eid = int(raw)
    except Exception:
        eid = None
    if eid is None:
        m = re.search(r"_(\d+)\.json$", path.name, re.IGNORECASE)
        if m:
            eid = int(m.group(1))
    if eid is not None and eid not in match_by_id:
        match_by_id[eid] = path

# event_id -> events_list entry (scan all events_list/cn files)
events_dir = root / "data" / "events_list" / "cn"
entry_by_id = {}
for path in events_dir.glob("*.json"):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    for event in data.get("events") or []:
        if not isinstance(event, dict):
            continue
        try:
            eid = int(event.get("event_id"))
        except (TypeError, ValueError):
            continue
        entry_by_id.setdefault(eid, event)

missing_match, missing_entry = [], []
resolved_entries, resolved_match_files = [], []
for eid in event_ids:
    if eid not in match_by_id:
        missing_match.append(eid)
    if eid not in entry_by_id:
        missing_entry.append(eid)
    if eid in match_by_id and eid in entry_by_id:
        resolved_entries.append(entry_by_id[eid])
        resolved_match_files.append(match_by_id[eid])

errors = []
if missing_entry:
    errors.append("no events_list entry: " + " ".join(map(str, missing_entry)))
if missing_match:
    errors.append("no event_matches/cn file: " + " ".join(map(str, missing_match)))
if errors:
    for e in errors:
        print("ERROR: " + e, file=sys.stderr)
    sys.exit(1)

# Write filtered events list payload.
filtered_path = Path(os.environ["FILTERED_EVENTS_PATH"])
filtered_path.write_text(
    json.dumps({"events": resolved_entries}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

# Stage match files.
for src in resolved_match_files:
    shutil.copy2(src, staging / "event_matches" / "cn" / src.name)
    print(src.name)

# Stage same-name player-centric evidence (small set; needed by import_matches
# since the server skips the scraping/preparation step).
pc_dir = root / "data" / "matches_complete" / "cn"
for src in pc_dir.glob("player_*.json"):
    shutil.copy2(src, staging / "matches_complete" / "cn" / src.name)

# Stage the manually-maintained country history (canonical on the dev machine).
country_history = root / "data" / "player_country_history.json"
if country_history.exists():
    shutil.copy2(country_history, staging / "data" / "player_country_history.json")

# event_id=2860 needs both orig and cn payloads for the source fix.
if 2860 in event_ids:
    orig_2860 = root / "data" / "event_matches" / "orig" / "ITTF_Mixed_Team_World_Cup_Chengdu_2023_2860.json"
    if orig_2860.exists():
        shutil.copy2(orig_2860, staging / "event_matches" / "orig" / orig_2860.name)
    else:
        print("WARN: event 2860 in batch but orig file missing: " + str(orig_2860), file=sys.stderr)
PY
}

write_payload_manifest() {
    local manifest_path="$1"
    local remote_payload_dir="$2"
    local remote_manifest_log_path="$3"
    shift 3
    {
        echo "run_id=${RUN_ID}"
        echo "created_at=$(date -Is)"
        echo "event_ids=${EVENT_IDS_STR}"
        echo "remote_host=${REMOTE_HOST}"
        echo "remote_project_dir=${REMOTE_PROJECT_DIR}"
        echo "remote_data_dir=${REMOTE_DATA_DIR}"
        echo "remote_tmp_dir=${REMOTE_TMP_DIR}"
        echo "remote_payload_dir=${remote_payload_dir}"
        echo "remote_import_log_dir=${REMOTE_IMPORT_LOG_DIR}"
        echo "remote_manifest_log_path=${remote_manifest_log_path}"
        echo "local_log_file=${LOG_FILE}"
        echo "match_files:"
        for name in "$@"; do
            echo "  - ${name}"
        done
    } > "$manifest_path"
}

run_remote_preflight() {
    local remote_payload_dir="$1"

    echo "==> Running remote historical-events preflight checks"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && EVENT_IDS='${EVENT_IDS_STR}' PAYLOAD_DIR='${remote_payload_dir}' ${REMOTE_PYTHON} -" <<'PY'
import json
import os
import sys
from pathlib import Path

event_ids = [int(x) for x in os.environ["EVENT_IDS"].split()]
payload = Path(os.environ["PAYLOAD_DIR"])
errors = []

events_files = list((payload / "events_list" / "cn").glob("*.json"))
if not events_files:
    errors.append("filtered_events_file_missing")
    entry_ids = set()
else:
    try:
        data = json.loads(events_files[0].read_text(encoding="utf-8"))
        entry_ids = {int(e.get("event_id")) for e in data.get("events") or [] if e.get("event_id") is not None}
    except Exception as exc:
        errors.append(f"events_json_invalid={exc}")
        entry_ids = set()

match_dir = payload / "event_matches" / "cn"
match_ids = set()
for path in match_dir.glob("*.json"):
    try:
        raw = json.loads(path.read_text(encoding="utf-8")).get("event_id")
        if raw not in (None, ""):
            match_ids.add(int(raw))
    except Exception as exc:
        errors.append(f"match_json_invalid={path.name}:{exc}")

missing_entry = [e for e in event_ids if e not in entry_ids]
missing_match = [e for e in event_ids if e not in match_ids]
if missing_entry:
    errors.append("missing_events_entry=" + " ".join(map(str, missing_entry)))
if missing_match:
    errors.append("missing_match_file=" + " ".join(map(str, missing_match)))

print("Remote historical-events preflight summary:")
print(f"  event_ids: {event_ids}")
print(f"  events_entries: {sorted(entry_ids)}")
print(f"  match_files: {sorted(match_ids)}")

if errors:
    print("Remote historical-events preflight failed:")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)
PY
}

# Copy payload data files into the permanent remote data dir so the production
# data tree stays the source of truth for the importers.
publish_remote_payload_data() {
    local remote_payload_dir="$1"

    echo "==> Publishing historical-events JSON into ${REMOTE_DATA_DIR}"
    ssh "$REMOTE_HOST" "set -e
        mkdir -p '${REMOTE_DATA_DIR}/event_matches/cn' '${REMOTE_DATA_DIR}/event_matches/orig' '${REMOTE_DATA_DIR}/matches_complete/cn'
        cp '${remote_payload_dir}'/event_matches/cn/*.json '${REMOTE_DATA_DIR}/event_matches/cn/'
        if ls '${remote_payload_dir}'/event_matches/orig/*.json >/dev/null 2>&1; then
            cp '${remote_payload_dir}'/event_matches/orig/*.json '${REMOTE_DATA_DIR}/event_matches/orig/'
        fi
        if ls '${remote_payload_dir}'/matches_complete/cn/*.json >/dev/null 2>&1; then
            cp '${remote_payload_dir}'/matches_complete/cn/*.json '${REMOTE_DATA_DIR}/matches_complete/cn/'
        fi
        if [ -f '${remote_payload_dir}/data/player_country_history.json' ]; then
            cp '${remote_payload_dir}/data/player_country_history.json' '${REMOTE_DATA_DIR}/player_country_history.json'
        fi"
}

run_remote_import() {
    local remote_payload_dir="$1"
    local filtered_events_remote="${remote_payload_dir}/events_list/cn/events_publish_${RUN_ID}.json"
    local fix_2860_cmd=""
    if [ "$HAS_2860" -eq 1 ]; then
        fix_2860_cmd="echo '==> Applying event 2860 source fix' && ${REMOTE_PYTHON} scripts/fix_special_event_2860_stage_round.py &&"
    fi

    echo "==> Running remote historical-events import (event ids: ${EVENT_IDS_STR})"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && set -e && mkdir -p scripts/data && \
        echo '==> Refreshing same-name players from production DB' && \
        ${REMOTE_PYTHON} scripts/audit_same_name_players.py --db-path data/db/ittf.db --output scripts/data/same_name_players.txt --country-history data/player_country_history.json --update && \
        echo '==> Importing events rows' && \
        ${REMOTE_PYTHON} scripts/db/import_events.py --input-file '${filtered_events_remote}' && \
        ${fix_2860_cmd} \
        echo '==> Importing matches' && \
        ${REMOTE_PYTHON} scripts/db/import_matches.py --source-dir data/event_matches/cn --event-id ${EVENT_IDS_STR} --same-name-players scripts/data/same_name_players.txt --player-matches-dir data/matches_complete/cn --country-history data/player_country_history.json && \
        for eid in ${EVENT_IDS_STR}; do \
            echo \"==> Rebuilding draw + sub_events for event \$eid\" && \
            ${REMOTE_PYTHON} scripts/db/import_event_draw_matches.py --event-id \"\$eid\" && \
            ${REMOTE_PYTHON} scripts/db/import_sub_events.py --event-id \"\$eid\"; \
        done"
}

verify_remote_import() {
    echo "==> Verifying remote database after historical-events import"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && EVENT_IDS='${EVENT_IDS_STR}' ${REMOTE_PYTHON} -" <<'PY'
import os
import sqlite3
import sys

event_ids = [int(x) for x in os.environ["EVENT_IDS"].split()]
conn = sqlite3.connect("data/db/ittf.db")
errors = []
print("Remote historical-events import verification summary:")
try:
    for eid in event_ids:
        in_events = conn.execute("SELECT COUNT(*) FROM events WHERE event_id = ?", (eid,)).fetchone()[0]
        matches = conn.execute("SELECT COUNT(*) FROM matches WHERE event_id = ?", (eid,)).fetchone()[0]
        draws = conn.execute("SELECT COUNT(*) FROM event_draw_matches WHERE event_id = ?", (eid,)).fetchone()[0]
        subs = conn.execute("SELECT COUNT(*) FROM sub_events WHERE event_id = ?", (eid,)).fetchone()[0]
        print(f"  event {eid}: events={in_events} matches={matches} draw_matches={draws} sub_events={subs}")
        if not in_events:
            errors.append(f"event_row_missing={eid}")
        if not matches:
            errors.append(f"no_matches={eid}")
        if not subs:
            errors.append(f"no_sub_events={eid}")
finally:
    conn.close()

if errors:
    print("Remote historical-events import verification failed:")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)
PY
}

upload_data_and_import() {
    local staging_dir archive_path remote_archive
    local remote_payload_dir manifest_path remote_manifest_log_path
    local match_files

    staging_dir="$(mktemp -d)"
    archive_path="$(mktemp -p /tmp ittf-historical-events.XXXXXX.tar.gz)"
    remote_archive="${REMOTE_TMP_DIR}/${REMOTE_BUNDLE_NAME}"
    remote_payload_dir="${REMOTE_TMP_DIR}/payload-${RUN_ID}-$$"
    remote_manifest_log_path="${REMOTE_IMPORT_LOG_DIR}/historical-events-${RUN_ID}.manifest.txt"
    trap 'rm -rf "$staging_dir" "$archive_path"' RETURN

    echo "==> Collecting and staging historical-events payload"
    mapfile -t match_files < <(collect_local_payload "$staging_dir")
    echo "    resolved ${#match_files[@]} match file(s):"
    for name in "${match_files[@]}"; do
        echo "      - ${name}"
    done

    manifest_path="${staging_dir}/import_manifest.txt"
    write_payload_manifest "$manifest_path" "$remote_payload_dir" "$remote_manifest_log_path" "${match_files[@]}"
    echo "==> Payload manifest"
    cat "$manifest_path"

    tar -czf "$archive_path" -C "$staging_dir" .

    echo "==> Uploading data bundle to ${REMOTE_HOST}:${remote_archive}"
    ssh "$REMOTE_HOST" "mkdir -p '${REMOTE_TMP_DIR}' '${REMOTE_DATA_DIR}'"
    scp "$archive_path" "${REMOTE_HOST}:${remote_archive}"

    echo "==> Extracting data bundle under ${remote_payload_dir}"
    ssh "$REMOTE_HOST" "rm -rf '${remote_payload_dir}' && mkdir -p '${remote_payload_dir}' && tar -xzf '${remote_archive}' -C '${remote_payload_dir}' && rm -f '${remote_archive}'"

    run_remote_preflight "$remote_payload_dir"
    publish_remote_payload_data "$remote_payload_dir"
    backup_remote_database
    run_remote_import "$remote_payload_dir"
    verify_remote_import

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
