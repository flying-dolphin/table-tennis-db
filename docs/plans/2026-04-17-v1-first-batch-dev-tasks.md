# ITTF V1 第一批开发任务清单

日期：2026-04-17  
关联文档：`docs/design/PRD-v1.md`、`docs/design/database.md`、`docs/design/backend.md`、`docs/design/frontend.md`、`docs/plans/2026-04-17-plan.md`

---

## 0. 目标与范围

本文档是在 `docs/plans/2026-04-17-plan.md` 基础上的第一批开发执行清单，目标不是覆盖 V1 全部内容，而是把最关键的架构对齐与主链路能力拆成可直接开工的任务。

第一批开发聚焦：

- 数据层与 schema 对齐
- `/api/v1` 基础公开接口
- 首页真实数据驱动
- 排名页与双球员对比主链路
- 球员详情页重构
- 赛事页与比赛页链路
- 最小账号体系
- 搜索结果页基础闭环

---

## 1. 当前完成度 Review

### 1.1 已有基础

- 首页原型已存在：`web/app/page.tsx`
- 首页模块雏形已存在：`web/components/home/*`
- 球员详情页雏形已存在：`web/app/players/[slug]/page.tsx`
- 旧版 API 已存在：
  - `web/app/api/rankings/route.ts`
  - `web/app/api/players/[slug]/route.ts`
- SQLite 基础接入已做过一轮：
  - `scripts/db/schema.sql`
  - `scripts/db/import*.py`
- Python 正式入库链路已存在一套：
  - `scripts/db/import_players.py`
- `scripts/db/import_rankings.py`
- `scripts/db/import_events.py`
- `scripts/db/import_events_calendar.py`
- `scripts/db/import_matches.py`
- `scripts/db/import_event_categories.py`
  - `scripts/db/import_points_rules.py`

### 1.2 当前主要问题

- 首页和列表仍使用 mock 数据
- 数据层仍大量直接读 JSON：`web/lib/data.ts`
- `scripts/db/schema.sql` 与 `docs/design/database.md` 仍需进一步对齐和验证
- `web/scripts/sync-to-db.ts` 已被确认应删除，不再进入正式链路
- Python 入库脚本仍有部分逻辑需要继续从旧结构切到 `event_categories`
- `events_calendar` 仍需正式导入脚本支撑首页和赛事链路
- 尚未建立 `/api/v1` 新接口体系
- 尚未实现：
  - `/rankings`
  - `/compare`
  - `/events`
  - `/events/[eventId]`
  - `/matches/[matchId]`
  - `/auth`
  - `/me`
  - `/search`
- 底部导航与 PRD 不一致

### 1.3 结论

当前状态更接近“有一个可浏览的原型”，而不是“已经进入正式 V1 开发”。  
第一批开发的重点必须是：先完成**数据模型、入库链路、API 边界和主链路页面**的统一，再做局部功能补丁。

---

## 2. 第一批任务总览

本清单按 8 个主任务组织，与 `2026-04-17-plan.md` 保持一致，但每个任务进一步拆细到执行层。

### Task 1：后端数据层与 schema 对齐

目标：把现有临时 SQLite 结构切到新设计基线，保证后续 API 站在统一数据模型上。

### Task 2：打通 `/api/v1` 基础公开接口

目标：建立首页、排名页、球员页、对比页所需的新 API 骨架。

### Task 3：首页改造为真实数据驱动

目标：用真实接口替换首页 mock，并对齐底部导航与搜索框交互。

### Task 4：实现排名页与对比页主链路

目标：落地 `首页 -> 排名页 -> 勾选两名球员 -> 对比页`。

### Task 5：重构球员详情页

目标：把现有球员页改造成 PRD 正式结构。

### Task 6：实现赛事列表页、赛事详情页与比赛详情页

目标：落地赛事维度浏览链路。

### Task 7：实现最小账号体系和搜索拦截

目标：建立登录后可搜的权限门槛。

### Task 8：实现搜索结果页

目标：落地 V1 自然语言搜索闭环。

---

## 3. 依赖关系与执行顺序

