# 赛事数据日常更新流程

最后核对：2026-06-26

本文档是赛事数据更新的唯一操作说明。数据库维护、部署和脚本总览文档只保留职责说明，并链接到本文档。

本文记录当前代码库实际存在的入口。以下旧入口已经不存在，不应再使用：

- `scripts/scrape_event_results_daily.py`
- `scripts/scrape_wtt_event.py`
- `scripts/db/import_wtt_event.py`

## 1. 链路选择

系统有两套赛事数据链路，但日常操作分为三个场景。

| 场景 | 使用链路 | 是否安装 cron |
| --- | --- | --- |
| 2026 年及以后的赛事，在赛前或赛中接入 | 当前赛事主链路 | 是 |
| 2026 年及以后的赛事，在完赛后才接入或需要补抓 | 当前赛事主链路 | 否 |
| 补全 2026 年以前的历史赛事 | ITTF Results 历史链路 | 否 |

选择原则：

1. 新增赛事默认使用当前赛事主链路。
2. 即使赛事已经结束，只要是 2026 年及以后的赛事，也应先抓取 WTT 当前赛事数据，导入 `current_event_*`，再 promote 到历史事实表。
3. 只有补全 2026 年以前的历史赛事时，才从 `results.ittf.link` 的历史赛事页面抓取。
4. 不应为了省略初始化步骤，直接把 2026 年及以后的赛事导入历史表。当前赛事数据包含更完整的 session、台号、签表、小组积分和外部比赛编号。

## 2. 两套数据模型

### 2.1 当前赛事主链路

抓取结果目录：

```text
data/live_event_data/{event_id}/
```

主要运行态表：

- `current_event_session_schedule`
- `current_event_group_standings`
- `current_event_brackets`
- `current_event_team_ties`
- `current_event_team_tie_sides`
- `current_event_team_tie_side_players`
- `current_event_matches`
- `current_event_match_sides`
- `current_event_match_side_players`

完赛后由 `scripts/db/promote_current_event.py` 写入：

- `team_ties`
- `team_tie_sides`
- `team_tie_side_players`
- `matches`
- `match_sides`
- `match_side_players`
- `event_draw_matches`
- `sub_events`

promote 后保留 `current_event_*`。赛事详情页可继续使用信息更丰富的运行态数据，球员统计、H2H 和冠军统计使用历史事实表。

### 2.2 ITTF Results 历史链路

数据来源：

- `https://results.ittf.link/index.php/events`
- 对应赛事的 event matches 页面

主要文件：

```text
data/events_list/orig/
data/events_list/cn/
data/event_matches/orig/
data/event_matches/cn/
```

主要目标表：

- `events`
- `matches`
- `event_draw_matches`
- `sub_events`

这条链路只用于补全 2026 年以前的历史赛事。

## 3. 主链路的共同前置条件

以下命令均在仓库根目录执行。

### 3.1 确认赛事基础记录

先检查：

```bash
sqlite3 data/db/ittf.db "
SELECT event_id, year, name, start_date, end_date, time_zone, lifecycle_status
FROM events
WHERE event_id = <event_id>;
"
```

如果赛事已经存在于 `events_calendar`，但尚未进入 `events`：

```bash
python scripts/runtime/backfill_events_calendar_event_id.py
```

该脚本会从 `events_calendar.href` 提取 `event_id`，并为缺失赛事建立 `lifecycle_status='upcoming'` 的基础记录。

如果日历数据本身尚未更新，先执行赛历抓取、翻译和导入，再执行上述 backfill：

```bash
scripts/run_update_events_calendar.sh 2026
python scripts/runtime/backfill_events_calendar_event_id.py
```

`run_update_events_calendar.sh` 会顺序抓取、翻译并按年整年替换导入 `events_calendar`。

### 3.2 核对时区和生命周期

cron 生成器要求 `events.time_zone` 是有效的 IANA 时区，例如 `Europe/London`。promote 默认要求赛事状态为 `in_progress` 或 `completed`。

当前代码没有统一的 lifecycle 自动推进器。开始抓取前必须核对，必要时更新：

