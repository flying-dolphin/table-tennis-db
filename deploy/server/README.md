# 服务器 A：赛事自动刷新

适用场景：

- 进行中 / 已发布签表赛事的日常自动刷新
- 直接在 Linux 服务器上跑，不依赖浏览器、CDP 或人工过 Cloudflare

不适用场景：

- ITTF rankings 抓取
- 需要先手动打开 Windows 浏览器并通过 Cloudflare 风控的抓取任务

## 最小部署方式

服务器上不需要完整仓库。

只需要上传：

- [event_refresh.sh](/D:/dev/project/ittf/deploy/server/event_refresh.sh)
- [upload_runtime.ps1](/D:/dev/project/ittf/deploy/server/upload_runtime.ps1)
- [runtime/README.md](/D:/dev/project/ittf/deploy/server/runtime/README.md)
- `runtime/data/stage_round_mapping.json`
- `runtime/python/backfill_events_calendar_event_id.py`
- `runtime/python/import_session_schedule.py`
- `runtime/python/import_wtt_event.py`
- `runtime/python/refresh_event_results_daily.py`
- `runtime/python/scrape_wtt_event.py`

推荐部署到：

```text
/opt/ittf-ops/
  event_refresh.sh
  runtime/
```

配套数据目录单独放：

```text
/opt/ittf-data/
  db/ittf.db
  wtt_raw/
  event_schedule/   # 可选
```

## Windows 一键上传

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\server\upload_runtime.ps1 -ServerHost deploy@serverA
```

如果目标目录不是 `/opt/ittf-ops`：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\server\upload_runtime.ps1 `
  -ServerHost deploy@serverA `
  -RemoteOpsDir /data/ittf-ops
```

这个脚本会：

1. 在服务器上创建 `runtime/data` 和 `runtime/python`
2. 精确上传最小运行包所需文件
3. 给 `event_refresh.sh` 加执行权限

## 一次性准备

```bash
ssh deploy@serverA
sudo apt install -y sqlite3

mkdir -p /opt/ittf-ops /opt/ittf-data/db /opt/ittf-data/wtt_raw /opt/ittf-data/event_schedule /opt/ittf-logs
chmod +x /opt/ittf-ops/event_refresh.sh
pyenv activate venv
python --version
```

说明：

- 这套 runtime 只依赖 Python 标准库，不需要 `pip install -r requirements.txt`
- 代码文件只上传最小 runtime 包，不上传完整仓库
- `upload_runtime.ps1` 依赖本机可用的 `ssh` / `scp`
- 默认推荐通过 `PYENV_ENV_NAME` 让脚本内部执行 `pyenv activate <env>`
- 不使用 pyenv 时，才需要改回 `VENV_PATH` 方案

## 从零到可跑

### 1. Windows 开发机上传最小运行包

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\server\upload_runtime.ps1 -ServerHost deploy@serverA
```

### 2. 服务器首次准备目录和 Python

```bash
ssh deploy@serverA
sudo apt install -y sqlite3
mkdir -p /opt/ittf-ops /opt/ittf-data/db /opt/ittf-data/wtt_raw /opt/ittf-data/event_schedule /opt/ittf-logs
chmod +x /opt/ittf-ops/event_refresh.sh
pyenv activate venv
python --version
```

### 3. 放好数据库

至少确保这里已经有你的线上 SQLite：

```text
/opt/ittf-data/db/ittf.db
```

如果当前数据库还在别处，先自行拷过去，例如：

```bash
scp ittf.db deploy@serverA:/opt/ittf-data/db/ittf.db
```

### 4. 手动跑一次验证

```bash
ITTF_DATA_DIR=/opt/ittf-data \
PYENV_ENV_NAME=venv \
/opt/ittf-ops/event_refresh.sh
```

验证点：

- 命令返回 `完成`
- `/opt/ittf-data/wtt_raw/` 下出现最新赛事目录
- `/opt/ittf-data/db/backups/` 下生成备份
- 实际使用的解释器建议先确认：`pyenv activate venv && python --version`

### 5. 安装每日 cron

```bash
crontab -e
10 6 * * * ITTF_DATA_DIR=/opt/ittf-data PYENV_ENV_NAME=venv /opt/ittf-ops/event_refresh.sh >> /opt/ittf-logs/event-refresh.log 2>&1
```

### 6. 可选：接入 Sentry Crons

先把模板上传为正式脚本：

```bash
cp /opt/ittf-ops/cron_event_refresh_with_sentry.sh.example /opt/ittf-ops/cron_event_refresh_with_sentry.sh
chmod +x /opt/ittf-ops/cron_event_refresh_with_sentry.sh
```

然后把 cron 改成：

```bash
10 6 * * * PYENV_ENV_NAME=venv /opt/ittf-ops/cron_event_refresh_with_sentry.sh >> /opt/ittf-logs/event-refresh.log 2>&1
```

## 手动执行

```bash
ITTF_DATA_DIR=/opt/ittf-data \
PYENV_ENV_NAME=venv \
/opt/ittf-ops/event_refresh.sh
```

脚本会：

1. 备份 `/opt/ittf-data/db/ittf.db`
2. 回填 `events_calendar.event_id` 并 seed 缺失的 `events`
3. 导入 `/opt/ittf-data/event_schedule/*.json`（如果存在）
4. 刷新 `draw_published` / `in_progress` 赛事的 WTT raw 与 `event_schedule_*` 表

## Cron

不接 Sentry 时，可直接加 cron：

```bash
crontab -e
10 6 * * * ITTF_DATA_DIR=/opt/ittf-data PYENV_ENV_NAME=venv /opt/ittf-ops/event_refresh.sh >> /opt/ittf-logs/event-refresh.log 2>&1
```

## Sentry Crons（可选）

把 [cron_event_refresh_with_sentry.sh.example](/D:/dev/project/ittf/deploy/server/cron_event_refresh_with_sentry.sh.example) 上传为：

```text
/opt/ittf-ops/cron_event_refresh_with_sentry.sh
```

然后加 cron：

```bash
10 6 * * * /opt/ittf-ops/cron_event_refresh_with_sentry.sh >> /opt/ittf-logs/event-refresh.log 2>&1
```

建议的 monitor 配置：

- Slug: `ittf-event-refresh`
- Schedule: `10 6 * * *`
- Check-in Margin: `30 minutes`
- Max Runtime: `30 minutes`
- Failure Tolerance: `0`
