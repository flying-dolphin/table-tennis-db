# ITTF 乒乓球数据项目

本项目用于抓取、存储和展示 ITTF 世界排名、运动员 profile、头像和比赛记录。

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

### 1. 抓取排名

```bash
python scripts/scrape_rankings.py --category women --top 50 --headless
```

### 2. 抓取排名 + 运动员 profile + 头像

```bash
python scripts/scrape_rankings.py --category women --top 50 --scrape-profiles --headless
```

输出会写到：
- `data/ranking_snapshots/`
- `data/player_profiles/`
- `data/player_avatars/`
- `web/db/ittf_rankings.sqlite`

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
