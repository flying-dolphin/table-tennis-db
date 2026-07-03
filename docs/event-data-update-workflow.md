# 赛事数据日常更新流程

最后核对：2026-06-28

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

该脚本会从 `events_calendar.href` 提取 `event_id`，并为缺失赛事建立 `lifecycle_status='upcoming'` 的基础记录。本节命令面向开发机本地库；**生产库无需手动 backfill**——第 4.4 节的 `update_current_event.sh` 会按 `events_calendar` 自动建/更新该赛事的 `events` 行。

如果日历数据本身尚未更新，先执行赛历抓取、翻译和导入，再执行上述 backfill：

```bash
scripts/run_update_events_calendar.sh 2026
python scripts/runtime/backfill_events_calendar_event_id.py
```

`run_update_events_calendar.sh` 会顺序抓取、翻译并按年整年替换导入 `events_calendar`。

### 3.2 确定时区与生命周期的取值

本节只负责**确定** `events` 两个专有字段的取值（日历里没有这两列）。怎么写进库分两种：
**开发机本地库**用下面的 `--apply` / sqlite；**生产库不要手动改**，用第 4.4 节
`update_current_event.sh` 的 `--time-zone` / `--lifecycle`。

- `time_zone`：cron 生成器要求有效 IANA 时区（`Area/Location`），如 `Asia/Shanghai`、
  `Asia/Qatar`、`America/Los_Angeles`、`Europe/Paris`；不要写 `UTC+8`、`CST`、`GMT` 这类简称。
- `lifecycle_status`：promote 要求 `in_progress` 或 `completed`。**生产侧不用手动设**——
  第 4.4 节的 `update_current_event.sh` 会按 `start_date`（配合事件时区）自动判定：已开赛
  （含已结束）→ `in_progress`，未开赛 → `upcoming`；**永不自动设 `completed`**（只由 promote 设）。
  需要强制某状态时用 `--lifecycle` 覆盖。开发机本地库仍可用下面的 sqlite 手动改。

先用推断脚本得到 time_zone 值（按赛事名城市 + `events_calendar.location` 国家代码）：

```bash
python scripts/runtime/infer_event_time_zone.py --event-id <event_id>
python scripts/runtime/infer_event_time_zone.py --event-id <event_id> --explain
```

只处理确定性场景：赛事名含已知城市优先按城市推断；单时区国家按国家代码推断。遇到 `USA`、
`AUS`、`CAN`、`BRA`、`MEX`、`RUS` 等多时区国家代码会失败并提示手动传 `--time-zone <IANA>`，
避免 cron 时间算错。

写入**开发机本地库**（生产库改用第 4.4 节的命令）：

```bash
# 用推断值写本地库
python scripts/runtime/infer_event_time_zone.py --event-id <event_id> --apply

# 或手动指定时区/生命周期
sqlite3 data/db/ittf.db "
UPDATE events
SET time_zone = '<IANA time zone>',
    lifecycle_status = 'in_progress'
WHERE event_id = <event_id>;
"
```

安装 cron 前至少要确保基础记录、时区和 session 日程完整。

### 3.3 一次性 schema 迁移：per-session session 日程

`current_event_session_schedule` 已从「每天一条」升级为「每天每个时段一条」（per-session），新增 `session_index / session_title / start_time / table_label`，并把唯一约束由 `UNIQUE(event_id, day_index)` 改为 `UNIQUE(event_id, session_index)`。

全新库执行 `schema.sql` 已是新结构，无需迁移。已有库在导入 per-session 日程前必须先跑一次迁移（幂等、自动备份，已迁移则跳过）：

```bash
python scripts/db/upgrade_schema_session_per_session.py
```

旧的 per-day 数据会被保留并把 `session_index` 回填为 `day_index`。详见 [DATABASE_MAINTENANCE.md](DATABASE_MAINTENANCE.md)。

## 4. 场景 A：赛前或赛中接入

> **生产更新只有一个入口 `update_current_event.sh`，集中说明在 4.4**（含命令速查表，所有用法以那张表为准）。
> 4.1 准备 session 日程（含上线一步）；4.2/4.3/4.5 是开发机本地裸命令，写开发机库或排障用，**不是生产路径、无导入前备份**。

### 4.1 准备 session 日程（开发机生成 + 上线）

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

#### 线上更新 session 日程

以上命令写的是**开发机本地库**。要让生产生效，把生成好的 `data/event_schedule/{event_id}.json`
同步到服务器，再用生产入口只导入 session_schedule（会先发布 runtime、备份生产库，然后
仅导入，不重抓其它 source）。这等同于第 4.4 节命令表的「只更新 session 日程」一行；
**首次接入新赛事**请改用第 4.4 节的完整接入命令（会一并设置时区、生命周期、装 cron）。

