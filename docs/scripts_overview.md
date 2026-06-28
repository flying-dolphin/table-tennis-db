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
将排名数据中的特定字段翻译为中文（经统一 `Translator`，默认 `--mode dict` 仅词典）。
翻译字段：name、country、location、event、category、expires_on、position。
可选 `--mode both`（词典未命中走 LLM 兜底）/`--mode llm`，配 `--provider/--model`。
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
翻译球员档案中的特定字段（经统一 `Translator`，默认 `--mode dict` 仅词典；可选 `--mode both/llm`）。
翻译字段：name（球员名）、country（国家）、gender（性别）、style/playing_hand/grip（握拍相关）。
不翻译：recent_matches（近期比赛）。
输入：`data/player_profiles/orig/player_*.json` → 输出：`data/player_profiles/cn/player_*.json`
支持增量翻译：`--since "YYYY-MM-DD HH:MM"` 只处理该时间点之后新增或修改的源 profile 文件（按 `orig` 文件修改时间筛选）；`--file` 仍用于只翻译单个文件。

### update_players.py
从比赛数据（matches_complete）中发现未录入数据库的球员，并调用 scrape_profiles_from_search.py 抓取其档案。
数据源：从 `data/matches_complete/cn/*.json` 的 side_a/side_b 字段提取球员名+国家
输出：新增球员列表到 `data/player_profiles/pending_from_matches.json`
与 scrape_profiles.py 的区别：此脚本从比赛记录中发现缺失球员，而非从排名页获取。

### db/import_players.py
将中文版球员档案导入 SQLite 的 `players` 表。
输入：`data/player_profiles/cn/player_*.json`

### deploy/server/update_rankings_profiles.sh
将 ranking/profile 导入代码和增量数据发布到远程服务器，并在远程执行导入。
输入：
- 最新一份 `data/rankings/cn/*.json`
- `--changed-since` 或 `CHANGED_SINCE` 指定时间之后修改的 `data/player_profiles/cn/player_*.json`
- 同一时间条件之后修改的 `data/player_country_history.json`

关键逻辑：
- 不发布赛事刷新脚本。
- 数据包先解压到远程 `${REMOTE_TMP_DIR}/payload-*` 独立目录。
- preflight、dry-run、导入和校验通过后，才把 payload 文件发布到远程 data 目录。
- 导入前备份远程 SQLite，并按 `REMOTE_DB_BACKUPS_KEEP` 保留最新备份。
- 本地完整执行日志写入 `LOG_FILE`，默认 `logs/deploy/ranking-profile-${RUN_ID}.log`。
- 远程导入 manifest 写入 `${REMOTE_IMPORT_LOG_DIR}/ranking-profile-${RUN_ID}.manifest.txt`，记录本次导入的 ranking、profile 清单和 `player_country_history.json` 状态。

### deploy/server/update_events_calendar.sh
将赛事日历导入代码和单年中文日历 JSON 发布到远程服务器，并在远程执行导入。
输入：
- `--year` 目标年份。
- `data/events_calendar/cn/events_calendar_{year}.json`

关键逻辑：
- 发布 `scripts/db/import_events_calendar.py`、`event_classification_overrides.py`、`config.py` 和 `event_category_mapping.json`。
- 数据包先解压到远程 `${REMOTE_TMP_DIR}/payload-*` 独立目录。
- 远程先执行 `import_events_calendar.py --year --dry-run` 和 JSON preflight。
- 导入前备份远程 SQLite，并按 `REMOTE_DB_BACKUPS_KEEP` 保留最新备份。
- 导入后校验该年 `events_calendar` 行数是否等于 JSON event 数。
- 本地完整执行日志写入 `LOG_FILE`，默认 `logs/deploy/events-calendar-${RUN_ID}.log`。
- 远程导入 manifest 写入 `${REMOTE_IMPORT_LOG_DIR}/events-calendar-{year}-${RUN_ID}.manifest.txt`。

---

## 3. 比赛数据 (Matches)

数据来源：https://results.ittf.link/index.php/matches/players-matches-per-event（需登录）

