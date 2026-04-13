# ITTF 女单数据平台 — 实施计划

更新时间：2026-04-13  
关联设计文档：`docs/design/2026-04-13-fullstack-solution.md`

---

## 0. 计划总览

本计划分三大阶段，按顺序推进：

1. **数据采集与翻译** — 完成 ranking、profile、match 数据的抓取、翻译、校验，支持断点续抓
2. **SQLite 入库** — 将 JSON 数据导入 SQLite，建立统一事实源
3. **后端 API** — 实现查询接口，前端改为 API 驱动

每个阶段内部按里程碑拆分，完成一个再进入下一个。

---

## 1. 当前基线（2026-04-13）

### 已有产物
- 比赛原始数据 33 份（`data/matches_complete/orig/`），覆盖 top50 中 33 人，缺失 17 人
- 球员 profile 原始数据 30 份（`data/player_profiles/orig/`），中文目录为空
- 赛事日历已有原始和中文文件（`data/events_calendar/`）
- 排名数据散落在 `data/women_singles_*.json`，格式不统一
- SQLite 数据库已有 schema 但未成为主查询路径（`web/db/ittf_rankings.sqlite`）

### 已知问题
- `scrape_rankings.py` 混合了 ranking 和 profile 两个职责（`--scrape-profiles` 耦合在排名脚本中）
- 缺少独立的 ranking 数据抓取（当前脚本抓的是排名表，但没有抓取每个运动员的 points breakdown）
- `web/lib/data.ts` 读取路径与实际数据目录不一致
- 抓取脚本不支持断点续抓，失败后只能从头重来
- profile、match 翻译未全部完成
- 自动化测试缺失

### 已完成事项（不再纳入计划）
- [x] 翻译词典已切到 V2（`translation_dict_v2.json`）
- [x] events calendar 翻译完成语义已修复
- [x] events calendar checkpoint 已拆分为 scrape / translate 两段
- [x] 已有词典与 events 翻译结果校验脚本

---

## 阶段一：数据采集与翻译

### M1：Ranking 与 Profile 抓取职责拆分

**目标：** 现有 `scrape_rankings.py` 本质上抓取的是球员 profile 数据，需要将其改为 profile 专用脚本；另外新建一个全新的 `scrape_rankings.py` 从 ITTF 官网抓取真正的排名数据。

**背景：** 现有 `scrape_rankings.py` 的数据源是 `results.ittf.link`，抓取的是排名表格中的球员信息（姓名、国家、头像链接等），本质是 profile 数据。真正的 ranking 数据（含积分明细 points breakdown）需要从 `https://www.ittf.com/rankings/` 入口获取，这是一个完全不同的页面和数据结构。

**执行项：**

**Profile 侧（改造现有脚本）：**
- [ ] 将现有 `scrape_rankings.py` 重命名为 `scrape_profiles.py`（或合并到已有的 `scrape_profiles.py`）
- [ ] 清理脚本中与 ranking 语义不符的命名和参数（如 `--top` 改为 `--limit` 等）
- [ ] 确保 profile 脚本独立可运行，输出到 `data/player_profiles/orig/`
- [ ] 对应更新 `run_rankings.py` → `run_profiles.py`

**Ranking 侧（新建脚本）：**
- [ ] 新建 `scrape_rankings.py`，入口为 `https://www.ittf.com/rankings/`
- [ ] 在该页面查找 Women's Singles 对应的链接并进入
- [ ] 抓取 Top 100 排名列表，字段包括：
  - 排名时间（ranking week）
  - 运动员排名（rank）
  - 运动员名称（name）
  - 国家（country）
  - 积分（points）
- [ ] 点击每个运动员的链接，抓取 points breakdown 明细：
  - Event（赛事名称）
  - Category（赛事类别）
  - Expires on（积分过期时间）
  - Position（名次）
  - Points（积分）
- [ ] 支持断点续抓：
  - checkpoint 记录已完成的运动员
  - 重新运行时跳过已完成的，只补抓失败的
- [ ] 输出到 `data/rankings/orig/`

**目录约定：**
- `data/rankings/orig/` — ranking 原始数据（新）
- `data/rankings/cn/` — ranking 中文数据（新）
- `data/player_profiles/orig/` — profile 原始数据（已有）
- `data/player_profiles/cn/` — profile 中文数据

**完成标准：**
- 新 `scrape_rankings.py` 可独立运行，从 ittf.com/rankings 抓取 Top 100 排名 + points breakdown
- 原脚本改为 profile 专用，不再承担 ranking 职责
- 两个脚本输出到各自独立目录，互不依赖

---

### M2：Profile 与 Match 数据补齐

**目标：** 补齐缺失的球员 profile 和 match 数据。

**执行项：**

- [ ] 排查当前 30 份 profile 与 top 100 的差异，生成缺失清单
- [ ] 补抓缺失球员的 profile 数据
- [ ] 补抓缺失球员的 match 数据（当前 33 份 vs top 100）
- [ ] 为 profile 和 match 抓取脚本增加断点续抓支持：
  - checkpoint 记录已完成/失败的球员
  - 支持 `--resume` 参数从上次中断处继续
  - 失败记录包含原因（页面无数据 / 网络错误 / 风控触发）
- [ ] 修复已知的抓取 bug（变量引用时序问题等）

**完成标准：**
- Top 100 球员的 profile 覆盖率 ≥ 95%（允许少量因站点无数据而缺失）
- Top 100 球员的 match 覆盖率 ≥ 95%
- 所有缺失均有明确原因记录

---

### M4：数据翻译与校验