```bash
sqlite3 data/db/ittf.db "
UPDATE events
SET time_zone = '<IANA time zone>',
    lifecycle_status = 'in_progress'
WHERE event_id = <event_id>;
"
```

赛前准备但尚未开赛时可以暂时保留 `upcoming`；安装 cron 前至少要确保基础记录、时区和 session 日程完整。进入实际比赛更新阶段后，将状态设为 `in_progress`。

### 3.3 一次性 schema 迁移：per-session session 日程

`current_event_session_schedule` 已从「每天一条」升级为「每天每个时段一条」（per-session），新增 `session_index / session_title / start_time / table_label`，并把唯一约束由 `UNIQUE(event_id, day_index)` 改为 `UNIQUE(event_id, session_index)`。

全新库执行 `schema.sql` 已是新结构，无需迁移。已有库在导入 per-session 日程前必须先跑一次迁移（幂等、自动备份，已迁移则跳过）：

```bash
python scripts/db/upgrade_schema_session_per_session.py
```

旧的 per-day 数据会被保留并把 `session_index` 回填为 `day_index`。详见 [DATABASE_MAINTENANCE.md](DATABASE_MAINTENANCE.md)。

## 4. 场景 A：赛前或赛中接入

### 4.1 准备 session 日程

目标文件：

```text
data/event_schedule/{event_id}.json
```

支持两种格式，importer 会按行自动识别：

- **per-day（旧格式，示例 `data/event_schedule/3216.json`）**：每天一条，`时间` 为 `[首场, 末场]` 列表，含 `球台数`。
- **per-session（新格式，示例 `data/event_schedule/3242.json`）**：每天每个时段一条，含 `场次`、`时间`（单个字符串）、`球台`（具体台号文案）、`场馆`（原始英文），以及机器可读的 `_parsed` 轮次结构。

优先用抓取脚本从 WTT Event Info 页直接生成 per-session 文件（自动翻译，场馆名保留英文）：

```bash
python scripts/scrape_event_schedule.py --event-id <event_id>
# 默认先查词典再走 LLM；MiniMax 配额受限时可换 provider，例如 --provider qwen
```

也可以手工编写该 JSON。导入前如尚未迁移 schema，先执行第 3.3 节的一次性迁移。

导入：

```bash
python scripts/runtime/import_current_event.py \
  --event-id <event_id> \
  --sources session_schedule
```

检查（per-session 看 `session_index / start_time / table_label`，per-day 看 `morning/afternoon_session_start`）：

```bash
sqlite3 data/db/ittf.db "
SELECT day_index, session_index, local_date, session_title,
       start_time, morning_session_start, afternoon_session_start, table_label
FROM current_event_session_schedule
WHERE event_id = <event_id>
ORDER BY local_date, session_index;
"
```

### 4.2 首次完整抓取和导入

抓取：

```bash
python scripts/runtime/scrape_current_event.py \
  --event-id <event_id> \
  --headless
```

默认抓取：

- `schedule`：官方赛程和队伍 roster
- `standings`：小组积分
- `brackets`：淘汰赛签表
- `live`：正在进行的比赛
- `completed`：官方完赛结果

导入：

```bash
python scripts/runtime/import_current_event.py --event-id <event_id>
```

默认导入顺序：

1. `session_schedule`
2. `schedule`
3. `standings`
4. `brackets`
5. `live`
6. `completed`

### 4.3 验证首次导入

```bash
sqlite3 data/db/ittf.db "
SELECT 'sessions', COUNT(*) FROM current_event_session_schedule WHERE event_id = <event_id>
UNION ALL
SELECT 'standings', COUNT(*) FROM current_event_group_standings WHERE event_id = <event_id>
UNION ALL
SELECT 'brackets', COUNT(*) FROM current_event_brackets WHERE event_id = <event_id>
UNION ALL
SELECT 'team_ties', COUNT(*) FROM current_event_team_ties WHERE event_id = <event_id>
UNION ALL
SELECT 'matches', COUNT(*) FROM current_event_matches WHERE event_id = <event_id>;
"
```