### scrape_matches_from_player.py
按球员抓取指定日期之后的全部比赛数据。
核心流程：autocomplete 输入球员名 → 点击搜索 → 遍历赛事列表 → 进入每个赛事详情页抓取比赛。
输入：球员列表文件（由 rankings JSON 生成）
输出：
- `data/matches_complete/orig/player_<player_id>_{player_name}.json`：有 player_id 时的原始比赛数据
- `data/matches_complete/orig/{player_name}.json`：无 player_id 时的兼容文件名
- `data/raw_event_payloads/{player_name}/{event}.json`：每个赛事的原始抓取内容

`scripts/scrape_matches.py` 保留为兼容 wrapper，新脚本和文档应使用 `scripts/scrape_matches_from_player.py`。

### run_matches.py
按球员比赛数据完整流程主入口：调用 `scrape_matches_from_player.py` → `translate_matches.py`。
用法：`python run_matches.py --players-file data/women_singles_top50.json --top-n 30`

### scrape_matches_from_events.py
按赛事抓取历史赛事比赛数据。
输入：`data/event_matches_url_list.txt` 中的 event matches URL。
输出：`data/event_matches/orig/*.json`。
这是历史完赛赛事导入 `matches` / `event_draw_matches` / `sub_events` 的主数据源。

### translate_matches.py
翻译比赛数据中的字段（使用词典 translation_dict_v2.json）。
翻译字段：
- 顶层：player_name、country
- events[]：event_name、event_type
- matches[]：sub_event、stage、round、side_a、side_b（球员名+国家）
常见输入/输出：
- player-centric：`data/matches_complete/orig/*.json` → `data/matches_complete/cn/*.json`
- event-centric：`data/event_matches/orig/*.json` → `data/event_matches/cn/*.json`

### db/import_matches.py
将中文版 event-centric 比赛数据导入 SQLite 的 `matches`、`match_sides`、`match_side_players` 表。
输入：`data/event_matches/cn/*.json`
关键逻辑：
- 优先使用 payload 或文件名中的 event_id 关联 `events`。
- 非同名球员通过 player name + 当前/历史 country_code 唯一匹配 player_id。
- 同名同协会球员读取 `scripts/data/same_name_players.txt`，并用 `data/matches_complete/cn/player_<player_id>_*.json` 中的 player-centric matches 做唯一消歧。
- 支持 `--event-id` 做局部 replace。

### audit_same_name_players.py
扫描 `players` 表并维护 `scripts/data/same_name_players.txt`。
输入：
- `data/db/ittf.db`
- `data/player_country_history.json`
- 现有 `scripts/data/same_name_players.txt`

逻辑：
- 按 normalized player name + country_code 找出同名同协会 player 组。
- 将历史协会也作为有效 country 检查，发现协会变更导致的同名冲突。
- `--update` 时合并写回名单，不删除已有人工条目。

### run_import_wtt_events.sh
历史完赛赛事事实表导入入口。
按顺序执行：
- `scripts/audit_same_name_players.py --update`
- `scripts/db/import_events.py`
- `scripts/prepare_same_name_player_matches.py`
- `scripts/db/import_matches.py`
- `scripts/db/import_event_draw_matches.py`
- `scripts/db/import_sub_events.py`

常用模式：
- 无参数：全量重建。
- `--event-id <id...>`：只导入指定 event id。
- `--since "<time>"`：从 `data/event_matches/cn/*.json` 文件修改时间发现 event id 后增量导入。
- `--skip-same-name-player-matches`：跳过缺失同名球员 player-centric matches 的自动准备。
- `--same-name-from-date <YYYY-MM-DD>`：覆盖自动推断的同名球员抓取起始日期。

该脚本导入已存在的中文 events/event matches JSON。唯一会自动触发抓取和翻译的情况，
是本次待导入 matches 涉及同名球员且缺少对应 player-centric matches 消歧证据。

输出与人工检查汇总：
- 每次 run 生成日志目录 `data/logs/wtt-event-import/<run_id>/`（`<run_id>` 为时间戳）。
- 每个子命令 stdout/stderr `tee` 到 `.log`，同时通过 `--summary-json` 写结构化 `.json`
  （`import_events.json` 或 `events/*.json`、`import_matches.json`、`draw/<eid>.json`、
  `sub_events/<eid>.json`、`player_matches/prepare_same_name_player_matches.json`）。
- run 末尾调用 `scripts/db/summarize_wtt_import.py` 读取这些 JSON，渲染统一的
  `⚠ MANUAL CHECK REQUIRED` 区块（skipped files 按原因分类、各 event 的 problem
  events / unmatched champion members 等），无问题的 event 不打印。

