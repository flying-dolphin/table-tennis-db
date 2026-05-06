# 服务器自动赛事刷新最小运行包

这个目录是服务器 A 上 `/opt/ittf-ops/runtime/` 的目标结构说明。实际源码统一维护在 `scripts/runtime/`，通过 `deploy/server/upload_runtime.ps1` 上传，不要求服务器有完整仓库。

统一操作手册维护在 `docs/DEPLOY_ANALYTICS.md` 的“数据更新”章节。本文件只说明目录职责。

```text
/opt/ittf-ops/
  event_refresh.sh
  install_current_event_crontab.sh
  cron_event_refresh_with_sentry.sh.example
  runtime/
    README.md
    python/
      generate_current_event_crontab.py
      scrape_current_event.py
      import_current_event.py
      import_current_event_schedule.py
      scrape_wtt_*.py
      import_current_event_*.py
      wtt_import_shared.py
      wtt_scrape_shared.py
      lib/
        browser_runtime.py
```

配套数据目录建议独立放在 `/opt/ittf-data/`：

```text
/opt/ittf-data/
  db/ittf.db
  live_event_data/
  event_schedule/
  logs/                          # cron 任务日志，按 event_<id>_YYYYMMDD.log 命名
```

运行时依赖（服务器 A）：

- `sqlite3`（`event_refresh.sh` 备份与查询 SQLite 需要）
- Python 3.8+（pyenv 或 venv）
- `patchright` 或 `playwright` + Chromium（`live` / `standings` 源需要）

参考安装（Ubuntu）：

```bash
sudo apt install -y sqlite3
pyenv activate venv
pip install patchright playwright beautifulsoup4 brotli python-dotenv requests pypdf
python -m patchright install chromium
```

关键约束：

- `events.time_zone` 必须是 IANA 时区名。
- 赛事日程由 `current_event_session_schedule` 提供，通常来自 `/opt/ittf-data/event_schedule/{event_id}.json`。
- 当前赛事刷新会先抓取 `live_event_data/{event_id}/GetEventSchedule.json`，再由 `import_current_event_schedule.py` 导入 `current_event_team_ties / current_event_team_tie_sides / current_event_team_tie_side_players`，作为赛事页“比赛”tab 的基础赛程数据。
- 动态 current-event crontab 中，`schedule` 源按赛事当地时间每天第 2 个 session 开始后 5 小时执行 1 次；若当天只有 1 个 session，则回退到当天最后一个 session 开始后 5 小时。
- 按赛程生成并安装高频 cron 使用 `install_current_event_crontab.sh`。它会替换唯一的 `ITTF current-event refresh` 托管区块，不会累积历史赛事任务。日志默认写入 `${ITTF_DATA_DIR}/logs/event_<id>_YYYYMMDD.log`，可通过 `LOG_DIR` 环境变量覆盖。
