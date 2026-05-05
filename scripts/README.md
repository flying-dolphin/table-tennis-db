# ITTF Scripts

本文档是 `scripts/` 目录的统一说明，按当前代码行为维护。

## 运行前提

- Python 3.10+
- 安装依赖：`pip install -r requirements.txt`
- 在仓库根目录配置 `.env`（如需 API 翻译，提供 `MINIMAX_API_KEY`）

以下命令默认在仓库根目录执行；若在 `scripts/` 目录执行，请去掉 `scripts/` 前缀。

## 翻译系统（当前标准）

- 词典只使用 V2：`scripts/data/translation_dict_v2.json`
- 不再支持旧词典：`translation_dict.json`
- 分类固定为：`players / terms / events / locations / others`
- `locations` 未命中时会回退 `others`（例如 `TBD -> 待定`）

### 词典校验

```bash
python scripts/validate_translation_dict.py --input scripts/data/translation_dict_v2.json
```

通过标准：
- `errors: 0`
- `warnings: 0`

### 翻译结果校验（events_calendar）

```bash
python scripts/validate_events_translation.py --translated data/events_calendar/cn/events_calendar_2026.json
```

严格对照原始文件：

```bash
python scripts/validate_events_translation.py --translated data/events_calendar/cn/events_calendar_2026.json --raw data/events_calendar/orig/events_calendar_2026.json
```

## Events Calendar 流程

### 1) 抓取（可选内置翻译）

```bash
python scripts/scrape_events_calendar.py --year 2026
```

常用参数：
- `--force`：忽略 checkpoint 重新抓取
- `--cdp-port`：复用已启动浏览器

checkpoint 已拆分：
- `data/events_calendar/checkpoint_scrape_{year}.json`
- `data/events_calendar/checkpoint_translate_{year}.json`

### 2) 独立翻译

```bash
python scripts/translate_events_calendar.py --year 2026
```

常用参数：
- `--force`：从头翻译
- `--rebuild-checkpoint`：从现有 cn 文件重建 checkpoint

说明：
- cn 文件保持与 orig 相同的结构，只翻译字符串值。
- 若存在未翻译项，脚本会返回非 0，并保留已生成的 cn 文件。

## Matches 抓取与翻译

抓取比赛数据：

```bash
python scripts/scrape_matches.py
```

常用参数：
- `--player-name "DOO Hoi Kem"`：只抓单个球员
- `--cdp-port 9222`：复用已启动浏览器
- `--init-session`：初始化登录态

翻译比赛文件：

```bash
python scripts/translate_matches.py --file data/matches_complete/xxx.json
```

## WTT 当前赛事流水线

当前进行中的赛事统一使用 `scripts/runtime/` 下的新入口：

抓取当前赛事数据：

```bash
python scripts/runtime/scrape_current_event.py --event-id 3216
```

导入当前赛事数据：

```bash
python scripts/runtime/import_current_event.py --event-id 3216
```

默认导入顺序：

1. `session_schedule`：导入人工维护的按日日程到 `current_event_session_schedule`
2. `standings`：导入小组积分到 `current_event_group_standings`
3. `brackets`：导入淘汰赛签表到 `current_event_brackets`
4. `live`：从 `GetLiveResult.json` 同步进行中 team tie 和 rubber
5. `completed`：从 `completed_matches.json` 同步已完结 team tie 和 rubber

可只导入当前比赛结果：

```bash
python scripts/runtime/import_current_event.py --event-id 3216 --sources live completed
python scripts/runtime/import_current_event_live.py --event-id 3216
python scripts/runtime/import_current_event_completed.py --event-id 3216
```

`current_event_team_ties` 现在由 live/completed 导入器随 `current_event_matches` 一起维护。`GetEventSchedule.json` 只作为抓取和导入时的补充信息来源，不再通过单独的 team_ties skeleton 导入脚本重建 `current_event_team_ties`。

当前赛事积分表单独导入：

```bash
python scripts/runtime/import_current_event_group_standings.py --input-dir data/live_event_data/3216 --event-id 3216
```

生成当前赛事刷新 crontab：

```bash
python scripts/runtime/generate_current_event_crontab.py --event-id 3216 --headless
```

脚本会读取 `events.time_zone` 和 `current_event_session_schedule`，把赛事当地时间转换成 `Asia/Shanghai` 后输出 crontab 内容；不会自动安装到系统 crontab。生产服务器上应显式传入服务器路径，例如：

```bash
python scripts/runtime/generate_current_event_crontab.py \
  --event-id 3216 \
  --db-path /opt/ittf/data/db/ittf.db \
  --project-root /opt/ittf \
  --runtime-python-dir /opt/ittf/scripts/runtime \
  --python-bin /opt/ittf-venv/bin/python \
  --live-event-data-root /opt/ittf/data/live_event_data \
  --headless
```

如果在本机读取本地 SQLite、但要输出服务器 crontab 命令，可用 `--emit-db-path` 指定写入 cron 命令的服务器 DB 路径。

如果 `events.time_zone` 为空或不是 IANA 时区名，脚本会直接失败。不要用本机时区代替赛事时区。

