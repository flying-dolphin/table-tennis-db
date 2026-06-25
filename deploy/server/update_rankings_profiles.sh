#!/usr/bin/env bash
#
# Publish ranking/profile import code, upload the latest ranking JSON plus
# translated profile JSON files, then import them on the remote server.
#
# Defaults target:
#   flyingfox@xiaodoubao.site:doubao_tt/data
#
# Usage:
#   deploy/server/update_rankings_profiles.sh
#   deploy/server/update_rankings_profiles.sh --publish-only
#   deploy/server/update_rankings_profiles.sh --skip-publish
#
# Optional env:
#   MIN_RANKING_ENTRIES=900

set -euo pipefail

REMOTE_HOST=${REMOTE_HOST:-flyingfox@xiaodoubao.site}
REMOTE_PROJECT_DIR=${REMOTE_PROJECT_DIR:-doubao_tt}
REMOTE_DATA_DIR=${REMOTE_DATA_DIR:-${REMOTE_PROJECT_DIR}/data}
REMOTE_PYTHON=${REMOTE_PYTHON:-python3}
REMOTE_TMP_DIR=${REMOTE_TMP_DIR:-/tmp/ittf-ranking-profile-update}
REMOTE_BUNDLE_NAME=${REMOTE_BUNDLE_NAME:-ranking_profile_payload.tar.gz}
MIN_RANKING_ENTRIES=${MIN_RANKING_ENTRIES:-900}

PUBLISH_ONLY=0
SKIP_PUBLISH=0

