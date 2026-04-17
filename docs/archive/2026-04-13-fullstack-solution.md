# ITTF 全栈方案设计（先设计后开发）

版本：v1.0  
日期：2026-04-13

---

## 1. 设计目标

在不立即改现有代码的前提下，先完成可落地的前后端整体方案，确保后续修复与开发都围绕统一架构执行。

核心目标：
- 统一数据事实来源，解决“文档、代码、数据目录不一致”问题。
- 明确前后端边界与 API 合同，避免页面直接耦合原始 JSON。
- 设计可持续的数据采集-翻译-入库-发布链路。
- 为上线运营预留监控、告警、回滚与手动干预能力。
- 数据均为离线采集，不涉及实时更新，在线只有查询和浏览功能。尽量做到轻量级方案，避免过度设计。
- 前端采用移动优先 + 响应式设计，样式风格与交互方式以移动端为准，桌面端基本可用。

---

## 2. 产品范围（V1）

一期范围：女子单打数据平台

功能模块：
- 首页：赛事日程，世界排名前20
- ranking页：支持按积分排序、按运动员胜率、对手交手次数排序
- 运动员详情：运动员的个人信息、头像、统计数据、比赛记录
- 赛事列表页：展示历年赛事日程
- 比赛详情：展示比赛的详细信息、对战图、比赛结果

非目标（V1 不做）：
- 搜索功能（V2 实现基于 LLM API 的自然语言搜索）。
- 全项目种（男单/双打）全面覆盖。
- 复杂社交功能（收藏、评论）。
- 高频实时比分推送。

---

## 3. 方案设计

### 3.1 整体设计

技术栈选择：
- 前端：Next.js (App Router) + TypeScript
- 后端：Node.js
- 数据处理: Python
- 数据库：SQLite
- 爬虫：Playwright/Patchright

### 3.2. 信息架构与前端路由

路由设计：
- `/` 首页
- `/rankings` 排名页
- `/players/[slug]` 球员详情
- `/events` 赛事列表
- `/events/[eventId]` 赛事详情
- `/matches/[matchId]` 比赛详情
- `/search` 搜索结果页（V2）

API 路由（BFF）：
- `GET /api/v1/rankings?week=...&category=women_singles`
- `GET /api/v1/players?country=...&page=...`
- `GET /api/v1/players/{slug}`
- `GET /api/v1/players/{slug}/matches?year=...&event_type=...`
- `GET /api/v1/events?year=...&level=...&page=...`
- `GET /api/v1/events/{eventId}`
- `GET /api/v1/matches/{matchId}`
- `GET /api/v1/search?q=...`（V2）

前端分层：
- `app/*` 页面与路由。
- `components/*` 业务组件（榜单表格、球员卡、赛事时间线）。
- `features/*` 页面级聚合逻辑。
- `lib/api/*` API client 与类型。
- `lib/ui/*` design tokens + 组件样式规范。

### 3.3. API 合同与响应规范

统一返回格式：
- 成功：`{ code: 0, message: "ok", data: ..., meta: ... }`
- 失败：`{ code: <non-zero>, message: "...", error: { type, detail, trace_id } }`

分页规范：
- `page`, `page_size`, `total`, `has_next`

缓存策略：
- 暂时不做设计，后续根据情况添加

### 3.4 详细后端设计
详见 docs/design/backend.md 

### 3.5 详细前端设计
详见 docs/design/frontend.md

---

## 4. 质量保证与测试策略

测试金字塔：
- 单元测试：字段归一化、聚合计算、slug 映射。
- 集成测试：API -> DB 查询 -> 响应结构。
- E2E：`/rankings -> /players/[slug] -> /events` 主链路。

质量红线：
- 构建失败禁止发布。
- 类型错误禁止发布。
- 核心 API 契约变更必须同步更新文档与前端类型。

---

## 5. 发布与运维方案

发布方案：自有云服务器 + Docker + docker-compose

环境：
- `dev`（本地开发）
- `prod`（线上）

发布流程：
1. 数据任务完成并通过校验。
2. 触发构建（lint/type/test/build）。
3. 部署 prod 并跑冒烟验证。
4. 失败自动回滚到上一个稳定版本。

监控指标：
- 抓取成功率、任务时长、失败类型分布。
- 数据完整率（top50 覆盖率、翻译覆盖率）。
- API 延迟、错误率。

---

## 6. 分阶段落地顺序（严格按“先设计后开发”）

### Phase A：方案冻结（当前）

输出物：
- 本文档（全栈总方案）
- 接口字段字典
- 页面原型清单（低保真）

完成标准：
- 前后端、数据、发布 4 条线达成一致。
- 所有后续开发均以该方案为基线。

### Phase B：详细设计

输出物：
- DB 详细 ERD
- API OpenAPI 草案
- 前端页面交互稿与组件规格
- 抓取任务状态机定义

### Phase C：实现执行（下一阶段）

先修“架构阻塞项”，再做功能开发：
1. 数据路径与 schema 对齐
2. API 收口
3. 前端替换为 API 驱动
4. 功能扩展与体验优化

---

## 7. 当前决策结论

你提出的“先完整方案设计，再动修复和开发”是正确顺序。  
接下来建议先进入 **Phase B（详细设计）**，先把 3 份文档补齐：
- `ERD + 数据字典`
- `API 合同（OpenAPI）`
- `前端页面与组件规格`

这三份确定后，再开始逐项修复与开发，能显著降低返工风险。


## 8 附录: 现状基线（2026-04-13）

- README 与实际实现不一致：脚本入口、输出目录、前端读取方式均有偏差。
- 前端当前直接读取 JSON；SQLite 已建模但未成为线上主读取路径。
- `web/lib/data.ts` 读取 `data/matches_complete/*.json`，而实际数据在 `data/matches_complete/orig/*.json`，导致比赛统计与详情数据无法正常加载。
- 已有比赛原始数据 33 份（`matches_complete/orig`），覆盖 top50 中 33 人，缺失 17 人。
- 已有球员 profile 原始数据 30 份（`player_profiles/orig`），中文目录仍为空。
- 事件日历已有原始和中文文件，但抓取脚本存在流程级 bug 风险（如变量引用时序问题）。
- 自动化测试几乎缺失（无前后端单测/集成测试体系）。