同时检查 `data/live_event_data/{event_id}/` 中的原始文件和抓取日志，不能只根据命令退出码判断数据完整。

### 4.4 安装赛事专属 cron

开发机侧推荐使用事件 runtime 发布脚本安装或替换 cron：

```bash
REMOTE_HOST=deploy@serverA \
REMOTE_PYENV_ENV_NAME=venv \
deploy/server/update_event_runtime.sh --install-crontab <event_id>
```

如果本次不需要重新发布事件 runtime，只更新 cron：

```bash
REMOTE_HOST=deploy@serverA \
REMOTE_PYENV_ENV_NAME=venv \
deploy/server/update_event_runtime.sh --skip-publish --install-crontab <event_id>
```

登录生产服务器后也可以直接使用：

```bash
ITTF_DATA_DIR=/opt/ittf-data \
PYENV_ENV_NAME=venv \
/opt/ittf-ops/install_current_event_crontab.sh <event_id>
```

生成器依据 `current_event_session_schedule` 安排：

- `schedule`：每日刷新
- `standings`：Main Draw 前刷新
- `brackets`：Main Draw 前及比赛阶段刷新
- `live`：每个 session 开始后每 30 分钟刷新
- `completed`：每个 session 开始后每 2 小时刷新
- `promote`：最后一个比赛日的最后一个 session 起点后 24 小时执行

安装后检查托管区块：

```bash
crontab -l | sed -n \
  '/ITTF current-event refresh begin/,/ITTF current-event refresh end/p'
```

注意：当前部署包对自动 promote 的支持存在缺口，见第 8 节。修复前必须把赛后手动 promote 和校验作为正式操作。

### 4.5 赛事期间的手动补跑

完整刷新：

```bash
python scripts/runtime/scrape_current_event.py --event-id <event_id> --headless
python scripts/runtime/import_current_event.py --event-id <event_id>
```

只刷新 live 和 completed：

```bash
python scripts/runtime/scrape_current_event.py \
  --event-id <event_id> \
  --sources live completed \
  --headless

python scripts/runtime/import_current_event.py \
  --event-id <event_id> \
  --sources live completed
```

## 5. 场景 B：2026 年及以后赛事的赛后补抓

适用示例：2026 年 6 月的一场 WTT 赛事已经结束，系统在完赛后才开始接入。

该场景仍使用当前赛事主链路，但不安装 cron。流程是一次性抓取完整的赛程、签表、积分和官方完赛结果，导入运行态表，然后 promote。

### 5.1 建立基础记录并设置状态

完成第 3 节的基础记录检查，将 `time_zone` 填完整，并把 `lifecycle_status` 设置为 `in_progress`。这里的 `in_progress` 表示“允许进入 current-event promote 流程”，不表示赛事现实中仍在进行。

### 5.2 按可用数据抓取

优先执行：

```bash
python scripts/runtime/scrape_current_event.py \
  --event-id <event_id> \
  --sources schedule standings brackets completed \
  --headless
```

说明：

- `completed` 是完赛比赛结果的主要来源。
- `schedule` 用于补充比赛编号、时间、台号和 roster。
- `brackets`、`standings` 用于保留完整赛事结构。
- 完赛后通常不需要抓 `live`；只有官方 completed 数据明显缺失时才将其作为排查项。
- 如果某类页面或接口对该赛事不存在，可去掉对应 source，并在 promote 前确认核心完赛比赛数据完整。

### 5.3 导入运行态表

有人工 session 日程时：

```bash
python scripts/runtime/import_current_event.py \
  --event-id <event_id> \
  --sources session_schedule schedule standings brackets completed
```

没有人工 session 日程时：

```bash
python scripts/runtime/import_current_event.py \
  --event-id <event_id> \
  --sources schedule standings brackets completed
```

导入后执行第 4.3 节的数量检查，并重点检查：

```bash
sqlite3 data/db/ittf.db "
SELECT status, COUNT(*)
FROM current_event_matches
WHERE event_id = <event_id>
GROUP BY status;
"
```

