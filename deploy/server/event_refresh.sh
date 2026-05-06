#!/usr/bin/env bash
#
# 服务器 A 上的赛事自动刷新最小部署入口。
# 依赖 deploy/server/runtime/ 目录，不依赖整仓库。
#
# 运行前提：
#   - 已上传 deploy/server/event_refresh.sh
#   - 已上传 deploy/server/runtime/
#   - 已准备好 pyenv 环境（推荐）或传统 venv（兜底）
#   - sqlite3 命令可用
#   - 若使用默认 sources（含 completed/live/standings），还需：
#       patchright/playwright + chromium（例如 python -m patchright install chromium）
#
# 外部数据目录结构（默认 /opt/ittf-data）：
#   /opt/ittf-data/db/ittf.db
#   /opt/ittf-data/live_event_data/
#   /opt/ittf-data/event_schedule/   (可选)

set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME_DIR="${SCRIPT_DIR}/runtime"
ITTF_DATA_DIR=${ITTF_DATA_DIR:-/opt/ittf-data}
DB_PATH=${DB_PATH:-${ITTF_DATA_DIR}/db/ittf.db}
PYENV_ROOT=${PYENV_ROOT:-${HOME}/.pyenv}
PYENV_ENV_NAME=${PYENV_ENV_NAME:-}
VENV_PATH=${VENV_PATH:-/opt/ittf-venv}
BACKUP_DIR=${BACKUP_DIR:-${ITTF_DATA_DIR}/db/backups}
RETENTION_DAYS=${RETENTION_DAYS:-30}
EVENT_SCHEDULE_DIR=${EVENT_SCHEDULE_DIR:-${ITTF_DATA_DIR}/event_schedule}
LIVE_EVENT_DATA_DIR=${LIVE_EVENT_DATA_DIR:-${ITTF_DATA_DIR}/live_event_data}

timestamp() {
    date '+%F %T'
}

log() {
    echo "==> [$(timestamp)] $*"
}

require_file() {
    local path="$1"
    if [[ ! -e "${path}" ]]; then
        echo "[ERROR] Required path not found: ${path}" >&2
        exit 1
    fi
}

require_command() {
    local cmd="$1"
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        echo "[ERROR] Command not found: ${cmd}" >&2
        exit 1
    fi
}

require_command sqlite3
require_file "${RUNTIME_DIR}"
require_file "${RUNTIME_DIR}/python/backfill_events_calendar_event_id.py"
require_file "${RUNTIME_DIR}/python/scrape_current_event.py"
require_file "${RUNTIME_DIR}/python/import_current_event.py"
require_file "${RUNTIME_DIR}/python/import_current_event_session_schedule.py"
require_file "${DB_PATH}"

mkdir -p "${BACKUP_DIR}"
mkdir -p "${LIVE_EVENT_DATA_DIR}"

cd "${SCRIPT_DIR}"
export DB_PATH

if [[ -n "${PYENV_ENV_NAME}" ]]; then
    require_file "${PYENV_ROOT}/bin/pyenv"
    export PYENV_ROOT
    export PATH="${PYENV_ROOT}/bin:${PATH}"
    # shellcheck disable=SC1091
    eval "$("${PYENV_ROOT}/bin/pyenv" init -)"
    # shellcheck disable=SC1091
    eval "$("${PYENV_ROOT}/bin/pyenv" virtualenv-init -)"
    pyenv activate "${PYENV_ENV_NAME}"
    PYTHON_BIN="$(pyenv which python)"
    log "使用 pyenv 环境 ${PYENV_ENV_NAME}: ${PYTHON_BIN}"
else
    require_file "${VENV_PATH}/bin/activate"
    require_file "${VENV_PATH}/bin/python"
    # shellcheck disable=SC1091
    source "${VENV_PATH}/bin/activate"
    PYTHON_BIN="${VENV_PATH}/bin/python"
    log "使用 venv 解释器: ${PYTHON_BIN}"
fi

BACKUP_DATE="$(date +%Y%m%d)"
BACKUP_FILE="${BACKUP_DIR}/ittf-pre-event-refresh-${BACKUP_DATE}.db"

if [[ -f "${BACKUP_FILE}" ]]; then
    log "跳过 SQLite 备份（今日已存在 ${BACKUP_FILE}）"
else
    log "生成刷新前 SQLite 备份"
    sqlite3 "${DB_PATH}" ".backup ${BACKUP_FILE}"
fi
find "${BACKUP_DIR}" -name 'ittf-pre-event-refresh-*.db' -mtime +"${RETENTION_DAYS}" -delete

log "回填 events_calendar.event_id 并补齐 events"
"${PYTHON_BIN}" "${RUNTIME_DIR}/python/backfill_events_calendar_event_id.py" --db "${DB_PATH}"

if [[ -n "${EVENT_ID:-}" ]]; then
    EVENT_IDS="${EVENT_ID}"
else
    EVENT_IDS="$(sqlite3 -noheader -batch "${DB_PATH}" \
        "SELECT event_id FROM events WHERE lifecycle_status IN ('draw_published', 'in_progress') ORDER BY event_id")"
fi

if [[ -z "${EVENT_IDS}" ]]; then
    log "跳过当前赛事刷新（未找到 draw_published / in_progress 赛事）"
    log "完成"
    exit 0
fi

while IFS= read -r CURRENT_EVENT_ID; do
    [[ -z "${CURRENT_EVENT_ID}" ]] && continue
    log "刷新当前赛事 ${CURRENT_EVENT_ID}"
    "${PYTHON_BIN}" "${RUNTIME_DIR}/python/scrape_current_event.py" \
        --event-id "${CURRENT_EVENT_ID}" \
        --live-event-data-root "${LIVE_EVENT_DATA_DIR}" \
        --headless

    "${PYTHON_BIN}" "${RUNTIME_DIR}/python/import_current_event.py" \
        --event-id "${CURRENT_EVENT_ID}" \
        --db-path "${DB_PATH}" \
        --live-event-data-root "${LIVE_EVENT_DATA_DIR}" \
        --event-schedule-dir "${EVENT_SCHEDULE_DIR}"
done <<< "${EVENT_IDS}"

log "完成"