### db/summarize_wtt_import.py
读取单次 run 的日志目录，把三个导入脚本的结构化 JSON 汇总成一个人工检查区块。
仅做汇报，始终 exit 0。由 `run_import_wtt_events.sh` 在 run 末尾调用。

### db/_import_summary.py
共享工具：把导入脚本的 `result`/`stats` dict 序列化为 JSON（set→sorted list、
Path→str）。三个导入脚本的 `--summary-json PATH`（支持 `auto`）均复用它。

### backfill_event_dates.py
回填 matches_complete JSON 文件中的 start_date / end_date 字段。
数据源：重新访问球员赛事列表页，提取日期信息。
输入：已有球员比赛 JSON 文件
输出：更新原文件（添加 start_date/end_date 字段）
与 `scrape_matches_from_player.py` 的区别：此脚本只访问赛事列表页抓日期，不进详情页抓比赛。

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
输出目录由 `--output-dir` 指定；历史赛事流程使用 `data/events_list/orig/`

### translate_events.py
翻译赛事列表中的字段（经统一 `Translator`，默认 `--mode dict` 仅词典；可选 `--mode both/llm`）。
翻译字段：name（赛事名）、event_type、event_kind。
支持增量翻译：`--since "YYYY-MM-DD HH:MM"` 只处理该时间点之后新增或修改的源 events 文件（按 `orig` 文件修改时间筛选）；`--file` 仍用于只翻译单个文件。
输入：`data/events_list/orig/*.json` → 输出：`data/events_list/cn/*.json`

### db/import_events.py
将中文版赛事列表导入 SQLite 的 `events` 表。
同时通过 event_type + event_kind 匹配 event_categories 和 event_type_mapping 表。
输入：`data/events_list/cn/*.json`，或通过 `--input-file` 指定单个 JSON。

### db/import_sub_events.py
导入 sub_events 表（赛事子类型，如 WS/MS/WD/MD/XD）。

### db/import_sub_event_type.py
导入 sub_event_type 表（赛事子类型映射）。

---

## 5. 赛事日历 (Events Calendar)

数据来源：https://www.ittf.com/{year}-events-calendar/（公开页面，无需登录）

### run_update_events_calendar.sh
赛事日历更新入口。顺序执行抓取、翻译和数据库导入：
1. `scrape_events_calendar.py --force`
2. `translate_events_calendar.py --force`
3. `db/import_events_calendar.py --year`

用法：
```bash
scripts/run_update_events_calendar.sh 2026
CDP_PORT=9224 scripts/run_update_events_calendar.sh 2026
```

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

## 6. 当前赛事运行态

本节只说明脚本职责。新增赛事、赛后补抓、cron 和 promote 的操作顺序统一见 [赛事数据日常更新流程](event-data-update-workflow.md)。

### runtime/backfill_events_calendar_event_id.py
从 `events_calendar.href` 提取 `event_id`，对 `events` 表里缺失的赛事补 INSERT。
主要用途：
- 建立 upcoming 赛事的基础 `events` 记录
- 初始化 `lifecycle_status='upcoming'`

### scrape_event_schedule.py
抓取 WTT Event Info 页（`provisional_schedule` 接口）的赛事日程并翻译，生成 per-session 的 `data/event_schedule/{event_id}.json`。
- 输出每天每个时段一条：`日期 / 场次 / 时间 / 赛事 / 球台 / 场馆 / _parsed`
- 场馆名保留原始英文；其余字段经 `scripts/lib/translator.py` 翻译
- `_parsed` 由英文 `competition` 解析出机器可读的 sub-event / stage / round，供 importer 直接使用
- 翻译模式默认先查词典再走 LLM，可用 `--provider`/`--model` 切换（MiniMax 配额受限时常用 `--provider qwen`）
- 产出的文件由 `runtime/import_current_event_session_schedule.py` 导入

### runtime/scrape_current_event.py
当前 WTT 团体赛事抓取总入口。

输出目录：`data/live_event_data/{event_id}/`

默认抓取：
- `GetEventSchedule.json`：官方基础赛程，用于补充 match code、时间、台号、队伍 roster
- `MTEAM_standings.json` / `WTEAM_standings.json`：小组积分
- `GetBrackets_{sub_event}.json`：淘汰赛签表
- `GetLiveResult.json`：进行中比赛 DOM 结果
- `GetOfficialResult.json`：官方已完结 team tie 和 individual rubber 明细

