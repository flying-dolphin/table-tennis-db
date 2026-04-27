# 排名统计数据库优化设计方案

更新时间：2026-04-27  
关联文档：`docs/design/database.md`、`docs/design/backend.md`、`docs/DATABASE_MAINTENANCE.md`

---

## 1. 背景

当前站点已完成一轮页面侧性能优化：

- 首页赛历与首页排名改为服务端首屏注入
- `/rankings` 默认 `points` 排序改为轻量 SQL 路径
- `/rankings` 首屏默认榜单改为服务端直接注入
- `/rankings` 的 `win_rate` 路径增加了进程内缓存，缓解重复访问

这些改动已经明显降低了默认路径的等待时间，但也暴露出一个更底层的问题：

- `sort_by=win_rate` 和 `sort_by=head_to_head_count` 仍然依赖请求时在线聚合统计
- 首次进入或跨进程访问时，仍会出现 1s 以上延迟
- 这类慢查询不是单纯缺索引，而是“把不该在请求时做的统计工作放在了请求时做”

因此，需要把这类统计从“在线现算”迁移到“导入链路预计算”。

---

## 2. 当前问题

### 2.1 现状实现

当前 `/api/v1/rankings` 的实现位于：

- `web/lib/server/rankings.ts`
- `web/lib/server/stats.ts`

默认 `points` 排序已经可以直接走 `ranking_entries + players` 的轻量查询。  
但 `win_rate` / `head_to_head_count` 仍然会：

1. 读取当前 ranking snapshot 下的全部球员
2. 根据全部球员 ID 扫描 `matches / match_sides / match_side_players / events / event_categories`
3. 在 Node 层做分组、胜率、赛事统计、冠军统计等二次聚合
4. 最后再排序与分页

### 2.2 具体症状

- 即使接口只返回前 20 条，服务端也会先为整份榜单计算统计
- 本地测得联表核心查询命中约 `146739` 行
- `win_rate` 首次请求耗时约 `1.5s`
- 同进程第二次请求可命中内存缓存降到毫秒级
- 但用户离开页面后再次进入，或者请求落到新进程/重启后的容器时，仍会回到冷启动延迟

### 2.3 根因

根因不是“缺少一个索引”，而是数据模型与访问模式不匹配：

- 用户请求是分页读
- 当前实现却是全量聚合后再分页
- 聚合逻辑依赖多张比赛明细表，不适合在高频页面请求中重复执行

---

## 3. 优化目标

本次数据库优化的目标不是继续堆更多运行时缓存，而是把排名页依赖的统计指标变成正式的数据资产。

目标如下：

1. `/api/v1/rankings?sort_by=win_rate` 首次请求降为正常 SQL 排序级别
2. 排名页统计排序不再依赖运行时扫全量比赛明细
3. 统计结果随着数据同步自动更新，而不是依赖手动重启 Web 进程清缓存
4. 后续 `/players/[slug]`、`/compare` 等页面可以复用同一份聚合结果

非目标：

- 本轮不追求把所有球员分析指标一次性建全
- 本轮不引入独立 OLAP 数据库
- 本轮不把 SQLite 替换为别的数据库

---

## 4. 设计原则

### 4.1 预计算优先

凡是符合以下条件的指标，都优先进入预计算层：

- 页面访问频率高
- 统计逻辑跨多张明细表
- 一次请求只读取少量结果，但计算要扫描大量原始数据

### 4.2 同步链路生成，查询链路只读

统计数据应在 `scripts/db/import*.py` 正式导入链路中生成：

- 导入阶段：重算聚合统计
- Web 查询阶段：只读聚合结果，不再重新推导

### 4.3 渐进替换

先覆盖排名页当前真正用到的字段：

- `win_rate`
- `head_to_head_count`

其它统计字段保留后续扩展空间，但不要求首批全部落表。

---

## 5. 目标表设计

建议新增正式表：`player_aggregate_stats`

用途：

- 存储球员级聚合统计结果
- 作为排名页、球员页、对比页的共享统计来源

建议字段：

```sql
CREATE TABLE IF NOT EXISTS player_aggregate_stats (
    player_id              INTEGER PRIMARY KEY,
    total_matches          INTEGER NOT NULL DEFAULT 0,
    total_wins             INTEGER NOT NULL DEFAULT 0,
    win_rate               REAL NOT NULL DEFAULT 0,
    head_to_head_count     INTEGER NOT NULL DEFAULT 0,
    foreign_matches        INTEGER NOT NULL DEFAULT 0,
    foreign_wins           INTEGER NOT NULL DEFAULT 0,
    foreign_win_rate       REAL NOT NULL DEFAULT 0,
    domestic_matches       INTEGER NOT NULL DEFAULT 0,
    domestic_wins          INTEGER NOT NULL DEFAULT 0,
    domestic_win_rate      REAL NOT NULL DEFAULT 0,
    events_total           INTEGER NOT NULL DEFAULT 0,
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    stats_version          TEXT,
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);
```

建议索引：

```sql
CREATE INDEX IF NOT EXISTS idx_player_aggregate_stats_win_rate
ON player_aggregate_stats(win_rate DESC);
```

说明：