```bash
# 1) 上传人工/抓取得到的 session 日程到服务器
scp data/event_schedule/<event_id>.json \
  flyingfox@xiaodoubao.site:doubao_tt/data/event_schedule/

# 2) 仅导入 session_schedule（--sources session_schedule 时脚本会自动跳过 scrape）
REMOTE_PYENV_ENV_NAME=venv \
deploy/server/update_current_event.sh --event-id <event_id> --sources session_schedule
```

脚本与数据在服务器上的位置：

- `scrape_event_schedule.py` 已包含在发布的 runtime 里，线上路径
  `doubao_tt/scripts/scrape_event_schedule.py`；因此也可登录服务器在 `doubao_tt/` 下重新
  生成该 JSON，但它走 LLM 翻译，需要 `.env` 配好 `DEFAULT_PROVIDER` 及其对应 key
  （见第 8.1 节）。日常更推荐在开发机生成、scp 上传，再用上面的命令导入。
- `import_current_event.py` 线上路径 `doubao_tt/scripts/runtime/import_current_event.py`，
  由 `update_current_event.sh` 调用，从 `doubao_tt/data/event_schedule/` 读取该 JSON。
- 人工 session 日程 JSON 不随发布包上传，必须像上面那样手动 scp（见第 8.1 节一次性数据说明）。

### 4.2 首次完整抓取和导入（开发机本地）

> 本节及 4.3、4.5 是开发机本地裸命令，写本地库、无导入前备份，仅用于本地验证、按 source
> 局部刷新或排障。生产一律用 4.4 的 `update_current_event.sh`。

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
- `live`：正在进行的比赛；默认带 `--include-official`，会同时拉取最近完赛的
  official 结果，避免 WTT live 数据缺比赛或缺 score
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

### 4.3 验证首次导入（开发机本地）

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

### 4.4 生产更新入口 `update_current_event.sh` 与安装 cron

生产更新统一走这一个入口 `deploy/server/update_current_event.sh`（开发机运行，ssh 到
生产 `doubao_tt`，写网站读取的 `doubao_tt/data/db/ittf.db`）。一条命令完成：按
`events_calendar` 建/更新该赛事 `events` 行 → 设时区/生命周期（`--time-zone`/`--lifecycle`）→
preflight → **备份生产库** → 抓取+导入 → 校验 →（可选）装 cron。

**首次接入一个新赛事。** 前提：① 赛事已在 `events_calendar`（否则先更新赛历，见 3.1）；
② 已确定 IANA 时区（取值见 3.2）；③ 如需 session 信息或要装 cron，已把
`data/event_schedule/{event_id}.json` scp 到服务器（见 4.1）。然后：

```bash
REMOTE_PYENV_ENV_NAME=venv \
deploy/server/update_current_event.sh --event-id <event_id> \
  --time-zone <IANA> --install-crontab
```

`--time-zone` 仅在 `events` 行尚未设时区时需要，设过后可省略。`lifecycle_status` 由脚本按
`start_date`（配合事件时区）自动判定（已开赛→`in_progress`，未开赛→`upcoming`），无需手填；
需要强制时用 `--lifecycle <status>` 覆盖。`--time-zone` / `--lifecycle` 只写**未完结**赛事，
`completed`（历史/已 promote）一律不动，且**永不自动设 `completed`**——只由 promote 设置。

**命令速查**（同一脚本按场景选参数，所有用法以此表为准；除 `--publish-only` 外都加
`REMOTE_PYENV_ENV_NAME=venv` 前缀）：

| 场景 | 参数 |
| --- | --- |
| 首次接入新赛事 | `--event-id <id> --time-zone <IANA> --install-crontab` |
| 常规整体刷新（已设过时区） | `--event-id <id>` |
| 只刷 live/completed（赛中轻量） | `--event-id <id> --sources live completed` |
| 只更新 session 日程（先 scp，见 4.1） | `--event-id <id> --sources session_schedule` |
| 只装/换 cron、本次不重抓 | `--event-id <id> --no-refresh --install-crontab` |
| 只发布代码、不碰数据 | `--publish-only` |
| 跳过发布、只更新数据 | `--event-id <id> --skip-publish` |

默认刷新（不带 `--sources`）抓取并导入五类 source（`schedule / standings / brackets /
live / completed`）；cron 则只用 `live`（每 10 分钟刷新比分，合并最近完赛 official 结果）。
`session_schedule` 是人工日程，不在默认里，只通过上表
「只更新 session 日程」单独导入，因此默认刷新不会因服务器缺该赛事日程文件而失败。