用法：
`python scripts/runtime/scrape_current_event.py --event-id 3216`

### runtime/import_current_event.py
当前 WTT 团体赛事导入总入口。

默认 sources：
- `session_schedule` -> `current_event_session_schedule`
- `schedule` -> 当前赛事赛程相关表
- `standings` -> `current_event_group_standings`
- `brackets` -> `current_event_brackets`
- `live` -> `current_event_team_ties` + `current_event_matches`
- `completed` -> `current_event_team_ties` + `current_event_matches`

用法：
`python scripts/runtime/import_current_event.py --event-id 3216`

只刷新比赛结果：
`python scripts/runtime/import_current_event.py --event-id 3216 --sources live completed`

兼容说明：
- `--sources team_ties` 和 `--sources matches` 仍可用，但会映射为 `live + completed`
- `current_event_team_ties` 由 live/completed 导入器随 `current_event_matches` 一起维护
- `GetEventSchedule.json` 不再通过单独 skeleton importer 重建 `current_event_team_ties`
- `GetOfficialResult.json` 是当前总入口的已完结 team tie 和 rubber 数据源

### runtime/import_current_event_session_schedule.py
将 `data/event_schedule/{event_id}.json` 导入 `current_event_session_schedule`。按行自动识别 per-day（旧格式，如 3216）和 per-session（每天每个时段一条，如 3242）两种结构；per-session 行写入 `session_index / session_title / start_time / table_label`，并把 `start_time` 同时写进 `morning_session_start` 以兼容 cron 生成器。导入 per-session 前需先执行 `scripts/db/upgrade_schema_session_per_session.py`。

### runtime/import_current_event_matches.py
将 WTT `GetEventSchedule.json` 比赛单元导入当前赛事比赛表，补充比赛编号、时间、台号和 roster。不同于 `scripts/scrape_event_schedule.py` 抓取的 Event Info / Provisional Schedule。

### runtime/import_current_event_live.py
从 `data/live_event_data/{event_id}/GetLiveResult.json` 导入进行中比赛。

写入：
- `current_event_team_ties`
- `current_event_team_tie_sides`
- `current_event_team_tie_side_players`
- `current_event_matches`
- `current_event_match_sides`
- `current_event_match_side_players`

### runtime/import_current_event_official_results.py
从当前赛事官方结果文件导入已完结比赛。`import_current_event.py` 的 `completed` source 实际调用该脚本。

写入：
- `current_event_team_ties`
- `current_event_team_tie_sides`
- `current_event_matches`
- `current_event_match_sides`
- `current_event_match_side_players`

### runtime/generate_current_event_crontab.py
根据 `current_event_session_schedule` 和赛事时区生成赛事专属 cron，包括每日 DB 备份（backup）、schedule、standings、brackets、live、completed 和赛后 promote 任务。

### db/promote_current_event.py
将 `current_event_*` 数据写入历史事实表，重建签表与冠军，并把赛事 lifecycle 更新为 `completed`。

### deploy/server/update_current_event.sh
current-event 生产更新的**唯一入口**（开发机运行，ssh 到生产）。一条命令完成：发布
runtime（含 per-session 赛程抓取、翻译栈、promote 及其依赖，按仓库目录镜像到默认
`doubao_tt`）→ 按 `events_calendar` 建/更新该赛事 events 行（`lifecycle_status='completed'`
的历史赛事冻结不动）→ preflight → 备份生产 `doubao_tt/data/db/ittf.db` → 抓取+导入 →
校验 `current_event_*` 行数 →（可选）安装高频 cron。

```bash
deploy/server/update_current_event.sh --event-id 3216 --time-zone Europe/London   # 首次接入设时区
deploy/server/update_current_event.sh --event-id 3216 --install-crontab
deploy/server/update_current_event.sh --event-id 3216 --sources live completed
deploy/server/update_current_event.sh --event-id 3216 --sources session_schedule  # 仅导入人工日程
deploy/server/update_current_event.sh --publish-only
```

`--time-zone <IANA>` 把日历不含的时区写到该赛事 `events` 行；`lifecycle_status` 按
`start_date`（配合事件时区）自动判 `upcoming`/`in_progress`，`--lifecycle <status>` 可覆盖。
两者只写未完结赛事，`completed` 仅由 promote 设置（永不自动）。