promote 只会处理 `completed` 和 `walkover`。如果仍有应当完赛却处于 `scheduled` 或 `live` 的比赛，先修复抓取或导入结果。

### 5.4 直接 promote，不安装 cron

先 dry-run：

```bash
python scripts/db/promote_current_event.py \
  --event-id <event_id> \
  --dry-run
```

确认无误后执行：

```bash
python scripts/db/promote_current_event.py --event-id <event_id>
```

如果该赛事已有不完整的历史事实数据，需要整届替换：

```bash
python scripts/db/promote_current_event.py \
  --event-id <event_id> \
  --replace
```

只有在无法合理调整 lifecycle 时才使用 `--force`。正常流程应明确设置状态，而不是长期依赖绕过校验。

## 6. 完赛 promote 与校验

无论赛事通过 cron 自动触发，还是赛后手动补抓，都必须完成本节校验。

### 6.1 Promote 行为

`scripts/db/promote_current_event.py` 在单个事务中：

1. 校验赛事、生命周期和已完赛比赛。
2. 将团体对阵写入 `team_ties` 相关表。
3. 将单场比赛写入 `matches` 相关表。
4. 重建该赛事的 `event_draw_matches`。
5. 重建该赛事的 `sub_events` 和冠军。
6. 将 `events.lifecycle_status` 更新为 `completed`。

### 6.2 完赛后检查

```bash
sqlite3 data/db/ittf.db "
SELECT event_id, lifecycle_status, last_synced_at
FROM events
WHERE event_id = <event_id>;

SELECT COUNT(*) AS current_matches
FROM current_event_matches
WHERE event_id = <event_id>;

SELECT COUNT(*) AS historical_matches
FROM matches
WHERE event_id = <event_id>;

SELECT COUNT(*) AS draw_matches
FROM event_draw_matches
WHERE event_id = <event_id>;

SELECT sub_event_type_code, champion_name, champion_country
FROM sub_events
WHERE event_id = <event_id>;
"
```

还应在网站上检查：

- 赛事详情页仍能展示日程、签表和比赛结果。
- 球员页出现该赛事记录。
- H2H 数据包含该赛事。
- 各 sub-event 冠军正确。

### 6.3 不完整 promote 的恢复

如果第一次 promote 时还有未完成状态的比赛，后续默认执行会因为历史数据已经存在而跳过。修复运行态数据后使用：

```bash
python scripts/db/promote_current_event.py \
  --event-id <event_id> \
  --replace
```

`--replace` 会删除该赛事已有的历史事实数据并从 `current_event_*` 重新生成。执行前应备份数据库。

## 7. 场景 C：补全 2026 年以前的历史赛事

这条链路依赖 `results.ittf.link` 登录态和浏览器风控，通常在开发机手动执行。

### 7.1 抓取历史赛事列表

```bash
python scripts/scrape_events.py \
  --from-date <YYYY-MM-DD> \
  --output-dir data/events_list/orig
```

翻译并导入赛事基础信息：

```bash
python scripts/translate_events.py
python scripts/db/import_events.py
```

### 7.2 准备赛事比赛 URL

将需要补录赛事的 event matches URL 写入：

```text
data/event_matches_url_list.txt
```

每行一个 URL。只放本次需要补录的赛事，避免无关重抓。

### 7.3 抓取赛事比赛

```bash
python scripts/scrape_matches_from_events.py \
  --urls-file data/event_matches_url_list.txt \
  --output-dir data/event_matches/orig
```

翻译：

```bash
python scripts/translate_matches.py \
  --orig-dir data/event_matches/orig \
  --cn-dir data/event_matches/cn
```

检查 `missing_translations` 和 `data/event_matches/problematic/`，有问题时不要继续入库。

### 7.4 同名球员消歧数据

历史赛事比赛文件本身只有球员名和协会，没有官方 `player_id`。导入时会按以下顺序写入 `match_side_players.player_id`：

