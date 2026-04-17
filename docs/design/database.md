# 数据库设计方案

版本：v1.1
日期：2026-04-17
数据库：SQLite

---

## 0. 当前数据库现状

本章记录截至 2026-04-17 的正式数据库基线，作为后续开发和入库的实现依据。

### 0.1 正式链路

- 正式 schema 源文件：`scripts/db/schema.sql`
- 正式数据库文件：`data/db/ittf.db`
- 正式入库链路：`scripts/db/import*.py`
- web 侧早期 demo 数据库目录和同步脚本已退出正式链路

### 0.2 当前状态

- schema 已统一为以赛事为中心的正式模型
- `event_categories + event_type_mapping` 已成为唯一正式赛事分类体系
- `points_breakdown` 已使用 `category_name_zh` 作为中文分类展示字段
- `events_calendar` 已纳入正式 schema，后续通过独立导入脚本入库
- `points_rules` 仅保留 schema 设计，导入脚本延后到后续实现计划

### 0.3 与目标 schema 的主要差距

| 维度 | 现状 | 目标 |
|------|------|------|
| 赛事分类 | 已切到 `event_categories` | 继续补全映射覆盖率和校验 |
| 排名条目 | 已切到 `ranking_entries` | 继续验证查询与页面口径一致 |
| 赛事日历 | schema 已支持 | 通过正式脚本导入并补全事件关联 |
| 比赛关联 | 已使用赛事中心模型 | 继续保证 `matches` 只依赖数据库内 `events` 关联 |
| 积分规则 | schema 已预留 | `points_rules` 延后到后续实现 |
| 数据对账 | schema 已预留 | 后续补 `unmatched_records` / `ingestion_runs` 的正式使用 |

---

## 1. 设计原则

- SQLite 为线上查询唯一数据源，JSON 文件仅作离线审计与回放用途
- 中英文字段并存，便于前端直接消费
- 所有时间字段统一 ISO8601 格式（`YYYY-MM-DD` 或 `YYYY-MM-DDTHH:MM:SS`）
- `country_code` 统一 ISO 3166-1 alpha-3（如 CHN、JPN、GER）
- V1 范围：女子单打为主，schema 兼容全项目扩展
- 赛事分类、原始赛事类型映射、积分规则以 `DATABASE_DESIGN.md` 为准

---

## 2. ER 关系概览

```
event_categories 1──N event_type_mapping
event_categories 1──N points_rules
event_categories 1──N events
events           1──N sub_events
events           1──N matches
players          1──N matches (通过 player_a_id / player_b_id)
players          1──N ranking_entries
players          1──N points_breakdown
ranking_snapshots 1──N ranking_entries
ranking_snapshots 1──N points_breakdown
sub_event_types (字典表，独立)
```

赛事分类相关关系：

```
event_categories (1)
    ├── (N) event_type_mapping         [ON DELETE RESTRICT]
    └── (N) events                     [via event_category_id]

points_rules 独立维护，通过 category_id 与 event_categories 关联
```

---

## 3. 表结构定义

### 3.1 players — 运动员主档

存储运动员基本信息和统计数据。对应 `data/player_profiles/cn/*.json`。

