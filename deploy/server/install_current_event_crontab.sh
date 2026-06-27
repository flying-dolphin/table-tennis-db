#!/usr/bin/env bash
#
# Replace the managed high-frequency current-event cron block.
#
# 布局：与 event_refresh.sh 同根（doubao_tt/），生成的 cron 命令直接 cd 到
# PROJECT_ROOT 后用相对路径调用 scripts/runtime/*.py 和 scripts/db/promote_current_event.py，
# 因此 promote 自动任务也能正确解析（依赖随 update_event_runtime.sh 一起发布）。
#
# Usage:
#   PYENV_ENV_NAME=venv doubao_tt/deploy/server/install_current_event_crontab.sh 3216

set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=${PROJECT_ROOT:-$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)}
RUNTIME_PY_DIR="${PROJECT_ROOT}/scripts/runtime"
ITTF_DATA_DIR=${ITTF_DATA_DIR:-${PROJECT_ROOT}/data}
DB_PATH=${DB_PATH:-${ITTF_DATA_DIR}/db/ittf.db}
LIVE_EVENT_DATA_DIR=${LIVE_EVENT_DATA_DIR:-${ITTF_DATA_DIR}/live_event_data}
LOG_DIR=${LOG_DIR:-${ITTF_DATA_DIR}/logs}
PYENV_ROOT=${PYENV_ROOT:-${HOME}/.pyenv}
PYENV_ENV_NAME=${PYENV_ENV_NAME:-}
PYTHON_BIN=${PYTHON_BIN:-}
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

require_file "${RUNTIME_PY_DIR}/generate_current_event_crontab.py"
require_file "${RUNTIME_PY_DIR}/scrape_current_event.py"
require_file "${RUNTIME_PY_DIR}/import_current_event.py"
# promote 自动任务依赖以下文件，缺失则装出来的 promote cron 会失败。
require_file "${PROJECT_ROOT}/scripts/db/promote_current_event.py"
require_file "${PROJECT_ROOT}/scripts/db/import_event_draw_matches.py"
require_file "${PROJECT_ROOT}/scripts/db/import_sub_events.py"
require_file "${DB_PATH}"

if [[ -n "${PYENV_ENV_NAME}" ]]; then
    require_file "${PYENV_ROOT}/bin/pyenv"
    export PYENV_ROOT
    export PATH="${PYENV_ROOT}/bin:${PATH}"
    eval "$("${PYENV_ROOT}/bin/pyenv" init -)"
    eval "$("${PYENV_ROOT}/bin/pyenv" virtualenv-init -)"
    pyenv activate "${PYENV_ENV_NAME}"
    PYTHON_BIN="$(pyenv which python)"
elif [[ -n "${PYTHON_BIN}" ]]; then
    require_file "${PYTHON_BIN}"
else
    echo "[ERROR] 需设置 PYENV_ENV_NAME（推荐）或 PYTHON_BIN 指向装有 playwright/patchright 的解释器" >&2
    exit 1
fi

GENERATED_FILE="$(mktemp)"
CURRENT_FILE="$(mktemp)"
NEXT_FILE="$(mktemp)"
trap 'rm -f "${GENERATED_FILE}" "${CURRENT_FILE}" "${NEXT_FILE}"' EXIT

# --project-root + --runtime-python-dir 一起让生成的命令形如：
#   cd <PROJECT_ROOT> && <python> scripts/runtime/scrape_current_event.py ...
#   cd <PROJECT_ROOT> && <python> scripts/db/promote_current_event.py ...
"${PYTHON_BIN}" "${RUNTIME_PY_DIR}/generate_current_event_crontab.py" \
    --event-id "${EVENT_ID}" \
    --db-path "${DB_PATH}" \
    --project-root "${PROJECT_ROOT}" \
    --runtime-python-dir "scripts/runtime" \
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
