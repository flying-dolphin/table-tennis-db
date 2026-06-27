#!/usr/bin/env bash
#
# Publish current-event refresh runtime to the remote production tree, mirroring
# the repo layout under the same project root used by the rankings / calendar /
# historical deploy scripts.
#
# Defaults target:
#   flyingfox@xiaodoubao.site:doubao_tt
#
# What gets published (mirrored repo-relative paths under REMOTE_PROJECT_DIR):
#   scripts/runtime/**                     current-event scrape + import runtime
#   scripts/scrape_event_schedule.py       per-session schedule scraper
#   scripts/lib/{translator,dict_translator,event_translation}.py
#   scripts/data/translation_dict_v2.json  schedule translation dictionary
#   docs/rules/TRANSLATION_RULES.md        translator prompt rules
#   scripts/db/{config,_match_keys,_import_summary,
#               import_event_draw_matches,import_sub_events,
#               promote_current_event}.py  post-event promote + its deps
#   deploy/server/event_refresh.sh
#   deploy/server/install_current_event_crontab.sh
#
# NOT published (must already exist on the server):
#   - data/db/ittf.db (the DB the website reads)
#   - .env with MINIMAX_API_KEY (required by scrape_event_schedule.py)
#   - data/event_schedule/{event_id}.json (human session schedule; place manually)
#
# Usage:
#   deploy/server/update_event_runtime.sh
#   deploy/server/update_event_runtime.sh --install-crontab 3216
#   deploy/server/update_event_runtime.sh --skip-publish --install-crontab 3216
#
# Optional env:
#   REMOTE_HOST=flyingfox@xiaodoubao.site
#   REMOTE_PROJECT_DIR=doubao_tt
#   REMOTE_TMP_DIR=/tmp/ittf-event-runtime-update
#   REMOTE_PYENV_ENV_NAME=venv        # browser-capable python env for cron jobs
#   REMOTE_ITTF_DATA_DIR=doubao_tt/data
#   REMOTE_LOG_DIR=doubao_tt/data/logs
#   REMOTE_PYTHON_BIN=/path/to/venv/bin/python  # explicit interpreter when not using pyenv

set -euo pipefail

REMOTE_HOST=${REMOTE_HOST:-flyingfox@xiaodoubao.site}
REMOTE_PROJECT_DIR=${REMOTE_PROJECT_DIR:-doubao_tt}
REMOTE_TMP_DIR=${REMOTE_TMP_DIR:-/tmp/ittf-event-runtime-update}
REMOTE_PYENV_ENV_NAME=${REMOTE_PYENV_ENV_NAME:-${PYENV_ENV_NAME:-}}
REMOTE_ITTF_DATA_DIR=${REMOTE_ITTF_DATA_DIR:-${ITTF_DATA_DIR:-}}
REMOTE_LOG_DIR=${REMOTE_LOG_DIR:-}
REMOTE_PYTHON_BIN=${REMOTE_PYTHON_BIN:-}

SKIP_PUBLISH=0
INSTALL_CRONTAB_EVENT_ID=${INSTALL_CRONTAB_EVENT_ID:-}

usage() {
    sed -n '2,39p' "$0"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --skip-publish)
            SKIP_PUBLISH=1
            ;;
        --install-crontab|--event-id)
            if [ "$#" -lt 2 ]; then
                echo "ERROR: $1 requires an event_id value" >&2
                usage >&2
                exit 2
            fi
            INSTALL_CRONTAB_EVENT_ID="$2"
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
    shift
done

if [ -n "$INSTALL_CRONTAB_EVENT_ID" ] && ! [[ "$INSTALL_CRONTAB_EVENT_ID" =~ ^[0-9]+$ ]]; then
    echo "ERROR: event_id must be numeric: ${INSTALL_CRONTAB_EVENT_ID}" >&2
    exit 2
fi

cd "$(dirname "$0")/../.."

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

# Mirror scripts/runtime/** into the staging tree at the same repo-relative path,
# excluding tests and bytecode.
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

publish_event_runtime() {
    local staging_dir archive_path remote_archive
    staging_dir="$(mktemp -d)"
    archive_path="$(mktemp -p /tmp ittf-event-runtime.XXXXXX.tar.gz)"
    remote_archive="${REMOTE_TMP_DIR}/event_runtime_bundle.tar.gz"
    trap 'rm -rf "$staging_dir" "$archive_path"' RETURN

    echo "==> Staging current-event runtime files (mirrored under ${REMOTE_PROJECT_DIR})"
    # Runtime scrape/import.
    copy_runtime_python_to_staging "$staging_dir"
    # Deploy entry scripts.
    copy_file_to_staging "deploy/server/event_refresh.sh" "${staging_dir}/deploy/server/event_refresh.sh"
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
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && tar -xzf '${remote_archive}' && rm -f '${remote_archive}' && chmod +x deploy/server/event_refresh.sh deploy/server/install_current_event_crontab.sh"
}

install_remote_crontab() {
    local remote_env=""
    if [ -n "$REMOTE_ITTF_DATA_DIR" ]; then
        remote_env="ITTF_DATA_DIR='${REMOTE_ITTF_DATA_DIR}'"
    fi
    if [ -n "$REMOTE_PYENV_ENV_NAME" ]; then
        remote_env="${remote_env} PYENV_ENV_NAME='${REMOTE_PYENV_ENV_NAME}'"
    fi
    if [ -n "$REMOTE_LOG_DIR" ]; then
        remote_env="${remote_env} LOG_DIR='${REMOTE_LOG_DIR}'"
    fi
    if [ -n "$REMOTE_PYTHON_BIN" ]; then
        remote_env="${remote_env} PYTHON_BIN='${REMOTE_PYTHON_BIN}'"
    fi

    echo "==> Installing current-event crontab for event ${INSTALL_CRONTAB_EVENT_ID}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_PROJECT_DIR}' && ${remote_env} ./deploy/server/install_current_event_crontab.sh '${INSTALL_CRONTAB_EVENT_ID}'"
}

if [ "$SKIP_PUBLISH" -eq 0 ]; then
    publish_event_runtime
fi

if [ -n "$INSTALL_CRONTAB_EVENT_ID" ]; then
    install_remote_crontab
fi

echo "==> Done"
