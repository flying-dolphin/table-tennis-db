# WTT Historical Event Import Issues Plan

最后更新：2026-06-26

本文跟踪 `scripts/run_import_wtt_events.sh --since "2026-06-25 10:00:00"` 后发现的问题。修复完成后移入 `docs/archive/`。

## 背景

本轮增量导入从 `data/event_matches/cn/*.json` 中按 mtime 解析出 event id，再执行：

```bash
python scripts/db/import_matches.py --source-dir data/event_matches/cn --event-id ...
python scripts/db/import_event_draw_matches.py --event-id <event_id>
python scripts/db/import_sub_events.py --event-id <event_id>
```

本次 `--since` 解析到的 event id 包括：

```text
3391, 3406, 3407, 3216, 3238, 3239, 3240, 3361, 3358, 3360,
3271, 3241, 3308, 3311, 3307, 3305, 3309, 3312, 3478, 3310,
3320, 3306, 3313
```

## 问题 1：新增赛事前端球员名显示英文

### 现象

前端详细比赛页面中，本次新增 event id 的 player 都显示英文名。旧 event 仍能显示中文人名。

这说明问题不应简单归因于 `side_a_zh` / `winner_zh` 没有入库。历史表中这些字段本来就不存在或为空，但旧赛事仍能显示中文，前端很可能通过 `match_side_players.player_id -> players.name_zh` 或其他 player resolution 路径展示中文。

### 已知证据

`data/event_matches/cn/WTT_Contender_Skopje_2026_3239.json` 中存在翻译字段：

```json
{
  "winner": "PLAIAN Tania",
  "winner_zh": "普莱安·塔妮娅",
  "side_a": ["VEGA Paulina (CHI)"],
  "side_a_zh": ["维加·保琳娜 (智利)"],
  "side_b": ["PLAIAN Tania (ROU)"],
  "side_b_zh": ["普莱安·塔妮娅 (罗马尼亚)"]
}
```

数据库抽查显示 `matches` 的赛事、阶段、轮次中文已写入：

```sql
SELECT match_id, event_id, event_name, event_name_zh,
       sub_event_type_code, stage, stage_zh, round, round_zh,
       winner_name, winner_side
FROM matches
WHERE event_id = 3239
LIMIT 10;
```

但 `match_side_players.player_id` 当前全为空：

```sql
SELECT COUNT(*) AS total_players,
       SUM(CASE WHEN player_id IS NOT NULL THEN 1 ELSE 0 END) AS with_player_id
FROM match_side_players;
```

本地结果：

```text
total_players = 563198
with_player_id = 0
```

这表明历史 `import_matches.py` 当前没有把比赛球员解析回 `players.player_id`。如果旧前端能显示中文，需进一步确认旧赛事中文来源是否不是当前 `match_side_players.player_id`，或当前数据库已经被新的全量/增量导入清空了旧的 player_id 关联。

### 待验证

1. 前端详细比赛页面具体使用哪个查询展示 player 中文。

   重点查：

   - `web/lib/server/events.ts`
   - `web/lib/server/players.ts`
   - `web/lib/server/compare.ts`

2. 旧 event 的详细比赛中文名是否仍然来自 `players.name_zh`。

   对一个前端显示正常的旧 event 执行：

   ```sql
   SELECT m.event_id, m.match_id, ms.side_no,
          msp.player_id, msp.player_name, msp.player_country,
          p.name_zh, p.country_code
   FROM matches m
   JOIN match_sides ms ON ms.match_id = m.match_id
   JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
   LEFT JOIN players p ON p.player_id = msp.player_id
   WHERE m.event_id = <old_event_id>
   LIMIT 20;
   ```

3. 确认 `import_matches.py` 是否历史上曾经做过 player resolution，还是一直没有做。

   当前代码中明确存在：

   ```python
   player_id = None
   ```

### 初步处理方向

优先修复 player resolution，而不是先扩 `match_side_players` 中文字段。

原因：

