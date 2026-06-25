# 数据更新操作说明

本文档是 rankings、profiles、赛事日历和赛事数据的日常更新入口。所有命令默认在仓库根目录执行。

## 1. 更新前准备

### 1.1 Python 环境

```bash
pip install -r requirements.txt
```

需要浏览器自动化时，确保 Playwright/Patchright 的 Chromium 可用。

### 1.2 CDP 浏览器会话

ranking/profile 抓取建议复用人工登录过的 Windows Chrome。Windows 侧启动 Chrome：

```bat
chrome.exe --remote-debugging-port=9223 --user-data-dir="%TEMP%\ittf-cdp"
```

WSL 侧运行脚本时使用：

```bash
--cdp-port 9223 --cdp-only
```

`--cdp-only` 表示必须连接已有 Chrome。连接失败时脚本直接退出，不会自动打开新浏览器。

### 1.3 词典

翻译词典固定使用：

```text
scripts/data/translation_dict_v2.json
```

补充人工翻译后，建议校验：

```bash
python scripts/validate_translation_dict.py --input scripts/data/translation_dict_v2.json
```

## 2. Rankings 和 Profiles 更新流程

### 2.1 数据流

```text
scrape rankings/results/profile
  -> data/rankings/orig/
  -> data/rankings/id_snapshots/
  -> data/player_profiles/orig/
  -> merge player_id
  -> translate ranking/profile
  -> manual review/apply
  -> import players/rankings
```

profile 抓取阶段只写 JSON、头像和 checkpoint，不直接写 `player_profiles` 数据表。正式入库由 `scripts/db/import_players.py` 负责。

### 2.2 一键抓取 ranking、results player_id 和 profiles

```bash
python scripts/run_ranking_profile.py \
  --cdp-port 9223 \
  --cdp-only \
  --resume
```

常用参数：

- `--top 1000`：抓取排名数量，默认 1000。
- `--category women|men`：默认 `women`。
- `--resume`：复用已完成的 weekly ranking 和 results snapshot，继续 profile 抓取。
- `--force`：忽略 checkpoint 和已有产物，重新抓取。
- `--ranking-only`：只抓 ranking，不刷新 profiles。

中断后继续运行同一命令即可：

```bash
python scripts/run_ranking_profile.py \
  --cdp-port 9223 \
  --cdp-only \
  --resume
```

### 2.3 翻译 ranking

找到带 player_id 的 ranking 文件，例如：

```text
data/rankings/orig/women_singles_top1000_week25_with_ids.json
```

执行：

```bash
python scripts/translate_rankings.py \
  --file data/rankings/orig/women_singles_top1000_week25_with_ids.json \
  --force
```

输出：

```text
data/rankings/cn/women_singles_top1000_week25_with_ids.json
scripts/logs/translate_ranks.log
```

### 2.4 翻译 profiles

```bash
python scripts/translate_profiles.py
```

只翻译某个时间点之后新增或修改过的源 profile 文件时，使用 `--since`：

```bash
python scripts/translate_profiles.py --since "2026-06-25 10:00"
```

`--since` 按 `data/player_profiles/orig/player_*.json` 的文件修改时间筛选，支持 `YYYY-MM-DD`、`YYYY-MM-DD HH:MM[:SS]` 和 `YYYY-MM-DDTHH:MM[:SS]`。传入 `--file` 时只处理指定文件，忽略 `--since`。

输出：

```text
data/player_profiles/cn/player_*.json
scripts/logs/translate_profiles.log
```

### 2.5 生成人工审核文件

ranking player_id 匹配失败和翻译缺失统一进入 review 文件。

```bash
python scripts/review_ranking_profile_outputs.py \
  --ranking-unresolved data/rankings/orig/women_singles_top1000_week25_with_ids_unresolved.json \
  --rank-translation-log scripts/logs/translate_ranks.log \
  --profile-translation-log scripts/logs/translate_profiles.log \
  --output data/review/ranking_profile_review_week25.json
```

人工编辑：

```text
data/review/ranking_profile_review_week25.json
```

需要补充：

- `unresolved_player_ids[].resolution.player_id`
- `unresolved_player_ids[].resolution.profile_url`
- `missing_translations[].translated`

### 2.6 应用人工审核结果

```bash
python scripts/apply_ranking_profile_review.py \
  --review data/review/ranking_profile_review_week25.json \
  --ranking-file data/rankings/orig/women_singles_top1000_week25_with_ids.json
```

该命令会：

- 将人工补充的 `player_id/profile_url` 写回 ranking JSON。
- 将人工补充的翻译写入 `scripts/data/translation_dict_v2.json`。

应用后重新翻译 ranking 和 profiles：

