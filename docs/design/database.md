# 数据库设计方案

版本：v1.0
日期：2026-04-16
数据库：SQLite

---

## 1. 设计原则

- SQLite 为线上查询唯一数据源，JSON 文件仅作离线审计与回放用途
- 中英文字段并存，便于前端直接消费
- 所有时间字段统一 ISO8601 格式（`YYYY-MM-DD` 或 `YYYY-MM-DDTHH:MM:SS`）
- `country_code` 统一 ISO 3166-1 alpha-3（如 CHN、JPN、GER）
- V1 范围：女子单打为主，schema 兼容全项目扩展

---

## 2. ER 关系概览

```
event_types 1──N events
events      1──N sub_events
sub_events  1──N matches
players     1──N matches (通过 player_a_id / player_b_id)
players     1──N ranking_entries
players     1──N points_breakdown
ranking_snapshots 1──N ranking_entries
sub_event_types (字典表，独立)
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

### 3.2 event_types — 赛事类别字典

对应 `data/event_type.txt` 和 `data/event_type.selected`。

```sql
CREATE TABLE event_types (
    event_type_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,  -- 如 "WTT Grand Smash"
    name_zh         TEXT,                  -- 如 "WTT大满贯"
    code            TEXT,                  -- 简称，如 "GS", "WTTC", "WC"（手动维护）
    is_selected     INTEGER DEFAULT 0,    -- 是否为重要赛事（出现在 event_type.selected 中）
    sort_order      INTEGER DEFAULT 0     -- 排序权重（越大越靠前）, 用于标识三大赛、九大赛
);
```

### 3.3 sub_event_types — 项目类别字典

对应 `data/sub_events.txt`。

```sql
CREATE TABLE sub_event_types (
    sub_event_type_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT NOT NULL UNIQUE,  -- WS, MS, WD, MD, XD, XT, WT, MT
    name                TEXT NOT NULL,          -- 如 "Women's Singles"
    name_zh             TEXT NOT NULL           -- 如 "女子单打"
);
```

预置数据：

| code | name_zh  |
|------|----------|
| WS   | 女子单打 |
| MS   | 男子单打 |
| WD   | 女子双打 |
| MD   | 男子双打 |
| XD   | 混合双打 |
| XT   | 混合团队 |
| WT   | 女子团体 |
| MT   | 男子团体 |

### 3.4 events — 赛事

存储历史赛事信息。对应 `data/events_list/cn/*.json`。

```sql
CREATE TABLE events (
    event_id        INTEGER PRIMARY KEY,   -- ITTF 赛事 ID，如 3298
    year            INTEGER NOT NULL,
    name            TEXT NOT NULL,          -- 英文赛事名
    name_zh         TEXT,                   -- 中文赛事名
    event_type_id   INTEGER,               -- 关联 event_types
    event_type_name TEXT,                   -- 冗余：原始赛事类别名（用于未映射情况）
    event_kind      TEXT,                   -- 赛事子类别（如 "WTT Contender"）
    event_kind_zh   TEXT,
    total_matches   INTEGER DEFAULT 0,     -- 该赛事比赛总数
    start_date      TEXT,                  -- YYYY-MM-DD
    end_date        TEXT,                  -- YYYY-MM-DD
    location        TEXT,                  -- 举办地
    href            TEXT,                  -- ITTF 详情链接
    scraped_at      TEXT,

    FOREIGN KEY (event_type_id) REFERENCES event_types(event_type_id)
);

CREATE INDEX idx_events_year ON events(year);
CREATE INDEX idx_events_type ON events(event_type_id);
CREATE INDEX idx_events_date ON events(start_date);
```

### 3.5 sub_events — 赛事子项目

一个赛事（event）下有多个子项目（如女单、男单等）。冠军信息存储在此。

```sql
CREATE TABLE sub_events (
    sub_event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id            INTEGER NOT NULL,
    sub_event_type_code TEXT NOT NULL,         -- WS, MS, WD, MD, XD 等
    champion_player_ids TEXT,                  -- 冠军球员 ID，多人用逗号分隔，如 "131163" 或 "131163,121411"
    champion_name       TEXT,                  -- 冠军名字，多人用逗号分隔，如 "SUN Yingsha" 或 "SUN Yingsha,WANG Manyu"
    champion_country_code TEXT,                -- 国家代码

    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
    UNIQUE(event_id, sub_event_type_code)
);

CREATE INDEX idx_sub_events_event ON sub_events(event_id);
```

### 3.6 matches — 比赛记录

存储每一场具体比赛。对应 `data/matches_complete/cn/*.json`。

唯一标识：`event_id + sub_event_type_code + stage + round + player_a_id + player_b_id`

```sql
CREATE TABLE matches (
    match_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id            INTEGER NOT NULL,
    event_name          TEXT,                  -- 冗余赛事英文名（方便查询展示）
    event_name_zh       TEXT,                  -- 冗余赛事中文名
    event_year          INTEGER,
    sub_event_type_code TEXT NOT NULL,          -- WS, MS, WD 等
    stage               TEXT,                  -- Qualification / Main Draw
    stage_zh            TEXT,
    round               TEXT,                  -- R16, QuarterFinal, SemiFinal, Final 等
    round_zh            TEXT,

    -- 对阵双方（单打为 1 人，双打为 2 人组合用斜杠分隔）
    player_a_id         INTEGER,               -- 选手A的 player_id
    player_a_name       TEXT,                  -- 选手A 英文名
    player_a_country    TEXT,                  -- 选手A 国家代码
    player_b_id         INTEGER,               -- 选手B
    player_b_name       TEXT,
    player_b_country    TEXT,

    match_score         TEXT,                  -- 如 "4-2"
    games               TEXT,                  -- JSON 数组，如 '["11:3","11:4","9:11","11:6","11:8"]'
    winner_id           INTEGER,               -- 胜者 player_id
    winner_name         TEXT,                  -- 胜者名字（兜底）

    raw_row_text        TEXT,                  -- 原始行文本（审计用）
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

### 3.7 ranking_snapshots — 排名快照

每周生成一条快照记录。

```sql
CREATE TABLE ranking_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,         -- women_singles, men_singles 等
    ranking_week    TEXT NOT NULL,          -- 如 "Week 16, 2026"
    ranking_date    TEXT NOT NULL,          -- YYYY-MM-DD
    total_players   INTEGER,
    scraped_at      TEXT,

    UNIQUE(category, ranking_week)
);
```

### 3.8 ranking_entries — 排名条目

每条快照下的具体排名记录。对应 `data/rankings/cn/*.json` 中的 rankings 数组。

```sql
CREATE TABLE ranking_entries (
    entry_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL,
    player_id       INTEGER NOT NULL,
    rank            INTEGER NOT NULL,
    points          INTEGER NOT NULL,
    rank_change     INTEGER DEFAULT 0,     -- 排名变动（正数上升，负数下降，0不变，NULL新入榜）

    FOREIGN KEY (snapshot_id) REFERENCES ranking_snapshots(snapshot_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    UNIQUE(snapshot_id, player_id)
);

CREATE INDEX idx_ranking_entries_snapshot ON ranking_entries(snapshot_id);
CREATE INDEX idx_ranking_entries_player ON ranking_entries(player_id);
CREATE INDEX idx_ranking_entries_rank ON ranking_entries(rank);
```

### 3.9 points_breakdown — 积分明细

存储每位运动员当前排名积分的来源明细。对应 rankings JSON 中的 `points_breakdown` 数组。

```sql
CREATE TABLE points_breakdown (
    breakdown_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL,      -- 关联排名快照
    player_id       INTEGER NOT NULL,
    event_name      TEXT NOT NULL,          -- 赛事英文名
    event_name_zh   TEXT,                  -- 赛事中文名
    event_type_code TEXT,                  -- 赛事类别简称，关联 event_types.code（如 GS, WC, WTTC）
    event_type_code_zh TEXT,               -- 赛事类别中文简称（如 大满贯、世界杯）
    position        TEXT,                  -- W, F, SF, QF, R16 等
    position_zh     TEXT,                  -- 冠军、亚军 等
    points          INTEGER NOT NULL,
    expires_on      TEXT,                  -- 积分到期日 YYYY-MM-DD

    FOREIGN KEY (snapshot_id) REFERENCES ranking_snapshots(snapshot_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE INDEX idx_points_breakdown_player ON points_breakdown(player_id);
CREATE INDEX idx_points_breakdown_snapshot ON points_breakdown(snapshot_id);
```

### 3.10 events_calendar — 赛事日历

按年存储赛事日程（含未进行的赛事）。对应 `data/events_calendar/cn/*.json`。

```sql
CREATE TABLE events_calendar (
    calendar_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL,
    name            TEXT NOT NULL,
    name_zh         TEXT,
    date_range      TEXT,                  -- 原始日期范围文本，如 "02-05 Jan"
    date_range_zh   TEXT,
    start_date      TEXT,                  -- 解析后的 YYYY-MM-DD（可为空）
    end_date        TEXT,
    location        TEXT,                  -- 国家代码
    location_zh     TEXT,                  -- 国家中文名
    status          TEXT,                  -- 赛事状态（如取消等）
    href            TEXT,                  -- WTT 官网链接
    event_id        INTEGER,              -- 关联 events 表（赛事完成后可关联）

    FOREIGN KEY (event_id) REFERENCES events(event_id)
);

CREATE INDEX idx_calendar_year ON events_calendar(year);
CREATE INDEX idx_calendar_date ON events_calendar(start_date);
```

### 3.11 points_rules — 积分规则表

存储各赛事类型各轮次的积分规则。对应 `docs/ITTF-Ranking-Regulations-CN-20260127.md` 中的积分表。

```sql
CREATE TABLE points_rules (
    rule_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_category      TEXT NOT NULL,      -- 赛事类别，如 "WTT Grand Smash", "Olympic Games"
    event_category_zh   TEXT,
    sub_event_category  TEXT NOT NULL,      -- singles / doubles / mixed_doubles / team
    draw_qualifier      TEXT,              -- 签表规模条件，如 "Q48/Q64", "MD32"（无条件则为空）
    stage_type          TEXT NOT NULL,      -- main_draw / qualification / qual_extra
    position            TEXT NOT NULL,      -- W, F, SF, QF, R16, R32, R64, R128, QUAL, QER 等
    points              INTEGER NOT NULL,
    effective_date      TEXT NOT NULL,      -- 规则生效日期 YYYY-MM-DD（规则会更新，需标记版本）

    UNIQUE(event_category, sub_event_category, draw_qualifier, stage_type, position, effective_date)
);
```

### 3.12 ingestion_runs — 数据摄入记录（运维表）

```sql
CREATE TABLE ingestion_runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type       TEXT NOT NULL,          -- scrape_rankings, scrape_profiles, scrape_matches 等
    status          TEXT NOT NULL DEFAULT 'running',  -- running, success, failed
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    records_count   INTEGER DEFAULT 0,     -- 处理记录数
    error_message   TEXT,
    metadata        TEXT                   -- JSON 格式的额外信息
);
```

---

## 4. 数据映射说明

### 4.1 JSON → 表映射

| JSON 数据源 | 目标表 | 说明 |
|---|---|---|
| `data/player_profiles/cn/*.json` | `players` | 每个 JSON 文件对应一条记录 |
| `data/rankings/cn/*.json` → rankings[] | `ranking_snapshots` + `ranking_entries` | 顶层信息入 snapshots，每人一条 entry |
| `data/rankings/cn/*.json` → points_breakdown[] | `points_breakdown` | 每人多条积分来源 |
| `data/events_list/cn/*.json` → events[] | `events` | 每条赛事一条记录 |
| `data/events_calendar/cn/*.json` → events[] | `events_calendar` | 日程表独立存储 |
| `data/matches_complete/cn/*.json` → matches[] | `matches` | 需解析 raw_row_text 提取对手信息 |
| `data/event_type.txt` | `event_types` | 每行一个赛事类别 |
| `data/sub_events.txt` | `sub_event_types` | 8 种项目类别 |

### 4.2 matches 字段映射注意事项

当前 matches JSON 中部分结构化字段为空（`side_a`, `side_b`, `opponents` 等为空数组），需要从 `raw_row_text` 解析：

```
raw_row_text 格式：
"2026 | 赛事名 | 选手A (国家A) | 选手B (国家B) | 项目 | 阶段 | 轮次 | 比分 | 局分... | 胜者"
```

解析规则：
- 按 `|` 分割
- 字段[2]: 选手A + 国家
- 字段[3]: 选手B + 国家
- 字段[4]: sub_event_type_code
- 字段[5]: stage
- 字段[6]: round（若不含 round 信息则可能合并到 stage）
- 最后字段: winner name

### 4.3 player_id 关联

matches JSON 中没有直接的 player_id，需要通过名字 + 国家代码匹配 players 表。入库脚本需要：
1. 先建立 `name + country_code → player_id` 的查找表
2. 匹配不上的记录标记为待人工审核

### 4.4 sub_events 数据来源

sub_events 表的数据可以从 matches 表中聚合得到：
```sql
-- 从 matches 中生成 sub_events
INSERT INTO sub_events (event_id, sub_event_type_code, champion_name, champion_country_code)
SELECT DISTINCT
    m.event_id,
    m.sub_event_type_code,
    m.winner_name,
    m.player_a_country  -- 需要更精确的逻辑
FROM matches m
WHERE m.stage = 'Main Draw'
  AND m.round = 'Final';
```

---

## 5. 关键查询示例

### 5.1 排名页 — 获取最新排名

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

### 5.2 运动员详情 — 积分明细

```sql
SELECT pb.event_name_zh, pb.category_zh, pb.position_zh,
       pb.points, pb.expires_on
FROM points_breakdown pb
JOIN ranking_snapshots rs ON pb.snapshot_id = rs.snapshot_id
WHERE pb.player_id = 131163
  AND rs.ranking_date = (
      SELECT MAX(ranking_date) FROM ranking_snapshots
      WHERE category = 'women_singles'
  )
ORDER BY pb.points DESC;
```

### 5.3 运动员比赛记录

```sql
SELECT m.event_name, m.event_year, m.sub_event_type_code,
       m.stage_zh, m.round_zh, m.match_score, m.games,
       m.player_b_name AS opponent,
       CASE WHEN m.winner_id = 131163 THEN 'W' ELSE 'L' END AS result
FROM matches m
WHERE m.player_a_id = 131163 OR m.player_b_id = 131163
ORDER BY m.event_year DESC, m.event_id;
```

### 5.4 赛事详情 — 对战图

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

### 5.5 交手记录查询

```sql
SELECT m.event_name, m.event_year, m.round_zh,
       m.match_score, m.games, m.winner_name
FROM matches m
WHERE (m.player_a_id = :player1 AND m.player_b_id = :player2)
   OR (m.player_a_id = :player2 AND m.player_b_id = :player1)
ORDER BY m.event_year DESC;
```

---

## 6. 入库流程

```
JSON 文件 → Python 入库脚本 → SQLite

步骤：
1. 初始化：执行 DDL 建表
2. 字典表：导入 event_types, sub_event_types
3. 球员：遍历 player_profiles/cn/*.json → players
4. 赛事：遍历 events_list/cn/*.json → events
5. 排名：遍历 rankings/cn/*.json → ranking_snapshots + ranking_entries + points_breakdown
6. 比赛：遍历 matches_complete/cn/*.json → matches（需解析 raw_row_text）
7. 聚合：从 matches 生成 sub_events
8. 日历：遍历 events_calendar/cn/*.json → events_calendar
9. 校验：运行完整性检查（外键一致性、记录数对比）
```

---

## 7. 注意事项与后续规划

### 已知数据问题
- matches JSON 中 `side_a`, `side_b`, `opponents` 等字段为空，需从 `raw_row_text` 解析
- matches JSON 中 `player_id` 为 null，需要通过姓名匹配
- `winner` 字段为空，需从 `raw_row_text` 最后字段提取
- 部分 round 字段缺失（如 QuarterFinal, SemiFinal 未填入 round 字段）

### V2 扩展方向
- 支持男单及双打项目：schema 已预留 sub_event_type_code
- 搜索功能：可基于 SQLite FTS5 全文索引或 LLM API
- 历史排名趋势：ranking_snapshots 已支持多周快照对比
- 赛事积分自动计算：points_rules 表可驱动积分验证逻辑
