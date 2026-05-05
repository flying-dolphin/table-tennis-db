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

### 5. 抓取团体赛官方积分表

独立无头分析抓取：

```bash
python scripts/runtime/scrape_wtt_pool_standings.py --event-id 3216 --stage-label "Groups" --verbose
```

导入到 SQLite 当前积分表：

```bash
python scripts/runtime/import_current_event_group_standings.py --input-dir data/live_event_data/3216 --event-id 3216
```

如果需要走完整的当前赛事刷新链路，使用 runtime 总入口：

```bash
python scripts/runtime/scrape_current_event.py --event-id 3216
python scripts/runtime/import_current_event.py --event-id 3216
```

导入总入口默认写入 session 赛程、小组积分、淘汰赛签表、live 比赛和 completed 比赛。`current_event_team_ties` 由 live/completed 导入器随 `current_event_matches` 一起维护。

## 依赖

```bash
pip install requests beautifulsoup4 pypdf playwright
playwright install chromium
```

## 文档

- [数据库设计](docs/design/database.md) — 表结构、关系、数据来源
- [数据库使用与维护](docs/DATABASE_MAINTENANCE.md) — 部署、查询、更新、备份
- [ITTF 排名规则](data/point_rules/ITTF-Ranking-Regulations-20260127.md) — 官方积分规则

## 数据来源

- ITTF Results: <https://results.ittf.link>
- ITTF Rankings: <https://results.ittf.link/index.php/ittf-rankings>
- Player Profile: <https://results.ittf.link/index.php/player-profile/list/60>
- ITTF Rankings page: <https://ittf.com/rankings>
