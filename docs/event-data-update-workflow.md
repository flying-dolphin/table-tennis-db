# 赛事数据日常更新流程

最后核对：2026-06-15

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
python scripts/run_events_calendar.py --year 2026
python scripts/db/import_events_calendar.py
python scripts/runtime/backfill_events_calendar_event_id.py
```

`run_events_calendar.py` 已包含抓取和翻译，不需要再单独运行 `translate_events_calendar.py`。

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

## 4. 场景 A：赛前或赛中接入

### 4.1 准备人工 session 日程

创建：

```text
data/event_schedule/{event_id}.json
```

已有示例：

```text
data/event_schedule/3216.json
```

导入：

```bash
python scripts/runtime/import_current_event.py \
  --event-id <event_id> \
  --sources session_schedule
```

检查：

```bash
sqlite3 data/db/ittf.db "
SELECT local_date, morning_session_start, afternoon_session_start
FROM current_event_session_schedule
WHERE event_id = <event_id>
ORDER BY local_date;
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

### 7.4 导入历史事实表

```bash
python scripts/db/import_matches.py
python scripts/db/import_event_draw_matches.py
python scripts/db/import_sub_events.py
```

如果只需要重建单个已导入赛事的签表和冠军：

```bash
python scripts/db/import_event_draw_matches.py --event-id <event_id>
python scripts/db/import_sub_events.py --event-id <event_id>
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