```sql
CREATE TABLE players (
    player_id       INTEGER PRIMARY KEY,  -- ITTF 官方 ID，如 131163
    name            TEXT NOT NULL,         -- 英文名，如 "SUN Yingsha"
    name_zh         TEXT,                  -- 中文名，如 "孙颖莎"
    slug            TEXT UNIQUE NOT NULL,  -- URL 友好标识，如 "sun-yingsha"
    country         TEXT,                  -- 国家中文名
    country_code    TEXT NOT NULL,         -- ISO 3 字母，如 "CHN"
    gender          TEXT NOT NULL DEFAULT 'Female',  -- Female / Male
    birth_year      INTEGER,
    age             INTEGER,
    style           TEXT,                  -- 如 "Right-Hand Attack (ShakeHand)"
    style_zh        TEXT,                  -- 如 "右手进攻型(横拍)"
    playing_hand    TEXT,                  -- Right / Left
    playing_hand_zh TEXT,
    grip            TEXT,                  -- ShakeHand / Penhold
    grip_zh         TEXT,
    avatar_url      TEXT,                  -- 头像远程 URL
    avatar_file     TEXT,                  -- 本地头像文件路径

    -- 职业生涯统计（定期更新）
    career_events       INTEGER DEFAULT 0,
    career_matches      INTEGER DEFAULT 0,
    career_wins         INTEGER DEFAULT 0,
    career_losses       INTEGER DEFAULT 0,
    career_wtt_titles   INTEGER DEFAULT 0,
    career_all_titles   INTEGER DEFAULT 0,
    career_best_rank    INTEGER,
    career_best_week    TEXT,

    -- 当年统计（每年重置）
    year_events         INTEGER DEFAULT 0,
    year_matches        INTEGER DEFAULT 0,
    year_wins           INTEGER DEFAULT 0,
    year_losses         INTEGER DEFAULT 0,
    year_games          INTEGER DEFAULT 0,
    year_games_won      INTEGER DEFAULT 0,
    year_games_lost     INTEGER DEFAULT 0,
    year_wtt_titles     INTEGER DEFAULT 0,
    year_all_titles     INTEGER DEFAULT 0,

    scraped_at      TEXT,                  -- 数据抓取时间
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_players_country ON players(country_code);
CREATE INDEX idx_players_slug ON players(slug);
```

### 3.2 event_categories — 赛事分类

赛事分类标准字典。该设计以 `docs/design/DATABASE_DESIGN.md` 为准。

```sql
CREATE TABLE event_categories (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id         TEXT NOT NULL UNIQUE,   -- 唯一标识，如 "WTT_GRAND_SMASH"
    category_name       TEXT NOT NULL,          -- 英文名称
    category_name_zh    TEXT,                   -- 中文名称（与词典同步）
    json_code           TEXT,                   -- ranking JSON 中的缩写，如 "GS"
    sort_order          INTEGER,               -- 排序序号，1-3 为三大赛，1-7 为七大赛
    points_tier         TEXT,                   -- Premium / High / Medium / Low / None
    points_eligible     INTEGER NOT NULL DEFAULT 1,
    filtering_only      INTEGER NOT NULL DEFAULT 0,
    applicable_formats  TEXT,                   -- JSON 数组，如 '["Singles","Doubles","Mixed Doubles"]'
    ittf_rule_name      TEXT                    -- ITTF 规则文档中的正式名称
);

CREATE INDEX idx_event_categories_json_code ON event_categories(json_code);
CREATE INDEX idx_event_categories_points_eligible ON event_categories(points_eligible);
```

### 3.3 event_type_mapping — 原始数据映射

将 `event_list` / `events_calendar` / 其他原始数据中的 `event_type` + `event_kind` 映射到标准赛事分类。

```sql
CREATE TABLE event_type_mapping (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,      -- 原始 event_type 字段
    event_kind      TEXT,               -- 原始 event_kind 字段
    category_id     INTEGER NOT NULL,   -- -> event_categories.id
    priority        INTEGER DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,

    FOREIGN KEY (category_id) REFERENCES event_categories(id) ON DELETE RESTRICT
);

CREATE INDEX idx_event_type_mapping_lookup
    ON event_type_mapping(event_type, event_kind, is_active, priority);
```

### 3.4 sub_event_types — 项目类别字典

对应 `data/sub_events.txt`。

```sql
CREATE TABLE sub_event_types (
    sub_event_type_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT NOT NULL UNIQUE,  -- WS, MS, WD, MD, XD, XT, WT, MT
    name                TEXT NOT NULL,         -- 如 "Women's Singles"
    name_zh             TEXT NOT NULL          -- 如 "女子单打"
);
```

预置数据：

| code | name_zh |
|------|---------|
| WS | 女子单打 |
| MS | 男子单打 |
| WD | 女子双打 |
| MD | 男子双打 |
| XD | 混合双打 |
| XT | 混合团队 |
| WT | 女子团体 |
| MT | 男子团体 |
| CGD | 少年女子双打 | 
| CGT | 少年女子团体 | 
| CXD | 少年混合双打 | 
| HGS | 希望之星女子单打 | 
| JGD | 青少年女子双打 | 
| JGT | 青少年女子团体 | 
| JXD | 青少年混合双打 | 
| MCGS | 小少年女子单打 | 