- `player_id` 一球员一行
- `updated_at` 用于观测最近重算时间
- `stats_version` 用于标识本次统计来自哪一轮同步/导入批次
- 如果后续指标继续扩展，可以在同表增列，不必先拆多表

---

## 6. 排名页查询改造

### 6.1 当前目标

将 `win_rate` / `head_to_head_count` 排序改成直接 join 聚合表：

```sql
SELECT
  re.player_id,
  re.rank,
  re.points,
  re.rank_change,
  p.slug,
  p.name,
  p.name_zh,
  p.country,
  p.country_code,
  pas.win_rate,
  pas.head_to_head_count
FROM ranking_entries re
JOIN players p ON p.player_id = re.player_id
LEFT JOIN player_aggregate_stats pas ON pas.player_id = re.player_id
WHERE re.snapshot_id = ?
ORDER BY pas.win_rate DESC, re.rank ASC
LIMIT ? OFFSET ?;
```

### 6.2 改造后的收益

- 排名页统计排序变成标准 SQL 查询
- 不再依赖 Node 运行时遍历十几万联表结果
- 分页在 SQL 层生效，而不是 JS 层最后裁剪
- 首次进入页面和跨页面回访的性能更加稳定

---

## 7. 导入链路改造

### 7.1 新增脚本

建议新增正式脚本：

- `scripts/db/import_player_aggregate_stats.py`

职责：

- 基于 `players / matches / match_sides / match_side_players / events / event_categories`
  统一重算 `player_aggregate_stats`

### 7.2 执行顺序

建议放入正式导入链路，位置在：

1. `import_players.py`
2. `import_rankings.py`
3. `import_events.py`
4. `import_matches.py`
5. `import_event_draw_matches.py`
6. `import_sub_events.py`
7. `import_player_aggregate_stats.py`

原因：

- 它依赖玩家、赛事、比赛明细都已完整入库
- 不应在 Web 请求阶段兜底计算

### 7.3 写入策略

建议首版使用“全量重算 + 全量覆盖”：

- `DELETE FROM player_aggregate_stats`
- 全表重新写入

原因：

- 数据规模当前可控
- 逻辑简单、确定性高
- 更容易和当前“整库重建/整批同步”模式保持一致

后续如有需要，再演进到增量更新。

---

## 8. 缓存策略调整建议

当前 `web/lib/server/rankings.ts` 中已有进程内缓存，它可以作为过渡期优化保留，但不应再作为长期主方案。

长期建议：

- 主性能依赖数据库预计算表
- 运行时缓存只做“锦上添花”，不做正确性依赖

完成预计算表落地后：

- 可以删除当前 `win_rate` 的进程内缓存
- 或保留一个很轻的 query-level cache，但不再承载主要性能职责

---

## 9. 一致性与更新机制

### 9.1 当前问题

进程内缓存存在天然缺陷：

- 无法感知数据库底层表变化
- 重启后全部失效
- 多实例/多进程之间不共享

### 9.2 新方案

预计算表生成后，数据更新应依赖同步批次，而不是 TTL：

- 同步完成
- 导入脚本更新 `player_aggregate_stats`
- Web 请求自然读到新结果

如需追踪版本，可在表中写入：

- `stats_version`：例如同步批次号、日期、snapshot 版本
- `updated_at`：最近重算时间

---

## 10. 与后续页面优化的关系

这份设计文档不是只服务 `/rankings`。

后续一系列页面优化都可能复用同一思路：

- `/players/[slug]`
  - 球员概览统计、国内外战绩、赛事覆盖数
- `/compare`
  - 双人对比面板中的基础统计项
- 首页或专题页
  - Top 胜率、Top 外战能力等扩展榜单

因此，`player_aggregate_stats` 应视为正式公共数据层，而不是某个页面的临时性能补丁。

---

## 11. 风险与取舍

### 11.1 优点

- 查询性能稳定
- 接口复杂度降低
- 页面性能不再依赖 Node 运行时缓存
- 更适合后续多页面复用

### 11.2 成本

- 需要新增 schema
- 需要新增正式导入脚本
- 需要维护统计口径文档
- 同步链路时长会略有增加

### 11.3 当前建议

即便同步链路增加几十秒，只要换来高频页面从秒级降到毫秒级，也是合理取舍。  
因为数据同步是低频后台任务，而页面访问是高频前台路径。

---

## 12. 分阶段实施建议

### Phase 1

- 新增 `player_aggregate_stats` 表
- 新增 `import_player_aggregate_stats.py`
- `/api/v1/rankings` 的 `win_rate` / `head_to_head_count` 改为 join 该表

### Phase 2

- `players.ts` / `compare.ts` 改读聚合表中的通用字段
- 移除运行时重统计逻辑的重复代码

### Phase 3

- 根据产品需求继续扩展更多稳定统计项
- 评估是否需要拆分更细粒度的赛事级、年度级统计表

---

## 13. 结论

对于排名页当前的统计排序性能问题，继续增加运行时缓存不是最终方案。  
正确方向是：

- 把高频页面依赖的聚合统计从“请求时现算”迁移到“导入时预计算”
- 让 Web 查询层只承担读取与排序
- 把 `player_aggregate_stats` 作为后续多页面优化的共享数据底座

这份文档作为后续数据库优化实施的设计基线，待后续排期落地。