默认每次先发布 runtime（除非 `--skip-publish`），镜像到 `doubao_tt/scripts/` 等，包含
`scripts/runtime/`（scrape/import 及各 importer）、`scripts/scrape_event_schedule.py` 及翻译栈、
`scripts/db/promote_current_event.py` 及依赖、`deploy/server/install_current_event_crontab.sh`；
完整清单见 [DEPLOY_ANALYTICS.md](DEPLOY_ANALYTICS.md) 第 8.2 节。线上脚本因此始终与开发机一致。

**cron 与手动的关系**：装了 cron 后，赛事期间的常规刷新、赛后 promote、每日
DB 备份都由 cron 自动完成，**不需要再手动跑**。只在这些情况再手动跑
`update_current_event.sh`：接入新赛事、想立刻刷新一次、赛后没装 cron 需要补抓。
裸 py 仅用于开发机/排障，**不要直接对生产库跑**（无备份）。

cron 生成器依据 `current_event_session_schedule` 安排。每个 session 有一个 **5 小时刷新窗口**
（从 session 起点开始），窗口内高频任务使用 cron 范围表达式代替逐条条目：

- `backup`：每个比赛日首个 session 起点做一次 DB 备份（保留最近 3 份）
- `schedule`：每日刷新（`session_start + 7h`）
- `standings`：Main Draw 前刷新（`session_start + 5h`）
- `brackets`：Main Draw 前及比赛阶段刷新（`session_start + 5h`）
- **session 刷新窗口**（`live`）：
  - `live`：每 **10 分钟**刷新一次比分，并带 `--include-official` 合并最近完赛 official
    结果（导入 `live` 表）
- `promote`：最后一个比赛日的最后一个 session 起点后 24 小时执行

登录生产服务器后也可只装 cron：

```bash
cd doubao_tt
PYENV_ENV_NAME=venv ./deploy/server/install_current_event_crontab.sh <event_id>
```

安装后检查托管区块：

```bash
crontab -l | sed -n \
  '/ITTF current-event refresh begin/,/ITTF current-event refresh end/p'
```

注意：`promote` 自动任务依赖的脚本已随发布包部署、cron 命令路径与发布布局一致
（见第 8 节）。但完赛后仍必须人工核对 promote 是否实际成功，不能仅因 crontab 中
存在 `sources=promote` 就认为已进入历史事实表。

### 4.5 赛事期间的手动补跑（开发机本地）

> 生产侧赛中补跑用 4.4 的 `--sources`（带备份）；本节是开发机本地等价命令。

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

### 7.6 发布已完赛历史数据到线上数据库

第 7.1–7.5 节都在开发机执行：抓取、翻译，并通过 `scripts/run_import_wtt_events.sh`
把已完赛历史赛事导入开发机数据库。确认开发机数据无误后，用专用发布脚本把同一批
赛事导入服务器 A 的线上数据库。

推荐用 `--event-file` 直接指向本批的 events_list JSON，脚本会自动解析其中的
`events[].event_id`，无需逐一手填 id（与 `run_import_wtt_events.sh --event-file` 语义
一致）：

```bash
REMOTE_HOST=deploy@serverA \
deploy/server/update_historical_events.sh \
  --event-file data/events_list/cn/events_from_2026-05-05.json
```

`--event-file` 模式只发布文件中**已经有 `data/event_matches/cn` match 文件**的赛事，
尚未抓取/翻译的赛事会被跳过并告警，不会误删线上数据。

也可以显式指定少量 id（每个 id 必须既有 events_list 条目又有 match 文件，否则报错）：

```bash
REMOTE_HOST=deploy@serverA \
deploy/server/update_historical_events.sh --event-id <event_id> [<event_id> ...]
```

该脚本与 `update_events_calendar.sh` / `update_rankings_profiles.sh` 同构，流程是：

1. 发布历史导入所需的最小 Python 运行包（`scripts/db/import_events.py`、
   `import_matches.py`、`import_event_draw_matches.py`、`import_sub_events.py`
   及其本地依赖 `_match_keys.py`、`_import_summary.py`、`event_classification_overrides.py`、
   `config.py`，以及 `scripts/audit_same_name_players.py`、
   `scripts/fix_special_event_2860_stage_round.py`）。不上传任何抓取/浏览器代码。
2. 仅打包本批 event id 对应的数据：从 `data/event_matches/cn/` 选出对应 match 文件、
   从 `data/events_list/cn/*.json` 过滤出对应 events 条目生成精简 events 列表、
   连同 `data/matches_complete/cn/player_*.json` 同名球员证据和
   `data/player_country_history.json` 一起上传。
3. 远端 preflight（校验每个 event id 都有 events 条目和 match 文件、JSON 可解析）。
4. 把 match 文件、player-centric 证据、country history 发布到线上 data 目录。
5. 备份线上 SQLite（默认保留最近 5 份 `ittf-before-historical-events-*.db`）。
6. 在线上依次执行：`audit_same_name_players.py --update`（基于线上 players 表刷新同名名单）、
   `import_events.py --input-file <精简列表>`（upsert events 行）、必要时 2860 修复、
   `import_matches.py --event-id <ids>`（按 id 删后重建）、逐赛事
   `import_event_draw_matches.py` 和 `import_sub_events.py`。