可配置项包括 `REMOTE_HOST`、`REMOTE_PROJECT_DIR`、`REMOTE_PYTHON`、`REMOTE_PYENV_ENV_NAME`、`REMOTE_PYTHON_BIN`、`REMOTE_TMP_DIR`、`REMOTE_DB_BACKUPS_KEEP`、`REMOTE_LOG_DIR`。裸 `scripts/runtime/scrape_current_event.py` / `import_current_event.py` 仅用于开发机/排障。

---

## 7. 积分规则 (Points Rules / Regulations)

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

## 8. 翻译词典管理

### lib/translator.py（统一翻译模块）
组合词典翻译与 LLM 翻译的统一入口：
- `DictTranslator`：纯词典查询（`scripts/data/translation_dict_v2.json`）。
- `LLMTranslator`：纯 LLM API 调用（minimax/kimi/qwen/glm/deepseek）。
- `Translator`：统一类，`mode ∈ {dict, llm, both}`（both=先词典后 LLM）。
  开启 `confirm=True` 时，对每条 LLM 译文逐条人工确认（accept / other / stop），
  确认结果回写词典文件。数据类型与词典 categories 一致：
  `players / events / locations / terms / others / position / round / stage`。
  另提供 `translate(value, category)` 兼容接口，便于保留字段编排逻辑的脚本
  最小化替换 `DictTranslator.translate`。

### run_translator.py
统一翻译命令行入口：读取每行一个词的文本文件，按 `--type` 翻译，
输出每行对应译文（保持顺序）。
用法：`python scripts/run_translator.py --file words.txt --type players [--mode dict|llm|both] [--confirm]`
`--confirm` 仅在使用 LLM 时生效，逐条人工确认并回写词典。

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

## 9. 数据库相关

### db/config.py
数据库配置：PROJECT_ROOT、DB_PATH、SCHEMA_PATH。

### db/init_database.py
初始化 SQLite 数据库，执行 DDL 建表。
建表前会备份旧数据库。

### db/upgrade_schema.py
数据库 schema 升级脚本。

### db/upgrade_schema_session_per_session.py
将 `current_event_session_schedule` 从「每天一条」升级为 per-session：新增 `session_index / session_title / start_time / table_label`，唯一约束改为 `UNIQUE(event_id, session_index)`。SQLite 无法直接改约束，脚本重建表并迁移旧数据（`session_index` 回填为 `day_index`）。幂等、运行前自动备份。导入 per-session 日程前需先执行一次。

### db/normalize_events.py
规范化赛事名称（与 import_matches.py 中的一致）。

---

## 10. 其他工具脚本

### avatar_crop.py
裁剪球员头像图片。

### dump_dict.py
导出翻译词典内容。

### json_extract.py
从 JSON 文件提取数据。

### regulations_manager.py
规则文件管理工具。

---

## 11. 已归档脚本 (archive/)

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
    ├─ scrape_matches_from_player.py ──→ data/matches_complete/orig/
    │                                      │
    │                                 translate_matches.py
    │                                      │
    │                                 同名球员消歧数据
    │
    └─ scrape_matches_from_events.py ──→ data/event_matches/orig/
                                           │
                                      translate_matches.py
                                           │
                                      run_import_wtt_events.sh → SQLite matches / event_draw_matches / sub_events

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
                                        │
                                   runtime/backfill_events_calendar_event_id.py
                                        │
                                   SQLite events(upcoming)

赛事日程（抓取或人工维护）
    │
    ├─ scrape_event_schedule.py ──→ data/event_schedule/{event_id}.json
    └─ 人工维护 ───────────────────→ data/event_schedule/{event_id}.json
            │
            └─ runtime/import_current_event_session_schedule.py
                    │  （per-session 前置：db/upgrade_schema_session_per_session.py）
                    └─ current_event_session_schedule

WTT 当前赛事数据
    │
    └─ runtime/scrape_current_event.py ──→ data/live_event_data/{event_id}/
                                             │
                                        runtime/import_current_event.py
                                             │
                                        current_event_*
                                             │
                                        db/promote_current_event.py
                                             │
                                        历史事实表
```

完整操作流程见 [赛事数据日常更新流程](event-data-update-workflow.md)。
