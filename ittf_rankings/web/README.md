# ITTF Rankings Web

一个轻量级的 ITTF 女子单打数据展示站，技术栈为 Next.js + TypeScript + SQLite。

## 架构概览

- `app/`：Next.js App Router 页面和 API
- `lib/`：JSON 数据读取、聚合、slug/格式化工具
- `db/schema.sql`：SQLite 表结构
- `scripts/migrate.ts`：初始化数据库
- `scripts/seed.ts`：从 `../data` 导入榜单和比赛 JSON

## 页面规划

- `/`：女子单打 TOP 50 榜单，带移动端卡片式展示
- `/players/[slug]`：球员详情页，展示基础统计和近期赛事
- `/api/rankings`：榜单 JSON API
- `/api/players/[slug]`：球员详情 JSON API

## 数据模型

### 1. ranking_snapshots
保存某一周的排名快照元信息。

### 2. players
保存球员基础档案，可复用到多期排名和多项赛事。

### 3. rankings
关联某个快照中的球员排名、积分、涨跌变化。

### 4. player_match_sources
记录导入来源文件和原始 JSON，方便追溯。

### 5. events
保存球员参加的赛事。

### 6. matches
保存单场比赛数据，支持后续做胜率、阶段分布、对手分析等统计。

## 快速开始

```bash
cd ittf_rankings/web
npm install
npm run db:migrate
npm run db:seed
npm run dev
```

默认会读取上一级 `data/` 目录里的：

- `women_singles_top50.json`
- `matches_complete/*.json`

## 适合后续扩展的方向

- 增加球员头像、国旗、积分趋势图
- 增加按国家/大洲筛选
- 增加赛事级别和年份过滤
- 统计常见对手、关键轮次胜率、冠军/亚军次数
- 接入定时任务，自动刷新 SQLite 和静态缓存