1. 非同名球员：用球员名 + 当前或历史协会唯一匹配 `players.player_id`。
2. 协会变更：读取 `data/player_country_history.json`，允许历史协会匹配到当前 `players` 记录。
3. 同名同协会球员：读取 `scripts/data/same_name_players.txt`，禁止直接用 name + country 匹配，必须使用按球员抓取的 matches 文件做消歧。

同名名单格式：

```text
player_id,player_name,country_code
```

人工审核 rankings/profile 时，`scripts/apply_ranking_profile_review.py` 会在应用 `resolution.player_id` 后检查 DB 中是否存在同名同协会多条 player；如果存在，会把整组写入 `scripts/data/same_name_players.txt`。

正式导入前还会运行独立审计：

```bash
python scripts/audit_same_name_players.py --update
```

`scripts/run_import_wtt_events.sh` 已内置该步骤。它会扫描 `players` 表，合并已有名单，发现同名同当前协会，以及 `data/player_country_history.json` 导致的历史协会冲突。这样即使本次没有 `unresolved.json`，新增同名 player 也会进入名单。

如果本次赛事涉及同名名单中的球员，`scripts/run_import_wtt_events.sh` 会在导入
`matches` 前自动检查本次 event matches 文件，并为缺失证据的同名候选 player 抓取
player-centric matches：

```bash
python scripts/scrape_matches_from_player.py \
  --player-name "<player_name>" \
  --player-country <country_code> \
  --player-id <player_id> \
  --from-date <YYYY-MM-DD>
```

抓取后会自动翻译对应的单个 player-centric matches 文件：

```bash
python scripts/translate_matches.py \
  --orig-dir data/matches_complete/orig \
  --cn-dir data/matches_complete/cn
```

有 `player_id` 时，按球员抓取的输出文件名为：

```text
data/matches_complete/orig/player_<player_id>_<player_name>.json
data/matches_complete/cn/player_<player_id>_<player_name>.json
```

`scripts/prepare_same_name_player_matches.py` 会跳过已经存在的
`data/matches_complete/cn/player_<player_id>_*.json`，避免重复抓取。自动推断的
`--from-date` 是本次导入赛事最早 `event_year` 的 `YYYY-01-01`；如需手动覆盖：

```bash
scripts/run_import_wtt_events.sh \
  --event-id <event_id> \
  --same-name-from-date <YYYY-MM-DD>
```

如浏览器环境不可用、只想离线重导已有数据，可以临时跳过自动准备步骤：

```bash
scripts/run_import_wtt_events.sh \
  --event-id <event_id> \
  --skip-same-name-player-matches
```

`import_matches.py` 会读取这些文件，把 event-centric match 与 player-centric match 按
`event_id/sub_event/stage/round/match_score/side_a/side_b` 对齐；只有唯一匹配到某个
player_id 时才写入，否则保留 NULL 并输出到 `unresolved_same_name_players` 或
`ambiguous_same_name_players`。

### 7.5 导入历史事实表

```bash
scripts/run_import_wtt_events.sh
```

该脚本会按顺序执行：

1. `scripts/audit_same_name_players.py --update`
2. `scripts/db/import_events.py`
3. `scripts/prepare_same_name_player_matches.py`
4. `scripts/db/import_matches.py`
5. `scripts/db/import_event_draw_matches.py`
6. `scripts/db/import_sub_events.py`

无 `--since` 或 `--event-id` 时是全量导入：`events` 会从
`data/events_list/cn/*.json` upsert，`matches`、`event_draw_matches`、`sub_events`
会整表重建。

该脚本默认导入已经翻译好的 `data/events_list/cn/*.json` 和
`data/event_matches/cn/*.json`。唯一会自动触发抓取/翻译的情况，是本次待导入
matches 涉及同名名单球员且对应 player-centric matches 证据缺失。导入前会先刷新
`scripts/data/same_name_players.txt`；导入 matches 时会同时读取：

- `scripts/data/same_name_players.txt`
- `data/matches_complete/cn/player_<player_id>_*.json`
- `data/player_country_history.json`

如果只需要导入本次更新的赛事，推荐显式传入 event id：

```bash
scripts/run_import_wtt_events.sh --event-id <event_id> [<event_id> ...]
```