### 3.1 推荐依赖

```
Task 1（数据层）
  └─> Task 2（API 骨架）
        ├─> Task 3（首页）
        ├─> Task 4（排名页 + 对比页）
        ├─> Task 5（球员详情页）
        ├─> Task 6（赛事页 + 比赛页）
        └─> Task 7（账号体系）
              └─> Task 8（搜索结果页）
```

### 3.2 推荐执行顺序

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7
8. Task 8

说明：

- Task 3-6 可以在 Task 2 完成后适度并行
- Task 8 明确依赖 Task 7，而不是 Task 6

---

## 4. Task 1：后端数据层与 schema 对齐

## 4.1 盘点现有 schema 与目标 schema 差异

**目标**

- 对比 `scripts/db/schema.sql` 与 `docs/design/database.md`
- 明确旧表保留/废弃/迁移策略

**涉及文件**

- `scripts/db/schema.sql`
- `docs/design/database.md`
- `docs/design/backend.md`

**输出**

- 一份差异清单
- 一份第一批必须落地的表和字段清单

## 4.2 重写 `scripts/db/schema.sql`

**目标**

- 建立最小可用但与正式设计一致的 schema

**必须覆盖的核心表**

- `players`
- `ranking_snapshots`
- `ranking_entries`
- `points_breakdown`
- `event_categories`
- `event_type_mapping`
- `sub_event_types`
- `events`
- `sub_events`
- `matches`
- `events_calendar`

**要求**

- 表名、字段名尽量与 `database.md` 一致
- 三大赛 / 七大赛相关统计必须能落地到字段和查询
- 为首页、排名页、球员页、赛事页、比赛页增加必要索引

**完成标准**

- 新 schema 可执行
- 不再依赖当前 demo 版 `players/events/matches` 简化结构

## 4.3 统一正式入库链路，废弃 web 侧 demo 同步脚本

**目标**

- 以 `scripts/db/import*.py` 作为唯一正式入库链路
- 删除 `web/scripts/sync-to-db.ts`
- 将 Python 入库脚本升级到最新 schema 和赛事分类体系

**涉及文件**

- `scripts/db/schema.sql`
- `scripts/db/import_players.py`
- `scripts/db/import_rankings.py`
- `scripts/db/import_events.py`
- `scripts/db/import_events_calendar.py`
- `scripts/db/import_matches.py`
- `scripts/db/import_event_categories.py`
- `scripts/db/import_points_rules.py`
- 如有必要：
  - `scripts/db/import_dictionaries.py`
  - `scripts/db/init_database.py`
  - `scripts/db/upgrade_schema.py`

**要求**

- `sync-to-db.ts` 不再作为正式入库方案
- `import_event_categories.py` 的 `sort_order` 必须按 `data/event_category_mapping.json` 的顺序从 1 开始写入
- 盘点 Python 入库脚本与最新 schema 的差异
- 增加 `import_events_calendar.py`，正式导入 `events_calendar`
- `import_matches.py` 不再依赖 `tmp/event_mapping.json`，改为基于数据库内 `events` 表关联 `event_id`
- 优先改造 `import_events.py`，从旧 `event_types` 切到新 `event_categories + event_type_mapping`
- 明确统一入库顺序：
  1. init schema
  2. import dictionaries / categories
  3. import players
  4. import rankings
  5. import events
  6. import events calendar
  7. import matches
- web 前端和 `/api/v1` 只读 SQLite，不再维护独立 web 侧入库脚本
- `import_points_rules.py` 保留为后续实现任务，本批不要求导入 `points_rules`

**完成标准**

- Python 入库链路可写入新 schema
- `sync-to-db.ts` 已删除并从开发链路中移除

## 4.4 迁移现有 `player_profiles` 数据

**目标**

- 从现有 profile 数据迁移到新 `players` 表

**要求**

- 保证 slug、国家、头像、职业统计字段可用
- 兼容后续球员详情页和排名页需要的字段

## 4.5 建立统一数据访问层

**目标**

- 把当前 `web/lib/data.ts` 的直接读 JSON 逻辑迁移到 SQLite 查询层

