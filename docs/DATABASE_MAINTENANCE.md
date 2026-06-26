# 数据库使用与维护（SQLite）

## 正式基线

- 正式 schema 源文件：`scripts/db/schema.sql`
- 正式数据库文件：`data/db/ittf.db`
- 正式入库链路：`scripts/db/import*.py`

说明：

- `web/db` 和 `web/scripts/sync-to-db.ts` 已退出正式链路
- 前端和 `/api/v1` 只读取 `data/db/ittf.db`
- `data/player_country_history.json` 是运行时辅助数据，不进 SQLite；部署时要和 `ITTF_DATA_DIR` 一起同步到服务器数据卷

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
python scripts/runtime/backfill_events_calendar_event_id.py
python scripts/fix_special_event_2860_stage_round.py
scripts/run_import_wtt_events.sh
```

注意：

- `import_matches.py` 正式读取 `data/event_matches/cn/*.json`，不再以 `data/matches_complete/cn/*.json` 作为基础比赛表来源
- `scripts/run_import_wtt_events.sh` 导入已翻译好的历史赛事 events 和 matches 数据；底层顺序是 `audit_same_name_players.py --update` → `import_events.py` → `prepare_same_name_player_matches.py` → `import_matches.py` → `import_event_draw_matches.py` → `import_sub_events.py`
- `prepare_same_name_player_matches.py` 只在本次待导入 matches 涉及同名球员且缺少 `data/matches_complete/cn/player_<player_id>_*.json` 时，自动抓取并翻译 player-centric matches；离线重导可用 `--skip-same-name-player-matches` 跳过
- `import_matches.py` 会读取 `scripts/data/same_name_players.txt`、`data/matches_complete/cn/player_<player_id>_*.json` 和 `data/player_country_history.json` 来回填 `match_side_players.player_id`
- `event_id=2860`（`ITTF Mixed Team World Cup Chengdu 2023`）在 ITTF 原始数据中被整届错误标记为 `Qualification`
- 该赛事真实赛制是“两阶段循环赛”，入库前必须先执行 `python scripts/fix_special_event_2860_stage_round.py`
- 该修复脚本会把 `data/event_matches/orig|cn/ITTF_Mixed_Team_World_Cup_Chengdu_2023_2860.json` 改写为：
  `Main Draw - Stage 1 + Group 1/2/3/4` 和 `Main Draw - Stage 2 + Round Robin`
- `import_event_draw_matches.py` 必须在 `import_sub_events.py` 之前执行，冠军统计只读取正赛表里的 `draw_round='Final'`
- 暂时不要执行 `python scripts/db/import_points_rules.py`
- 该脚本当前为占位状态，`points_rules` 导入放在后续实现计划

---

## 赛事增量更新

赛事增量更新不属于数据库全量重建流程。

赛前/赛中接入、2026 年及以后赛事的赛后补抓、2026 年以前历史赛事补录，以及完赛 promote 的操作步骤，统一见：

- [赛事数据日常更新流程](event-data-update-workflow.md)

如果旧数据库尚未包含 lifecycle 和 `current_event_*` 结构，按实际缺失情况执行：

```bash
python scripts/db/upgrade_schema_event_lifecycle.py
python scripts/db/upgrade_schema_current_event_model.py
```

新建数据库应直接使用最新 `scripts/db/schema.sql`，不需要重复执行升级脚本。

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
SELECT COUNT(*) FROM current_event_session_schedule;
SELECT COUNT(*) FROM current_event_matches;
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

检查某个当前赛事的 session / match 数据量：

```sql
SELECT COUNT(*) AS session_days
FROM current_event_session_schedule
WHERE event_id = 3216;

SELECT COUNT(*) AS current_matches
FROM current_event_matches
WHERE event_id = 3216;
```

---

## 完赛 Promote

`scripts/db/promote_current_event.py` 是从 `current_event_*` 写入历史事实表并将 lifecycle 更新为 `completed` 的入口。

- 日常操作、赛后补抓和校验：[赛事数据日常更新流程](event-data-update-workflow.md)
- 字段映射与实现设计：[Current Event → 历史事实表 Promote 方案](design/promote_current_event.md)

---

## 备份与恢复

在重建前建议先备份旧库文件：

```bash
copy data\db\ittf.db data\db\ittf_backup_20260417.db
```

恢复时直接替换文件或从备份重新拷回。
