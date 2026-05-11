# Current Event → 历史事实表 Promote 方案

> 状态：执行中
> 关联表：`current_event_*`（运行态/展示态） / `matches`、`team_ties`、`event_draw_matches`、`sub_events`（统计事实）
> 关联代码：`scripts/db/`、`scripts/runtime/`、`web/lib/server/events.ts`、`web/app/events/[eventId]/page.tsx`

---

## 1. 背景

系统中存在两套并行的赛事数据：

| 维度 | `current_event_*` | `matches` / `team_ties` / `event_draw_matches` / `sub_events` |
| --- | --- | --- |
| 数据来源 | WTT live API（运行态） | ITTF profile + 历史 JSON |
| 字段完备度 | 完整（session、台号、scheduled_utc_at、external_code） | 仅核心比分/胜方 |
| 写入路径 | `scripts/runtime/import_current_event*.py` | `scripts/db/import_*.py` 一次性 bootstrap |
| 用途 | 详情页展示 | 球员统计 / H2H / 冠军数 / 对手统计 |

之前的处理：`lifecycle_status='in_progress'` 时 `events.ts` 读 current，其它状态读历史。结果是**赛事一旦完结，详情页会突然降级到历史表的低保真展示**，且历史表里**根本没有这场赛事**（current 数据从未流入统计层），导致：

- 球员个人页缺该赛事履历
- `compare` 对比页 H2H 漏数
- `sub_events` 缺该赛事冠军记录
- 排名页 / 对手统计 / 冠军数全部漏算

本方案的目标是：**赛事完结后执行 promote，把 `current_event_*` 数据复制到历史事实表，同时保留 `current_event_*` 不动作为展示数据源**。

---

## 2. 决策摘要

| # | 决策 | 理由 |
| - | --- | --- |
| D1 | **不修改 `matches` schema**（不加 source_type/source_key 列） | 历史 import 用内存 dedup，没有 `external_code` 概念；新增列会破坏既有 dedup 假设。promote 改用"按 event_id 整批 DELETE + INSERT"实现幂等。 |
| D2 | **不修改 `event_draw_matches` schema** | 同 D1。它通过 `UNIQUE(match_id) + FK ON DELETE CASCADE` 跟随 matches 删除。 |
| D3 | `team_ties` schema **不变**，复用已有的 `source_type='promoted_from_current'` + `source_key=external_match_code` + `uq_team_ties_source` 去重。 | 该表已为 promote 设计。 |
| D4 | **promote 后保留 `current_event_*` 不动** | 展示路径继续读 current 表（信息更全：台号、session、scheduled_utc_at、external_code）。不存在被 cron 覆盖的风险，因为 cron 按比赛日期生成、完赛后不再触发。 |
| D5 | **promote 由 cron 触发**，脚本同时把 `events.lifecycle_status` 翻为 `'completed'`，是 lifecycle 切换的**唯一入口**。 | 闭环 lifecycle，避免人工漏跑。 |
| D6 | **排名页胜率不动**，仍读 `players.career_wins/career_matches`（ITTF profile 抓取来源）。 | 与 promote 链路解耦，物化缓存表延后到 Phase 2。 |
| D7 | **`matches.stage_zh` / `matches.round_zh` 通过 `stage_codes` / `round_codes` 表查表填充**，不依赖翻译字典或源 JSON 的 stage_zh 字段。 | current_event 已用 stage_code，promote 时直接 lookup 即可。 |
| D8 | `import_sub_events.py` 团体赛冠军逻辑**无需改造**。 | 已确认逻辑从 final 多 rubber 反推（按 country 分组取胜方所有队员），promote 只要把 final rubbers 正确写入 matches + event_draw_matches，结果自然正确。 |
| D9 | 给 `import_sub_events.py` 和 `import_event_draw_matches.py` **增加 `--event-id` 模式**（per-event delete + rebuild），全量模式保留。 |
| D10 | 抽出 `make_side_key` 到公共模块 `scripts/db/_match_keys.py`，promote 与 historical import 共用，避免 key 不一致导致 H2H 重复。 |

---

## 3. 文件改动清单

### 3.1 新增

| 文件 | 用途 |
| --- | --- |
| `scripts/db/_match_keys.py` | 抽出公共 `make_side_key` 和 `make_dedup_key` 函数。 |
| `scripts/db/promote_current_event.py` | promote 主脚本。CLI 入口 + 5 步原子化 promote。 |
| `docs/design/promote_current_event.md` | 本文件。 |

### 3.2 修改