**目标：** 完成所有数据的中文翻译，建立数据校验机制。

**执行项：**

- [ ] 完成 ranking 数据翻译（运动员名、国家名、赛事名）
- [ ] 完成 profile 数据翻译（`data/player_profiles/cn/` 当前为空）
- [ ] 完成 match 数据翻译（检查 `data/matches_complete/` 下 cn 目录覆盖率）
- [ ] 翻译脚本支持断点续翻：
  - 跳过已有翻译结果的文件
  - 支持只翻译新增/变更的文件
- [ ] 建立数据校验脚本，检查：
  - 必填字段完整性（名称、国家、积分等不能为空）
  - 排名数据与 profile 数据的球员 ID 一致性
  - 翻译覆盖率报告
  - orig 与 cn 目录文件数量一致性

**完成标准：**
- 所有 orig 目录下的数据在 cn 目录有对应翻译
- 校验脚本可以一键输出数据质量报告
- 翻译脚本支持增量执行

---

## 阶段二：SQLite 入库

### M5：数据模型设计与建表

**目标：** 基于稳定的 JSON 数据，冻结 SQLite schema。

**执行项：**

- [ ] 整理数据字典，明确每张表的字段来源和约束
- [ ] 定稿 SQLite 表结构，至少覆盖：
  - `players` — 球员主表（id, slug, name_en, name_cn, country_code, country_cn, continent）
  - `ranking_snapshots` — 排名快照（snapshot_id, category, ranking_week）
  - `rankings` — 排名记录（snapshot_id, player_id, rank, points, change）
  - `player_points_breakdown` — 积分明细（player_id, snapshot_id, event_name, category, expires_on, position, points）
  - `events` — 赛事（event_id, name_en, name_cn, year, level, dates）
  - `matches` — 比赛记录（match_id, event_id, player_id, opponent_id, score, result, round）
- [ ] 明确主键、外键、唯一约束和索引
- [ ] 复用/更新现有 `web/db/schema.sql`

**完成标准：**
- schema 可以指导后续 seed 脚本开发，不需要边写边改

---

### M6：数据导入（seed）

**目标：** 将 JSON 数据导入 SQLite，seed 幂等可重跑。

**执行项：**

- [ ] 实现 `db:migrate` — 创建/升级表结构
- [ ] 实现 `db:seed` — 从 JSON 导入数据到 SQLite
  - ranking 数据导入
  - player 数据导入
  - points breakdown 导入
  - match 数据导入
  - event 数据导入
- [ ] seed 前校验输入数据（必填字段、重复键、引用完整性）
- [ ] seed 幂等：重复执行不产生重复数据
- [ ] 导入后验证：编写最小查询脚本确认数据正确

**完成标准：**
- `db:migrate` + `db:seed` 可连续重复执行
- Top 100 排名、球员详情、积分明细可从 SQLite 正确查询
- JSON 不再作为前端主读取源

---

## 阶段三：后端 API

### M7：API 实现

**目标：** 基于 SQLite 实现 BFF 层 API，供前端调用。

**执行项：**

- [ ] 实现核心 API 端点（Next.js API Routes）：
  - `GET /api/v1/rankings?week=...&category=women_singles` — 排名列表
  - `GET /api/v1/players/{slug}` — 球员详情（含 profile + 积分明细）
  - `GET /api/v1/players/{slug}/matches?year=...` — 球员比赛记录
  - `GET /api/v1/events?year=...&level=...` — 赛事列表
  - `GET /api/v1/events/{eventId}` — 赛事详情
- [ ] 统一响应格式：`{ code, message, data, meta }`
- [ ] 分页支持：`page, page_size, total, has_next`
- [ ] 全部查询走 SQLite，不读 JSON
- [ ] 清理 `web/lib/data.ts` 对 JSON 文件的直接读取，改为调用 API

**完成标准：**
- 前端不再依赖 JSON 文件目录结构
- API 响应格式统一，字段稳定
- 核心查询性能可接受（top 100 数据量下无明显延迟）

---

### M8：前端接入 API

**目标：** 前端页面改为 API 驱动，移除对原始 JSON 的依赖。

**执行项：**

- [ ] `web/lib/api/` 建立 API client 层
- [ ] 首页改为调用 rankings API + events API
- [ ] 球员详情页改为调用 players API
- [ ] 修复 `web/lib/data.ts` 读取路径不一致问题（作为过渡，最终废弃该文件）
- [ ] 验证移动端和桌面端页面正常渲染

**完成标准：**
- 所有页面数据来自 API
- `web/lib/data.ts` 中不再有对 `data/` 目录的直接文件读取

---

## 后续事项（当前不实施）

以下事项在核心链路完成后再考虑：

- **Pipeline 编排** — 统一入口 `run_pipeline.py`，子命令分任务执行
- **自动化测试** — 字段归一化单测、seed 集成测试、API 冒烟测试
- **CI 门禁** — lint + type check + 核心测试
- **发布部署** — Docker + docker-compose，冒烟验证，自动回滚
- **V2 功能** — 搜索、男单/双打扩展、社交功能

---

## 风险与应对

| 风险 | 应对 |
|------|------|
| ITTF 页面结构变化导致抓取失效 | 保留原始 HTML 快照；解析逻辑支持回退 |
| 风控/验证码中断抓取 | checkpoint 机制支持续抓；保留手动接管能力 |
| 翻译质量不稳定 | 优先词典命中；保留失败重跑和人工修正入口 |
| 数据模型变更 | schema 变更先更新数据字典，seed 校验同步更新 |
