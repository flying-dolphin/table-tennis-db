#!/usr/bin/env bash
#
# Replace the managed high-frequency current-event cron block.
#
# Usage:
#   PYENV_ENV_NAME=venv /opt/ittf-ops/install_current_event_crontab.sh 3216

set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME_DIR="${SCRIPT_DIR}/runtime"
ITTF_DATA_DIR=${ITTF_DATA_DIR:-/opt/ittf-data}
DB_PATH=${DB_PATH:-${ITTF_DATA_DIR}/db/ittf.db}
LIVE_EVENT_DATA_DIR=${LIVE_EVENT_DATA_DIR:-${ITTF_DATA_DIR}/live_event_data}
LOG_DIR=${LOG_DIR:-${ITTF_DATA_DIR}/logs}
PYENV_ROOT=${PYENV_ROOT:-${HOME}/.pyenv}
PYENV_ENV_NAME=${PYENV_ENV_NAME:-}
VENV_PATH=${VENV_PATH:-/opt/ittf-venv}
BLOCK_BEGIN="# ITTF current-event refresh begin"
BLOCK_END="# ITTF current-event refresh end"

usage() {
    echo "Usage: PYENV_ENV_NAME=venv $0 <event_id>" >&2
}

require_file() {
    local path="$1"
    if [[ ! -e "${path}" ]]; then
        echo "[ERROR] Required path not found: ${path}" >&2
        exit 1
    fi
}

if [[ $# -ne 1 ]]; then
    usage
    exit 2
fi

EVENT_ID="$1"
if ! [[ "${EVENT_ID}" =~ ^[0-9]+$ ]]; then
    echo "[ERROR] event_id must be numeric: ${EVENT_ID}" >&2
    exit 2
fi

require_file "${RUNTIME_DIR}/python/generate_current_event_crontab.py"
require_file "${RUNTIME_DIR}/python/scrape_current_event.py"
require_file "${RUNTIME_DIR}/python/import_current_event.py"
require_file "${DB_PATH}"

if [[ -n "${PYENV_ENV_NAME}" ]]; then
    require_file "${PYENV_ROOT}/bin/pyenv"
    export PYENV_ROOT
    export PATH="${PYENV_ROOT}/bin:${PATH}"
    eval "$("${PYENV_ROOT}/bin/pyenv" init -)"
    eval "$("${PYENV_ROOT}/bin/pyenv" virtualenv-init -)"
    pyenv activate "${PYENV_ENV_NAME}"
    PYTHON_BIN="$(pyenv which python)"
else
    require_file "${VENV_PATH}/bin/python"
    PYTHON_BIN="${VENV_PATH}/bin/python"
fi

GENERATED_FILE="$(mktemp)"
CURRENT_FILE="$(mktemp)"
NEXT_FILE="$(mktemp)"
trap 'rm -f "${GENERATED_FILE}" "${CURRENT_FILE}" "${NEXT_FILE}"' EXIT

"${PYTHON_BIN}" "${RUNTIME_DIR}/python/generate_current_event_crontab.py" \
    --event-id "${EVENT_ID}" \
    --db-path "${DB_PATH}" \
    --project-root "${SCRIPT_DIR}" \
    --runtime-python-dir "${RUNTIME_DIR}/python" \
    --python-bin "${PYTHON_BIN}" \
    --live-event-data-root "${LIVE_EVENT_DATA_DIR}" \
    --log-dir "${LOG_DIR}" \
    --headless > "${GENERATED_FILE}"

crontab -l 2>/dev/null | sed "/${BLOCK_BEGIN}/,/${BLOCK_END}/d" > "${CURRENT_FILE}" || true
cp "${CURRENT_FILE}" "${NEXT_FILE}"

if grep -Eq '^[0-9]+[[:space:]]+[0-9]+[[:space:]]+[0-9*]+[[:space:]]+[0-9*]+[[:space:]]+' "${GENERATED_FILE}"; then
    {
        echo "${BLOCK_BEGIN}"
        cat "${GENERATED_FILE}"
        echo "${BLOCK_END}"
    } >> "${NEXT_FILE}"
    echo "Installed managed current-event cron block for event ${EVENT_ID}."
else
    echo "No future current-event cron jobs generated for event ${EVENT_ID}; removed existing managed block."
fi

crontab "${NEXT_FILE}"