旧的 WTT 当前赛事脚本已经归档到 `tmp/scripts/`，不再作为主入口使用。以下旧底层导入脚本已移除或合并：

- `import_current_event_matches_from_live.py`
- `import_current_event_team_ties_from_live.py`
- `import_current_event_team_ties_from_schedule.py`
- `import_current_event_matches_from_completed.py`，已更名为 `import_current_event_completed.py`

## 历史团体赛 team_ties 回填

历史团体赛的顶层对阵从 `matches / match_sides / match_side_players` 离线构建，前端不再实时聚合。

预览回填结果：

```bash
python scripts/db/backfill_historical_team_ties.py --dry-run
```

执行全量回填：

```bash
python scripts/db/backfill_historical_team_ties.py
```

只回填单个赛事：

```bash
python scripts/db/backfill_historical_team_ties.py --event-id 250
```

脚本会写入 `team_ties / team_tie_sides / team_tie_side_players`，并回填 `matches.team_tie_id`。重跑时按 `source_key` 更新既有记录，保留 `team_tie_id` 稳定。

## 旧 event_schedule 表清理

确认前端与导入链路不再使用旧表后，可删除旧的 `event_schedule_*` 和 `event_session_schedule` 表：

```bash
python scripts/db/drop_legacy_event_schedule_tables.py --dry-run
python scripts/db/drop_legacy_event_schedule_tables.py
```

默认执行前会备份数据库。旧表已由 `current_event_*` 与历史 `team_ties / matches` 替代。

## 特殊赛事修复

### 修复 `event_id=2860` 的 stage/round

`2023 ITTF Mixed Team World Cup Chengdu` 在 ITTF 原始赛事维度数据里，全部被错误标记为 `Qualification`。
该赛事真实赛制是：

- 第一阶段：4 个小组循环赛
- 第二阶段：8 强循环赛
- 冠军按第二阶段积分榜产生，不是淘汰赛 `Final`

修复脚本：

```bash
python scripts/fix_special_event_2860_stage_round.py --dry-run
python scripts/fix_special_event_2860_stage_round.py
```

作用范围：

- `data/event_matches/orig/ITTF_Mixed_Team_World_Cup_Chengdu_2023_2860.json`
- `data/event_matches/cn/ITTF_Mixed_Team_World_Cup_Chengdu_2023_2860.json`

修正结果：

- `Main Draw - Stage 1` + `Group 1/2/3/4`
- `Main Draw - Stage 2` + `Round Robin`

如果后续要执行 `python scripts/db/import_matches.py` 重建比赛表，先跑这个修复脚本。

### 修复 `event_id=2979/3263` 的铜牌赛标签

`2024/2025 ITTF Mixed Team World Cup Chengdu` 的铜牌赛在 ITTF 原始赛事维度数据里标注不一致：

- `2024`：铜牌赛被错误标成 `Main Draw / Final`
- `2025`：铜牌赛被标成 `Position Draw / 2`

修复脚本：

```bash
python scripts/fix_special_event_mixed_team_world_cup_2024_2025.py --dry-run
python scripts/fix_special_event_mixed_team_world_cup_2024_2025.py
```

作用范围：

- `data/event_matches/orig/ITTF_Mixed_Team_World_Cup_Chengdu_2024_2979.json`
- `data/event_matches/cn/ITTF_Mixed_Team_World_Cup_Chengdu_2024_2979.json`
- `data/event_matches/orig/ittf_mixed_team_world_cup_chengdu_2025_3263.json`
- `data/event_matches/cn/ittf_mixed_team_world_cup_chengdu_2025_3263.json`

修正结果：

- 两届铜牌赛统一改成 `Main Draw / Bronze`
- `2024` 铜牌赛：`ROU vs HKG`
- `2025` 铜牌赛：`KOR vs GER`

## Rankings 抓取

从 https://www.ittf.com/rankings/ 抓取 Women's Singles 排名 + points breakdown：

```bash
python scripts/run_rankings.py --top 100 --headless
```

常用参数：
- `--top N`：抓取前 N 名（默认 100）
- `--force`：忽略 checkpoint 重新抓取
- `--output-dir`：输出目录（默认 `data/rankings/orig`）

输出：`data/rankings/orig/women_singles_top{N}_week{W}.json`

## Player Profiles 抓取

从 results.ittf.link 抓取运动员详情档案：

```bash
python scripts/run_profiles.py --category women --top 50 --headless
```

输出：
- `data/player_profiles/orig/` — 原始档案
- `data/player_profiles/cn/` — 中文翻译版
- `data/player_avatars/` — 头像

## Rankings 翻译

翻译排名文件：

```bash
python scripts/translate_rankings.py --file data/rankings/orig/women_singles_top100_week16.json
```

## Regulations（规则文档）

入口脚本：

```bash
python scripts/regulations_manager.py
```

常用参数：
- `--force`
- `--translate`
- `--api --api-key YOUR_KEY`
- `--daemon`

底层抓取模块：

```bash
python scripts/scrape_regulations.py
```

## 翻译模块示例

```bash
python scripts/translate_example.py --basic
python scripts/translate_example.py --batch-test
python scripts/translate_example.py --api-key YOUR_KEY
```