```bash
python scripts/translate_rankings.py \
  --file data/rankings/orig/women_singles_top1000_week25_with_ids.json \
  --force

python scripts/translate_profiles.py
```

如果本次只补充了增量 profile 的翻译词条，也可以只重跑增量 profile 翻译：

```bash
python scripts/translate_profiles.py --since "2026-06-25 10:00"
```

### 2.7 入库

先导入 players，再导入 rankings：

```bash
python scripts/db/import_players.py
python scripts/db/import_rankings.py
```

`import_rankings.py` 会输出数据完整性报告。如果报告里仍有缺失中文名、无法匹配 players 表的条目，先回到人工审核和翻译步骤修正，不要忽略后继续发布。

### 2.8 验证

```bash
sqlite3 data/db/ittf.db "
SELECT COUNT(*) FROM players;
SELECT COUNT(*) FROM ranking_snapshots;
SELECT COUNT(*) FROM ranking_entries;
"
```

## 3. Rankings 和 Profiles 脚本说明

### 3.1 `scripts/run_ranking_profile.py`

- 功能：ranking/profile 更新编排入口。
- 输入：
  - CDP Chrome：`--cdp-port`。
  - 参数：`--category`、`--top`、`--resume`、`--force`。
  - checkpoint：`data/rankings/checkpoint_results_rankings.json`。
- 输出：
  - weekly ranking：`data/rankings/orig/women_singles_top*_week*.json`。
  - results snapshot：`data/rankings/id_snapshots/results_*_top*_*.json`。
  - merged ranking：默认在 weekly ranking 同目录生成 `*_with_ids.json`。
  - unresolved report：默认生成 `*_with_ids_unresolved.json`。
  - profile JSON：`data/player_profiles/orig/player_*.json`。
  - avatars：`data/player_avatars/`。
- 逻辑：
  1. 抓取 `ittf.com` weekly ranking。
  2. 抓取 `results.ittf.link` ranking，获得 `player_id/profile_url`。
  3. 刷新每个球员 profile。
  4. 将 weekly ranking 和 results ranking 合并。
  5. `--resume` 时复用已有 ranking snapshot，从未完成 profile 附近继续。

### 3.2 `scripts/merge_ranking_ids.py`

- 功能：把 weekly ranking 和 results ranking 中的 `player_id` 合并。
- 输入：
  - `--weekly`：`data/rankings/orig/*.json`。
  - `--results`：`data/rankings/id_snapshots/*.json`。
- 输出：
  - merged ranking：`*_with_ids.json`。
  - unresolved report：`*_with_ids_unresolved.json`。
- 逻辑：
  1. 用姓名、国家/地区和积分做精确匹配。
  2. 精确匹配失败时，用姓名和国家/地区做宽松匹配。
  3. 匹配成功写入 `player_id/profile_url`。
  4. 无法匹配或候选不唯一时写入 unresolved report。

### 3.3 `scripts/translate_rankings.py`

- 功能：将 ranking JSON 从英文翻译为中文。
- 输入：
  - `data/rankings/orig/*.json` 或 `--file` 指定文件。
  - 词典：`scripts/data/translation_dict_v2.json`。
- 输出：
  - `data/rankings/cn/*.json`。
  - 缺失词条日志：`scripts/logs/translate_ranks.log`。
- 逻辑：
  1. 翻译球员姓名、国家/地区、points breakdown 中的赛事、类别、过期日期和名次字段。
  2. 只使用词典，不直接调用 LLM。
  3. 未命中的词条写入日志，后续进入人工 review。

### 3.4 `scripts/translate_profiles.py`

- 功能：将 profile JSON 从英文翻译为中文。
- 输入：
  - `data/player_profiles/orig/player_*.json` 或 `--file` 指定文件。
  - 词典：`scripts/data/translation_dict_v2.json`。
- 输出：
  - `data/player_profiles/cn/player_*.json`。
  - 缺失词条日志：`scripts/logs/translate_profiles.log`。
- 逻辑：
  1. 删除 `recent_matches` 字段。
  2. 翻译 `name`、`country`、`gender`、`style`、`playing_hand`、`grip`。
  3. 只使用词典。
  4. 未命中的词条写入日志。

### 3.5 `scripts/review_ranking_profile_outputs.py`

- 功能：生成统一人工审核文件。
- 输入：
  - ranking unresolved report：`*_with_ids_unresolved.json`。
  - ranking 翻译缺失日志：`scripts/logs/translate_ranks.log`。
  - profile 翻译缺失日志：`scripts/logs/translate_profiles.log`。
- 输出：
  - review JSON：默认 `data/review/ranking_profile_review.json`，可用 `--output` 指定。
- 逻辑：
  1. 读取 unresolved player_id。
  2. 读取 ranking/profile 翻译缺失日志。
  3. 生成带空白 `resolution` 和 `translated` 字段的人工补全文件。

