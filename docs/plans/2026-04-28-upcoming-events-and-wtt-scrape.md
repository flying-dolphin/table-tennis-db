# 即将开赛 / 进行中赛事接入实施结果

日期：2026-04-28  
最后更新：2026-04-29  
关联文档：`docs/design/database.md`、`docs/design/PRD-v1.md`、`docs/event-data-update-workflow.md`

---

## 0. 结论

本轮“即将开赛 / 进行中赛事”接入已经完成到可用状态，网站目前已经具备：

- 首页和赛事列表展示 `draw_published` / `in_progress` 赛事
- 赛事详情页展示按天日程
- 赛事详情页展示按日期切换的比赛卡片
- 进行中团体赛在无历史签表落库时，直接基于 `event_schedule_matches` 展示小组赛积分表
- 当赛事同时存在小组赛与淘汰赛内容时，在同一签表页上下并存展示
- 进行中赛事在详情页补充北京时间提示

当前这条链路已经不再是纯计划状态，而是实际运行中的数据流。

---

## 1. 当前实际数据流

即将开赛 / 进行中赛事目前使用两套并行数据：

| 数据层 | 主要来源 | 主要落点 | 前端用途 |
| --- | --- | --- | --- |
| 按日纲要日程 | `data/event_schedule/{event_id}.json` | `event_session_schedule` | `日程` tab |
| 按场比赛赛程 | `data/wtt_raw/{event_id}/GetEventSchedule.json` | `event_schedule_matches` 及 side 表 | `比赛` tab、进行中团体赛积分表 |
| 官方已完赛结果补充 | `data/wtt_raw/{event_id}/GetOfficialResult_take10.json` | 当前主要由服务端运行时读取 | 进行中团体赛积分表、比分补充 |

历史赛事仍然主要走：

- `matches`
- `event_draw_matches`
- `sub_events`

也就是说，当前站点已经形成：

- 已完赛赛事：历史表链路
- 即将开赛 / 进行中赛事：`event_session_schedule` + `event_schedule_matches` 链路

---

## 2. 已完成项

### 2.1 Schema 与生命周期

已完成：

- `scripts/db/upgrade_schema_event_lifecycle.py`
- `events.lifecycle_status`
- `events.time_zone`
- `events.last_synced_at`
- `event_session_schedule`
- `event_draw_entries`
- `event_draw_entry_players`
- `event_schedule_matches`
- `event_schedule_match_sides`
- `event_schedule_match_side_players`

### 2.2 即将开赛事件回填

已完成：

- `scripts/db/backfill_events_calendar_event_id.py`

职责：

- 从 `events_calendar.href` 提取 `event_id`
- 对 `events` 中缺失的赛事补 INSERT
- 初始标记 `lifecycle_status='upcoming'`

### 2.3 按日日程导入

已完成：

- `scripts/db/import_session_schedule.py`

职责：

- 读取 `data/event_schedule/{event_id}.json`
- 解析中文项目、阶段、轮次
- 写入 `event_session_schedule`
- 将赛事从 `upcoming` 推进到 `draw_published`

### 2.4 WTT raw 抓取

已完成：

- `scripts/scrape_wtt_event.py`

当前抓取的核心文件包括：

- `GetEventDraws.json`
- `GetEventSchedule.json`
- `GetOfficialResult_take10.json`
- `GetLiveResult.json`
- `GetBrackets_{sub_event}.json`

### 2.5 WTT 赛程入库

已完成：

- `scripts/db/import_wtt_event.py`

职责：

- 读取 `data/wtt_raw/{event_id}/GetEventSchedule.json`
- 生成 `event_draw_entries`
- 生成 `event_draw_entry_players`
- 生成 `event_schedule_matches`
- 生成 `event_schedule_match_sides`
- 生成 `event_schedule_match_side_players`
- 按需补 `events.time_zone`
- 根据开赛时间推进 `events.lifecycle_status`

### 2.6 日常刷新调度

已完成：

- `scripts/scrape_event_results_daily.py`

