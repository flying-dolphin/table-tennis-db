# ITTF Rankings Web

一个轻量级的 ITTF 女子单打数据展示站，技术栈为 Next.js + TypeScript + SQLite。

## 架构概览

- `app/`：Next.js App Router 页面和 API
- `lib/`：数据访问、工具与服务端查询层
- `scripts/migrate.ts`：按 `scripts/db/schema.sql` 初始化数据库
- `scripts/seed.ts`：已废弃，正式入库请使用 `scripts/db/import*.py`

## 页面规划

- `/`：女子单打 TOP 50 榜单，带移动端卡片式展示
- `/players/[slug]`：球员详情页，展示基础统计和近期赛事
- `/api/v1/*`：V1 正式 API

## 数据模型

当前请以 `docs/design/database.md` 为准，不以本 README 中的旧表说明为准。

## 快速开始

```bash
cd ittf_rankings/web
npm install
npm run db:migrate
npm run dev
```

数据库正式初始化与导入请使用 `scripts/db/*.py`。

## 适合后续扩展的方向

- 增加球员头像、国旗、积分趋势图
- 增加按国家/大洲筛选
- 增加赛事级别和年份过滤
- 统计常见对手、关键轮次胜率、冠军/亚军次数
- 接入定时任务，自动刷新 SQLite 和静态缓存
