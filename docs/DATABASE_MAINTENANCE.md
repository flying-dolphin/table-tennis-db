# 数据库使用与维护（SQLite）

## 正式基线

- 正式 schema 源文件：`scripts/db/schema.sql`
- 正式数据库文件：`data/db/ittf.db`
- 正式入库链路：`scripts/db/import*.py`

说明：

- `web/db` 和 `web/scripts/sync-to-db.ts` 已退出正式链路
- 前端和 `/api/v1` 只读取 `data/db/ittf.db`

---

## 初始化与入库顺序

以下命令在项目根目录执行：

```bash
python scripts/db/init_database.py
python scripts/db/import_sub_event_type.py 
python scripts/db/import_event_categories.py
python scripts/db/import_players.py
python scripts/db/import_rankings.py
python scripts/db/import_events.py
python scripts/db/import_events_calendar.py
python scripts/db/backfill_events_calendar_event_id.py
python scripts/fix_special_event_2860_stage_round.py
python scripts/db/import_matches.py
python scripts/db/import_event_draw_matches.py
python scripts/db/import_sub_events.py
```

注意：

- `import_matches.py` 正式读取 `data/event_matches/cn/*.json`，不再以 `data/matches_complete/cn/*.json` 作为基础比赛表来源
- `event_id=2860`（`ITTF Mixed Team World Cup Chengdu 2023`）在 ITTF 原始数据中被整届错误标记为 `Qualification`
- 该赛事真实赛制是“两阶段循环赛”，入库前必须先执行 `python scripts/fix_special_event_2860_stage_round.py`
- 该修复脚本会把 `data/event_matches/orig|cn/ITTF_Mixed_Team_World_Cup_Chengdu_2023_2860.json` 改写为：
  `Main Draw - Stage 1 + Group 1/2/3/4` 和 `Main Draw - Stage 2 + Round Robin`
- `import_event_draw_matches.py` 必须在 `import_sub_events.py` 之前执行，冠军统计只读取正赛表里的 `draw_round='Final'`
- 暂时不要执行 `python scripts/db/import_points_rules.py`
- 该脚本当前为占位状态，`points_rules` 导入放在后续实现计划

---

## 即将开赛 / 进行中赛事维护链路

这条链路不属于历史赛事的全量重建顺序，而是 upcoming / in-progress 赛事的增量维护流程。

### 1. Schema 升级

如果本地库还没有以下字段/表，需要先执行：

```bash
python scripts/db/upgrade_schema_event_lifecycle.py
```

这个脚本会补：

- `events.lifecycle_status`
- `events.time_zone`
- `events.last_synced_at`
- `event_session_schedule`
- `event_draw_entries`
- `event_draw_entry_players`
- `event_schedule_matches`
- `event_schedule_match_sides`
- `event_schedule_match_side_players`

### 2. 补 upcoming 赛事基础记录

```bash
python scripts/db/backfill_events_calendar_event_id.py
```

用途：

- 从 `events_calendar.href` 提取 `event_id`
- 对 `events` 表中缺失的赛事补 INSERT
- 初始化 `lifecycle_status='upcoming'`

### 3. 导入按日日程

```bash
python scripts/db/import_session_schedule.py --event 3216
```

用途：

- 读取 `data/event_schedule/{event_id}.json`
- 写入 `event_session_schedule`
- 将 `events.lifecycle_status` 从 `upcoming` 推进到 `draw_published`

### 4. 抓取 WTT raw 数据

```bash
python scripts/scrape_wtt_event.py --event-id 3216 --sub-events MTEAM WTEAM
```

输出目录：

- `data/wtt_raw/{event_id}/`

当前主要 raw 文件：

- `GetEventDraws.json`
- `GetEventSchedule.json`
- `GetOfficialResult_take10.json`
- `GetLiveResult.json`
- `GetBrackets_{sub_event}.json`

### 5. 导入按场比赛赛程

```bash
python scripts/db/import_wtt_event.py --event 3216
```

用途：

- 把 `GetEventSchedule.json` 解析到：
  - `event_draw_entries`
  - `event_draw_entry_players`
  - `event_schedule_matches`
  - `event_schedule_match_sides`
  - `event_schedule_match_side_players`
- 按需补 `events.time_zone`
- 根据赛事时间推进 `events.lifecycle_status`

### 6. 日常刷新

```bash
python scripts/scrape_event_results_daily.py
python scripts/scrape_event_results_daily.py --event 3216
python scripts/scrape_event_results_daily.py --event 3216 --skip-scrape
```