| 文件 | 变更 |
| --- | --- |
| `scripts/db/import_matches.py` | 改为 `from _match_keys import make_side_key, make_dedup_key`。 |
| `scripts/db/import_sub_events.py` | 增加 `--event-id` 参数，单 event 模式只 DELETE + 重建该 event 的 sub_events。 |
| `scripts/db/import_event_draw_matches.py` | 增加 `--event-id` 参数，单 event 模式只 DELETE + 重建该 event 的 event_draw_matches。 |
| `scripts/runtime/generate_current_event_crontab.py` | 给每个 event 多生成一条 promote cron（最后一个比赛日 +24h）。 |
| `web/lib/server/events.ts` | 新增 `hasCurrentEventPresentationData(eventId)`，改 `useCurrentEventModel` 决策；解除"completed 即隐藏小组赛视图"的硬编码。 |
| `web/app/events/[eventId]/page.tsx` | `useNewLiveTabs` 改名 `useScheduleTabs`，条件改为按数据存在性判定；北京时间提示保留 `lifecycleStatus === 'in_progress'`。 |

### 3.3 不动

- `matches` / `event_draw_matches` / `sub_events` schema —— 完全不变。
- `web/lib/server/stats.ts` / `players.ts` / `compare.ts` / `rankings.ts` —— 完全不变（已确认这 4 个文件没有引用 current_event_*，promote 后历史表自然变全）。
- `scripts/runtime/import_current_event*.py` —— 完全不变（cron 自动停止触发，无需 lifecycle 守卫）。

---

## 4. Promote 脚本 `scripts/db/promote_current_event.py`

### 4.1 命令行接口

```bash
python scripts/db/promote_current_event.py --event-id 3216 --dry-run
python scripts/db/promote_current_event.py --event-id 3216
python scripts/db/promote_current_event.py --event-id 3216 --replace
python scripts/db/promote_current_event.py --event-id 3216 --force   # 跳过 lifecycle 校验
```

| Flag | 行为 |
| --- | --- |
| 无 flag（默认增量） | 若 `matches WHERE event_id=?` 已有数据 → 退出 0 并打印"已 promote 过，跳过"；否则正常导入。 |
| `--replace` | 先 `DELETE FROM matches WHERE event_id=?`（cascade 到 event_draw_matches / match_sides）+ `DELETE FROM team_ties WHERE event_id=?` + `DELETE FROM sub_events WHERE event_id=?`，再全部重建。 |
| `--force` | 跳过"`events.lifecycle_status` 必须为 `completed`"的前置校验。 |
| `--dry-run` | 只统计与打印差异，不写任何表，不切 lifecycle。 |

### 4.2 流程（单事务）

整个流程包在 `BEGIN IMMEDIATE` ... `COMMIT` 里，任一阶段失败 → `ROLLBACK`，retry-safe。

```
Step 0  pre_check(event_id)
Step 1  promote_team_ties(event_id)       → 写 team_ties / team_tie_sides / team_tie_side_players
Step 2  promote_matches(event_id)         → 写 matches / match_sides / match_side_players
Step 3  rebuild_event_draw_matches(event_id)   ← 复用 import_event_draw_matches 的核心函数
Step 4  rebuild_sub_events(event_id)      ← 复用 import_sub_events 的核心函数
Step 5  set_lifecycle_completed(event_id)
COMMIT
```

### 4.3 Step 0 前置校验

```python
def pre_check(conn, event_id, force=False):
    # 1. event 存在
    if not row_exists("SELECT 1 FROM events WHERE event_id=?", event_id):
        raise PromoteError(f"event {event_id} not found")

    # 2. lifecycle 校验
    status = conn.execute(
        "SELECT lifecycle_status FROM events WHERE event_id=?", (event_id,)
    ).fetchone()[0]
    if not force and status not in ('in_progress', 'completed'):
        raise PromoteError(f"lifecycle_status={status}, expected in_progress/completed")

    # 3. current_event_matches 必须存在并至少一条 completed
    has_completed = conn.execute("""
        SELECT 1 FROM current_event_matches
         WHERE event_id=? AND status IN ('completed', 'walkover') LIMIT 1
    """, (event_id,)).fetchone()
    if not has_completed:
        raise PromoteError("no completed current_event_matches")

    # 4. 警告：仍有未完成的 match
    pending = conn.execute("""
        SELECT COUNT(*) FROM current_event_matches
         WHERE event_id=? AND status IN ('scheduled', 'live')
    """, (event_id,)).fetchone()[0]
    if pending > 0:
        log.warning("event %s has %d non-final matches; they will be skipped", event_id, pending)

    # 5. 增量幂等
    already = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE event_id=?", (event_id,)
    ).fetchone()[0]
    if already > 0 and not args.replace:
        log.info("event %s already promoted (%d matches), skip", event_id, already)
        return False  # 调用方 early-return
    return True
```

