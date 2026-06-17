# ITTF 乒乓球数据项目

本项目用于抓取、存储和展示 ITTF 世界排名、赛事日程、运动员信息、头像和比赛记录。

第一期仅限女子单打

当前赛事链路已包含 WTT 团体赛进行中的赛程导入，以及 Stage Groups 页官方积分表导入。

## 产品功能

- 首页：展示世界排名、赛事日程，以及暂未开放的搜索入口（首页弹框提示“稍后开放，敬请期待”）
- ranking页：支持按积分排序、按运动员胜率、对手交手次数排序
- 运动员详情：展示运动员的个人信息、头像、统计数据、比赛记录
- 赛事列表页：展示历年赛事日程
- 比赛详情：展示比赛的详细信息、对战图、比赛结果
- 搜索结果页：预留展示基于 LLM 的搜索结果，待搜索功能开放后启用

## 项目结构

```text
ittf_rankings/
├── data/                 # 抓取结果、快照、头像、profile json、比赛数据
├── docs/                 # 规则文档与翻译
├── scripts/              # Python 抓取与处理脚本
├── web/                  # Next.js 前端
├── data/db/              # SQLite 数据库与导入生成文件
│   └── ittf.db
└── README.md
```

## 常用脚本

### 1. 抓取排名数据（含 points breakdown）

```bash
python scripts/run_rankings.py --top 100 --headless
```

输出：`data/rankings/orig/women_singles_top100_week{W}.json`

### 2. 抓取运动员 profile + 头像

```bash
python scripts/run_profiles.py --category women --top 50 --headless
```

输出：
- `data/player_profiles/orig/` — 原始运动员档案
- `data/player_profiles/cn/` — 中文翻译版
- `data/player_avatars/` — 运动员头像

### 3. 抓取运动员比赛记录

```bash
python scripts/scrape_matches.py --players-file data/women_singles_top50.json
```

### 4. 规则文档更新

```bash
python scripts/ittf_rankings_updater.py
```

### 5. 更新赛事数据

赛事数据根据接入时间和年份选择不同链路。不要直接根据单个脚本名称推断操作顺序，统一按 [赛事数据日常更新流程](docs/event-data-update-workflow.md) 执行。

## 依赖

```bash
pip install requests beautifulsoup4 pypdf playwright
playwright install chromium
```

抓取脚本会通过 Playwright/Patchright 启动 Chromium。Ubuntu 24.04 等最小化环境可能缺少浏览器运行库；如果启动时报错 `libnspr4.so`、`libnss3.so` 或 `libasound.so.2` not found，先安装系统依赖：

```bash
sudo apt-get update
sudo apt-get install -y libnspr4 libnss3 libasound2t64
```

可用下面命令检查 Chromium 是否仍有缺失库：

```bash
ldd ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome | grep "not found"
```

## 文档

- [数据库设计](docs/design/database.md) — 表结构、关系、数据来源
- [赛事数据日常更新流程](docs/event-data-update-workflow.md) — 新赛事、赛后补抓、历史补录、cron 与 promote
- [数据库使用与维护](docs/DATABASE_MAINTENANCE.md) — 部署、查询、更新、备份
- [脚本总览](docs/scripts_overview.md) — `scripts/` 与 `scripts/runtime/` 的入口和用途
- [部署与运维](docs/DEPLOY_ANALYTICS.md) — 生产部署、current-event cron、Umami、运维手册
- [ITTF 排名规则](data/point_rules/ITTF-Ranking-Regulations-20260127.md) — 官方积分规则

## 数据来源

- ITTF Results: <https://results.ittf.link>
- ITTF Rankings: <https://results.ittf.link/index.php/ittf-rankings>
- Player Profile: <https://results.ittf.link/index.php/player-profile/list/60>
- ITTF Rankings page: <https://ittf.com/rankings>
