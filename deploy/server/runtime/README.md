# 服务器自动赛事刷新最小运行包

这个目录是给服务器 A 用的**最小部署包输出结构**。实际源码统一维护在 `scripts/runtime/`，上传时再落到这里，不要求服务器上有完整仓库。

上传到服务器后的建议结构：

```text
/opt/ittf-ops/
  event_refresh.sh
  runtime/
    README.md
    data/
      stage_round_mapping.json
    python/
      backfill_events_calendar_event_id.py
      import_session_schedule.py
      import_wtt_event.py
      import_wtt_pool_standings.py
      event_refresh.py
      scrape_wtt_event.py
      scrape_wtt_pool_standings.py
      lib/
        browser_runtime.py
```

配套的数据目录建议独立放在别处，例如：

```text
/opt/ittf-data/
  db/
    ittf.db
  live_event_data/
  event_schedule/   # 可选
```

## 你实际需要上传的文件

- `deploy/server/event_refresh.sh`
- `deploy/server/runtime/data/stage_round_mapping.json`
- `scripts/runtime/backfill_events_calendar_event_id.py`
- `scripts/runtime/import_session_schedule.py`
- `scripts/runtime/import_wtt_event.py`
- `scripts/runtime/import_wtt_pool_standings.py`
- `scripts/runtime/event_refresh.py`
- `scripts/runtime/scrape_wtt_event.py`
- `scripts/runtime/scrape_wtt_pool_standings.py`
- `scripts/runtime/lib/browser_runtime.py`

## 运行依赖

- Linux
- Python 3.10+
- `sqlite3` 命令
- Playwright 或 Patchright 可用的 Python 环境
- 可供无头浏览器启动的 Chromium

这套最小包本身不依赖：

- Next.js 源码
- `web/`
- 除 standings 抓取所需文件外的其他 `scripts/` 目录内容

## 当前 refresh 流程

`event_refresh.py` 现在除了原有的赛程抓取/导入，还会追加：

1. 打开 `Stage 1B(Groups)` 页面，无头抓取 `MTEAM/WTEAM` 的官方积分表
2. 打开 `Stage 1A(Groups)` 页面，无头抓取 `MTEAM/WTEAM` 的官方积分表
3. 导入到 SQLite 的 `event_group_standings`

这一步是 best-effort：

- 原有 `GetEventSchedule` 导入成功后才会尝试
- standings 抓取或导入失败只记 warning，不会让整场 refresh 失败
- `--skip-scrape` 和 `--dry-run` 会跳过 standings

## 运行时数据目录

除了原有目录，建议再准备：

```text
/opt/ittf-data/
  live_event_data/
```

其中每个赛事会按业务语义分目录，例如：

```text
/opt/ittf-data/live_event_data/3216/
  schedule/
  match_results/
  group_standings/
```

## 入口

从 `event_refresh.sh` 启动。

它会读取这些外部路径：

- `ITTF_DATA_DIR`
- `DB_PATH`
- `EVENT_SCHEDULE_DIR`
- `LIVE_EVENT_DATA_DIR`
- `VENV_PATH`