### 4.4 Step 1 promote team_ties

源：`current_event_team_ties` → `team_ties`
源：`current_event_team_tie_sides` → `team_tie_sides`
源：`current_event_team_tie_side_players` → `team_tie_side_players`

只 promote `status IN ('completed', 'walkover')`。

| current_event_team_ties | team_ties |
| --- | --- |
| `event_id` | `event_id` |
| `sub_event_type_code` | `sub_event_type_code` |
| `stage_label` | `stage` |
| `stage_code` | `stage_code` |
| — lookup `stage_codes.name_zh` | `stage_zh` |
| `round_label` | `round` |
| `round_code` | `round_code` |
| — lookup `round_codes.name_zh` | `round_zh` |
| `group_code` | `group_code` |
| `match_score` | `match_score` |
| `winner_side` | `winner_side` |
| `winner_team_code` | `winner_team_code` |
| `status` | `status` |
| `'promoted_from_current'` | `source_type` |
| `external_match_code` | `source_key` |
| `event_id` | `promoted_from_event_id` |
| `datetime('now')` | `promoted_at` |

INSERT 使用 `INSERT OR IGNORE`（依赖 `uq_team_ties_source`）。返回 `Dict[current_team_tie_id → team_tie_id]` 供 Step 2 使用（如果是 ignore 的，则回查现有行的 team_tie_id）。

side 和 side_player 的 promote 在 team_tie 落库后立即执行，按 `current_team_tie_id` 关联。已有 sides 的 tie 跳过（INSERT OR IGNORE 走 `UNIQUE(team_tie_id, side_no)`）。

### 4.5 Step 2 promote matches

源：`current_event_matches` → `matches`
源：`current_event_match_sides` → `match_sides`
源：`current_event_match_side_players` → `match_side_players`

只 promote `status IN ('completed', 'walkover')`。

#### 字段映射

| current_event_matches | matches |
| --- | --- |
| `event_id` | `event_id` |
| — lookup `events.name` | `event_name` |
| — lookup `events.name_zh` | `event_name_zh` |
| — lookup `events.year` | `event_year` |
| `sub_event_type_code` | `sub_event_type_code` |
| `stage_label` | `stage` |
| `stage_code` | `stage_code` |
| — lookup `stage_codes.name_zh WHERE code=stage_code` | `stage_zh` |
| `round_label` | `round` |
| `round_code` | `round_code` |
| — lookup `round_codes.name_zh WHERE code=round_code` | `round_zh` |
| `make_side_key(side_a_players)` | `side_a_key` |
| `make_side_key(side_b_players)` | `side_b_key` |
| `match_score` | `match_score` |
| `games` | `games` |
| `winner_side` | `winner_side` |
| `winner_name`（若 NULL，从 winner_side 的 sides 拼接） | `winner_name` (NOT NULL) |
| `raw_source_payload`（json.dumps，若 NULL 兜底 `external_match_code`） | `raw_row_text` (NOT NULL) |
| `datetime('now')` | `scraped_at` |
| step1 映射的 `team_tie_id`（个人赛为 NULL） | `team_tie_id` |

#### side_a_key / side_b_key 生成规则

直接调用 `_match_keys.make_side_key`：

```python
side_a_players = conn.execute("""
    SELECT p.player_name, p.player_country
      FROM current_event_match_sides s
      JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
     WHERE s.current_match_id = ? AND s.side_no = 1
     ORDER BY p.player_order
""", (current_match_id,)).fetchall()
side_a_key = make_side_key([(name, country) for name, country in side_a_players])
```

#### 边界：source data 缺失

- `winner_name` 为 NULL 但 `winner_side` 已知：取 `winner_side` 那一侧的 player_name（多人时用 `/` 连接，与历史 import 行为一致）。
- `winner_name` 与 `winner_side` 都为 NULL：跳过该行 + 记 warning（出现概率极低，通常意味着 status=cancelled）。
- `raw_source_payload` 为 NULL：兜底用 `f"promoted:event={event_id};code={external_match_code}"`。

INSERT 后返回 `Dict[current_match_id → match_id]`，给 match_sides / match_side_players 用。

### 4.6 Step 3 rebuild_event_draw_matches(event_id)

抽出 `import_event_draw_matches.py` 的核心逻辑到 `rebuild_for_event(conn, event_id)` 函数：