### 3.5 events — 赛事

存储历史赛事信息。对应 `data/events_list/cn/*.json`。

```sql
CREATE TABLE events (
    event_id            INTEGER PRIMARY KEY,   -- ITTF 赛事 ID，如 3298
    year                INTEGER NOT NULL,
    name                TEXT NOT NULL,         -- 英文赛事名
    name_zh             TEXT,                  -- 中文赛事名
    event_type_name     TEXT,                  -- 原始 event_type
    event_kind          TEXT,                  -- 原始 event_kind
    event_kind_zh       TEXT,
    event_category_id   INTEGER,               -- -> event_categories.id
    category_code       TEXT,                  -- 冗余：event_categories.category_id
    category_name_zh    TEXT,                  -- 冗余：中文分类名，便于前端和审计
    total_matches       INTEGER DEFAULT 0,
    start_date          TEXT,                  -- YYYY-MM-DD
    end_date            TEXT,                  -- YYYY-MM-DD
    location            TEXT,                  -- 举办地
    href                TEXT,                  -- ITTF 详情链接
    scraped_at          TEXT,

    FOREIGN KEY (event_category_id) REFERENCES event_categories(id)
);

CREATE INDEX idx_events_year ON events(year);
CREATE INDEX idx_events_category ON events(event_category_id);
CREATE INDEX idx_events_date ON events(start_date);
```

说明：

- `events.event_type_name` / `event_kind` 保留原始值，便于重新映射
- `events.event_category_id` 为标准化后的赛事分类
- 若暂未命中映射，可允许 `event_category_id` 为空，后续通过 `event_type_mapping` 回填

### 3.6 sub_events — 赛事子项目

一个赛事（event）下有多个子项目（如女单、男单等）。冠军信息存储在此。

```sql
CREATE TABLE sub_events (
    sub_event_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id                INTEGER NOT NULL,
    sub_event_type_code     TEXT NOT NULL,      -- WS, MS, WD, MD, XD 等
    champion_player_ids     TEXT,               -- 冠军球员 ID，多人用逗号分隔
    champion_name           TEXT,               -- 冠军名字，多人用逗号分隔
    champion_country_code   TEXT,

    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
    UNIQUE(event_id, sub_event_type_code)
);

CREATE INDEX idx_sub_events_event ON sub_events(event_id);
```

### 3.7 matches — 比赛记录

存储每一场具体比赛。对应 `data/matches_complete/cn/*.json`。

唯一标识：`event_id + sub_event_type_code + stage + round + player_a_id + player_b_id`

```sql
CREATE TABLE matches (
    match_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id            INTEGER NOT NULL,
    event_name          TEXT,
    event_name_zh       TEXT,
    event_year          INTEGER,
    sub_event_type_code TEXT NOT NULL,      -- WS, MS, WD 等
    stage               TEXT,               -- Qualification / Main Draw
    stage_zh            TEXT,
    round               TEXT,               -- R16, QuarterFinal, SemiFinal, Final 等
    round_zh            TEXT,

    player_a_id         INTEGER,            -- 可能为 NULL，如果未匹配到
    player_a_name       TEXT NOT NULL,
    player_a_country    TEXT,
    player_b_id         INTEGER,
    player_b_name       TEXT,
    player_b_country    TEXT,

    match_score         TEXT,               -- 如 "4-2"
    games               TEXT,               -- JSON 数组
    winner_id           INTEGER,
    winner_name         TEXT NOT NULL,

    raw_row_text        TEXT NOT NULL,
    scraped_at          TEXT,

    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (player_a_id) REFERENCES players(player_id),
    FOREIGN KEY (player_b_id) REFERENCES players(player_id),
    UNIQUE(event_id, sub_event_type_code, stage, round, player_a_id, player_b_id)
);

CREATE INDEX idx_matches_event ON matches(event_id);
CREATE INDEX idx_matches_player_a ON matches(player_a_id);
CREATE INDEX idx_matches_player_b ON matches(player_b_id);
CREATE INDEX idx_matches_winner ON matches(winner_id);
CREATE INDEX idx_matches_sub_event ON matches(sub_event_type_code);
CREATE INDEX idx_matches_year ON matches(event_year);
```