也可以按本地文件更新时间增量导入：

```bash
scripts/run_import_wtt_events.sh --since '2026-06-20T00:00:00'
```

`--since` 的语义是：从 `data/event_matches/cn/` 中该时间后更新的 JSON 解析出 event id 集合，最后按 event id 对 `matches` 做局部 replace，并逐赛事重建 `event_draw_matches` 和 `sub_events`。它依赖文件系统 mtime，不等同于业务更新时间；如果文件来自复制、rsync、checkout 或重新翻译，mtime 可能变化。

底层命令仍可单独使用。全量：

```bash
python scripts/db/import_matches.py
python scripts/db/import_event_draw_matches.py
python scripts/db/import_sub_events.py
```

单赛事增量：

```bash
python scripts/db/import_matches.py --event-id <event_id>
python scripts/db/import_event_draw_matches.py --event-id <event_id>
python scripts/db/import_sub_events.py --event-id <event_id>
```

`import_matches.py` 的同名/历史协会相关参数默认已经指向标准路径；一般不需要显式传入：

```bash
python scripts/db/import_matches.py \
  --event-id <event_id> \
  --same-name-players scripts/data/same_name_players.txt \
  --player-matches-dir data/matches_complete/cn \
  --country-history data/player_country_history.json
```

特殊赛事修复仍按数据库维护文档执行。例如 `event_id=2860` 在导入比赛前必须运行：

```bash
python scripts/fix_special_event_2860_stage_round.py
```

## 8. 当前已知运维缺口

截至 2026-06-15，代码中的 cron 生成器会生成赛后 promote 任务，但服务器最小部署链路尚未形成可靠闭环：

1. `deploy/server/update_event_runtime.sh` 只发布当前赛事刷新 runtime，没有上传 `scripts/db/promote_current_event.py`。
2. promote 依赖的 `_match_keys.py`、`import_event_draw_matches.py`、`import_sub_events.py` 等文件也不在最小运行包中。
3. `generate_current_event_crontab.py` 生成的 promote 命令使用 `scripts/db/promote_current_event.py`，与 `/opt/ittf-ops/runtime/python/` 的最小部署目录结构不一致。
4. 当前 `current_event_*` 抓取和导入实现明显以团体赛为中心，默认 sub-event 为 `MTEAM`、`WTEAM`，官方结果导入器也按 team tie/rubber 建模。将主链路用于个人赛事前，必须先验证该赛事类型的数据能否被现有 importer 完整表达。

因此当前正式操作要求：

- cron 仍用于赛事期间的定时刷新。
- 赛事结束后必须人工检查 promote 是否实际成功。
- 在部署缺口修复前，以仓库完整环境中的手动 promote 为准。
- 不要仅因 crontab 中存在 `sources=promote` 就认为赛事已经进入历史事实表。

## 9. 故障排查

### cron 无法生成

检查：

- `events.time_zone` 是否为有效 IANA 时区。
- `current_event_session_schedule` 是否有数据。
- session 日期和 Main Draw 轮次能否被识别。
- 生成时赛事任务是否已经全部处于过去。

### 抓取成功但数据库没有更新

检查：

- 抓取输出是否写入了预期的 `data/live_event_data/{event_id}/`。
- 导入命令的 `--db-path` 和网站读取的数据库是否一致。
- 所选 `--sources` 是否同时用于 scrape 和 import。
- 原始 JSON 是否为空、被风控页面替代或仍是旧文件。

### Promote 失败

先执行 `--dry-run`，重点检查：

- lifecycle 是否为 `in_progress` 或 `completed`。
- `current_event_matches` 是否至少有一条 `completed` 或 `walkover`。
- 是否已有历史数据，需要使用 `--replace`。
- 球员无法关联时是否生成了 unmatched 报告。

## 10. 相关文档

- [数据库初始化、重建与通用校验](DATABASE_MAINTENANCE.md)
- [服务器运行环境与 cron 安装](DEPLOY_ANALYTICS.md)
- [各脚本职责](scripts_overview.md)
- [Promote 设计与字段映射](design/promote_current_event.md)