当前真实行为：

- 选择 `lifecycle_status IN ('draw_published', 'in_progress')` 的赛事
- 刷新 `data/wtt_raw/{event_id}/`
- 重新执行 `import_wtt_event.py`

注意：

- 当前不会自动 promote 到 `matches / event_draw_matches`
- 当前不会把 `GetOfficialResult_take10.json` 系统化写回数据库结果表

### 7. 当前赛事 runtime 刷新

当前 WTT 团体赛事使用 `scripts/runtime/` 下的独立链路，数据落在 `current_event_*` 表，不写入历史 `matches / event_draw_matches`。

抓取：

```bash
python scripts/runtime/scrape_current_event.py --event-id 3216
```

导入：

```bash
python scripts/runtime/import_current_event.py --event-id 3216
```

只刷新 live/completed 比赛结果：

```bash
python scripts/runtime/import_current_event.py --event-id 3216 --sources live completed
```

默认导入顺序：

1. `session_schedule` -> `current_event_session_schedule`
2. `standings` -> `current_event_group_standings`
3. `brackets` -> `current_event_brackets`
4. `live` -> `current_event_team_ties` + `current_event_matches`
5. `completed` -> `current_event_team_ties` + `current_event_matches`

数据源边界：

- `completed_matches.json` 是已完结 team tie 和 rubber 的主数据源
- `GetLiveResult.json` 是进行中 team tie 和 rubber 的主数据源
- `GetEventSchedule.json` 只作为 match code、赛程时间、台号、队伍 roster 等补充信息，不再单独重建 `current_event_team_ties`

---

## 何时需要重建数据库

以下场景建议直接重建 `data/db/ittf.db` 并按上述顺序重新入库：

- `scripts/db/schema.sql` 有结构变更（表/字段/索引/约束）
- 赛事分类映射逻辑有变更（如 `event_categories`、`event_type_mapping`）
- 比赛关联逻辑有变更（如 `import_matches.py` 的 `event_id` 关联规则）
- 新增了正式导入脚本（如 `import_events_calendar.py`）

不建议手工对旧库零散执行 `ALTER TABLE` 追版本。

---

## 本轮变更影响（2026-04-17）

本轮变更后，如果你的本地库是在变更前初始化的，建议重建：

- `event_categories.sort_order` 已改为按 `data/event_category_mapping.json` 顺序从 1 开始写入
- 新增 `events_calendar` 正式导入脚本
- `import_matches.py` 不再依赖 `tmp/event_mapping.json`，改为基于数据库内 `events` 关联
- `import_matches.py` 已切换为赛事维度 `data/event_matches/cn` 数据源，并允许同一双方在同一轮次重复交手
- 新增 `import_sub_events.py`，从决赛 `matches` 聚合写入 `sub_events`
- 新增 `import_event_draw_matches.py`，从 `matches` 生成正赛对战表 `event_draw_matches`

---

## 常用校验

```sql
SELECT COUNT(*) FROM event_categories;
SELECT COUNT(*) FROM event_type_mapping;
SELECT COUNT(*) FROM events;
SELECT COUNT(*) FROM events_calendar;
SELECT COUNT(*) FROM event_session_schedule;
SELECT COUNT(*) FROM event_schedule_matches;
SELECT COUNT(*) FROM matches;
SELECT COUNT(*) FROM event_draw_matches;
```

检查分类顺序：

```sql
SELECT category_id, sort_order
FROM event_categories
ORDER BY sort_order;
```

检查赛历关联质量：

```sql
SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN event_id IS NOT NULL THEN 1 ELSE 0 END) AS linked_event,
  SUM(CASE WHEN event_category_id IS NOT NULL THEN 1 ELSE 0 END) AS linked_category
FROM events_calendar;
```

检查 lifecycle 分布：

```sql
SELECT lifecycle_status, COUNT(*)
FROM events
GROUP BY lifecycle_status
ORDER BY lifecycle_status;
```

检查某个进行中赛事的 session / schedule 数据量：

```sql
SELECT COUNT(*) AS session_days
FROM event_session_schedule
WHERE event_id = 3216;

SELECT COUNT(*) AS schedule_matches
FROM event_schedule_matches
WHERE event_id = 3216;
```

---

## 备份与恢复

在重建前建议先备份旧库文件：

```bash
copy data\db\ittf.db data\db\ittf_backup_20260417.db
```

恢复时直接替换文件或从备份重新拷回。
