# 特殊赛事两阶段循环赛开发任务清单

日期：2026-04-24  
关联文档：`docs/design/special-event-round-robin.md`、`docs/design/backend.md`、`docs/design/frontend.md`、`docs/design/database.md`

---

## 0. 目标与范围

本文档用于把“特殊赛事两阶段循环赛展示方案”拆成可直接开发的任务。

本轮目标只覆盖：

- `event_id=2860`
- `sub_event_type_code=XT`
- 赛事详情页的冠军、流程、分阶段对阵与最终排名展示

本轮不要求：

- 通用 tie-break 规则自动计算
- 所有历史特殊赛事的一次性回填
- 为所有特殊赛制新增正式数据库表

---

## 1. 问题定义

当前系统对赛事详情页有两个强假设：

1. 冠军来自 `Final`
2. 赛事流程可被表达为 bracket

`event_id=2860` 不满足这两个假设，因此目前会出现：

- 无法得到冠军 / 亚军 / 季军
- 无法展示真实赛事流程
- 无法在赛事页展示团体赛级别对阵

---

## 2. 方案总览

本轮采用“最小可用方案”：

1. 新增 `manual_event_overrides/2860.json`
2. 后端在 `getEventDetail()` 中读取 override
3. 后端从 `matches` 聚合出团体赛级别 `TeamTie`
4. 前端赛事页增加 `RoundRobinView`
5. 赛事页根据 `presentationMode` 在 `BracketView` 与 `RoundRobinView` 之间切换

---

## 3. 推荐实施顺序

### Phase 1：数据与后端最小支撑

1. 新增 override 文件
2. 新增后端 override 读取逻辑
3. 新增团体赛聚合逻辑
4. 扩展赛事详情返回结构

### Phase 2：前端页面承载

5. 新增 `RoundRobinView`
6. 修改赛事详情页分支渲染
7. 补冠军 / 排名 / 团体赛列表展示

### Phase 3：验证与补文档

8. 完成 `2860` 页面验证
9. 补充数据库维护与实现说明

---

## 4. Task A：新增 override 数据文件

### 目标

建立 `event_id=2860` 的人工覆盖语义数据源。

### 涉及文件

- `data/manual_event_overrides/2860.json`

### 必须包含

- `presentation_mode`
- `sub_event_type_code`
- `stages`
- `final_standings`
- `podium`

### 验收标准

- 文件可被后端稳定读取
- 分组、第二阶段 8 队、最终排名与文档一致

---

## 5. Task B：后端增加 override 读取能力

### 目标

让 `getEventDetail()` 能识别特殊赛事模式。

### 涉及文件

- `web/lib/server/events.ts`

### 需要新增的能力

- 读取 `data/manual_event_overrides/{event_id}.json`
- 如果存在 override，则返回：
  - `presentationMode`
  - `roundRobinView`
- 如果不存在 override，则维持现有 knockout 逻辑

### 验收标准

- `event_id=2860` 返回 `presentationMode = "staged_round_robin"`
- 普通赛事返回值不受影响

---

## 6. Task C：从 matches 聚合团体赛级别对阵

### 目标

从 rubber 级记录恢复出团体赛级别 team tie。

### 涉及文件

- `web/lib/server/events.ts`

### 实现要求

- 聚合 key：
  - `event_id`
  - `sub_event_type_code`
  - `stage`
  - `round`
  - `team_a_code`
  - `team_b_code`
- `team_code` 来自每侧 `match_side_players.player_country`
- 团体赛比分规则：
  - `scoreA = rubber 胜场数`
  - `scoreB = rubber 负场数`

### 返回结构

- `TeamTie[]`
- 每条包含：
  - 团体赛双方
  - 总比分
  - winner
  - rubbers 明细

### 验收标准

- 中国 vs 法国、中国 vs 日本、中国 vs 韩国等比赛能正确聚合成一场团体赛
- 团体赛比分与百科页面一致

---

## 7. Task D：扩展赛事详情返回结构

### 目标

让赛事详情接口可同时承载 knockout 和 staged round robin。

### 涉及文件

- `web/lib/server/events.ts`
- 如有 API route 包装，则同步更新对应 route

### 新增字段

- `presentationMode`
- `roundRobinView`