当前真实行为：

- 选择 `lifecycle_status IN ('draw_published', 'in_progress')` 的赛事
- 调用 `scrape_wtt_event.py` 刷新 raw JSON
- 调用 `import_wtt_event.py` 重新导入 `GetEventSchedule.json`

注意：

- 这个脚本当前不会把进行中赛事 promote 到 `matches` / `event_draw_matches`
- 当前也不会把 `GetOfficialResult_take10.json` 写回数据库明细表

### 2.7 前端接入

已完成：

- 首页卡片已接入即将开赛 / 进行中赛事
- 赛事详情页已接入 `日程 / 签表 / 比赛` 三个 tab
- `比赛` tab 改成按日期横向切换
- 赛程重复比赛在服务端取数层完成去重
- 进行中团体赛支持小组赛积分表
- 小组赛与淘汰赛支持同页并存
- 进行中赛事详情页补充北京时间提示

---

## 3. event 3216 现状

`event_id = 3216` 已作为这条链路的主要验证样例跑通。

已验证的能力：

- `event_session_schedule` 已导入
- `data/wtt_raw/3216/*` 已抓取
- `event_schedule_matches` 已导入
- `比赛` tab 按日期展示比赛卡片
- `签表` tab 在小组赛阶段展示积分表
- 赛事详情页对进行中赛事显示北京时间提示

补充说明：

- `3216` 的原始赛程源数据存在重复 `external_match_code`
- 当前页面侧重复展示问题已通过服务端去重解决

---

## 4. 与原计划相比的实际差异

### 4.1 前端时区策略已调整

原计划里有“前端按用户本地时区自动转换”的设想。  
当前实际实现不是统一自动转用户本地时区，而是：

- 日程 / 比赛主时间仍以赛事当地时间为主
- 对进行中赛事额外提示北京时间

这更符合当前主要用户场景，也避免所有历史页面同时改动。

### 4.2 团体赛进行中展示不再依赖历史表

原计划更偏向“等 `matches/event_draw_matches` 完整后再展示”。  
当前实际实现是：

- 对进行中团体赛，直接从 `event_schedule_matches` 构建小组赛视图
- 再结合 `GetOfficialResult_take10.json` 在运行时补充部分已完赛比分

### 4.3 官方结果当前主要是运行时消费

原计划里提到把 `GetOfficialResult` 明细逐步写回 DB。  
目前实际代码里，这部分更多是：

- raw JSON 抓下来
- `web/lib/server/events.ts` 在读取赛事详情时直接消费

因此当前结果补充能力存在，但还不是完整落库链路。

---

## 5. 剩余事项

当前未完成或仍需增强的点主要有这些：

1. 完赛赛事从 `event_schedule_*` 晋升到 `matches / event_draw_matches`
   当前计划中的 `promote_schedule_to_history.py` 还没有成为实际日常链路。

2. `events.time_zone` 的完整治理
   目前部分赛事仍为空，`import_wtt_event.py` 只做了有限推断。

3. `GetOfficialResult_take10.json` 的数据库化
   当前主要由服务端运行时读取，后续可考虑补正式落库表或回写逻辑。

4. 进行中淘汰赛签表的进一步完善
   当前团体赛小组阶段已经可用，但更完整的进行中淘汰树还有增强空间。

---

## 6. 现阶段建议

当前建议把这条链路视为“已落地的第一版生产方案”，后续优先级建议如下：

1. 优先补数据治理
   - `events.time_zone`
   - official result 落库

2. 再补完赛晋升
   - `event_schedule_* -> matches`
   - `event_draw_entries -> event_draw_matches`

3. 最后再做更多前端细化
   - 更完整的进行中淘汰赛视图
   - 更多时区展示策略

---

## 7. 相关文档

- 数据更新流程：`docs/event-data-update-workflow.md`
- 赛事详情页运行时逻辑：`web/lib/server/events.ts`
- 赛事详情页 UI：`web/app/events/[eventId]/page.tsx`
