# 4. 后端与数据架构


## 1 单一事实来源

- 抓取落地层：JSON（保留原始审计数据，不直接给前端消费）。
- 查询服务层：SQLite（前端 API 只读 SQLite）。
- 结论：SQLite 为线上查询主数据源；JSON 为离线审计与回放源。

## 2 数据域模型

核心实体：
- `ranking_snapshots`（每周排名快照）
- `players`（球员主档）
- `rankings`（快照内排名记录）
- `events`（赛事）
- `player_events`（球员-赛事关联表）
- `matches`（每一个赛事内的具体每一场比赛）
- `player_profiles`（球员详细档案）
- `ingestion_runs`（抓取任务执行记录）
- `translation_jobs`（翻译任务执行记录）

关键关系：
- 一个 `ranking_snapshot` 对应多条 `rankings`。
- 一个 `player` 对应多条 `rankings`、多场 `matches`。
- 一个 `player` 通过 `player_events`（中间表）关联多个 `events`。
- 一个 `event` 对应多场 `matches`。

## 3 统一 schema 约束

- 所有时间字段统一 ISO8601。
- 原始枚举统一：`result_for_player` ∈ {`W`,`L`,`UNKNOWN`}。
- `country_code` 统一 ISO 3 字母。
- 关键唯一键：
  - player: `player_external_id` or normalized name fallback
  - event: `event_name + start_date + end_date`
  - match: `event_id + round + side_a + side_b`

---

## 4. 数据管道设计（抓取 -> 翻译 -> 入库）

### 4.1 Pipeline 拆分

- P1 排名和档案抓取：`scrape_rankings`
- P2 比赛抓取：`scrape_matches`
- P3 赛历抓取：`scrape_events_calendar`
- P4 翻译任务：profiles/matches/events 三条翻译线
- P5 入库任务：`seed + upsert + validate`

### 4.2 任务调度策略

- 周更：rankings（ITTF 排名为周更频率）
- 根据events_calendar中赛事的结束时间确定是否需要更新比赛数据。
- 补数：缺失球员回填队列（人工触发 + 定时自动重试）。

### 4.3 失败恢复策略

- checkpoint 断点续抓。
- 风控触发立即熔断并标记任务失败。
- 每个任务写入 `ingestion_runs`，支持按 run_id 回放。

### 4.4 抓取策略

- 排名抓取：目前档案抓取和排名抓取是耦合在一起的，后面需要拆开。
- 赛事抓取：当前所有赛事都会抓取，后续需要过滤掉一些不重要的赛事。

---