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

set -euo pipefail

REMOTE_HOST=${REMOTE_HOST:-flyingfox@xiaodoubao.site}
REMOTE_PROJECT_DIR=${REMOTE_PROJECT_DIR:-doubao_tt}
REMOTE_DATA_DIR=${REMOTE_DATA_DIR:-${REMOTE_PROJECT_DIR}/data}
REMOTE_PYTHON=${REMOTE_PYTHON:-python3}
REMOTE_TMP_DIR=${REMOTE_TMP_DIR:-/tmp/ittf-ranking-profile-update}
REMOTE_BUNDLE_NAME=${REMOTE_BUNDLE_NAME:-ranking_profile_payload.tar.gz}

PUBLISH_ONLY=0
SKIP_PUBLISH=0

usage() {
    sed -n '2,13p' "$0"
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

    backup_remote_database

    echo "==> Running remote imports"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && ${REMOTE_PYTHON} scripts/db/import_players.py && ${REMOTE_PYTHON} scripts/db/import_rankings.py --file data/rankings/cn/${ranking_basename}"
}

if [ "$SKIP_PUBLISH" -eq 0 ]; then
    publish_runtime
fi

if [ "$PUBLISH_ONLY" -eq 0 ]; then
    upload_data_and_import
fi

echo "==> Done"
