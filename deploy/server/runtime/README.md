# 服务器自动赛事刷新最小运行包

这个目录是给服务器 A 用的**最小部署包**，不要求服务器上有完整仓库。

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
      refresh_event_results_daily.py
      scrape_wtt_event.py
```

配套的数据目录建议独立放在别处，例如：

```text
/opt/ittf-data/
  db/
    ittf.db
  wtt_raw/
  event_schedule/   # 可选
```

## 你实际需要上传的文件

- `deploy/server/event_refresh.sh`
- `deploy/server/runtime/data/stage_round_mapping.json`
- `deploy/server/runtime/python/backfill_events_calendar_event_id.py`
- `deploy/server/runtime/python/import_session_schedule.py`
- `deploy/server/runtime/python/import_wtt_event.py`
- `deploy/server/runtime/python/refresh_event_results_daily.py`
- `deploy/server/runtime/python/scrape_wtt_event.py`

## 运行依赖

- Linux
- Python 3.10+
- `sqlite3` 命令

这套最小包本身不依赖：

- Next.js 源码
- `web/`
- `scripts/` 目录的其他抓取脚本
- Playwright / Chromium
- 第三方 Python 包

## 入口

从 `event_refresh.sh` 启动。

它会读取这些外部路径：

- `ITTF_DATA_DIR`
- `DB_PATH`
- `EVENT_SCHEDULE_DIR`
- `RAW_ROOT`
- `VENV_PATH`