- 旧赛事能显示中文，说明前端已有通过 canonical `players` 表展示中文的路径。
- 修复 `player_id` 还能同时改善 `sub_events.champion_player_ids`、球员页记录、H2H 等统计链路。
- `side_a_zh` / `winner_zh` 可作为 fallback，但不应替代 canonical player identity。

## 问题 2：输出按 event 分散，人工检查信息难找

### 现象

`run_import_wtt_events.sh --since ...` 对每个 event 单独执行：

```bash
python scripts/db/import_event_draw_matches.py --event-id <event_id>
python scripts/db/import_sub_events.py --event-id <event_id>
```

因此 `unmatched champion members`、problem events 等人工检查信息散落在大量输出里，需要从头翻找。

### 优化处理方向（结构化 JSON，不解析文本）

#### 核心决策

三个导入脚本内部**已经构建了完整的结构化结果字典**，人工检查需要的信息全在里面：

- `import_matches.py` → `result`：`skipped_files`、`unmatched_events`、
  `raw_event_mismatch_examples`、`unresolved_winner_side`
  （见 `scripts/db/import_matches.py:468-474`）
- `import_event_draw_matches.py` → `stats`：`unsupported_main_round`、
  `duplicate_match_ids` 等
- `import_sub_events.py` → `result`：`problem_events`、
  `unmatched_champion_members`（见 `scripts/db/import_sub_events.py:690-697`）

问题纯粹在**呈现层**：这些 dict 被 `print` 成人类文本后，又被 bash 的
per-event 循环（`run_import_wtt_events.sh:138-141`）打散到几十段输出里。

因此**不走 grep/解析人类文本的路线**（脆弱、每次改 print 就坏），而是让脚本
直接吐结构化 JSON，bash 只做编排，最后由聚合器渲染统一摘要。

#### 设计

1. **三个脚本各加 `--summary-json PATH` 选项**（复用已有 dict，低成本）：

   - 全量 stdout 照旧打印，保留现场。
   - `set` 字段（如 `unmatched_events`）序列化前转 `sorted(list)`。
   - 支持 `--summary-json auto`，沿用本仓库 `promote_current_event.py
     --unmatched-out auto` 约定，写到 per-run 日志目录。

2. **`run_import_wtt_events.sh` 建立 per-run 日志目录**：

   ```text
   data/logs/wtt-event-import/<run_id>/
     import_matches.log     import_matches.json
     draw/<event_id>.log    draw/<event_id>.json
     sub_events/<eid>.log   sub_events/<eid>.json
   ```

   `run_id` 用时间戳。每条命令 `2>&1 | tee` 到 `.log`，同时 `--summary-json`
   产出 `.json`。

3. **末尾 Python 聚合器**读所有 `.json`，渲染统一的
   `⚠ MANUAL CHECK REQUIRED` 区块：

   ```text
   ============ WTT Import Summary  run=20260626-1012 ============
   Event ids (23): 3216 3238 3239 ...
   import_matches: inserted=4821 unresolved_winner_side=3 skipped_files=5
     skipped (name mismatch):  3406, 3216, 3305
     skipped (not in events):  3391, 3407
     unresolved winner_side:   3478 (3 rows, score 0-0 → 未完赛)
   per-event problems:
     3239 sub_events: unmatched champion members=7 (JORGIC Darko, ...)
     3313 ⚠ HARD MISMATCH payload≠db (Sao Jose vs Rio De Janeiro)
   detailed logs: data/logs/wtt-event-import/20260626-1012/
   ==============================================================
   ```

   无问题的 event 不打印，只列有 manual-check 项的。脚本仍 `exit 0`，但用明确
   的 `⚠ MANUAL CHECK REQUIRED` 标题，避免被漏看。

#### 保留 per-event 编排（约束）

本方案**保留 bash per-event rebuild 循环**，只改输出。

> 更彻底的可选项（不在本期）：给 `import_event_draw_matches.py` /
> `import_sub_events.py` 也加 `--event-id ID...` 多值支持（`import_matches.py`
> 已是这样），bash 只调一次、脚本内部循环、天然产出合并摘要，省掉 N 次解释器/
> DB 启动开销，也不需要外部聚合器。属于行为重构，后续单独评估。

