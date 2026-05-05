# ITTF Rankings Web

一个轻量级的 ITTF 女子单打数据展示站，技术栈为 Next.js + TypeScript + SQLite。

## 架构概览

- `app/`：Next.js App Router 页面和 API
- `lib/`：数据访问、工具与服务端查询层
- `scripts/migrate.ts`：按 `scripts/db/schema.sql` 初始化数据库
- `scripts/seed.ts`：已废弃，正式入库请使用 `scripts/db/import*.py`

当前赛事页小组积分表优先读取数据库中的 `current_event_group_standings`，比赛详情与签表则读取 `current_event_*` 运行态表。

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

如果近期新增了赛事积分表相关字段或表，先重新执行：

```bash
npm run db:migrate
```

WTT 团体赛当前赛事积分表导入脚本：

```bash
python scripts/runtime/import_current_event_group_standings.py --input-dir data/live_event_data/<eventId> --event-id <eventId>
```

## 环境变量

- `APP_ORIGIN`
  - 生产环境站点的标准外部地址，例如 `https://example.com`
  - 用于校验认证类 `POST` 请求的 `Origin`
- `SESSION_COOKIE_SECURE`
  - `true`：强制会话 Cookie 使用 `Secure`
  - `false`：强制关闭 `Secure`
  - 未设置：在 `NODE_ENV=production` 时自动启用
- `TRUST_PROXY_HEADERS`
  - `true`：允许从受信任代理头读取客户端 IP
  - 建议仅在 Cloudflare / Nginx 等受控反向代理之后开启
- `TRUSTED_PROXY_IP_HEADER`
  - 默认 `cf-connecting-ip`
  - 如果前面不是 Cloudflare，可改成你的反向代理注入的真实客户端 IP 头

## 适合后续扩展的方向

- 增加球员头像、国旗、积分趋势图
- 增加按国家/大洲筛选
- 增加赛事级别和年份过滤
- 统计常见对手、关键轮次胜率、冠军/亚军次数
- 接入定时任务，自动刷新 SQLite 和静态缓存