### 3.8 ranking_snapshots — 排名快照

每周生成一条快照记录。

```sql
CREATE TABLE ranking_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,      -- women_singles, men_singles 等
    ranking_week    TEXT NOT NULL,      -- 如 "Week 16, 2026"
    ranking_date    TEXT NOT NULL,      -- YYYY-MM-DD
    total_players   INTEGER,
    scraped_at      TEXT,

    UNIQUE(category, ranking_week)
);
```

### 3.9 ranking_entries — 排名条目

每条快照下的具体排名记录。对应 `data/rankings/cn/*.json` 中的 `rankings` 数组。

```sql
CREATE TABLE ranking_entries (
    entry_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL,
    player_id       INTEGER NOT NULL,
    rank            INTEGER NOT NULL,
    points          INTEGER NOT NULL,
    rank_change     INTEGER DEFAULT 0,

    FOREIGN KEY (snapshot_id) REFERENCES ranking_snapshots(snapshot_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    UNIQUE(snapshot_id, player_id)
);

CREATE INDEX idx_ranking_entries_snapshot ON ranking_entries(snapshot_id);
CREATE INDEX idx_ranking_entries_player ON ranking_entries(player_id);
CREATE INDEX idx_ranking_entries_rank ON ranking_entries(rank);
```

### 3.10 points_breakdown — 积分明细

存储每位运动员当前排名积分来源。对应 rankings JSON 中的 `points_breakdown` 数组。

```sql
CREATE TABLE points_breakdown (
    breakdown_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id         INTEGER NOT NULL,
    player_id           INTEGER NOT NULL,
    event_name          TEXT NOT NULL,
    event_name_zh       TEXT,
    event_type_code     TEXT,            -- 对应 event_categories.json_code，如 GS / WC / WTTC
    category_name_zh    TEXT,            -- 对应标准赛事分类中文名
    position            TEXT,            -- W / F / SF / QF / R16 等
    position_zh         TEXT,
    points              INTEGER NOT NULL,
    expires_on          TEXT,

    FOREIGN KEY (snapshot_id) REFERENCES ranking_snapshots(snapshot_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE INDEX idx_points_breakdown_player ON points_breakdown(player_id);
CREATE INDEX idx_points_breakdown_snapshot ON points_breakdown(snapshot_id);
```

### 3.11 events_calendar — 赛事日历

按年存储赛事日程（含未进行的赛事）。对应 `data/events_calendar/cn/*.json`。

```sql
CREATE TABLE events_calendar (
    calendar_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    year                INTEGER NOT NULL,
    name                TEXT NOT NULL,
    name_zh             TEXT,
    event_type          TEXT,            -- 原始 event_type
    event_kind          TEXT,            -- 原始 event_kind
    event_category_id   INTEGER,         -- -> event_categories.id
    date_range          TEXT,
    date_range_zh       TEXT,
    start_date          TEXT,
    end_date            TEXT,
    location            TEXT,
    location_zh         TEXT,
    status              TEXT,
    href                TEXT,
    event_id            INTEGER,

    FOREIGN KEY (event_category_id) REFERENCES event_categories(id),
    FOREIGN KEY (event_id) REFERENCES events(event_id)
);

CREATE INDEX idx_calendar_year ON events_calendar(year);
CREATE INDEX idx_calendar_date ON events_calendar(start_date);
CREATE INDEX idx_calendar_category ON events_calendar(event_category_id);
```

### 3.12 points_rules — 积分规则

每个赛事分类 + 子分类 + 阶段 + 名次对应一条积分记录（行式存储）。来源于 `docs/ITTF-Ranking-Regulations-20260127.md`。

