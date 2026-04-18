# ITTF 数据脚本说明

按数据来源分类，整理 `scripts/` 目录下所有脚本的功能和数据源。

---

## 1. 排名数据 (Rankings)

数据来源：https://www.ittf.com/rankings/（ITTF 官方排名页面）

### scrape_rankings.py
抓取 ITTF Women's Singles 排名数据，包括每位运动员的 points breakdown 明细。
数据格式：排名、积分、排名变化、国家。
输出：`data/rankings/orig/women_singles_top{N}_week{W}.json`

### scrape_players.py
从 ITTF 排名页抓取运动员姓名和协会（国家）信息，支持男女单打分类。
数据格式：姓名、国家协会。
输出：`data/players/orig/{women/men}_singles_top{N}.json`
与 scrape_rankings.py 的区别：此脚本只提取姓名+国家，不含积分和排名变化。

### run_rankings.py
排名数据完整流程主入口：调用 scrape_rankings.py 抓取 → translate_rankings.py 翻译。
用法：`python run_rankings.py --top 100`

### translate_rankings.py
将排名数据中的特定字段翻译为中文（使用词典 translation_dict_v2.json）。
翻译字段：name、country、location、event、category、expires_on、position。
输入：`data/rankings/orig/*.json` → 输出：`data/rankings/cn/*.json`

### db/import_rankings.py
将中文版排名数据导入 SQLite 数据库（ranking_snapshots / ranking_entries / points_breakdown 三张表）。
输入：`data/rankings/cn/*.json`

---

## 2. 球员档案 (Player Profiles)

数据来源：https://results.ittf.link/index.php/player-profile（需登录）

### scrape_profiles.py
从 results.ittf.link ranking 页面抓取运动员详细档案，包含：
- 基本信息（性别、出生年份、年龄、握拍方式）
- 当前排名和历史最佳排名
- 职业生涯统计（参赛场次、胜败场次、冠军数）
- 当年统计
- 近期比赛记录
- 头像下载

输入：排名页（如 Women's Singles ranking）
输出：`data/player_profiles/orig/player_{id}_{name}.json`，同时写入 SQLite `player_profiles` 表

### scrape_profiles_from_search.py
通过球员搜索页面（players-profiles）逐个搜索并抓取球员档案。
输入：球员列表 JSON 文件（格式：`{"players": [{"english_name": ..., "country_code": ...}, ...]}`）
输出：与 scrape_profiles.py 相同，存入 `data/player_profiles/orig/` 并更新 `players` 表
与 scrape_profiles.py 的区别：此脚本通过搜索框搜索而非依赖排名页的链接，适合抓取缺失的球员。

### run_profiles.py
球员档案完整流程主入口：调用 scrape_profiles.py → translate_profiles.py。
用法：`python run_profiles.py --category women --top 50`

### translate_profiles.py
翻译球员档案中的特定字段（使用词典，不调用 LLM）。
翻译字段：name（球员名）、country（国家）、gender（性别）、style/playing_hand/grip（握拍相关）。
不翻译：recent_matches（近期比赛）。
输入：`data/player_profiles/orig/player_*.json` → 输出：`data/player_profiles/cn/player_*.json`

### update_players.py
从比赛数据（matches_complete）中发现未录入数据库的球员，并调用 scrape_profiles_from_search.py 抓取其档案。
数据源：从 `data/matches_complete/cn/*.json` 的 side_a/side_b 字段提取球员名+国家
输出：新增球员列表到 `data/player_profiles/pending_from_matches.json`
与 scrape_profiles.py 的区别：此脚本从比赛记录中发现缺失球员，而非从排名页获取。

### db/import_players.py
将中文版球员档案导入 SQLite 的 `players` 表。
输入：`data/player_profiles/cn/player_*.json`

---

## 3. 比赛数据 (Matches)

数据来源：https://results.ittf.link/index.php/matches/players-matches-per-event（需登录）

### scrape_matches.py
抓取指定球员在指定日期之后的全部比赛数据。
核心流程：autocomplete 输入球员名 → 点击搜索 → 遍历赛事列表 → 进入每个赛事详情页抓取比赛。
输入：球员列表文件（由 rankings JSON 生成）
输出：
- `data/matches_complete/orig/{player_name}.json`：原始比赛数据
- `data/raw_event_payloads/{player_name}/{event}.json`：每个赛事的原始抓取内容

### run_matches.py
比赛数据完整流程主入口：调用 scrape_matches.py → translate_matches.py。
用法：`python run_matches.py --players-file data/women_singles_top50.json --top-n 30`

### translate_matches.py
翻译比赛数据中的字段（使用词典 translation_dict_v2.json）。
翻译字段：
- 顶层：player_name、country
- events[]：event_name、event_type
- matches[]：sub_event、stage、round、side_a、side_b（球员名+国家）
输入：`data/matches_complete/orig/*.json` → 输出：`data/matches_complete/cn/*.json`

### db/import_matches.py
将中文版比赛数据导入 SQLite 的 `matches` 表。
输入：`data/matches_complete/cn/*.json`
关键逻辑：通过 event name + year 匹配 event_id，通过 player name + country_code 匹配 player_id。

### backfill_event_dates.py
回填 matches_complete JSON 文件中的 start_date / end_date 字段。
数据源：重新访问球员赛事列表页，提取日期信息。
输入：已有球员比赛 JSON 文件
输出：更新原文件（添加 start_date/end_date 字段）
与 scrape_matches.py 的区别：此脚本只访问赛事列表页抓日期，不进详情页抓比赛。

