#!/usr/bin/env bash
# WTT/ITTF 历史赛事导入编排器。
#
# 设计原则：批次的唯一真相来源是「赛事清单」，不是文件 mtime。
#   1. --event-file: 指定一个 events_list JSON，先导入它，再从 events[].event_id
#      派生出本批 event id 集合，然后重建这些 event 的 matches/draw/sub_events。
#   2. --event-id:   人工修复入口，直接重建给定 event id（假定 events 已入表）。
#
# 不再使用 --since（mtime 语义脆弱、易与 events 表不同步）。
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/data/event_matches/cn"
DB_PATH="$ROOT_DIR/data/db/ittf.db"
EVENT_FILE=""
EVENT_IDS=()
SKIP_SAME_NAME_PLAYER_MATCHES=0
SAME_NAME_FROM_DATE=""
SAME_NAME_HEADLESS=0
SAME_NAME_CDP_PORT=9223
SAME_NAME_FORCE=0
FAIL=0

usage() {
  cat <<'EOF'
Usage:
  # 推荐入口：由一个 events list 文件驱动整批导入
  scripts/run_import_wtt_events.sh --event-file data/events_list/cn/events_xxx.json

  # 修复入口：人工重建某几个赛事（假定 events 已在库中）
  scripts/run_import_wtt_events.sh --event-id 2860 2861

Options:
  --event-file PATH   Recommended. Import this events_list JSON, then derive the
                      batch event ids from its events[].event_id and rebuild their
                      matches / draw / sub_events.
  --event-id IDS...   Repair mode. Rebuild these event ids directly (events assumed
                      already imported).
  --source-dir PATH   Override data/event_matches/cn.
  --same-name-from-date YYYY-MM-DD
                      Override the auto from-date for same-name player-centric matches.
  --same-name-headless
                      Pass --headless when scraping same-name player-centric matches.
  --same-name-force   Re-scrape same-name player-centric matches even when evidence
                      already exists (use after fixing scraping logic).
  --same-name-cdp-port PORT
                      CDP port of an existing Chrome reused for same-name scraping
                      (default: 9223).
  --skip-same-name-player-matches
                      Do not scrape/translate missing same-name player-centric matches.
  -h, --help          Show this help.

This script imports already translated historical event and event-match JSON files.
Exactly one of --event-file / --event-id is required.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --event-file)
      EVENT_FILE="${2:-}"
      if [[ -z "$EVENT_FILE" ]]; then
        echo "[ERROR] --event-file requires a value" >&2
        exit 2
      fi
      shift 2
      ;;
    --event-id)
      shift
      while [[ $# -gt 0 && "$1" != --* ]]; do
        EVENT_IDS+=("$1")
        shift
      done
      ;;
    --source-dir)
      SOURCE_DIR="$2"
      shift 2
      ;;
    --same-name-from-date)
      SAME_NAME_FROM_DATE="${2:-}"
      if [[ -z "$SAME_NAME_FROM_DATE" ]]; then
        echo "[ERROR] --same-name-from-date requires a value" >&2
        exit 2
      fi
      shift 2
      ;;
    --same-name-headless)
      SAME_NAME_HEADLESS=1
      shift
      ;;
    --same-name-force)
      SAME_NAME_FORCE=1
      shift
      ;;
    --same-name-cdp-port)
      SAME_NAME_CDP_PORT="${2:-}"
      if [[ -z "$SAME_NAME_CDP_PORT" ]]; then
        echo "[ERROR] --same-name-cdp-port requires a value" >&2
        exit 2
      fi
      shift 2
      ;;
    --skip-same-name-player-matches)
      SKIP_SAME_NAME_PLAYER_MATCHES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# 入口互斥校验：恰好二选一。