```sql
CREATE TABLE points_rules (
    rule_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id         INTEGER NOT NULL,      -- -> event_categories.id
    sub_event_category  TEXT NOT NULL,         -- 子分类，如 "Q48" / "Q64" / "Singles"
    draw_qualifier      TEXT,                  -- 签表类型，如 "Main Draw" / "Qualification"
    stage_type          TEXT NOT NULL,         -- 阶段类型，如 "Main Draw" / "Qualification"
    position            TEXT NOT NULL,         -- 名次，如 "W" / "F" / "SF" / "QF" / "R16"
    points              INTEGER NOT NULL,      -- 积分值
    effective_date      TEXT NOT NULL,         -- 生效日期，如 "2026-01-27"

    FOREIGN KEY (category_id) REFERENCES event_categories(id),
    UNIQUE(category_id, sub_event_category, draw_qualifier, stage_type, position, effective_date)
);
```

说明：

- 行式存储比列式（w_points, f_points...）更灵活，便于不同赛事分类有不同的名次级别
- `category_id` 使用正式分类 FK，避免脚本和前端各自维护分类文本
- `effective_date` 支持同一赛事分类在不同规则版本下的积分差异
- 当前 V1 先不导入此表，相关脚本延后到后续实现计划

### 3.13 unmatched_records — 未匹配记录（数据对账表）

存储入库时无法关联到主表的记录，便于人工审查和补全。

```sql
CREATE TABLE unmatched_records (
    record_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type         TEXT NOT NULL,          -- player / event / sub_event / event_category_mapping
    source_name         TEXT NOT NULL,
    source_context      TEXT,
    ingestion_run_id    INTEGER,
    status              TEXT DEFAULT 'pending', -- pending / reviewed / matched / dismissed
    matched_id          INTEGER,
    notes               TEXT,
    reviewed_at         TEXT,
    reviewed_by         TEXT,

    FOREIGN KEY (ingestion_run_id) REFERENCES ingestion_runs(run_id)
);

CREATE INDEX idx_unmatched_type ON unmatched_records(record_type);
CREATE INDEX idx_unmatched_status ON unmatched_records(status);
```

### 3.14 ingestion_runs — 数据摄入记录（运维表）

```sql
CREATE TABLE ingestion_runs (
    run_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type           TEXT NOT NULL,          -- scrape_rankings / scrape_profiles / scrape_matches 等
    status              TEXT NOT NULL DEFAULT 'running',
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    records_processed   INTEGER DEFAULT 0,
    records_matched     INTEGER DEFAULT 0,
    records_unmatched   INTEGER DEFAULT 0,
    error_message       TEXT,
    metadata            TEXT                   -- JSON
);

CREATE INDEX idx_ingestion_runs_task ON ingestion_runs(task_type);
CREATE INDEX idx_ingestion_runs_status ON ingestion_runs(status);
```

---

## 4. 视图

### 4.1 v_event_type_category_mapping

```sql
CREATE VIEW v_event_type_category_mapping AS
SELECT
    m.event_type,
    m.event_kind,
    m.priority,
    m.is_active,
    c.category_id,
    c.category_name,
    c.category_name_zh,
    c.json_code,
    c.points_tier,
    c.points_eligible,
    c.filtering_only,
    c.applicable_formats,
    c.ittf_rule_name
FROM event_type_mapping m
JOIN event_categories c ON m.category_id = c.id;
```

用途：给定 `event_type` + `event_kind`，返回 `category_name_zh`、`json_code`、`points_tier` 等标准化信息。

### 4.2 v_points_eligible_events

```sql
CREATE VIEW v_points_eligible_events AS
SELECT *
FROM event_categories
WHERE points_eligible = 1;
```

用途：筛选参与积分计算的赛事分类。

---

## 5. 数据映射说明

### 5.1 JSON / 规则源 → 表映射