### `roundRobinView` 最少包含

- `stages`
- `finalStandings`
- `podium`

### 冠军来源规则

- 特殊赛事优先来自 override `podium`
- 普通赛事继续来自现有 `sub_events`

### 验收标准

- `2860` 能返回冠军 / 亚军 / 季军
- 普通赛事冠军逻辑不回归

---

## 8. Task E：前端新增 RoundRobinView

### 目标

为特殊赛制赛事提供非 bracket 型展示组件。

### 涉及文件

- `web/app/events/[eventId]/page.tsx`
- 建议新增：
  - `web/components/events/RoundRobinView.tsx`
  - `web/components/events/StageGroupCard.tsx`
  - `web/components/events/FinalStandingsCard.tsx`

### 页面结构

1. Podium
2. Stage 1 Groups
3. Stage 2 Round Robin
4. Final Standings

### 展示要求

- Podium：冠军 / 亚军 / 季军
- 第一阶段：4 个 group 卡片
- 第二阶段：对阵列表
- 最终排名：1-8 名

### 验收标准

- `2860` 页面不再渲染 fake bracket
- 页面能清晰表达“两阶段循环赛 -> 最终排名”

---

## 9. Task F：赛事详情页分模式渲染

### 目标

保持赛事页兼容两种赛事模型。

### 涉及文件

- `web/app/events/[eventId]/page.tsx`

### 规则

- `presentationMode === "knockout"`：
  - 继续使用现有 bracket 区域
- `presentationMode === "staged_round_robin"`：
  - 使用 `RoundRobinView`

### 验收标准

- 不影响现有普通赛事页
- `2860` 自动切到特殊赛事视图

---

## 10. Task G：补充页面交互细节

### 目标

确保特殊赛事详情页也能沿用现有跳转链路。

### 需要覆盖

- 点击 team tie 下的 rubber，可进入比赛详情页
- 比赛详情页仍可返回所属赛事
- 不要求从 team tie 直接跳队伍详情页

### 验收标准

- `2860` 页面中的单盘比赛可以正常跳转到 `/matches/[matchId]`

---

## 11. Task H：数据库与导入链路后续扩展

### 本轮不必须实现

- `event_team_ties`
- `event_stage_standings`
- `event_presentation_overrides`

### 但需要记录的约束

- `import_event_draw_matches.py` 不应为 `2860` 构造 fake bracket
- `import_sub_events.py` 后续应支持 override 冠军来源

### 建议后续任务

1. 给 `import_sub_events.py` 增加 override 冠军支持
2. 视同类赛事数量决定是否将 team tie / standings 正式入库

---

## 12. 验证清单

### 数据验证

- `2860.json` 中 stage / standings / podium 与已确认文档一致

### 后端验证

- `getEventDetail(2860)` 返回 `presentationMode = staged_round_robin`
- 返回 `roundRobinView.podium`
- 返回 `roundRobinView.finalStandings`
- 返回各阶段的 `TeamTie`

### 前端验证

- 页面展示冠军 / 亚军 / 季军
- 页面展示第一阶段分组
- 页面展示第二阶段对阵
- 页面展示最终排名
- 页面不再展示传统 bracket

### 回归验证

- 普通 knockout 赛事详情页不受影响
- 比赛详情页不受影响

---

## 13. 推荐提交拆分

建议按以下粒度提交：

1. `feat(data): add manual override for mixed team world cup 2023`
2. `feat(events): support staged round robin event detail mode`
3. `feat(web): add round robin event detail view`
4. `docs(events): document special event round robin implementation`

---

## 14. 最短可演示路径

如果只追求最快让 `2860` 可展示，建议按以下最短路径：

1. 新增 `2860.json`
2. 后端读取 override 并返回 podium + finalStandings
3. 后端聚合 team ties
4. 前端新增最小版 `RoundRobinView`

这样即使暂时没有 standings 自动计算，也能先做到：

- 正确显示冠军
- 正确显示赛事流程
- 正确显示团体赛级别对阵

---

## 15. 完成标准

完成后，`event_id=2860` 应满足：

- 冠军、亚军、季军可见
- 第一阶段与第二阶段结构可见
- 团体赛级别对阵可见
- 不依赖 fake `Final`
- 不依赖 fake bracket