**涉及文件**

- `web/lib/data.ts`
- `web/lib/server/db.ts`
- 可新增：
  - `web/lib/server/home.ts`
  - `web/lib/server/rankings.ts`
  - `web/lib/server/players.ts`
  - `web/lib/server/events.ts`
  - `web/lib/server/search.ts`

**完成标准**

- 页面和 API 不直接读 JSON
- 查询逻辑按域拆分

---

## 5. Task 2：打通 `/api/v1` 基础公开接口

## 5.1 建立 `/api/v1` 路由骨架

**建议目录**

- `web/app/api/v1/home/calendar/route.ts`
- `web/app/api/v1/home/rankings/route.ts`
- `web/app/api/v1/rankings/route.ts`
- `web/app/api/v1/compare/route.ts`
- `web/app/api/v1/players/[slug]/route.ts`
- `web/app/api/v1/events/route.ts`
- `web/app/api/v1/events/[eventId]/route.ts`
- `web/app/api/v1/matches/[matchId]/route.ts`
- `web/app/api/v1/search/route.ts`
- `web/app/api/v1/auth/register/route.ts`
- `web/app/api/v1/auth/login/route.ts`
- `web/app/api/v1/auth/logout/route.ts`
- `web/app/api/v1/auth/me/route.ts`
- `web/app/api/v1/feedback/route.ts`

## 5.2 统一响应格式

**目标**

- 所有新接口都对齐 PRD 第 11.3 章的响应结构

**完成标准**

- 成功/失败响应格式统一
- 未授权、限流、校验错误有统一 shape

## 5.3 优先实现 5 个基础公开接口

**必须先落地**

- `GET /api/v1/home/calendar`
- `GET /api/v1/home/rankings`
- `GET /api/v1/rankings`
- `GET /api/v1/players/{slug}`
- `GET /api/v1/compare`

**原因**

- 这 5 个接口能先支撑首页、排名页、球员详情页、对比页

## 5.4 暂时保留旧 API，但标记为待废弃

**涉及文件**

- `web/app/api/rankings/route.ts`
- `web/app/api/players/[slug]/route.ts`

**要求**

- 不立即删除，避免开发中断
- 标记 deprecated
- 新页面不再依赖旧接口

---

## 6. Task 3：首页改造为真实数据驱动

## 6.1 重写 SearchBox

**文件**

- `web/components/home/SearchBox.tsx`

**目标**

- 从 demo 搜索框改成 PRD 版本

**要求**

- 显示示例问题
- 未登录可见但不可执行
- 点击后跳登录页
- 已登录后提交搜索

## 6.2 重写 EventScroller 和 CalendarModal

**文件**

- `web/components/home/EventScroller.tsx`
- `web/components/home/CalendarModal.tsx`

**目标**

- 去掉 `MOCK_MONTHS`
- 改为接 `/api/v1/home/calendar`

**要求**

- 保留月卡 -> 放大态交互
- 放大态左右滑动切月
- 点击放大的日历图进入赛事列表页

## 6.3 重写 RankingTable

**文件**

- `web/components/home/RankingTable.tsx`

**目标**

- 去掉 `MOCK_RANKINGS`
- 接 `/api/v1/home/rankings`

**要求**

- 展示 PRD 约定字段
- 点击球员进入详情页
- 提供“查看更多”

## 6.4 修正底部导航

**文件**

- `web/components/BottomNav.tsx`
- `web/app/layout.tsx`

**目标**

- 改成：
  - 首页
  - 排名
  - 赛事
  - 用户入口

**要求**

- 去掉“日程”独立入口
- 未登录显示头像占位
- 已登录进入用户页

## 6.5 清理首页原型遗留文案

**文件**

- `web/components/home/Hero.tsx`
- `web/app/page.tsx`

**目标**

- 去掉英文 demo 文案
- 收敛为 PRD 的导航型首页

---

## 7. Task 4：实现排名页与对比页主链路

## 7.1 新建排名页

**文件**

- `web/app/rankings/page.tsx`
- 可新增 `web/components/rankings/*`

**模块**