### 3.6 `scripts/apply_ranking_profile_review.py`

- 功能：应用人工补全结果。
- 输入：
  - `--review`：人工补完的 review JSON。
  - `--ranking-file`：需要回写 player_id 的 merged ranking JSON。
  - `--dict-path`：默认 `scripts/data/translation_dict_v2.json`。
- 输出：
  - 更新后的 ranking JSON。
  - 更新后的翻译词典。
- 逻辑：
  1. 对填写了 `resolution.player_id` 的 unresolved ranking 条目回写 `player_id/profile_url`。
  2. 对填写了 `translated` 的缺失翻译条目写入词典。
  3. 未填写的条目跳过。

### 3.7 `scripts/db/import_players.py`

- 功能：将中文 profile 导入数据库 players 表。
- 输入：
  - `data/player_profiles/cn/player_*.json`。
  - 数据库：`data/db/ittf.db`。
- 输出：
  - 更新 `players` 表。
- 逻辑：
  1. 遍历中文 profile JSON。
  2. 提取球员基础信息、国家/地区、头像、打法等字段。
  3. 插入或更新 players 表。
  4. 输出 inserted、skipped 和 errors 统计。

### 3.8 `scripts/db/import_rankings.py`

- 功能：将中文 ranking 导入数据库 ranking 相关表。
- 输入：
  - `data/rankings/cn/*.json`。
  - 数据库：`data/db/ittf.db`。
- 输出：
  - `ranking_snapshots`
  - `ranking_entries`
  - ranking points breakdown 相关表
- 逻辑：
  1. 读取 ranking 快照。
  2. 匹配 players 表中的球员。
  3. 写入 ranking snapshot、ranking entries 和 points breakdown。
  4. 输出完整性报告，包括缺少中文名、无法匹配 players 的条目。

## 4. 赛事日历更新流程

### 4.1 抓取并翻译赛事日历

```bash
python scripts/run_events_calendar.py \
  --year 2026 \
  --cdp-port 9223
```

输出：

```text
data/events_calendar/orig/events_calendar_2026.json
data/events_calendar/cn/events_calendar_2026.json
```

如果需要强制重跑：

```bash
python scripts/run_events_calendar.py \
  --year 2026 \
  --cdp-port 9223 \
  --force
```

### 4.2 从日历翻译结果更新词典

```bash
python scripts/update_event_to_dict.py
```

如果只想预览：

```bash
python scripts/update_event_to_dict.py --dry-run
```

### 4.3 导入数据库

```bash
python scripts/db/import_events_calendar.py
```

### 4.4 反填 events 基础记录

如果日历里有 `href/event_id`，但 `events` 表缺少基础记录：

```bash
python scripts/runtime/backfill_events_calendar_event_id.py
```

### 4.5 验证

```bash
sqlite3 data/db/ittf.db "
SELECT COUNT(*) FROM events_calendar WHERE year = 2026;
SELECT event_id, year, name, start_date, end_date, lifecycle_status
FROM events
WHERE year = 2026
ORDER BY start_date DESC
LIMIT 20;
"
```

## 5. 赛事日历脚本说明

### 5.1 `scripts/run_events_calendar.py`

- 功能：赛事日历完整流程入口。
- 输入：
  - `--year`：目标年份。
  - CDP/browser 参数：`--cdp-port`、`--headless`、`--slow-mo`。
  - `--force`、`--rebuild-checkpoint`。
- 输出：
  - `data/events_calendar/orig/events_calendar_{year}.json`。
  - `data/events_calendar/cn/events_calendar_{year}.json`。
- 逻辑：
  1. 调用 `scrape_events_calendar.py` 抓取原始日历。
  2. 抓取成功后调用 `translate_events_calendar.py` 翻译。
  3. 输出 orig 和 cn 两份文件。

### 5.2 `scripts/scrape_events_calendar.py`

- 功能：抓取指定年份赛事日历。
- 输入：
  - ITTF/WTT 日历页面。
  - `--year` 或由 `run_events_calendar.py` 传入年份。
- 输出：
  - `data/events_calendar/orig/events_calendar_{year}.json`。
  - scrape checkpoint。
- 逻辑：
  1. 打开赛事日历页面。
  2. 解析赛事名称、起止日期、地点、链接等字段。
  3. 写入 orig JSON。

### 5.3 `scripts/translate_events_calendar.py`

- 功能：翻译赛事日历。
- 输入：
  - `data/events_calendar/orig/events_calendar_{year}.json`。
  - 词典：`scripts/data/translation_dict_v2.json`。
  - 可选 LLM API 配置。