| 数据源 | 目标表 | 说明 |
|---|---|---|
| `data/player_profiles/cn/*.json` | `players` | 每个 JSON 文件对应一条记录 |
| `data/rankings/cn/*.json` → `rankings[]` | `ranking_snapshots` + `ranking_entries` | 顶层信息入 snapshots，每人一条 entry |
| `data/rankings/cn/*.json` → `points_breakdown[]` | `points_breakdown` | 每人多条积分来源 |
| `data/events_list/cn/*.json` → `events[]` | `events` | 每条赛事一条记录 |
| `data/events_calendar/cn/*.json` | `events_calendar` | 日程表独立存储 |
| `data/matches_complete/cn/*.json` → `matches[]` | `matches` | 需解析 `raw_row_text` 提取对手信息 |
| `data/event_category_mapping.json` | `event_categories` | 46 个分类标准定义 |
| `data/event_type_kind.txt` | `event_type_mapping` | 原始 `event_type` / `event_kind` 统计来源 |
| `data/sub_events.txt` | `sub_event_types` | 8 种项目类别 |
| `docs/ITTF-Ranking-Regulations-20260127.md` | `points_rules` | 积分规则原始文档（行式存储，按名次逐条录入） |
| `scripts/data/translation_dict_v2.json` | `event_categories.category_name_zh` 等 | 中文翻译词典 |

### 5.2 赛事分类映射规则

赛事标准化不再直接把自由文本 `event_type` 作为最终分类，而是采用两步法：

1. 原始值保存在 `events.event_type_name`、`events.event_kind`、`events_calendar.event_type`、`events_calendar.event_kind`
2. 通过 `event_type_mapping` 映射到统一的 `event_categories`

说明：

- `events` / `events_calendar` 仍然保留原始字段，便于审计、回填和映射规则迭代
- `event_categories` 才是系统内部统一使用的标准赛事分类层

映射优先级：

- 优先匹配 `event_type + event_kind`
- 若同一 `event_type` 存在多个 `event_kind`，按 `priority` 取最高优先级
- 历史映射不删除，只将 `is_active = 0`
- 未命中的原始值写入 `unmatched_records(record_type='event_category_mapping')`

### 5.3 matches 字段映射注意事项

当前 matches JSON 中部分结构化字段为空（`side_a`、`side_b`、`opponents` 等），需要从 `raw_row_text` 解析：

```
双打 raw_row_text 格式：
"2026 | 赛事名 | 选手A (国家A) | 选手C (国家A) | 选手B (国家B) | 选手D (国家B) | 项目 | 阶段 | 轮次 | 比分 | 局分... | 胜者"
```

```
单打 raw_row_text 格式 有如下两种：
"2026 | 赛事名 | 选手A (国家A) |  | 选手B (国家B) | | 项目 | 阶段 | 轮次 | 比分 | 局分... | 胜者"
"2026 | 赛事名 | 选手A (国家A) | 选手B (国家B) | 项目 | 阶段 | 轮次 | 比分 | 局分... | 胜者"
```

### 5.4 孤立数据处理策略

matches / events / calendar 中可能存在以下情况：

- 孤立的 `player`：比赛记录中的选手在 `players` 表里找不到
- 孤立的 `event`：比赛记录中的 `event_id` 或赛事名称无法关联到 `events`
- 孤立的 `event_category_mapping`：`event_type + event_kind` 暂未收录到标准映射
- 孤立的 `sub_event_type`：`sub_event_type_code` 不在字典表中

处理流程：

1. 宽松外键约束：部分关联字段允许为空，避免因单条脏数据阻塞整批入库
2. 标准化映射：优先通过 `event_type_mapping` 归类赛事
3. 名称匹配：选手按 `name + country_code` 优先精确匹配，再进行模糊匹配
4. 无法匹配：写入 `unmatched_records`
5. 报告生成：输出总记录数、成功关联数、未关联数和典型问题列表

### 5.5 player_id 关联详细逻辑

```python
for match in matches:
    player_a_id = lookup_player_id(
        name=match["player_a_name"],
        country_code=match["player_a_country"]
    )
    if player_a_id is None:
        insert_into_unmatched_records(
            record_type="player",
            source_name=match["player_a_name"],
            source_context=f"country={match['player_a_country']}, event={match['event_id']}",
            ingestion_run_id=current_run_id
        )

    insert_into_matches(
        event_id=match["event_id"],
        player_a_id=player_a_id,
        player_a_name=match["player_a_name"],
        ...
    )
```

### 5.6 sub_events 数据来源

`sub_events` 表的数据来源如下：

1. 优先来自 `matches` 中 `Main Draw + Final` 的聚合结果
2. 如果比赛数据不完整，可人工补录 `sub_events`

说明：

