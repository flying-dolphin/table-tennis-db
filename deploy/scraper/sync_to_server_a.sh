#!/usr/bin/env bash
#
# 在「本地抓取服务器」上跑：抓取 → 导入到本地 SQLite → rsync 到服务器 A
#
# 用法：
#   1. 把仓库 clone 到本地服务器，准备好 venv + playwright + Node（见 README.md）
#   2. 在本地服务器上配置 ssh key 免密到 deploy@serverA
#   3. 编辑下面 SERVER_A_HOST / SSH_KEY / SCRAPE_USER 变量
#   4. 用 cron 调度本脚本，建议外面再套一层 sentry-cli monitors run（见 cron_with_sentry.sh.example）

set -euo pipefail

# ===== 配置 =====
SERVER_A_HOST=deploy@serverA.your-domain.com
SSH_KEY=$HOME/.ssh/ittf_deploy
REMOTE_PROJECT=/opt/ittf
LOCAL_PROJECT=/local/ittf            # 本地服务器上的项目根
COMPOSE_FILE_REMOTE=deploy/web/docker-compose.yml
ENV_FILE_REMOTE=deploy/web/.env

# ===== 1. 本地抓取 + 导入 =====
cd "${LOCAL_PROJECT}"
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> [$(date '+%F %T')] 抓取排名"
python scripts/run_rankings.py --top 100 --headless

echo "==> [$(date '+%F %T')] 抓取球员档案"
python scripts/run_profiles.py --category women --top 50 --headless

echo "==> [$(date '+%F %T')] 抓取比赛"
python scripts/scrape_matches.py --players-file data/women_singles_top50.json

echo "==> [$(date '+%F %T')] 写入本地 SQLite"
( cd web && npx tsx scripts/migrate.ts )
# 如果需要跑 import_*.py，按你的实际 pipeline 调整：
# python scripts/db/import_rankings.py
# python scripts/db/import_players.py
# python scripts/db/import_matches.py

# ===== 2. 生成一致性 SQLite 快照 =====
echo "==> [$(date '+%F %T')] 生成 SQLite 快照"
SNAPSHOT="data/db/ittf.snapshot.db"
rm -f "${SNAPSHOT}"
sqlite3 data/db/ittf.db ".backup ${SNAPSHOT}"

# ===== 3. 推送到服务器 A =====
RSYNC_BASE=(rsync -avz --human-readable -e "ssh -i ${SSH_KEY} -o StrictHostKeyChecking=accept-new")

echo "==> [$(date '+%F %T')] 推送 SQLite 到 incoming"
"${RSYNC_BASE[@]}" "${SNAPSHOT}" "${SERVER_A_HOST}:${REMOTE_PROJECT}/data/db/ittf.incoming.db"

echo "==> [$(date '+%F %T')] 推送抓取产物（rankings / profiles / avatars）"
"${RSYNC_BASE[@]}" --delete data/rankings/         "${SERVER_A_HOST}:${REMOTE_PROJECT}/data/rankings/"
"${RSYNC_BASE[@]}" --delete data/player_profiles/  "${SERVER_A_HOST}:${REMOTE_PROJECT}/data/player_profiles/"
"${RSYNC_BASE[@]}" --delete data/player_avatars/   "${SERVER_A_HOST}:${REMOTE_PROJECT}/data/player_avatars/"
"${RSYNC_BASE[@]}" --delete data/matches_complete/ "${SERVER_A_HOST}:${REMOTE_PROJECT}/data/matches_complete/"

# ===== 4. 在服务器 A 上原子切换 + 重启 Web =====
echo "==> [$(date '+%F %T')] 远程切换数据库（约 5 秒停机）"
ssh -i "${SSH_KEY}" "${SERVER_A_HOST}" bash -s <<REMOTE
set -euo pipefail
cd ${REMOTE_PROJECT}

# 停 Web，确保没有进程持有旧 db 的 fd
docker compose -f ${COMPOSE_FILE_REMOTE} --env-file ${ENV_FILE_REMOTE} stop web

# 备份当前 db（rotate 30 天）
mkdir -p data/db/backups
cp data/db/ittf.db "data/db/backups/ittf-\$(date +%Y%m%d_%H%M%S).db" 2>/dev/null || true
find data/db/backups -name 'ittf-*.db' -mtime +30 -delete

# 原子替换
mv data/db/ittf.incoming.db data/db/ittf.db
rm -f data/db/ittf.db-wal data/db/ittf.db-shm

# 起 Web
docker compose -f ${COMPOSE_FILE_REMOTE} --env-file ${ENV_FILE_REMOTE} start web
REMOTE

rm -f "${SNAPSHOT}"
echo "==> [$(date '+%F %T')] 完成"