- 输出：
  - `data/events_calendar/cn/events_calendar_{year}.json`。
  - `data/events_calendar/checkpoint_translate_events_calendar.json`。
- 逻辑：
  1. 地点和部分固定词条使用词典。
  2. 赛事名优先复用已有 cn 文件和词典。
  3. 必要时用 LLM fallback。
  4. 分批保存翻译进度。

### 5.4 `scripts/update_event_to_dict.py`

- 功能：从已翻译的赛事数据反向更新词典。
- 输入：
  - `data/events_list/orig` 与 `data/events_list/cn` 最新同名文件。
  - `data/events_calendar/orig` 与 `data/events_calendar/cn` 最新同名文件。
  - 词典：`scripts/data/translation_dict_v2.json`。
- 输出：
  - 更新后的 `scripts/data/translation_dict_v2.json`。
- 逻辑：
  1. 对齐 orig/cn 文件。
  2. 提取赛事名、地点等原文和中文译文。
  3. 检查同一原文是否有多个译文。
  4. 调用词典更新逻辑写入新词条。

### 5.5 `scripts/db/import_events_calendar.py`

- 功能：将中文赛事日历导入数据库。
- 输入：
  - `data/events_calendar/cn/*.json`。
  - 数据库：`data/db/ittf.db`。
- 输出：
  - 更新 `events_calendar` 表。
- 逻辑：
  1. 遍历中文赛事日历 JSON。
  2. 写入赛事名称、年份、起止日期、地点、链接等字段。
  3. 输出导入统计和校验信息。

### 5.6 `scripts/runtime/backfill_events_calendar_event_id.py`

- 功能：从赛事日历反填 `events` 基础记录。
- 输入：
  - 数据库中的 `events_calendar` 表。
- 输出：
  - 更新 `events` 表。
- 逻辑：
  1. 从 `events_calendar.href` 提取 `event_id`。
  2. 找出 `events` 表中不存在的赛事。
  3. 创建基础 event 记录，通常用于后续当前赛事链路接入。

## 6. 赛事数据更新流程

赛事数据更新不要在本文档重复维护完整步骤。统一使用：

[赛事数据日常更新流程](event-data-update-workflow.md)

该文档覆盖：

- 2026 年及以后的赛事赛前或赛中接入。
- 2026 年及以后的赛事赛后补抓。
- 2026 年以前历史赛事补录。
- 当前赛事主链路的 scrape/import/promote。
- ITTF Results 历史链路的 events/matches 抓取、翻译和入库。
- cron 安装、手动补跑和数据校验。

### 6.1 场景选择摘要

| 场景 | 使用流程 |
| --- | --- |
| 2026 年及以后，赛前或赛中接入 | 当前赛事主链路，按 `event-data-update-workflow.md` 安装赛事 cron |
| 2026 年及以后，赛后补抓 | 当前赛事主链路，不安装 cron，抓取后手动 import/promote |
| 2026 年以前历史补录 | ITTF Results 历史链路 |

### 6.2 常用入口

当前赛事主链路常用入口：

```bash
python scripts/runtime/scrape_current_event.py --event-id <event_id> --headless
python scripts/runtime/import_current_event.py --event-id <event_id>
python scripts/db/promote_current_event.py --event-id <event_id>
```

历史链路常用入口：

```bash
python scripts/scrape_events.py --from-date 2024-01-01
python scripts/translate_events.py
python scripts/scrape_matches_from_events.py \
  --urls-file data/event_matches_url_list.txt \
  --output-dir data/event_matches/orig
python scripts/translate_matches.py \
  --orig-dir data/event_matches/orig \
  --cn-dir data/event_matches/cn
python scripts/db/import_matches.py
```

具体执行顺序、前置检查和校验 SQL 以 [赛事数据日常更新流程](event-data-update-workflow.md) 为准。

## 7. 常见问题

### 7.1 `--resume` 和 `--force` 怎么选

- 日常中断续跑：使用 `--resume`。
- 确认旧数据不可用、需要重新抓取：使用 `--force`。
- 不要同时把 `--force` 当作常规续跑参数使用。

### 7.2 ranking unresolved 可以忽略吗

不建议忽略。unresolved 表示 weekly ranking 中某些球员没有可靠 `player_id`。这会影响 profile 关联、players 表匹配和 ranking 入库完整性。应通过 review 文件人工补齐。

### 7.3 翻译缺失可以忽略吗

不建议忽略。`import_rankings.py` 会报告缺少中文名或无法匹配 players 的条目。缺失翻译应进入 review 文件，补词典后重新翻译。

### 7.4 profile 抓取还会直接写 SQLite 吗

不会。profile 抓取只写：

```text
data/player_profiles/orig/
data/player_avatars/
checkpoint
```

正式入库只通过：

```bash
python scripts/db/import_players.py
```
