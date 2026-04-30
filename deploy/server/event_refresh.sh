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
#
# 外部数据目录结构（默认 /opt/ittf-data）：
#   /opt/ittf-data/db/ittf.db
#   /opt/ittf-data/wtt_raw/
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
RAW_ROOT=${RAW_ROOT:-${ITTF_DATA_DIR}/wtt_raw}

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
require_file "${RUNTIME_DIR}/python/refresh_event_results_daily.py"
require_file "${RUNTIME_DIR}/python/backfill_events_calendar_event_id.py"
require_file "${RUNTIME_DIR}/python/import_session_schedule.py"
require_file "${RUNTIME_DIR}/data/stage_round_mapping.json"
require_file "${DB_PATH}"

mkdir -p "${BACKUP_DIR}"
mkdir -p "${RAW_ROOT}"

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

BACKUP_FILE="${BACKUP_DIR}/ittf-pre-event-refresh-$(date +%Y%m%d_%H%M%S).db"

log "生成刷新前 SQLite 备份"
sqlite3 "${DB_PATH}" ".backup ${BACKUP_FILE}"
find "${BACKUP_DIR}" -name 'ittf-pre-event-refresh-*.db' -mtime +"${RETENTION_DAYS}" -delete

log "回填 events_calendar.event_id 并补齐 events"
"${PYTHON_BIN}" "${RUNTIME_DIR}/python/backfill_events_calendar_event_id.py" --db "${DB_PATH}"

if [[ -d "${EVENT_SCHEDULE_DIR}" ]] && compgen -G "${EVENT_SCHEDULE_DIR}/*.json" > /dev/null; then
    log "导入 data/event_schedule/*.json"
    "${PYTHON_BIN}" "${RUNTIME_DIR}/python/import_session_schedule.py" --db "${DB_PATH}" --dir "${EVENT_SCHEDULE_DIR}"
else
    log "跳过 event_schedule 导入（未发现 ${EVENT_SCHEDULE_DIR}/*.json）"
fi

log "刷新进行中 / 已发布签表赛事"
"${PYTHON_BIN}" "${RUNTIME_DIR}/python/refresh_event_results_daily.py" --db "${DB_PATH}" --raw-root "${RAW_ROOT}"

log "完成"