## 问题 3：Import Matches 输出 warning 的含义

### `Unresolved winner_side: 3`

抽查发现 3 条来自 `event_id=3478`：

```text
match_score = 0-0
winner_name = ''
winner_side = NULL
```

源 `raw_row_text` 类似：

```text
2026 | WTT Youth Contender San Francisco II 2026 | LIN Ryan (USA) |  | LO Austin (USA) |  | U17MS | Qualification |  | 0 - 0 | 0:0 0:0 0:0 |  |  |
```

这更像源数据未完赛或空结果，不是导入器无法处理正常完赛比赛。

### `Skipped files`

本轮输出中的 skipped files 分几类：

1. `event_id` 在文件中存在，但 `events` 表没有可匹配记录。

   示例：

   ```text
   3391 ETTU_European_U21_Championships_Cluj-Napoca_2026_3391.json
   3407 ITTF-Americas_South_American_Championships_Santiago_2026_3407.json
   ```

2. 文件 payload 名称和 `events` 表名称不完全一致。

   示例：

   ```text
   3406: Central American vs Central America
   3216: ITTF World Team Table Tennis Championships vs ITTF World Team Championships
   3305: apostrophe ' vs ’
   ```

3. 可能是真实错配，需要人工核对。

   示例：

   ```text
   3313: payload='WTT Youth Star Contender Sao Jose 2026',
         db='WTT Youth Star Contender Rio De Janeiro 2026'
   ```

### 初步处理方向

1. 增量模式下 `import_matches.py` 应优先只扫描目标 event id 对应的文件，减少无关 skipped files 噪音。
2. 对名称匹配做更稳健的 normalization：
   - 统一 ASCII apostrophe 和 curly apostrophe
   - 对少量已知官方简称差异做 override
3. 对真实错配保留 hard skip，并进入汇总区。

## 问题 4：Import Sub Events 中 unmatched champion members 很多

### 现象

例如 `event_id=3239`：

```text
unmatched champion members: 7
  - JORGIC Darko (SLO)
  - KIHARA Miyuu (JPN)
  - KOBAYASHI Hiromu (JPN)
  - LIM Jonghoon (KOR)
```

数据库中 `sub_events` 已能写冠军名字：

```sql
SELECT sub_event_type_code, champion_name, champion_player_ids, champion_country_code
FROM sub_events
WHERE event_id = 3239;
```

结果示例：

```text
MD  LIM Jonghoon,OH Junsung        champion_player_ids=","
MS  JORGIC Darko                   champion_player_ids=NULL
WD  ODO Satsuki,YOKOI Sakura       champion_player_ids=","
WS  ODO Satsuki                    champion_player_ids=NULL
XD  KOBAYASHI Hiromu,KIHARA Miyuu  champion_player_ids=","
```

### 初步根因

`import_sub_events.py` 从 `match_side_players.player_id` 汇总 `champion_player_ids`。但 `import_matches.py` 当前没有解析 player id，导致冠军成员能识别名字，不能识别 canonical player id。

### 初步处理方向

此问题应和问题 1 一起解决：先补 `import_matches.py` 的 player resolution。

## 建议处理顺序

### Phase 1：确认前端中文展示数据链路

目标：解释为什么旧 event 能显示中文、新增 event 不能。

检查：

```bash
rg -n "playerNameZh|name_zh|match_side_players|winnerName" web/lib/server/events.ts web/lib/server/players.ts web/lib/server/compare.ts
```

输出：

- 明确前端详情页读取字段。
- 选一个旧 event 和一个新增 event 做 SQL 对比。

已确认：

- 前端历史比赛详情和赛事签表不读取 `side_a_zh` / `side_b_zh` / `winner_zh`。
- 历史比赛球员中文来自：

  ```sql
  match_side_players.player_id -> players.name_zh
  ```