### repair_matches_offline.py
离线审计和修复 matches_complete JSON 文件。
修复能力：
- 重新解析 raw_row_text 还原 side_a/side_b
- 删除已废弃的 teammates/opponents 字段
- 重新计算 perspective、winner、result_for_player
- 回填缺失的 english_name/country/country_zh
用法：`python repair_matches_offline.py --check` 或 `--fix`

---

## 4. 赛事列表 (Events List)

数据来源：https://results.ittf.link/index.php/events（需登录）

### scrape_events.py
抓取赛事列表页全部赛事。
提取字段：event_id、year、name、event_type、event_kind、matches 数量、start_date、end_date。
支持分页翻页，基于 from_date 截止日期停止。
输入：--from-date 参数（默认 2024-01-01）
输出：`data/events_list/events_from_{date}.json`

### translate_events.py
翻译赛事列表中的字段（LLM 翻译，词典兜底）。
翻译字段：name（赛事名）、event_type、event_kind。
支持增量翻译（跳过已完成的 event_id）。
输入：`data/events_list/orig/*.json` → 输出：`data/events_list/cn/*.json`

### db/import_events.py
将中文版赛事列表导入 SQLite 的 `events` 表。
同时通过 event_type + event_kind 匹配 event_categories 和 event_type_mapping 表。
输入：`data/events_list/cn/*.json`

### db/import_sub_events.py
导入 sub_events 表（赛事子类型，如 WS/MS/WD/MD/XD）。

### db/import_sub_event_type.py
导入 sub_event_type 表（赛事子类型映射）。

---

## 5. 赛事日历 (Events Calendar)

数据来源：https://www.ittf.com/{year}-events-calendar/（公开页面，无需登录）

### scrape_events_calendar.py
抓取 ITTF 官网历年赛事日历页面。
提取：赛事名称、日期、时间、地点。
输出：`data/events_calendar/orig/events_calendar_{year}.json`

### translate_events_calendar.py
翻译赛事日历中的字段（词典 + LLM fallback）。
- name：词典优先，未命中调用 LLM
- location：仅词典
- date：规则转换（如 "02-05 Jan" → "01-02至01-05"）
输入：`data/events_calendar/orig/*.json` → 输出：`data/events_calendar/cn/*.json`

### db/import_events_calendar.py
将赛事日历数据导入数据库。

---

## 6. 积分规则 (Points Rules / Regulations)

数据来源：https://ittf.com/rankings/（发现 PDF 链接）

### scrape_regulations.py
抓取 ITTF 世界排名规则 PDF 文件。
流程：发现 PDF 链接 → 下载 → 提取 PDF 文本为 Markdown → 生成翻译 prompt。
输出：
- `data/regulations/latest_regulations.pdf`
- `data/regulations/latest_regulations.md`
- `data/regulations/latest_regulations.translation_prompt.txt`

### db/import_points_rules.py
导入积分规则相关数据到数据库。

---

## 7. 翻译词典管理

### dict_updator.py
将 key:value:category 格式的词条文件批量添加到 translation_dict_v2.json。
用法：`python dict_updator.py <input_file> --dict scripts/data/translation_dict_v2.json`

### update_event_to_dict.py
从 events_list 和 events_calendar 的翻译结果中提取词条并更新到翻译词典。
提取规则：
- events_list：events[].name / events[].event_type → events 类别
- events_calendar：name → events 类别；location → locations 类别
调用 dict_updator.py 完成实际更新。

### validate_translation_dict.py
验证翻译词典的格式和完整性。

### validate_events_translation.py
验证赛事翻译结果。

---

## 8. 数据库相关

### db/config.py
数据库配置：PROJECT_ROOT、DB_PATH、SCHEMA_PATH。

### db/init_database.py
初始化 SQLite 数据库，执行 DDL 建表。
建表前会备份旧数据库。

### db/upgrade_schema.py
数据库 schema 升级脚本。

### db/normalize_events.py
规范化赛事名称（与 import_matches.py 中的一致）。

---

## 9. 其他工具脚本

### avatar_crop.py
裁剪球员头像图片。

### dump_dict.py
导出翻译词典内容。

### json_extract.py
从 JSON 文件提取数据。

### translate_example.py
翻译示例脚本。

### regulations_manager.py
规则文件管理工具。

---

## 10. 已归档脚本 (archive/)

已废弃或被新版本替代的脚本：

- ittf_matches_browser.py
- ittf_matches_scraper.py
- ittf_matches_simple.py
- ittf_matches_playwright.py
- ittf_rankings.py
- ittf_rankings_updater.py
- manual_scraper.py

---

## 数据流向总览

```
ITTF 官网/排名页
    │
    ├─ scrape_rankings.py ──→ data/rankings/orig/
    │                              │
    │                         translate_rankings.py
    │                              │
    └─ scrape_players.py ──→ data/players/orig/   ← 原始运动员列表

results.ittf.link
    │
    ├─ scrape_profiles.py ──→ data/player_profiles/orig/
    │                              │
    │                         translate_profiles.py
    │                              │
    │                         db/import_players.py → SQLite players 表
    │
    ├─ scrape_profiles_from_search.py ──→ data/player_profiles/orig/
    │                                         │
    └─ scrape_matches.py ──→ data/matches_complete/orig/
                                │
                           translate_matches.py
                                │
                           db/import_matches.py → SQLite matches 表

    ├─ scrape_events.py ──→ data/events_list/orig/
    │                           │
    │                      translate_events.py (LLM)
    │                           │
    │                      db/import_events.py → SQLite events 表
    │
    └─ scrape_events_calendar.py ──→ data/events_calendar/orig/
                                        │
                                   translate_events_calendar.py
                                        │
                                   db/import_events_calendar.py
```