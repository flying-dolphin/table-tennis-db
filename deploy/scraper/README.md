# 数据抓取与同步（本地服务器 → 服务器 A）

## 拓扑

```
┌──────────────────────┐                ┌─────────────────────┐
│  本地抓取服务器        │                │   服务器 A           │
│                      │                │                     │
│  cron (sentry-cli) ──┼──┐             │  /opt/ittf/data/    │
│   ↓                  │  │ rsync       │   ├── db/ittf.db    │
│  sync_to_server_a.sh │  │  + ssh      │   ├── rankings/     │
│   ├─ run_*.py 抓取   │  └──────────►──┼─► ├── player_*/     │
│   ├─ import 入 SQLite│                │   └── matches_*/    │
│   ├─ .backup 快照    │                │                     │
│   └─ rsync 到 A      │                │  Web 容器读取        │
│                      │                │                     │
└──────────────────────┘                └─────────────────────┘
                                                  ▲
                                                  │
                                          错误 / 失败 / 超时告警
                                                  │
                                          ┌───────┴────────┐
                                          │   Sentry Crons  │
                                          └────────────────┘
```

## 为什么用本方案

- **抓取与对外站点解耦**：playwright + chromium 大且重，跑在公网服务器上不划算；放本地（家里/办公室服务器/Mac mini）随便挂。
- **数据流向单向**：本地 → A，A 永远不会写回，简单可靠。
- **服务器 A 完全无 Python 依赖**：A 上只要有 docker 和 nginx。
- **Sentry Crons 监控**：忘记跑、跑挂、跑超时都会告警，不必盯着 cron。

## 本地服务器一次性准备

```bash
# 1. clone 项目
mkdir -p /local && cd /local
git clone <repo-url> ittf
cd ittf

# 2. Python venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 3. Node（npx tsx 跑 migrate.ts 用）
# 用系统包管理器或 nvm 装 Node 20

# 4. 生成 SSH key 推到服务器 A
ssh-keygen -t ed25519 -f ~/.ssh/ittf_deploy -N ''
ssh-copy-id -i ~/.ssh/ittf_deploy.pub deploy@serverA.your-domain.com

# 5. 安装 sentry-cli
curl -sL https://sentry.io/get-cli/ | bash
```

## 服务器 A 一次性准备

```bash
# 创建 deploy 用户，加入 docker 组（无 sudo 即可重启容器）
sudo useradd -m -G docker deploy
sudo mkdir -p /opt/ittf/data/db /opt/ittf/data/rankings /opt/ittf/data/player_profiles /opt/ittf/data/player_avatars /opt/ittf/data/matches_complete
sudo chown -R deploy:deploy /opt/ittf

# 把本地服务器的 ittf_deploy.pub 追加到 /home/deploy/.ssh/authorized_keys
sudo -u deploy mkdir -p /home/deploy/.ssh
sudo -u deploy chmod 700 /home/deploy/.ssh
# echo "<本地 pubkey>" >> /home/deploy/.ssh/authorized_keys
sudo -u deploy chmod 600 /home/deploy/.ssh/authorized_keys
```

## 配置脚本

```bash
cd /local/ittf
cp deploy/scraper/cron_with_sentry.sh.example deploy/scraper/cron_with_sentry.sh
chmod +x deploy/scraper/sync_to_server_a.sh deploy/scraper/cron_with_sentry.sh
$EDITOR deploy/scraper/sync_to_server_a.sh    # 改 SERVER_A_HOST、LOCAL_PROJECT 等变量
$EDITOR deploy/scraper/cron_with_sentry.sh    # 填 SENTRY_AUTH_TOKEN 等
```

## 在 Sentry 创建 Cron Monitor

1. https://sentry.io → Crons → **Add Monitor**
2. Name: `ITTF Data Sync`
3. Slug: `ittf-data-sync`（与 `cron_with_sentry.sh` 里 `MONITOR_SLUG` 一致）
4. Schedule Type: **Crontab**，表达式与 cron 一致（例如 `0 3 * * 1`）
5. Check-in Margin: 30 分钟（容忍稍迟）
6. Max Runtime: 60 分钟（抓取通常 10–20 分钟，留余量）
7. Failure Tolerance: 0（一次失败就告警）
8. 保存

## 加入 cron

```bash
crontab -e
# 每周一凌晨 3 点跑：
0 3 * * 1 /local/ittf/deploy/scraper/cron_with_sentry.sh >> /local/ittf/scripts/logs/cron.log 2>&1
```

## 验证

```bash
# 1. 手动跑一次（不走 cron）
/local/ittf/deploy/scraper/cron_with_sentry.sh

# 2. 检查 Sentry：Crons → ittf-data-sync 应显示 "OK" check-in
# 3. 检查服务器 A：
ssh deploy@serverA "ls -la /opt/ittf/data/db/"
# 应看到 ittf.db 时间戳是刚刚，没有 ittf.db-wal / ittf.db-shm
ssh deploy@serverA "ls /opt/ittf/data/db/backups/" | tail
# 应看到自动备份的旧版 db
```

## 故障排查

**rsync permission denied**
- 服务器 A 的 `/opt/ittf/data/db/` 不属于 deploy 用户
- 修复：`sudo chown -R deploy:deploy /opt/ittf`

**docker compose stop web 失败**
- deploy 用户不在 docker 组
- 修复：`sudo usermod -aG docker deploy && newgrp docker`

**Sentry 没收到 check-in**
- `sentry-cli` 没装，或 `SENTRY_AUTH_TOKEN` / `SENTRY_DSN` 配置不完整
- 新版 `sentry-cli monitors run` 需要 `SENTRY_DSN`
- 验证：`sentry-cli info`

**Web 容器起来但读到旧数据**
- `mv` 后 Web 没重启，旧 fd 还指向旧 inode
- `sync_to_server_a.sh` 已经会 `stop` + `start`，正常无此问题
