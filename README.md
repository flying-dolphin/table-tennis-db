# ITTF 乒乓球数据项目

本项目用于抓取、存储和展示 ITTF 世界排名、赛事日程、运动员信息、头像和比赛记录。

第一期仅限女子单打

## 产品功能

- 首页：展示世界排名，搜索框(支持自然语言搜索)， 赛事日程
- ranking页：支持按积分排序、按运动员胜率、对手交手次数排序
- 运动员详情：展示运动员的个人信息、头像、统计数据、比赛记录
- 赛事列表页：展示历年赛事日程
- 比赛详情：展示比赛的详细信息、对战图、比赛结果
- 搜索结果页：展示基于LLM的搜索结果

## 项目结构

```text
ittf_rankings/
├── data/                 # 抓取结果、快照、头像、profile json、比赛数据
├── docs/                 # 规则文档与翻译
├── scripts/              # Python 抓取与处理脚本
├── web/                  # 前端与 sqlite 数据库
│   └── db/
│       └── ittf_rankings.sqlite
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

## 依赖

```bash
pip install requests beautifulsoup4 pypdf playwright
playwright install chromium
```

## 数据来源

- ITTF Results: <https://results.ittf.link>
- ITTF Rankings: <https://results.ittf.link/index.php/ittf-rankings>
- Player Profile: <https://results.ittf.link/index.php/player-profile/list/60>
- ITTF Rankings page: <https://ittf.com/rankings>
