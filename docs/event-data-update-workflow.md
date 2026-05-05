# 赛事数据更新流程

最后更新：2026-05-05

---

## 0. 目的

本文档描述当前代码库中“即将开赛 / 进行中赛事”的实际数据更新流程。  
这里写的是当前真实可运行链路，不是理想态设计。

---

## 1. 当前数据分层

系统现在有两套赛事数据链路：

### 1.1 历史赛事链路

主要表：

- `matches`
- `event_draw_matches`
- `sub_events`

适用场景：

- 已完赛赛事
- 已有完整结果、签表、冠军数据的赛事

### 1.2 即将开赛 / 进行中赛事链路

主要表：

- `events`
- `event_session_schedule`
- `event_draw_entries`
- `event_draw_entry_players`
- `event_schedule_matches`
- `event_schedule_match_sides`
- `event_schedule_match_side_players`
- `current_event_session_schedule`
- `current_event_group_standings`
- `current_event_brackets`
- `current_event_team_ties`
- `current_event_team_tie_sides`
- `current_event_team_tie_side_players`
- `current_event_matches`
- `current_event_match_sides`
- `current_event_match_side_players`

适用场景：

- 即将开赛
- 已开赛但仍在进行中
- 历史表尚未完整落库的赛事

---

## 2. 数据源

### 2.1 赛事基础信息

来源：

- `events_calendar`
- `data/events_list/...`

用途：

- 建立 `events` 基础行
- 补 `event_id`
- 初始化 `lifecycle_status`

### 2.2 人工维护的按日日程

来源：

- `data/event_schedule/{event_id}.json`

用途：

- 提供赛事每天的纲要式日程
- 驱动赛事详情页的 `日程` tab

### 2.3 WTT raw 数据

来源：

- `https://liveeventsapi.worldtabletennis.com/api/cms`

主要 raw 文件：

- `GetEventDraws.json`
- `GetEventSchedule.json`
- `GetOfficialResult_take10.json`
- `GetLiveResult.json`
- `GetBrackets_{sub_event}.json`

落地目录：

- `data/wtt_raw/{event_id}/`

用途：

- 按场比赛赛程
- 小组赛 / 淘汰赛结构信息
- 官方最近完赛结果补充

### 2.4 WTT 当前赛事 runtime 数据

来源：

- WTT 公开 CMS API
- WTT 团体赛事页面 DOM，包括 Live Matches、Completed、Standings 页面

主要文件：

- `GetEventSchedule.json`
- `MTEAM_standings.json`
- `WTEAM_standings.json`
- `GetBrackets_{sub_event}.json`
- `GetLiveResult.json`
- `completed_matches.json`

落地目录：

- `data/live_event_data/{event_id}/`

用途：

- 当前赛事的 session 赛程、小组积分、淘汰赛签表
- 进行中 team tie / individual rubber
- 已完结 team tie / individual rubber

数据源优先级：

- `completed_matches.json` 是已完结 team tie 和 rubber 的主数据源
- `GetLiveResult.json` 是进行中 team tie 和 rubber 的主数据源
- `GetEventSchedule.json` 只作为补充来源，用于 match code、赛程时间、台号、队伍 roster 等信息，不再单独重建 `current_event_team_ties`

---

## 3. 生命周期字段

当前主要使用 `events.lifecycle_status`：

- `upcoming`
- `draw_published`
- `in_progress`
- `completed`

实际推进方式：

1. `backfill_events_calendar_event_id.py`
   - 新建赛事时通常为 `upcoming`

2. `import_session_schedule.py`
   - 导入日程后把 `upcoming` 推进到 `draw_published`

3. `import_wtt_event.py`
   - 导入 WTT 赛程后，根据开赛时间推进到 `in_progress`

4. `completed`
   - 当前还没有完整自动晋升链路统一维护

---

## 4. 实际更新步骤

### 4.1 建立 / 补齐 events 基础记录

脚本：

- `scripts/db/backfill_events_calendar_event_id.py`

职责：

- 从 `events_calendar.href` 提取 `event_id`
- 对 `events` 中缺失的赛事插入基础记录

建议运行时机：

- 新抓完赛事日历后
- 发现某些 upcoming 赛事还没进入 `events` 时

### 4.2 导入按日日程

脚本：

- `scripts/db/import_session_schedule.py`

输入：

- `data/event_schedule/{event_id}.json`

输出：

- `event_session_schedule`

职责：

- 解析中文日期、时间、赛事项目、阶段、轮次
- 写入按天 session 纲要
- 把 `events.lifecycle_status` 从 `upcoming` 推到 `draw_published`

常用命令：

```bash
python scripts/db/import_session_schedule.py --event 3216
```

### 4.3 抓取 WTT raw 数据

脚本：

- `scripts/scrape_wtt_event.py`

输入：

- `event_id`
- sub-event 列表，当前默认 `MTEAM WTEAM`

输出：

- `data/wtt_raw/{event_id}/*.json`

常用命令：

```bash
python scripts/scrape_wtt_event.py --event-id 3216 --sub-events MTEAM WTEAM
```

### 4.4 导入按场比赛赛程

脚本：

- `scripts/db/import_wtt_event.py`

输入：

- `data/wtt_raw/{event_id}/GetEventSchedule.json`

输出：

- `event_draw_entries`
- `event_draw_entry_players`
- `event_schedule_matches`
- `event_schedule_match_sides`
- `event_schedule_match_side_players`

职责：

- 解析每个 unit
- 规范化 `Round -> stage_code / round_code / group_code`
- 生成 entry 与 side/player 结构
- 计算并保存：
  - `scheduled_local_at`
  - `scheduled_utc_at`