```python
def rebuild_for_event(conn, event_id):
    conn.execute("DELETE FROM event_draw_matches WHERE event_id=?", (event_id,))
    matches = conn.execute("""
        SELECT match_id, sub_event_type_code, stage, round, stage_code, round_code, ...
          FROM matches WHERE event_id=?
    """, (event_id,)).fetchall()
    rows = classify_draw_rounds(matches)   # 现有 stage/round → draw_stage/draw_round 分类逻辑
    conn.executemany("INSERT INTO event_draw_matches (...) VALUES (...)", rows)
```

CLI 入口 `--event-id` 走同一个函数。

### 4.7 Step 4 rebuild_sub_events(event_id)

抽出 `import_sub_events.py` 的核心逻辑到 `rebuild_for_event(conn, event_id)` 函数：

```python
def rebuild_for_event(conn, event_id):
    conn.execute("DELETE FROM sub_events WHERE event_id=?", (event_id,))
    sub_event_codes = conn.execute("""
        SELECT DISTINCT sub_event_type_code FROM matches WHERE event_id=?
    """, (event_id,)).fetchall()
    for (code,) in sub_event_codes:
        champion = derive_champion(conn, event_id, code)   # 复用现有 derive_champion 逻辑
        if champion:
            conn.execute("INSERT INTO sub_events ... VALUES ...", champion)
```

CLI 入口 `--event-id` 走同一个函数。

**团体赛冠军逻辑**：已确认现有 `derive_champion` 用 `group_final_team_ties` + `resolve_team_tie_by_side` 从 final 多 rubber 反推。promote 完成后该 event 的 matches/event_draw_matches 数据完整 → 该逻辑无需任何改动即可正确输出团体赛冠军。

### 4.8 Step 5 lifecycle 切换

```python
conn.execute("""
    UPDATE events
       SET lifecycle_status = 'completed',
           updated_at = datetime('now')
     WHERE event_id = ?
""", (event_id,))
```

`--dry-run` 模式下不执行。

### 4.9 退出码

| code | 含义 |
| - | --- |
| 0 | 成功 promote / 增量跳过（已 promote）/ dry-run 输出完成 |
| 1 | 前置校验失败（event 不存在 / lifecycle 不对 / 无 completed matches） |
| 2 | promote 过程中异常，事务已 rollback |
| 3 | 仍有未完赛 match 且未指定 `--allow-partial`（默认警告，不 fail；cron 可改为 fail 触发重跑） |

---

## 5. Cron 改造

`scripts/runtime/generate_current_event_crontab.py` 当前为每个 event 按比赛日期生成 N 条 cron。改造：

- 找到每个 event 的最后一个比赛日 `last_match_date`。
- 在 `last_match_date + 24h` 时刻额外生成一条：
  ```
  <ts>  python scripts/db/promote_current_event.py --event-id <EID>
  ```
- promote 命令默认走增量模式（已 promote 过则 no-op，cron 多跑无副作用）。
- 失败时退出码非 0，cron 监控可发邮件。

如果 promote 时仍有 'live' 状态的 match（极少见，理论上 +24h 后所有 WTT 数据已同步），脚本会跳过它们并打印 warning，下一次 cron 重跑（可手动配置 +48h 第二次兜底）。

---

## 6. 前端改造

### 6.1 `web/lib/server/events.ts`

**新增 helper**（紧邻 `getEventDetail` 上方）：

```typescript
function hasCurrentEventPresentationData(db: Database, eventId: number): boolean {
  const row = db.prepare(`
    SELECT 1 FROM current_event_matches WHERE event_id = ?
    UNION ALL
    SELECT 1 FROM current_event_team_ties WHERE event_id = ?
    UNION ALL
    SELECT 1 FROM current_event_brackets WHERE event_id = ?
    UNION ALL
    SELECT 1 FROM current_event_session_schedule WHERE event_id = ?
    LIMIT 1
  `).get(eventId, eventId, eventId, eventId);
  return Boolean(row);
}

function shouldUseCurrentEventPresentation(
  db: Database,
  eventId: number,
  lifecycleStatus: string | null
): boolean {
  if (lifecycleStatus === 'in_progress') return true;
  return hasCurrentEventPresentationData(db, eventId);
}
```

**改造决策点（约 line 3240）**：

```typescript
// 旧
const useCurrentEventModel = event.lifecycleStatus === 'in_progress';

// 新
const useCurrentEventModel = shouldUseCurrentEventPresentation(
  db, eventId, event.lifecycleStatus
);
```

**解除 round_robin 视图的 completed 短路（约 line 3558）**：

```typescript
// 旧
if (event.lifecycleStatus === 'completed') return null;

// 新：根据 current 数据是否存在决定，而不是 lifecycle
if (!useCurrentEventModel) return null;
```

### 6.2 `web/app/events/[eventId]/page.tsx`