usage() {
    sed -n '2,16p' "$0"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
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

if [ "$PUBLISH_ONLY" -eq 1 ] && [ "$SKIP_PUBLISH" -eq 1 ]; then
    echo "ERROR: --publish-only and --skip-publish cannot be used together" >&2
    exit 2
fi

cd "$(dirname "$0")/../.."
ROOT_DIR="$(pwd)"

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

latest_ranking_file() {
    find data/rankings/cn -maxdepth 1 -type f -name '*.json' -printf '%T@ %p\n' \
        | sort -nr \
        | awk 'NR == 1 {print $2}'
}

copy_file_to_staging() {
    local src="$1"
    local dest="$2"
    require_file "$src"
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
}

publish_runtime() {
    local staging_dir archive_path remote_archive
    staging_dir="$(mktemp -d)"
    archive_path="$(mktemp -p /tmp ittf-runtime.XXXXXX.tar.gz)"
    remote_archive="${REMOTE_TMP_DIR}/runtime_bundle.tar.gz"
    trap 'rm -rf "$staging_dir" "$archive_path"' RETURN

    echo "==> Staging runtime/import files"
    copy_file_to_staging "deploy/server/event_refresh.sh" "${staging_dir}/deploy/server/event_refresh.sh"
    copy_file_to_staging "deploy/server/install_current_event_crontab.sh" "${staging_dir}/deploy/server/install_current_event_crontab.sh"
    copy_file_to_staging "deploy/server/runtime/data/stage_round_mapping.json" "${staging_dir}/deploy/server/runtime/data/stage_round_mapping.json"

    copy_file_to_staging "scripts/db/config.py" "${staging_dir}/scripts/db/config.py"
    copy_file_to_staging "scripts/db/import_players.py" "${staging_dir}/scripts/db/import_players.py"
    copy_file_to_staging "scripts/db/import_rankings.py" "${staging_dir}/scripts/db/import_rankings.py"
    copy_file_to_staging "scripts/lib/career_best.py" "${staging_dir}/scripts/lib/career_best.py"
    copy_file_to_staging "data/player_country_history.json" "${staging_dir}/data/player_country_history.json"

    tar -czf "$archive_path" -C "$staging_dir" .

    echo "==> Uploading runtime/import bundle to ${REMOTE_HOST}:${remote_archive}"
    ssh "$REMOTE_HOST" "mkdir -p '${REMOTE_TMP_DIR}' '${REMOTE_PROJECT_DIR}'"
    scp "$archive_path" "${REMOTE_HOST}:${remote_archive}"

    echo "==> Extracting runtime/import bundle under ${REMOTE_PROJECT_DIR}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && tar -xzf '${remote_archive}' && rm -f '${remote_archive}' && chmod +x deploy/server/event_refresh.sh deploy/server/install_current_event_crontab.sh"
}

backup_remote_database() {
    echo "==> Backing up remote database before imports"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && mkdir -p data/db/backups && backup_path=\"data/db/backups/ittf-before-ranking-profile-\$(date +%Y%m%d_%H%M%S).db\" && ${REMOTE_PYTHON} -c \"import sqlite3, sys; src = sqlite3.connect('data/db/ittf.db'); dst = sqlite3.connect(sys.argv[1]); src.backup(dst); dst.close(); src.close()\" \"\$backup_path\" && ls -lh \"\$backup_path\""
}

run_remote_preflight() {
    local ranking_basename="$1"

    echo "==> Running remote ranking dry-run"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && ${REMOTE_PYTHON} scripts/db/import_rankings.py --dry --file data/rankings/cn/${ranking_basename}"

    echo "==> Running remote preflight checks"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && RANKING_FILE='data/rankings/cn/${ranking_basename}' MIN_RANKING_ENTRIES='${MIN_RANKING_ENTRIES}' ${REMOTE_PYTHON} -" <<'PY'
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ranking_path = Path(os.environ["RANKING_FILE"])
min_entries = int(os.environ["MIN_RANKING_ENTRIES"])
db_path = Path("data/db/ittf.db")
profile_dir = Path("data/player_profiles/cn")

errors = []
if not ranking_path.exists():
    errors.append(f"ranking_file_missing={ranking_path}")
if not db_path.exists():
    errors.append(f"db_missing={db_path}")
if not profile_dir.exists():
    errors.append(f"profile_dir_missing={profile_dir}")

payload = {}
rankings = []
if ranking_path.exists():
    try:
        payload = json.loads(ranking_path.read_text(encoding="utf-8"))
        rankings = payload.get("rankings") or []
    except Exception as exc:
        errors.append(f"ranking_json_invalid={exc}")

ranking_week = payload.get("ranking_week")
ranking_date = payload.get("ranking_date")
category = payload.get("category")
expected_entries = len(rankings)
missing_name_zh = [
    {"rank": row.get("rank"), "name": row.get("name")}
    for row in rankings
    if not row.get("name_zh")
]
player_ids = []
missing_json_player_ids = []
for row in rankings:
    raw_player_id = row.get("player_id")
    if raw_player_id in (None, ""):
        missing_json_player_ids.append({"rank": row.get("rank"), "name": row.get("name")})
        continue
    try:
        player_ids.append(int(raw_player_id))
    except (TypeError, ValueError):
        missing_json_player_ids.append({"rank": row.get("rank"), "name": row.get("name"), "player_id": raw_player_id})

duplicate_player_ids = sorted(player_id for player_id, count in Counter(player_ids).items() if count > 1)

existing_player_ids = set()
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    try:
        existing_player_ids = {int(row[0]) for row in conn.execute("SELECT player_id FROM players")}
    finally:
        conn.close()

profile_player_ids = set()
if profile_dir.exists():
    for path in profile_dir.glob("player_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        raw_player_id = data.get("player_id")
        try:
            profile_player_ids.add(int(raw_player_id))
        except (TypeError, ValueError):
            continue

covered_player_ids = existing_player_ids | profile_player_ids
missing_player_ids = sorted(set(player_ids) - covered_player_ids)

if expected_entries < min_entries:
    errors.append(f"expected_entries_below_min={expected_entries} min={min_entries}")
if not ranking_week:
    errors.append("ranking_week_missing")
if not ranking_date:
    errors.append("ranking_date_missing")
if not category:
    errors.append("category_missing")
if missing_name_zh:
    errors.append(f"missing_name_zh={len(missing_name_zh)}")
if missing_json_player_ids:
    errors.append(f"missing_json_player_ids={len(missing_json_player_ids)}")
if duplicate_player_ids:
    errors.append(f"duplicate_player_ids={len(duplicate_player_ids)}")
if missing_player_ids:
    errors.append(f"missing_player_ids={len(missing_player_ids)}")

print("Remote preflight summary:")
print(f"  ranking_file: {ranking_path}")
print(f"  category: {category}")
print(f"  ranking_week: {ranking_week}")
print(f"  ranking_date: {ranking_date}")
print(f"  expected_entries: {expected_entries}")
print(f"  min_entries: {min_entries}")
print(f"  db_players: {len(existing_player_ids)}")
print(f"  profile_files: {len(profile_player_ids)}")
print(f"  missing_name_zh: {len(missing_name_zh)}")
print(f"  missing_json_player_ids: {len(missing_json_player_ids)}")
print(f"  duplicate_player_ids: {len(duplicate_player_ids)}")
print(f"  missing_player_ids: {len(missing_player_ids)}")

if errors:
    print("Remote preflight failed:")
    for error in errors:
        print(f"  - {error}")
    if missing_name_zh:
        print("  missing_name_zh samples:", missing_name_zh[:10])
    if missing_json_player_ids:
        print("  missing_json_player_ids samples:", missing_json_player_ids[:10])
    if duplicate_player_ids:
        print("  duplicate_player_ids samples:", duplicate_player_ids[:10])
    if missing_player_ids:
        print("  missing_player_ids samples:", missing_player_ids[:10])
    sys.exit(1)
PY
}

verify_remote_import() {
    local ranking_basename="$1"

    echo "==> Verifying remote database after imports"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && RANKING_FILE='data/rankings/cn/${ranking_basename}' MIN_RANKING_ENTRIES='${MIN_RANKING_ENTRIES}' ${REMOTE_PYTHON} -" <<'PY'
import json
import os
import sqlite3
import sys
from pathlib import Path

ranking_path = Path(os.environ["RANKING_FILE"])
min_entries = int(os.environ["MIN_RANKING_ENTRIES"])
payload = json.loads(ranking_path.read_text(encoding="utf-8"))
rankings = payload.get("rankings") or []
category = payload.get("category")
ranking_week = payload.get("ranking_week")
ranking_date = payload.get("ranking_date")
expected_entries = len(rankings)
expected_player_ids = {
    int(row["player_id"])
    for row in rankings
    if row.get("player_id") not in (None, "")
}

conn = sqlite3.connect("data/db/ittf.db")
try:
    row = conn.execute(
        """
        SELECT snapshot_id, ranking_date
        FROM ranking_snapshots
        WHERE category = ? AND ranking_week = ?
        ORDER BY snapshot_id DESC
        LIMIT 1
        """,
        (category, ranking_week),
    ).fetchone()
    if row is None:
        print(f"Remote verify failed: ranking snapshot missing category={category} week={ranking_week}")
        sys.exit(1)

    snapshot_id, db_ranking_date = row
    entry_count = conn.execute(
        "SELECT COUNT(*) FROM ranking_entries WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchone()[0]
    distinct_entry_count = conn.execute(
        "SELECT COUNT(DISTINCT player_id) FROM ranking_entries WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchone()[0]
    breakdown_count = conn.execute(
        "SELECT COUNT(*) FROM points_breakdown WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchone()[0]
    missing_players = sorted(
        player_id
        for player_id in expected_player_ids
        if conn.execute("SELECT 1 FROM players WHERE player_id = ?", (player_id,)).fetchone() is None
    )
finally:
    conn.close()

errors = []
if expected_entries < min_entries:
    errors.append(f"expected_entries_below_min={expected_entries} min={min_entries}")
if entry_count != expected_entries:
    errors.append(f"ranking_entries_mismatch={entry_count} expected={expected_entries}")
if distinct_entry_count != len(expected_player_ids):
    errors.append(f"distinct_ranking_entries_mismatch={distinct_entry_count} expected={len(expected_player_ids)}")
if ranking_date and db_ranking_date != ranking_date:
    errors.append(f"ranking_date_mismatch={db_ranking_date} expected={ranking_date}")
if missing_players:
    errors.append(f"missing_player_ids={len(missing_players)}")

print("Remote import verification summary:")
print(f"  category: {category}")
print(f"  ranking_week: {ranking_week}")
print(f"  ranking_date: {ranking_date}")
print(f"  snapshot_id: {snapshot_id}")
print(f"  expected_entries: {expected_entries}")
print(f"  ranking_entries: {entry_count}")
print(f"  distinct_ranking_entries: {distinct_entry_count}")
print(f"  points_breakdown: {breakdown_count}")
print(f"  missing_player_ids: {len(missing_players)}")

if errors:
    print("Remote import verification failed:")
    for error in errors:
        print(f"  - {error}")
    if missing_players:
        print("  missing_player_ids samples:", missing_players[:10])
    sys.exit(1)
PY
}

upload_data_and_import() {
    local ranking_file profiles_count staging_dir archive_path remote_archive ranking_basename
    ranking_file="$(latest_ranking_file)"
    if [ -z "$ranking_file" ]; then
        echo "ERROR: no ranking JSON found in data/rankings/cn" >&2
        exit 1
    fi
    require_dir "data/player_profiles/cn"
    require_file "data/player_country_history.json"

    profiles_count="$(find data/player_profiles/cn -maxdepth 1 -type f -name 'player_*.json' | wc -l | tr -d ' ')"
    if [ "$profiles_count" = "0" ]; then
        echo "ERROR: no profile JSON files found in data/player_profiles/cn" >&2
        exit 1
    fi

    ranking_basename="$(basename "$ranking_file")"
    staging_dir="$(mktemp -d)"
    archive_path="$(mktemp -p /tmp ittf-ranking-profile.XXXXXX.tar.gz)"
    remote_archive="${REMOTE_TMP_DIR}/${REMOTE_BUNDLE_NAME}"
    trap 'rm -rf "$staging_dir" "$archive_path"' RETURN

    echo "==> Packaging ranking/profile data"
    echo "    ranking:  ${ranking_file}"
    echo "    profiles: ${profiles_count} files"

    mkdir -p "${staging_dir}/rankings/cn" "${staging_dir}/player_profiles"
    cp "$ranking_file" "${staging_dir}/rankings/cn/${ranking_basename}"
    cp -R data/player_profiles/cn "${staging_dir}/player_profiles/"
    cp data/player_country_history.json "${staging_dir}/player_country_history.json"
    tar -czf "$archive_path" -C "$staging_dir" .

    echo "==> Uploading data bundle to ${REMOTE_HOST}:${remote_archive}"
    ssh "$REMOTE_HOST" "mkdir -p '${REMOTE_TMP_DIR}' '${REMOTE_DATA_DIR}'"
    scp "$archive_path" "${REMOTE_HOST}:${remote_archive}"

    echo "==> Extracting data bundle under ${REMOTE_DATA_DIR}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_DATA_DIR}' && tar -xzf '${remote_archive}' && rm -f '${remote_archive}'"

    run_remote_preflight "$ranking_basename"

    backup_remote_database

    echo "==> Running remote imports"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && ${REMOTE_PYTHON} scripts/db/import_players.py && ${REMOTE_PYTHON} scripts/db/import_rankings.py --file data/rankings/cn/${ranking_basename}"

    verify_remote_import "$ranking_basename"
}

if [ "$SKIP_PUBLISH" -eq 0 ]; then
    publish_runtime
fi

if [ "$PUBLISH_ONLY" -eq 0 ]; then
    upload_data_and_import
fi

echo "==> Done"
