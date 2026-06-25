#!/usr/bin/env bash
#
# Publish current-event refresh runtime files to the remote ops directory.
#
# Defaults target:
#   flyingfox@xiaodoubao.site:/opt/ittf-ops
#
# Usage:
#   deploy/server/update_event_runtime.sh
#   deploy/server/update_event_runtime.sh --skip-publish --install-crontab 3216
#   deploy/server/update_event_runtime.sh --install-crontab 3216
#
# Optional env:
#   REMOTE_HOST=flyingfox@xiaodoubao.site
#   REMOTE_OPS_DIR=/opt/ittf-ops
#   REMOTE_TMP_DIR=/tmp/ittf-event-runtime-update
#   REMOTE_PYENV_ENV_NAME=venv
#   REMOTE_ITTF_DATA_DIR=/opt/ittf-data
#   REMOTE_LOG_DIR=/opt/ittf-data/logs
#   REMOTE_VENV_PATH=/opt/ittf-venv

set -euo pipefail

REMOTE_HOST=${REMOTE_HOST:-flyingfox@xiaodoubao.site}
REMOTE_OPS_DIR=${REMOTE_OPS_DIR:-/opt/ittf-ops}
REMOTE_TMP_DIR=${REMOTE_TMP_DIR:-/tmp/ittf-event-runtime-update}
REMOTE_PYENV_ENV_NAME=${REMOTE_PYENV_ENV_NAME:-${PYENV_ENV_NAME:-}}
REMOTE_ITTF_DATA_DIR=${REMOTE_ITTF_DATA_DIR:-${ITTF_DATA_DIR:-/opt/ittf-data}}
REMOTE_LOG_DIR=${REMOTE_LOG_DIR:-}
REMOTE_VENV_PATH=${REMOTE_VENV_PATH:-}

SKIP_PUBLISH=0
INSTALL_CRONTAB_EVENT_ID=${INSTALL_CRONTAB_EVENT_ID:-}

usage() {
    sed -n '2,20p' "$0"
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

copy_runtime_python_to_staging() {
    local staging_dir="$1"
    require_dir "scripts/runtime"
    mkdir -p "${staging_dir}/runtime/python"
    tar \
        --exclude='__pycache__' \
        --exclude='test_*.py' \
        -cf - \
        -C scripts/runtime . \
        | tar -xf - -C "${staging_dir}/runtime/python"
}

publish_event_runtime() {
    local staging_dir archive_path remote_archive
    staging_dir="$(mktemp -d)"
    archive_path="$(mktemp -p /tmp ittf-event-runtime.XXXXXX.tar.gz)"
    remote_archive="${REMOTE_TMP_DIR}/event_runtime_bundle.tar.gz"
    trap 'rm -rf "$staging_dir" "$archive_path"' RETURN

    echo "==> Staging current-event runtime files"
    copy_file_to_staging "deploy/server/event_refresh.sh" "${staging_dir}/event_refresh.sh"
    copy_file_to_staging "deploy/server/install_current_event_crontab.sh" "${staging_dir}/install_current_event_crontab.sh"
    copy_file_to_staging "deploy/server/runtime/data/stage_round_mapping.json" "${staging_dir}/runtime/data/stage_round_mapping.json"
    copy_runtime_python_to_staging "$staging_dir"

    tar -czf "$archive_path" -C "$staging_dir" .

    echo "==> Uploading current-event runtime to ${REMOTE_HOST}:${remote_archive}"
    ssh "$REMOTE_HOST" "mkdir -p '${REMOTE_TMP_DIR}' '${REMOTE_OPS_DIR}'"
    scp "$archive_path" "${REMOTE_HOST}:${remote_archive}"

    echo "==> Extracting current-event runtime under ${REMOTE_OPS_DIR}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_OPS_DIR}' && tar -xzf '${remote_archive}' && rm -f '${remote_archive}' && chmod +x event_refresh.sh install_current_event_crontab.sh"
}

install_remote_crontab() {
    local remote_env
    remote_env="ITTF_DATA_DIR='${REMOTE_ITTF_DATA_DIR}'"
    if [ -n "$REMOTE_PYENV_ENV_NAME" ]; then
        remote_env="${remote_env} PYENV_ENV_NAME='${REMOTE_PYENV_ENV_NAME}'"
    fi
    if [ -n "$REMOTE_LOG_DIR" ]; then
        remote_env="${remote_env} LOG_DIR='${REMOTE_LOG_DIR}'"
    fi
    if [ -n "$REMOTE_VENV_PATH" ]; then
        remote_env="${remote_env} VENV_PATH='${REMOTE_VENV_PATH}'"
    fi

    echo "==> Installing current-event crontab for event ${INSTALL_CRONTAB_EVENT_ID}"
    ssh "$REMOTE_HOST" "cd '${REMOTE_OPS_DIR}' && ${remote_env} ./install_current_event_crontab.sh '${INSTALL_CRONTAB_EVENT_ID}'"
}

if [ "$SKIP_PUBLISH" -eq 0 ]; then
    publish_event_runtime
fi

if [ -n "$INSTALL_CRONTAB_EVENT_ID" ]; then
    install_remote_crontab
fi

echo "==> Done"