7. 远端校验每个 event id 的 `events / matches / event_draw_matches / sub_events` 行数，
   并把 manifest 写入 `${REMOTE_IMPORT_LOG_DIR}/historical-events-${RUN_ID}.manifest.txt`。

说明：

- 发布脚本严格按本批解析出的 event id 限定范围（`--event-id` 显式给定，或
  `--event-file` 从 JSON 解析并按 match 文件存在性过滤），不会触碰其它赛事的历史
  事实数据。
- 线上不抓取同名球员证据；这些 `player_*.json` 必须先在开发机由
  `scripts/run_import_wtt_events.sh` 准备好，再由本脚本上传。
- 远端用 `${REMOTE_PYTHON}` 直接调用各导入器，不调用开发机的
  `run_import_wtt_events.sh`（其内部硬编码 `python` 且包含浏览器抓取步骤）。
- 远端目标服务器用户或 pyenv 路径不同时显式设置 `REMOTE_PYTHON`，例如
  `REMOTE_PYTHON=/home/deploy/.pyenv/shims/python3.11`。
- 只发布运行包而不导入：`--publish-only`；运行包已是最新只导入：`--skip-publish`。
- 本地完整日志在 `logs/deploy/historical-events-${RUN_ID}.log`。

2026 年及以后赛事（场景 A/B）走当前赛事主链路 + promote，其线上数据由服务器 A 的
赛事刷新和 promote 流程产生，不使用本脚本。本脚本只用于第 7 节的历史链路。

## 8. 部署闭环与剩余缺口

### 8.1 生产入口与 promote 部署闭环（已修复）

截至 2026-06-28，current-event 的生产更新已收敛为单一入口
`deploy/server/update_current_event.sh`，赛后自动 promote 链路已闭环：

1. `update_current_event.sh` 按仓库目录镜像发布到 `doubao_tt/` 下，
   除当前赛事刷新 runtime（`scripts/runtime/`）外，还发布
   `scripts/db/promote_current_event.py` 及其依赖（`_match_keys.py`、
   `_import_summary.py`、`import_event_draw_matches.py`、`import_sub_events.py`、
   `config.py`），并在每次刷新前**备份生产 SQLite**。
2. current-event 代码与 rankings/calendar/historical 发布脚本同根，统一写
   `doubao_tt/data/db/ittf.db`（即网站读取的库）。`generate_current_event_crontab.py`
   生成的命令形如 `cd doubao_tt && <python> scripts/db/promote_current_event.py ...`，
   路径与发布布局一致；并额外 emit `backup` 任务，每个比赛日首个 session 起点做一次
   DB 备份（保留最近 3 份），给高频刷新兜底。
3. 同时发布 per-session 赛程抓取脚本 `scripts/scrape_event_schedule.py` 及其翻译栈
   （`scripts/lib/{translator,dict_translator,event_translation}.py`、
   `scripts/data/translation_dict_v2.json`、`docs/rules/TRANSLATION_RULES.md`）。
   该脚本走 LLM 翻译，服务器需在 `doubao_tt/.env` 配置 `DEFAULT_PROVIDER` 及其对应的
   API key（如 minimax→`MINIMAX_API_KEY`、qwen→`DASHSCOPE_API_KEY`；provider 与 key 的
   映射见 `scripts/lib/translator.py`）。
4. `update_current_event.sh` 在刷新前会按 `events_calendar` 为该赛事**建/更新
   events 行**：缺失则插入，占位行（未完结）刷新描述字段，`lifecycle_status='completed'`
   的历史/已 promote 赛事一律冻结不动；不再依赖全局 `backfill`、不会灌入未来赛事。

仍需注意：

- 完赛后必须人工核对 promote 是否实际成功（见第 6 节校验），不要仅因 crontab 中存在
  `sources=promote` 就认为赛事已经进入历史事实表。
- schema 迁移脚本（`scripts/db/upgrade_schema_*.py`）和人工 session 日程
  （`data/event_schedule/{event_id}.json`）仍按一次性手动处理：手动 scp 到
  `doubao_tt/` 对应路径并在线上执行/导入，`update_current_event.sh` 不负责这两类
  一次性数据。

### 8.2 剩余缺口：个人赛建模

当前 `current_event_*` 抓取和导入实现明显以团体赛为中心，默认 sub-event 为 `MTEAM`、
`WTEAM`，官方结果导入器也按 team tie/rubber 建模。将主链路用于个人赛事前，必须先验证
该赛事类型的数据能否被现有 importer 完整表达。

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