- `import_matches.py` 在 2026-06-17 提交 `eaa0294` 中移除了 `player_id` 回填，导致本次新增赛事的 `match_side_players.player_id` 全为 NULL。
- 旧非团体赛事之所以曾能显示中文，是因为旧版 `import_matches.py` 会按球员名和协会回填 `player_id`。

### Phase 2：设计安全的 player resolution

目标：导入 `match_side_players.player_id`。

实现状态：已开始落地。当前已覆盖普通唯一匹配、历史协会匹配、同名名单拦截、同名 player-centric matches 唯一证据匹配、同名多证据保守置空。

不能简单恢复旧版 `(player_name, country_code) -> player_id`。需要同时处理：

- 球员协会变更，例如 `data/player_country_history.json` 中的 `ZHU Yuling`、`LIN Ye`。
- 同名同协会球员。
- event 维度 matches 中只有参赛方文本，没有官方 player id。
- player 维度 matches 能以单个球员为入口抓取，可作为同名消歧依据。

#### 2.1 新增同名球员名单

新增：

```text
scripts/data/same_name_players.txt
```

格式：

```text
# player_id,player_name,country_code
123456,ZHANG Wei,CHN
234567,ZHANG Wei,CHN
```

规则：

- 空行和 `#` 注释忽略。
- `player_id` 必须是数字。
- `player_name` 做空白规范化。
- `country_code` 大写。
- 同名名单是保守拦截表：在名单里的球员不能用普通 `(name, country)` 直接关联。

#### 2.2 人工审核应用时维护同名名单

修改：

```text
scripts/apply_ranking_profile_review.py
```

新增参数：

```bash
--same-name-players scripts/data/same_name_players.txt
--db-path data/db/ittf.db
```

在应用 `unresolved_player_ids` 的人工审核结果时：

1. 读取人工填写的 `resolution.player_id`。
2. 结合 `weekly.name` 和 `weekly.country_code`。
3. 查询 `players` 表中相同 normalized name + country_code 的全部 player。
4. 如果不同 `player_id` 数量大于 1，把这组 player 全部写入 `same_name_players.txt`。
5. 文件写入需去重、排序，避免重复追加。

注意：如果 review 文件只包含本次人工确认的一个 player，仍应以数据库 `players` 表为准补全同名组。

#### 2.3 player 维度 matches 抓取脚本命名和输出修复

当前 `scripts/scrape_matches.py` 是“按 player 抓取 matches”，但名称容易和 `scripts/scrape_matches_from_events.py` 混淆。

目标：

- 新增/重命名为：

  ```text
  scripts/scrape_matches_from_player.py
  ```

- 保留 `scripts/scrape_matches.py` 作为兼容 wrapper，避免旧入口立即失效。
- 更新引用该入口的文档和脚本。

已实现：

- `scripts/scrape_matches_from_player.py` 为新主入口。
- `scripts/scrape_matches.py` 保留为兼容 wrapper。
- `scripts/run_matches.py`、`scripts/scrape_matches_from_events.py`、`scripts/scrape_team_matches.py` 已改为引用新模块名。

必须先修的逻辑漏洞：

当前输出文件名为：

```python
orig_file = output_orig_dir / f"{sanitize_filename(player_name)}.json"
```

同名球员会互相覆盖。新规则：

- 有 `player_id` 时：

  ```text
  data/matches_complete/orig/player_<player_id>_<sanitized_name>.json
  data/matches_complete/cn/player_<player_id>_<sanitized_name>.json
  ```

- 无 `player_id` 时才保留旧文件名：

  ```text
  data/matches_complete/orig/<sanitized_name>.json
  ```

同名球员专属抓取流程应针对 `same_name_players.txt` 逐人执行：

```bash
python scripts/scrape_matches_from_player.py \
  --player-name "<player_name>" \
  --player-country <country_code> \
  --player-id <player_id> \
  --from-date <YYYY-MM-DD>
```

翻译仍走 `scripts/translate_matches.py`，但需确认它能处理 `player_<id>_<name>.json` 文件名。

已实现：有 `player_id` 时输出 `player_<player_id>_<sanitized_name>.json`；无 `player_id` 时保持旧文件名。

