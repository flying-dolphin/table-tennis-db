# ITTF 乒乓球数据项目

本项目用于获取和处理ITTF世界乒乓球排名数据及运动员比赛记录。

## 项目结构

```
ittf_rankings/
├── docs/                              # 文档目录
│   ├── ITTF-Ranking-Regulations-CN-20260127.md   # 中文版排名规则
│   ├── ITTF-Table-Tennis-World-Ranking-Regulations-20260127.pdf  # 原始PDF
│   └── ...
├── scripts/                           # 脚本目录
│   ├── ittf_rankings_updater.py      # 规则文档自动更新脚本
│   ├── ittf_matches_scraper.py       # 比赛记录爬虫
│   ├── ittf_process.py               # 数据处理脚本
│   └── README.md                     # 脚本使用说明
├── data/                              # 数据目录
│   ├── matches/                      # 运动员比赛记录
│   │   ├── SUN_Yingsha_131163.json
│   │   ├── WANG_Manyu_121411.json
│   │   └── ...
│   ├── top50_players.json            # TOP 50运动员列表
│   └── women_singles_top100.json      # 排名数据
└── ...
```

## 功能

### 1. 排名规则自动更新

每3天自动检查ITTF官网是否有新的排名规则PDF，下载并翻译成中文。

```bash
# 检查并下载最新规则
python scripts/ittf_rankings_updater.py

# 持续监控模式
python scripts/ittf_rankings_updater.py --daemon
```

### 2. TOP 50运动员比赛记录爬虫

获取女子单打TOP 50运动员从2024-2026年的所有比赛记录。

```bash
# 抓取全部TOP 50
python scripts/ittf_matches_scraper.py

# 抓取指定球员
python scripts/ittf_matches_scraper.py --player-id 131163 --player-name "SUN Yingsha"
```

### 3. 数据处理

处理和展示排名数据，生成HTML页面。

```bash
python scripts/ittf_process.py --input data.json --html
```

## 数据格式

### 运动员比赛记录 (JSON)

```json
{
  "player_id": "131163",
  "name": "SUN Yingsha",
  "recent_matches": [
    {
      "opponent": "WANG Manyu",
      "opponent_country": "CHN",
      "score": "4-1",
      "games": [[11, 9], [11, 8], [13, 11], [8, 11], [11, 7]],
      "stage": "Final",
      "result": "WON"
    }
  ],
  "wtt_results": [...],
  "ittf_results": [...]
}
```

## 依赖

```bash
pip install requests beautifulsoup4 pypdf
```

## 数据来源

- ITTF排名: https://results.ittf.link/ittf-rankings/ittf-ranking-women-singles
- 运动员Profile: https://results.ittf.link/index.php/player-profile/list/60
- ITTF规则PDF: https://ittf.com/rankings

## 作者

OpenClaw Agent - daily-shasha