- 页面标题
- 排序切换
- 排名表
- 对比操作区

## 7.2 实现三种排序切换

**要求**

- 积分
- 胜率
- 交手次数

## 7.3 实现勾选对比逻辑

**要求**

- 只能勾选两人
- 勾选两人后激活对比动作

## 7.4 新建对比页

**文件**

- `web/app/compare/page.tsx`
- 可新增 `web/components/compare/*`

**模块**

- 双方球员卡片
- 核心指标对比区
- 历史交手汇总区
- 历史交手记录表

## 7.5 对比页支持替换其中一个球员

**目标**

- 不返回排名页也能重新发起对比

## 7.6 对比页跳转链路补齐

**目标**

- 点击球员 -> 球员页
- 点击比赛 -> 比赛详情页

---

## 8. Task 5：重构球员详情页

## 8.1 重构页面结构

**文件**

- `web/app/players/[slug]/page.tsx`
- 可新增 `web/components/player/*`

**模块**

- 顶部信息区
- 核心统计区
- 最近比赛
- 比赛记录（events list）
- Top 3 对手

## 8.2 移除旧统计逻辑

**目标**

- 删除页面内基于 `events.reduce(...)` 的临时统计
- 完全依赖接口返回

## 8.3 最近比赛模块按 PRD 收敛

**要求**

- 固定最近 3 场
- 缺失时显示“暂无数据” + “想要”

## 8.4 比赛记录模块按 `events list` 展示

**要求**

- 不再逐场展开
- 按赛事倒序

## 8.5 Top 3 对手模块接入

**要求**

- 展示交手次数、胜率、最近一次交手时间
- 支持跳转对手详情页

---

## 9. Task 6：实现赛事列表页、赛事详情页与比赛详情页

## 9.1 新建赛事列表页

**文件**

- `web/app/events/page.tsx`
- 可新增 `web/components/events/*`

**要求**

- 支持按年份切换
- 最早支持到 2014

## 9.2 新建赛事详情页

**文件**

- `web/app/events/[eventId]/page.tsx`

**要求**

- 支持多个 `sub event`
- 普通赛事默认女单
- 团体赛默认女子团体
- 展示正赛对战图和晋级路径
- 展示当前 `sub event` 冠军
- 无数据 `sub event` 置灰

## 9.3 新建比赛详情页

**文件**

- `web/app/matches/[matchId]/page.tsx`

**要求**

- 展示赛事名称、sub event、轮次、日期、双方球员、国家、比分、局分、获胜方
- 提供返回所属赛事入口

## 9.4 打通页面跳转关系

**要求**

- 赛事列表页 -> 赛事详情页
- 赛事详情页对战图 -> 比赛详情页
- 比赛详情页 -> 所属赛事
- 比赛详情页双方球员 -> 球员详情页

## 9.5 落地对应公开接口

**接口**

- `GET /api/v1/events?year=...`
- `GET /api/v1/events/{eventId}?sub_event=...`
- `GET /api/v1/matches/{matchId}`

---

## 10. Task 7：实现最小账号体系和搜索拦截

## 10.1 新建统一登录 / 注册页

**文件**

- `web/app/auth/page.tsx`
- 可新增 `web/components/auth/*`

**要求**

- 一个页面内切换登录 / 注册

## 10.2 注册流程落地

**流程**

1. 输入邮箱、用户名
2. 发送验证码
3. 设置密码
4. 完成注册

**要求**

- 用户名长度与字符规则符合 PRD
- 明确错误提示符合 PRD

## 10.3 登录流程落地

**要求**

- 邮箱 + 密码
- 登录态记住 30 天
- 登录成功后回首页
- 登录态失效时直接跳登录页

## 10.4 新建用户页

**文件**

- `web/app/me/page.tsx`

**要求**

- 展示用户名、邮箱、注册时间
- 提供退出登录

## 10.5 实现账号接口

**接口**

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

## 10.6 实现搜索入口拦截

**目标**

- 未登录点击搜索框直接跳登录页
- 未登录不允许执行搜索

## 10.7 基础限流

**目标**