- 单打场景下，`champion_player_ids` 可直接存一个 ID
- 双打 / 团体场景下，需按冠军成员拼接为逗号分隔的 ID 列表，不能直接复用 `winner_id` 单值

```sql
INSERT INTO sub_events (event_id, sub_event_type_code, champion_name, champion_player_ids)
SELECT DISTINCT
    m.event_id,
    m.sub_event_type_code,
    m.winner_name,
    CASE
        WHEN m.winner_id IS NOT NULL THEN CAST(m.winner_id AS TEXT)
        ELSE NULL
    END
FROM matches m
WHERE m.stage = 'Main Draw'
  AND m.round = 'Final'
  AND m.winner_name IS NOT NULL;
```

### 5.7 points_tier 说明

| 等级 | 赛事 |
|------|------|
| Premium | WTT 大满贯、奥运会、ITTF 世锦赛决赛、ITTF 世界杯、WTT 总决赛、世界团体赛 |
| High | WTT 冠军赛 |
| Medium | WTT 球星挑战赛、WTT 挑战赛、洲际锦标赛 / 杯 / 运动会 |
| Low | WTT 支线赛、青年赛事、地区赛 |
| None | 历史赛事（ITTF Challenge / World Tour 等）、奥运资格赛 |

---

## 6. 关键查询示例

### 6.1 排名页 — 获取最新排名

```sql
SELECT re.rank, re.points, re.rank_change,
       p.player_id, p.name, p.name_zh, p.slug,
       p.country_code, p.avatar_file
FROM ranking_entries re
JOIN ranking_snapshots rs ON re.snapshot_id = rs.snapshot_id
JOIN players p ON re.player_id = p.player_id
WHERE rs.category = 'women_singles'
  AND rs.ranking_date = (
      SELECT MAX(ranking_date) FROM ranking_snapshots
      WHERE category = 'women_singles'
  )
ORDER BY re.rank;
```

### 6.2 运动员详情 — 积分明细

```sql
SELECT pb.event_name_zh,
       pb.category_name_zh,
       pb.position_zh,
       pb.points,
       pb.expires_on
FROM points_breakdown pb
JOIN ranking_snapshots rs ON pb.snapshot_id = rs.snapshot_id
WHERE pb.player_id = 131163
  AND rs.ranking_date = (
      SELECT MAX(ranking_date) FROM ranking_snapshots
      WHERE category = 'women_singles'
  )
ORDER BY pb.points DESC;
```

### 6.3 赛事列表 — 带标准分类查询

```sql
SELECT e.event_id,
       e.year,
       e.name_zh,
       c.category_name_zh,
       c.json_code,
       c.points_tier,
       e.start_date,
       e.end_date
FROM events e
LEFT JOIN event_categories c ON e.event_category_id = c.id
WHERE e.year = 2026
ORDER BY e.start_date DESC;
```

### 6.4 给定原始类型查询标准分类

```sql
SELECT category_name_zh, json_code, points_tier, points_eligible
FROM v_event_type_category_mapping
WHERE event_type = 'WTT Youth Series'
  AND event_kind = 'WTT Youth Contender'
  AND is_active = 1
ORDER BY priority DESC
LIMIT 1;
```

### 6.5 赛事详情 — 对战图

```sql
SELECT m.sub_event_type_code, m.stage, m.round,
       m.player_a_name, m.player_b_name,
       m.match_score, m.winner_name
FROM matches m
WHERE m.event_id = 3379
  AND m.sub_event_type_code = 'WS'
ORDER BY
    CASE m.stage WHEN 'Qualification' THEN 0 ELSE 1 END,
    CASE m.round
        WHEN 'Final' THEN 7
        WHEN 'SemiFinal' THEN 6
        WHEN 'QuarterFinal' THEN 5
        WHEN 'R16' THEN 4
        WHEN 'R32' THEN 3
        WHEN 'R64' THEN 2
        ELSE 1
    END;
```

### 6.6 交手记录查询

```sql
SELECT m.event_name, m.event_year, m.round_zh,
       m.match_score, m.games, m.winner_name
FROM matches m
WHERE (m.player_a_id = :player1 AND m.player_b_id = :player2)
   OR (m.player_a_id = :player2 AND m.player_b_id = :player1)
ORDER BY m.event_year DESC;
```

