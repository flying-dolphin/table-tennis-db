#!/usr/bin/env bash
#
# 服务器 A 上的赛事自动刷新最小部署入口。
#
# 布局：current-event 运行代码与 rankings/calendar/historical 发布脚本同根，
# 镜像仓库结构发布到 doubao_tt/ 下：
#   doubao_tt/deploy/server/event_refresh.sh                (本脚本)
#   doubao_tt/deploy/server/install_current_event_crontab.sh
#   doubao_tt/scripts/runtime/*.py                          (抓取/导入运行态)
#   doubao_tt/scripts/db/*.py                               (promote + 历史导入器)
#   doubao_tt/scripts/lib/*.py + scripts/data/translation_dict_v2.json  (赛程翻译)
#   doubao_tt/data/db/ittf.db                               (网站读取的库)
#   doubao_tt/data/live_event_data/                         (抓取产物)
#   doubao_tt/data/event_schedule/                          (人工 session 日程，可选)
#
# 运行前提：
#   - 已用 deploy/server/update_event_runtime.sh 发布上述代码
#   - 已准备好 pyenv 环境（设 PYENV_ENV_NAME，推荐）或用 PYTHON_BIN 显式指定解释器，
#     且该解释器装有 patchright/playwright + chromium（默认 sources 含 standings/live 需要无头浏览器）
#   - sqlite3 命令可用
#
# 路径默认从脚本位置推导（PROJECT_ROOT = 本脚本上两级目录），也可用环境变量覆盖。

set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=${PROJECT_ROOT:-$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)}
ITTF_DATA_DIR=${ITTF_DATA_DIR:-${PROJECT_ROOT}/data}
DB_PATH=${DB_PATH:-${ITTF_DATA_DIR}/db/ittf.db}
RUNTIME_PY_DIR="${PROJECT_ROOT}/scripts/runtime"
PYENV_ROOT=${PYENV_ROOT:-${HOME}/.pyenv}
PYENV_ENV_NAME=${PYENV_ENV_NAME:-}
PYTHON_BIN=${PYTHON_BIN:-}
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
require_file "${RUNTIME_PY_DIR}/backfill_events_calendar_event_id.py"
require_file "${RUNTIME_PY_DIR}/scrape_current_event.py"
require_file "${RUNTIME_PY_DIR}/import_current_event.py"
require_file "${RUNTIME_PY_DIR}/import_current_event_session_schedule.py"
require_file "${DB_PATH}"

mkdir -p "${BACKUP_DIR}"
mkdir -p "${LIVE_EVENT_DATA_DIR}"

cd "${PROJECT_ROOT}"
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
elif [[ -n "${PYTHON_BIN}" ]]; then
    require_file "${PYTHON_BIN}"
    log "使用指定解释器 PYTHON_BIN: ${PYTHON_BIN}"
else
    echo "[ERROR] 需设置 PYENV_ENV_NAME（推荐）或 PYTHON_BIN 指向装有 playwright/patchright 的解释器" >&2
    exit 1
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
"${PYTHON_BIN}" "${RUNTIME_PY_DIR}/backfill_events_calendar_event_id.py" --db "${DB_PATH}"

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
    "${PYTHON_BIN}" "${RUNTIME_PY_DIR}/scrape_current_event.py" \
        --event-id "${CURRENT_EVENT_ID}" \
        --live-event-data-root "${LIVE_EVENT_DATA_DIR}" \
        --headless

    "${PYTHON_BIN}" "${RUNTIME_PY_DIR}/import_current_event.py" \
        --event-id "${CURRENT_EVENT_ID}" \
        --db-path "${DB_PATH}" \
        --live-event-data-root "${LIVE_EVENT_DATA_DIR}" \
        --event-schedule-dir "${EVENT_SCHEDULE_DIR}"
done <<< "${EVENT_IDS}"

log "完成"