- 注册接口限流
- 登录接口限流
- 限流时前端收到明确提示

---

## 11. Task 8：实现搜索结果页

## 11.1 新建搜索结果页

**文件**

- `web/app/search/page.tsx`
- 可新增 `web/components/search/*`

## 11.2 实现搜索接口

**接口**

- `POST /api/v1/search`

**要求**

- 登录后访问
- 问题类型识别
- 结果路由

## 11.3 支持 4 种结果类型

- `redirect_compare`
- `search_result`
- `mixed_result`
- `unsupported`

## 11.4 优先支持的问题类型

- 两名球员最近 3 年交手记录
- 两名球员分别与第三名球员的交手次数、胜率对比
- 两名球员最近 3 年和某国家对手的交手记录对比
- 两名球员外战胜率对比

## 11.5 mixed_result 页面结构

**要求**

1. 先展示结构化结果
2. 再展示搜索结果表格

## 11.6 搜索状态处理

**要求**

- 无结果：显示“没有找到结果，点击反馈”
- 不支持：显示“暂不支持该问题类型”
- 搜索接口限流

## 11.7 反馈接口

**接口**

- `POST /api/v1/feedback`

**要求**

- 接收当前页面接口请求参数
- 成功后前端显示“已反馈”

---

## 12. 补充任务：统一空状态与反馈组件

## 12.1 统一反馈按钮接入

**涉及页面**

- 搜索页
- 缺失数据模块
- 赛事详情页无数据 `sub event`
- 球员页最近比赛缺失

## 12.2 统一空状态组件

**至少支持**

- 暂无数据
- 点击上报
- 点击反馈
- 想要

## 12.3 简单 loading 统一

**目标**

- 页面统一使用轻量 loading
- 不引入复杂 skeleton 体系

---

## 13. 每个主任务的验收检查

## Task 1 验收

- 新 schema 可执行
- Python 正式入库链路可写入新 schema
- `sync-to-db.ts` 已删除
- 页面查询不再依赖直接读 JSON

## Task 2 验收

- `/api/v1` 基础接口可访问
- 响应格式统一
- 旧接口不再被新页面依赖

## Task 3 验收

- 首页不再依赖 mock
- 底部导航符合 PRD
- 搜索框交互正确

## Task 4 验收

- 排名页三种排序可用
- 可勾选 2 名球员进入对比页
- 对比页可展示核心指标和历史交手记录

## Task 5 验收

- 球员详情页对齐 PRD
- 最近比赛、比赛记录、Top3 对手可用
- 页面不再使用旧统计逻辑

## Task 6 验收

- 赛事列表页可按年份切换
- 赛事详情页支持 `sub event` 切换
- 正赛对战图可用
- 比赛详情页可展示核心字段

## Task 7 验收

- 注册 / 登录 / 登出 / me 可用
- 未登录无法执行搜索
- 登录后回首页
- 限流和错误提示符合 PRD

## Task 8 验收

- 搜索页可承接自然语言搜索
- 4 种结果类型可正确处理
- 支持的问题类型可返回结果
- 无结果和不支持状态展示正确
- 反馈接口可用

---

## 14. 建议分批提交方式

建议按以下粒度提交代码：

1. `feat(db): align sqlite schema and import pipeline with prd v1`
2. `feat(api): add v1 public endpoints for home rankings players compare`
3. `feat(web): migrate home page from mock to api`
4. `feat(web): add rankings and compare pages`
5. `feat(web): rebuild player detail page with v1 modules`
6. `feat(web): add events event-detail and match-detail pages`
7. `feat(auth): add minimal auth flow and search access control`
8. `feat(search): add v1 search result flow and feedback endpoint`

---

## 15. 最短可演示路径

如果开发资源有限，建议先打通下面的演示链路：

1. 首页
2. 排名页
3. 对比页
4. 球员详情页
5. 登录页搜索拦截

第二阶段再补：

6. 赛事列表页
7. 赛事详情页
8. 比赛详情页
9. 搜索结果页

原因：

- 第一阶段最能体现产品差异化
- 第二阶段补齐赛事链路和搜索闭环