---

## 7. 入库流程

```
JSON / 规则文档 → Python 入库脚本 → SQLite（含标准化映射与数据对账）

步骤：
1. 初始化：执行 DDL 建表
2. 字典表：导入 event_categories、event_type_mapping、sub_event_types
3. 球员：遍历 player_profiles/cn/*.json → players
4. 赛事：遍历 events_list/cn/*.json → events
   - 保留原始 event_type / event_kind
   - 通过 event_type_mapping 归类到 event_categories
   - 未命中映射则写入 unmatched_records
5. 排名：遍历 rankings/cn/*.json → ranking_snapshots + ranking_entries + points_breakdown
6. 比赛：遍历 matches_complete/cn/*.json → matches
   - 解析 raw_row_text 提取名字
   - 通过 name + country_code 匹配 player_id
   - 如无法匹配，写入 unmatched_records
7. 聚合：从 matches Final 记录生成 sub_events
8. 日历：遍历 events_calendar/cn/*.json → events_calendar
   - 优先依赖数据库中的 `events` 补全 event_type / event_kind / event_category_id
   - 未命中时保留原始赛历字段，后续再补映射
9. 数据对账：生成摄入报告
   - 各表成功率
   - 未匹配记录统计
   - 分类映射覆盖率
10. 输出：
   - 更新 ingestion_runs
   - 生成 unmatched_records 待人工审查
   - 生成摄入报告供人工排查
```

---

## 8. 数据来源

| 文件 | 用途 |
|------|------|
| `data/player_profiles/cn/*.json` | 运动员主档数据来源 |
| `data/rankings/cn/*.json` | 排名快照、排名条目、积分明细来源 |
| `data/events_list/cn/*.json` | 历史赛事主数据来源 |
| `data/events_calendar/cn/*.json` | 赛事日历来源 |
| `data/matches_complete/cn/*.json` | 比赛记录与 `sub_events` 聚合来源 |
| `data/event_category_mapping.json` | 46 个分类的标准定义，`category_name_zh` 与词典同步 |
| `data/event_type_kind.txt` | 原始 `event_type` / `event_kind` 统计 |
| `docs/ITTF-Ranking-Regulations-20260127.md` | 积分规则原始文档 |
| `scripts/data/translation_dict_v2.json` | 中文翻译词典 |
| `scripts/db/create_event_category_tables.sql` | 赛事分类相关建表 SQL |
| `scripts/db/import_event_categories_data.sql` | 分类数据导入 SQL（由 Python 脚本生成） |
| `scripts/db/import_event_categories.py` | 从 JSON 重新生成导入 SQL |

---

## 9. 注意事项与后续规划

### 已知数据问题

结构化字段缺失：

- matches JSON 中 `side_a`、`side_b`、`opponents` 等字段为空，需从 `raw_row_text` 解析
- `player_id` 为 null，需要通过姓名 + 国家代码匹配
- `winner` 字段为空，需从 `raw_row_text` 最后字段提取
- 部分 `round` 字段缺失

数据一致性问题：

- 某些 matches 中的玩家不在 `players` 表里
- 某些 events 的 match 数据不完整，尤其是早期赛事
- 原始 `event_type + event_kind` 可能出现新值，需持续维护 `event_type_mapping`
- 球员名字可能有拼写变体、别名

处理方案：

- `unmatched_records` 表记录无法关联的记录
- 允许 `matches.player_a_id` 等外键为空
- 入库脚本生成对账报告，供人工补全和维护
- 赛事分类相关标准定义统一由 `event_categories` 维护，避免前端和脚本各自维护一套枚举

### V2 扩展方向

- 支持男单及双打项目：schema 已预留 `sub_event_type_code`
- 搜索功能：可基于 SQLite FTS5 全文索引或 LLM API
- 历史排名趋势：`ranking_snapshots` 已支持多周快照对比
- 赛事积分自动计算：`points_rules` 可驱动积分验证逻辑
- 别名映射表：为常见拼写变体、别名建立 `player_aliases` 表
- 若后续需要更强约束，可将 `applicable_formats` 从 JSON 文本拆分为独立关联表