- 按需补 `events.time_zone`
- 根据赛事时间推进 `events.lifecycle_status`

常用命令：

```bash
python scripts/db/import_wtt_event.py --event 3216
```

### 4.5 抓取当前赛事 runtime 数据

脚本：

- `scripts/runtime/scrape_current_event.py`

输出：

- `data/live_event_data/{event_id}/GetEventSchedule.json`
- `data/live_event_data/{event_id}/MTEAM_standings.json`
- `data/live_event_data/{event_id}/WTEAM_standings.json`
- `data/live_event_data/{event_id}/GetBrackets_{sub_event}.json`
- `data/live_event_data/{event_id}/GetLiveResult.json`
- `data/live_event_data/{event_id}/completed_matches.json`

常用命令：

```bash
python scripts/runtime/scrape_current_event.py --event-id 3216
```

### 4.6 导入当前赛事 runtime 数据

脚本：

- `scripts/runtime/import_current_event.py`

默认导入顺序：

1. `session_schedule` -> `current_event_session_schedule`
2. `standings` -> `current_event_group_standings`
3. `brackets` -> `current_event_brackets`
4. `live` -> `current_event_team_ties` + `current_event_matches`
5. `completed` -> `current_event_team_ties` + `current_event_matches`

常用命令：

```bash
python scripts/runtime/import_current_event.py --event-id 3216
python scripts/runtime/import_current_event.py --event-id 3216 --sources live completed
python scripts/runtime/import_current_event_live.py --event-id 3216
python scripts/runtime/import_current_event_completed.py --event-id 3216
```

注意：

- `current_event_team_ties` 由 `import_current_event_live.py` 和 `import_current_event_completed.py` 随 `current_event_matches` 一起维护
- `--sources team_ties` 和 `--sources matches` 是兼容别名，会执行 `live + completed`
- 不再运行 schedule-only team tie skeleton 导入；`GetEventSchedule.json` 只做补充数据

### 4.7 日常刷新进行中赛事

脚本：

- `scripts/scrape_event_results_daily.py`

当前真实行为：

1. 找出 `events.lifecycle_status IN ('draw_published', 'in_progress')`
2. 重新抓取 WTT raw 数据
3. 重新执行 `import_wtt_event.py`

常用命令：

```bash
python scripts/scrape_event_results_daily.py
python scripts/scrape_event_results_daily.py --event 3216
python scripts/scrape_event_results_daily.py --event 3216 --skip-scrape
```

注意：

- 当前这个脚本不会把数据 promote 到 `matches`
- 也不会把 `GetOfficialResult_take10.json` 系统化写回数据库比赛明细表

---

## 5. 前端当前读哪些数据

### 5.1 首页 / 赛事列表

主要读取：

- `events`
- `event_session_schedule`
- `matches`（部分历史信息）

### 5.2 赛事详情页 `日程` tab

主要读取：

- `event_session_schedule`

补充逻辑：

- 进行中赛事会根据 `event.timeZone` 额外提示北京时间

### 5.3 赛事详情页 `比赛` tab

主要读取：

- `event_schedule_matches`

当前逻辑：

- 按日期聚合
- 服务端对重复比赛做去重
- 对进行中赛事补北京时间提示

### 5.4 赛事详情页 `签表` tab

当前按赛事状态分两路：

1. 历史 / 已落库赛事
   - `matches`
   - `event_draw_matches`

2. 进行中团体赛
   - `event_schedule_matches`
   - `data/wtt_raw/{event_id}/GetOfficialResult_take10.json`（运行时读取）

也就是说，进行中团体赛的小组积分表不是从历史表来的，而是从赛程表推导出来的。

---

## 6. event 3216 这类赛事的推荐更新顺序

推荐顺序：

1. 补 `events`

```bash
python scripts/db/backfill_events_calendar_event_id.py
```

2. 导入日程

```bash
python scripts/db/import_session_schedule.py --event 3216
```

3. 抓 raw

```bash
python scripts/scrape_wtt_event.py --event-id 3216 --sub-events MTEAM WTEAM
```

4. 导入 WTT 赛程

```bash
python scripts/db/import_wtt_event.py --event 3216
```

5. 后续刷新

```bash
python scripts/scrape_event_results_daily.py --event 3216
```

---

## 7. 时区现状

当前时区相关字段：

- `events.time_zone`
- `event_schedule_matches.scheduled_local_at`
- `event_schedule_matches.scheduled_utc_at`

实际情况：

- `events.time_zone` 不是所有赛事都有
- `import_wtt_event.py` 会优先复用已有 `time_zone`
- 如果为空，会做有限推断，例如 London -> `Europe/London`

前端当前展示策略：

- 主时间仍显示赛事当地时间
- 对进行中赛事额外补北京时间提示

---

## 8. 当前已知限制

1. `events.time_zone` 仍不完整
   目前还有不少赛事为空，需要后续治理。

2. `GetOfficialResult_take10.json` 还不是正式落库链路
   当前主要由服务端运行时读取补充。

3. 历史表晋升链路未完全接上
   `event_schedule_* -> matches / event_draw_matches` 仍需后续实现或打通。

4. `scrape_event_results_daily.py` 当前只负责“抓 raw + 重导赛程”
   还不包含完整的结果归档流程。

---

## 9. 相关代码入口

- `scripts/db/backfill_events_calendar_event_id.py`
- `scripts/db/import_session_schedule.py`
- `scripts/scrape_wtt_event.py`
- `scripts/db/import_wtt_event.py`
- `scripts/scrape_event_results_daily.py`
- `web/lib/server/events.ts`
- `web/app/events/[eventId]/page.tsx`