if [[ -n "$EVENT_FILE" && ${#EVENT_IDS[@]} -gt 0 ]]; then
  echo "[ERROR] Use either --event-file or --event-id, not both" >&2
  exit 2
fi
if [[ -z "$EVENT_FILE" && ${#EVENT_IDS[@]} -eq 0 ]]; then
  echo "[ERROR] One of --event-file / --event-id is required" >&2
  usage >&2
  exit 2
fi
if [[ -n "$EVENT_FILE" && ! -f "$EVENT_FILE" ]]; then
  echo "[ERROR] events file not found: $EVENT_FILE" >&2
  exit 2
fi

cd "$ROOT_DIR"

# 统一使用项目 venv 的 Python：scrape 依赖 patchright，系统 Python 没有。
# prepare 通过 sys.executable 拉起 scraper，因此这里选对解释器即可贯穿整条链。
PYTHON="$ROOT_DIR/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python"
echo "[INFO] Python: $PYTHON"

RUN_ID="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="$ROOT_DIR/data/logs/wtt-event-import/$RUN_ID"
mkdir -p "$LOG_DIR/events" "$LOG_DIR/draw" "$LOG_DIR/sub_events" "$LOG_DIR/player_matches"
echo "[INFO] Run id: $RUN_ID"
echo "[INFO] Logs:   $LOG_DIR"

# 失败时也要产出汇总（manual-check 摘要正是为了暴露问题）。
finish() {
  "$PYTHON" scripts/db/summarize_wtt_import.py --run-dir "$LOG_DIR" || true
  exit "$FAIL"
}

# --- 0. 刷新同名球员名单（来自 players 表，与批次无关，但要在导入前最新）-------
if ! ( "$PYTHON" scripts/audit_same_name_players.py \
         --db-path "$DB_PATH" \
         --output "$ROOT_DIR/scripts/data/same_name_players.txt" \
         --country-history "$ROOT_DIR/data/player_country_history.json" \
         --update 2>&1 | tee "$LOG_DIR/audit_same_name_players.log" ); then
  echo "[ERROR] audit_same_name_players.py failed" >&2
  FAIL=1
  finish
fi

# --- 1. --event-file: 先导入 events，再派生 event id 集合 ---------------------
if [[ -n "$EVENT_FILE" ]]; then
  event_base="$(basename "$EVENT_FILE" .json)"
  if ! ( "$PYTHON" scripts/db/import_events.py \
           --input-file "$EVENT_FILE" \
           --summary-json "$LOG_DIR/import_events.json" 2>&1 \
         | tee "$LOG_DIR/import_events.log" ); then
    echo "[ERROR] import_events.py failed for $EVENT_FILE" >&2
    FAIL=1
    finish
  fi

  mapfile -t EVENT_IDS < <(
    "$PYTHON" - "$EVENT_FILE" <<'PY'
import json
import sys

data = json.loads(open(sys.argv[1], encoding="utf-8").read())
seen = set()
for event in data.get("events") or []:
    if not isinstance(event, dict):
        continue
    try:
        event_id = int(event.get("event_id"))
    except (TypeError, ValueError):
        continue
    if event_id not in seen:
        seen.add(event_id)
        print(event_id)
PY
  )
  echo "[INFO] Derived ${#EVENT_IDS[@]} event ids from $event_base"
fi

if [[ ${#EVENT_IDS[@]} -eq 0 ]]; then
  echo "[INFO] No event ids to import; nothing to do."
  finish
fi

# --- 2. 计算可导入 id：必须既在 events 表、又有对应 match 文件 -----------------
# import_matches.py 会对 --event-id 先删后插：若某 id 没有 match 文件，会删掉其
# 已有 matches 又无数据写回（丢数据）。因此缺文件的 id 一律排除并显式列出。
mapfile -t IMPORTABLE_IDS < <(
  "$PYTHON" - "$DB_PATH" "$SOURCE_DIR" "${EVENT_IDS[@]}" <<'PY'
import json
import re
import sqlite3
import sys
from pathlib import Path

db_path = sys.argv[1]
source_dir = Path(sys.argv[2])
target_ids = []
seen = set()
for value in sys.argv[3:]:
    eid = int(value)
    if eid not in seen:
        seen.add(eid)
        target_ids.append(eid)

in_db = {row[0] for row in sqlite3.connect(db_path).execute("SELECT event_id FROM events")}

with_file = set()
for path in source_dir.glob("*.json"):
    eid = None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("event_id")
        if raw not in (None, ""):
            eid = int(raw)
    except Exception:
        eid = None
    if eid is None:
        m = re.search(r"_(\d+)\.json$", path.name, re.IGNORECASE)
        if m:
            eid = int(m.group(1))
    if eid is not None:
        with_file.add(eid)

importable, no_event_row, no_match_file = [], [], []
for eid in target_ids:
    if eid not in in_db:
        no_event_row.append(eid)
    elif eid not in with_file:
        no_match_file.append(eid)
    else:
        importable.append(eid)

if no_event_row:
    print("[WARN] skipped (not in events table): "
          + " ".join(map(str, no_event_row)), file=sys.stderr)
if no_match_file:
    print("[WARN] skipped (no match file in source-dir, kept as-is, not deleted): "
          + " ".join(map(str, no_match_file)), file=sys.stderr)

for eid in importable:
    print(eid)
PY
)

if [[ ${#IMPORTABLE_IDS[@]} -eq 0 ]]; then
  echo "[WARN] No importable event ids (none have both an events row and a match file)." >&2
  finish
fi
echo "[INFO] Importable event ids (${#IMPORTABLE_IDS[@]}): ${IMPORTABLE_IDS[*]}"

# --- 3. event_id=2860 源数据特殊修复（仅当它在本批内）------------------------
for eid in "${IMPORTABLE_IDS[@]}"; do
  if [[ "$eid" == "2860" ]]; then
    echo "[INFO] event 2860 in batch; applying source fix first."
    if ! ( "$PYTHON" scripts/fix_special_event_2860_stage_round.py 2>&1 \
           | tee "$LOG_DIR/fix_special_event_2860.log" ); then
      echo "[ERROR] fix_special_event_2860_stage_round.py failed" >&2
      FAIL=1
      finish
    fi
    break
  fi
done

# --- 4. import_matches 前：准备同名球员 player-centric 证据 -------------------
if [[ "$SKIP_SAME_NAME_PLAYER_MATCHES" -eq 1 ]]; then
  echo "[INFO] Skipping same-name player-centric matches preparation."
else
  PREPARE_ARGS=(
    --source-dir "$SOURCE_DIR"
    --event-id "${IMPORTABLE_IDS[@]}"
    --same-name-players "$ROOT_DIR/scripts/data/same_name_players.txt"
    --matches-complete-dir "$ROOT_DIR/data/matches_complete"
    --cdp-port "$SAME_NAME_CDP_PORT"
    --summary-json "$LOG_DIR/player_matches/prepare_same_name_player_matches.json"
  )
  if [[ -n "$SAME_NAME_FROM_DATE" ]]; then
    PREPARE_ARGS+=(--from-date "$SAME_NAME_FROM_DATE")
  fi
  if [[ "$SAME_NAME_HEADLESS" -eq 1 ]]; then
    PREPARE_ARGS+=(--headless)
  fi
  if [[ "$SAME_NAME_FORCE" -eq 1 ]]; then
    PREPARE_ARGS+=(--force)
  fi
  if ! ( "$PYTHON" scripts/prepare_same_name_player_matches.py "${PREPARE_ARGS[@]}" 2>&1 \
         | tee "$LOG_DIR/player_matches/prepare_same_name_player_matches.log" ); then
    echo "[ERROR] prepare_same_name_player_matches.py failed" >&2
    FAIL=1
    finish
  fi
fi

# --- 5. 导入 matches（一次性，按 importable id 删后重建）---------------------
if ! ( "$PYTHON" scripts/db/import_matches.py \
         --source-dir "$SOURCE_DIR" \
         --event-id "${IMPORTABLE_IDS[@]}" \
         --summary-json "$LOG_DIR/import_matches.json" 2>&1 \
       | tee "$LOG_DIR/import_matches.log" ); then
  echo "[ERROR] import_matches.py failed" >&2
  FAIL=1
  finish
fi

# --- 6. 逐 event 重建 draw 与 sub_events（单个失败不中断整批）---------------
for eid in "${IMPORTABLE_IDS[@]}"; do
  if ! ( "$PYTHON" scripts/db/import_event_draw_matches.py --event-id "$eid" \
           --summary-json "$LOG_DIR/draw/$eid.json" 2>&1 \
         | tee "$LOG_DIR/draw/$eid.log" ); then
    echo "[ERROR] import_event_draw_matches.py failed for event $eid" >&2
    FAIL=1
  fi
  if ! ( "$PYTHON" scripts/db/import_sub_events.py --event-id "$eid" \
           --summary-json "$LOG_DIR/sub_events/$eid.json" 2>&1 \
         | tee "$LOG_DIR/sub_events/$eid.log" ); then
    echo "[ERROR] import_sub_events.py failed for event $eid" >&2
    FAIL=1
  fi
done

# --- 7. 统一汇总 + 退出码 ----------------------------------------------------
finish