#### 2.4 `import_matches.py` player resolution 规则

普通球员：

1. 构建 player index，包含：
   - `players.name + players.country_code`
   - `normalize_name_key(players.name) + players.country_code`
2. 加载 `data/player_country_history.json`，为有历史协会的球员增加可匹配 country：
   - 当前 `players.country_code`
   - `historical_country`
3. 如果 `(name, event_match_country)` 命中唯一 player，写入 `match_side_players.player_id`。
4. 如果 0 命中，保留 NULL，计入 unmatched。
5. 如果多命中，保留 NULL，计入 ambiguous。

同名名单球员：

1. 如果 `(player_name, country_code)` 落入 `same_name_players.txt` 对应的同名组，禁止直接写入。
2. 读取同名组中每个 player 的 player-centric matches：

   ```text
   data/matches_complete/cn/player_<player_id>_<sanitized_name>.json
   ```

3. 将 player-centric match 记录与 event-centric match 记录做唯一匹配。

匹配维度：

- `event_id` 或可解析出的 event identity。
- `sub_event`
- `stage`
- `round`
- `match_score`
- `side_a` / `side_b`
- `perspective`
- `result_for_player`
- `winner`

只有唯一匹配到某个 player_id 时才写入。否则保留 NULL，并输出：

```text
ambiguous_same_name_players
unresolved_same_name_players
```

已实现：`import_matches.py` 新增 `--same-name-players`、`--player-matches-dir`、`--country-history` 参数；普通球员使用 current/historical country 唯一匹配，同名名单命中时只使用 player-centric matches 证据。

#### 2.5 测试要求

需新增或扩展 `scripts/db/test_import_matches_incremental.py`：

- 非同名、当前协会唯一匹配时写入 `player_id`。
- 非同名、历史协会匹配时写入同一 `player_id`。
- 同名同协会但没有 player-centric matches 证据时保留 NULL。
- 同名同协会且 player-centric matches 唯一匹配时写入对应 `player_id`。
- 同名同协会且 player-centric matches 多个候选时保留 NULL 并计入 ambiguous。
- 无匹配时保留 NULL 并计入 unmatched。

当前已覆盖前五类；无匹配保留 NULL 的基础路径已有结果集统计覆盖，后续可补更窄的单测。

### Phase 3：收窄增量扫描范围

目标：`--event-id` 模式只扫描相关文件，减少无关 skipped files。

策略：

- 对 event-match payload 优先读取文件名末尾 `_<event_id>.json`。
- 若文件名 event id 不在目标集合，直接跳过，不进入 payload mismatch 检查。
- 对不能从文件名解析 event id 的文件，再读取 payload event_id。

### Phase 4：集中导入输出汇总（结构化 JSON）

目标：`run_import_wtt_events.sh` 最后输出一个可读的人工检查摘要。

策略（详见上文「问题 2 优化处理方向」）：

- 三个导入脚本各加 `--summary-json PATH`（支持 `auto`），复用已有 result/stats
  dict，序列化结构化结果，**不解析人类文本**。
- 为每次 run 生成日志目录 `data/logs/wtt-event-import/<run_id>/`，每个命令
  stdout/stderr `tee` 到 `.log`，结构化结果落 `.json`。
- 末尾 Python 聚合器读取所有 `.json`，渲染统一的 `⚠ MANUAL CHECK REQUIRED`
  区块；无问题的 event 不打印。脚本仍 `exit 0`。

### Phase 5：名称 mismatch 分类和修复

目标：区分可自动兼容的名称差异和真实错配。

处理：

- apostrophe normalization。
- 对 `Central American` / `Central America` 等确定等价的名称加入 normalization 或 override。
- 对 `3313 Sao Jose` vs `Rio De Janeiro` 保留人工核对，不自动兼容。

## 当前不立即做的事

暂不优先扩展 `match_side_players` schema 增加中文字段。

原因：前端旧数据能显示中文，说明优先问题是 canonical player identity 没有建立。等 player resolution 修复后，再评估是否需要为未知球员增加中文 fallback 字段。
