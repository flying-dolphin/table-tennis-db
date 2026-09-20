# 2026 亚运会乒乓球一次性抓取流程

本目录只服务爱知·名古屋 2026 亚运会，不与 WTT 抓取脚本混用。官方源时区为
`Asia/Tokyo`；数据库保存东京本地时间与 UTC，兼容赛程 JSON 显示北京时间。

## 常用命令

从项目根目录执行：

```bash
.venv/bin/python -m scripts.asian_games_2026.scrape_schedule
.venv/bin/python -m scripts.asian_games_2026.scrape_brackets
.venv/bin/python -m scripts.asian_games_2026.scrape_matches
.venv/bin/python -m scripts.asian_games_2026.import_current
```

一次完成上述三步：

```bash
.venv/bin/python -m scripts.asian_games_2026.refresh
```

团体主记录的完整提报名单写入 `current_event_team_tie_side_players`；每场实际或
计划对阵球员写入 `current_event_match_side_players`，两者不会混用。

男单、女单、男双、女双和混双签表来自官方 `/brackets/{event-code}` 接口，写入
`current_event_brackets`。原始响应保存在 `data/asian_games/2026/raw/brackets/`，
标准化快照为 `data/asian_games/2026/normalized/current_brackets.json`。
导入时会使用 `scripts/data/asian_games_player_aliases.json` 解析签表中的源名称，
并将解析结果写入现有 `current_event_brackets.raw_source_payload` 的
`_resolved_players` 字段；无需新增表。修改别名后重新运行导入即可修复已有签表数据。

## 定时任务

```bash
.venv/bin/python -m scripts.asian_games_2026.generate_crontab
bash scripts/asian_games_2026/install_crontab.sh
```

cron 使用 `CRON_TZ=Asia/Shanghai`，比赛日每五分钟刷新，23:30 做当日全量核对，
9 月 29 日 02:00 执行最终归档。安装脚本只替换自身标记区块，不修改其他任务。

## 赛事结束归档

先做全量抓取和只读核查：

```bash
.venv/bin/python -m scripts.asian_games_2026.finalize --dry-run
```

确认无未结束比赛、缺失胜者或团体名单后执行：

```bash
.venv/bin/python -m scripts.asian_games_2026.finalize
```

如历史数据已经存在且需要重建，显式增加 `--replace`。`--force` 会绕过亚运会
完整性拦截，仅应用于人工核查后的异常场景。

其他原始官方响应保存在 `data/asian_games/2026/raw/`，比赛标准化快照位于
`data/asian_games/2026/normalized/current_matches.json`。