```typescript
// 旧 (line 3133-3135)
const useNewLiveTabs =
  data?.event.lifecycleStatus === "in_progress" &&
  ((data?.sessionSchedule.length ?? 0) > 0 || (data?.scheduleDays.length ?? 0) > 0);

// 新
const useScheduleTabs =
  (data?.sessionSchedule.length ?? 0) > 0 ||
  (data?.scheduleDays.length ?? 0) > 0;
```

`useNewLiveTabs` 的所有引用同步改名为 `useScheduleTabs`。

**保留**（line 1337，北京时间标签）：

```typescript
const showBeijingTime = lifecycleStatus === "in_progress";
```

---

## 7. 验证清单

选 3216（或当前最近一个完结的 current event）作为黄金样本：

### 7.1 promote 前快照

```sql
SELECT COUNT(*) FROM matches WHERE event_id = 3216;           -- 期望 0
SELECT COUNT(*) FROM team_ties WHERE event_id = 3216;          -- 期望 0
SELECT COUNT(*) FROM event_draw_matches WHERE event_id = 3216; -- 期望 0
SELECT COUNT(*) FROM sub_events WHERE event_id = 3216;         -- 期望 0
SELECT COUNT(*) FROM current_event_matches
 WHERE event_id = 3216 AND status IN ('completed', 'walkover');  -- > 0
```

### 7.2 dry-run

```bash
python scripts/db/promote_current_event.py --event-id 3216 --dry-run
```

期望输出：会插入 N 条 matches / M 条 team_ties / K 条 sub_events，不实际写。

### 7.3 实际 promote

```bash
python scripts/db/promote_current_event.py --event-id 3216
```

### 7.4 promote 后断言

```sql
-- 行数与 dry-run 一致
SELECT COUNT(*) FROM matches WHERE event_id = 3216;
SELECT COUNT(*) FROM team_ties WHERE event_id = 3216 AND source_type = 'promoted_from_current';
SELECT COUNT(*) FROM event_draw_matches WHERE event_id = 3216;
SELECT COUNT(*) FROM sub_events WHERE event_id = 3216;

-- lifecycle 已切换
SELECT lifecycle_status FROM events WHERE event_id = 3216;  -- 'completed'

-- current 表保留
SELECT COUNT(*) FROM current_event_matches WHERE event_id = 3216;  -- 不变

-- 翻译已填
SELECT stage, stage_zh, round, round_zh FROM matches
 WHERE event_id = 3216 LIMIT 5;
-- 期望: stage_zh / round_zh 均非 NULL

-- 团体赛冠军
SELECT * FROM sub_events WHERE event_id = 3216;
-- 期望: champion_player_ids 是全队队员，champion_name 多人逗号分隔
```

### 7.5 幂等性

```bash
python scripts/db/promote_current_event.py --event-id 3216
# 期望: "already promoted, skip"，退出码 0
```

### 7.6 Replace

```bash
python scripts/db/promote_current_event.py --event-id 3216 --replace
# 期望: 全部删除后重建，行数与首次 promote 一致
```

### 7.7 Web 验证

```bash
cd web && npm run build && npm run dev
```

- `/events/3216` —— 仍显示完整赛程/签表/小组赛（current 表数据）
- `/players/<某参赛球员>` —— 履历包含该赛事（matches 数据）
- `/compare?a=...&b=...` —— H2H 包含该赛事
- 排名页：胜率排序不变（独立链路）

---

## 8. 落地顺序

| Step | 改动 | 风险 |
| - | --- | --- |
| 0 | 抽出 `_match_keys.py`，`import_matches.py` 改用 import | 极低，纯重构 |
| 1 | `import_event_draw_matches.py` 加 `--event-id` 模式 | 低（全量模式保留） |
| 2 | `import_sub_events.py` 加 `--event-id` 模式 | 低（全量模式保留） |
| 3 | 写 `promote_current_event.py`，全程 `--dry-run` 验证 | 中（事务边界 + 字段映射） |
| 4 | 选一个真实 completed-but-not-promoted 的 event 实跑 promote | 中（数据正确性） |
| 5 | 前端 `events.ts` + `page.tsx` 改造 | 低（小改动） |
| 6 | `generate_current_event_crontab.py` 加 promote 条目 | 低（仅生成器） |
| 7 | 文档更新 `CLAUDE.md` 加 promote 维护命令 | 极低 |

Phase 2（不在本次范围）：
- `player_stats_cache` 物化表
- `events.ts` 中分散的 `useCurrentEventModel ? 'current_event_X' : 'X'` 三元分支重构为单个 `pickEventTable` 函数
