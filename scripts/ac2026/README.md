# 2026 塔什干亚锦赛（3474）

目录按赛事年份命名为 `ac2026`，对应 **2026 年亚锦赛**。仅支持 event ID
`3474` 和 `TTE3474` 的静态 Bornan 数据，不保证适用于其他 ITTF 赛事。

官方页面：<https://results.ittf.com/ittf-web-results/html/TTE3474/results.html>。
七个项目为 MS、WS、MD、WD、XD、MT、WT。使用 Python 3.11+，无需浏览器和新的 Python 依赖。
从项目根目录执行以下命令；用项目现有 Python 解释器替换 `python`。

## 抓取和导入

```bash
# 第一次全量刷新，包含采集、标准化、事务导入
python -m scripts.ac2026.refresh --full

# 比赛期间刷新：重新获取元数据、实时、最新两日，以及仍有未完成比赛的旧日期
python -m scripts.ac2026.refresh

# 有代理配置但代理不可用时，显式直连
python -m scripts.ac2026.refresh --full --no-proxy

# 只采集，或只离线解析，不写数据库
python -m scripts.ac2026.scrape --full
python -m scripts.ac2026.normalize

# 在既有数据库上预览导入，事务最终回滚（含赛事初始化）
python -m scripts.ac2026.refresh --offline --dry-run

# 向临时数据库导入以验收
python -m scripts.ac2026.refresh --offline --db-path /tmp/ittf-ac2026-validation.db
```

`--db-path` 必须指向已初始化的 SQLite 数据库，不会静默创建空库。
所有入口的 `--event-id` 只接受 `3474`。`--data-root` 默认为
`data/ac2026/3474/`，用于采集快照、离线重放和异常报告。

```text
data/ac2026/3474/
  raw/<batch-id>/           原始 JSON 及该批次 manifest.json
  raw/latest.json           最近一次完整成功采集的清单
  normalized/<batch-id>.json
  normalized/current.json  当前标准化快照
  normalized/issues.json   修正警告和未解决的源数据错误
  normalized/import-report.json
```

每个原始文件记录来源 URL、采集时间、SHA-256 和资源是否已发布。请求失败不会
发布半批清单；项目资源的 404 被标为未发布，和有效的 `[]` 区分。离线重放会验证
摘要。`--all-linked` 额外请求每日列表中的每个单场详情，默认日常刷新直接使用
已包含逐局比分和子场的每日 JSON；`--full` 强制重抓全部发布日期以接收官方修正。

## PDF 完整赛程

`data/event_schedule/3474.json` 根据用户提供的
`data/ac2026/3474/raw/ATTC2026-Schedule.pdf`（PDF 元数据修改日期为 2026-10-11）逐页整理，
覆盖 10 月 19–25 日，共 93 条时段，包含比赛、休息、开幕式和颁奖。
时间采用 `Asia/Tashkent`，PDF 未注明具体场馆，因此场馆留空。

JSON 保留起止时间、各项目球台、电视转播标记、组别、原文及来源页码。
团体跨行单元格按完整时段记录；重复的 R 编号保留在 `source_round`，标准轮次
按括号内签表规模映射。`Prog K-O` 分支保留原文，轮次为 `UNKNOWN`，不推测名次。
这份 PDF 是总计划，与实时逐场赛程分别保存。

导入完整日程表（仅替换 event 3474 的时段）：

```bash
python scripts/runtime/import_current_event_session_schedule.py --event 3474
```

目标表为 `current_event_session_schedule`。结束时间还保存在每条
`parsed_rounds_json` 的 `end_time` 中，场次标题显示完整时间范围。

## 数据规则

- 复用 `events`、`sub_events`、`current_event_*`，不新增业务表。首次导入初始化
  event 3474，关联已有同名日历记录及其赛事分类；不会新增重复日历记录。
- 逐场赛程来自每日比赛和实时列表，存入 current 比赛/团体表；PDF 总计划单独导入
  `current_event_session_schedule`，不会覆盖逐场比赛及比分。
- 官方完整 Key 用于总场和单项比赛；团体子场使用 `<父场Key>:rubber:<1-based序号>`。
- 团体子场用报名名单中的选手编号解析所属队，协会为兜底。Home/Away 方向不一致时
  一并交换选手、比分和逐局分；不依赖有冲突的 TeamReg。修正写入 warning。
- `Win=false` 不能否定完整比分。已结束比赛的胜者由比分确定，并核对完整逐局分。
  团体未进行的 `0-0` 子场不创建比赛；第一局已有实时分数的子场仍然保留。
- `WO` 为 walkover，现有归档器会跳过其个人战绩；`RET` 为实际进行后的退赛，保存
  数字局分、`source_status=RET` 及原始响应。源站补齐的获判分数原样保留。
  双方均为 `WO`、`Win` 不为 `true` 且无已进行得分时，保留 `WO-WO` 和空胜者；重新导入
  会清除旧胜者。归档仅对原始数据可证实的这类双弃权允许空胜者，不计入个人战绩。
- 报名名单与实际出场名单分别存入团体名单表和比赛名单表。个人 Reg 先校验
  数据库 ID、姓名、协会和项目性别；ID 不存在时才允许唯一的规范姓名匹配。
  无法匹配的球员保留源姓名和协会、ID 为空，列在 import-report 中，不生成假 ID。
- MAIN、PREL、5-8/9-16/CONS 分别映射为正赛、预赛、排位赛。排位轮次包含
  `916-`（9–16 名）、`1616`（13–16 名首轮，按官方描述解释）、`1314`（13–14 名）
  和 `1516`（15–16 名）；两个决名次轮次排序相同，均位于 13–16 名首轮之后。
  CONS 保留源签表编码，不推断胜者或负者流向。完整保留空签位和
  BYE，轮空不创建比赛或个人胜场。只在正赛标准二叉结构中建立晋级前序。
- 签表提供 `Name` 展示别名及 `_resolved_players`，兼容已有前端；原始对象保留
  在 `_original`。不需要修改 WTT 或亚运会抓取逻辑及前端解析器。
- 时间是 `Asia/Tashkent` 本地时间，另存 UTC；北京时间由前端按现有规则展示。
  日期从每日文件获得，签表文本时间只按本届赛事十月解释；TBD 保存为空。
- 官方积分和排名直接导入；缺失的净胜分、局数等统计留空。新批次不会因空名单
  或空统计清除已知信息，缩短的人员名单保留已有完整名单供下次全量核对。
- 导入是单事务，重复批次不新增记录，旧批次不覆盖新批次；已完成结果不会退回
  scheduled/live。较新的完整终态结果可修正比分及胜者。资源短暂缺失不删除比赛。
- `issues.json` 中 error 对应的数据不强行推断；其余可解析数据仍可导入，归档会
  被阻止。不要手工绕过校验，需要先核对官方数据并重新采集。

## 定时刷新与部署

在部署主机发布这些代码后执行：

```bash
# 自动备份既有数据库，再执行一次全量刷新
bash deploy/server/update_ac2026.sh --full

# 首次刷新会自动建立赛事 3474 及关联项目；成功后再导入 PDF 完整日程
python scripts/runtime/import_current_event_session_schedule.py --event 3474

# 只预览定时配置
python -m scripts.ac2026.generate_crontab

# 显式安装自身标记区块，保留其他 cron 任务
bash scripts/ac2026/install_crontab.sh
```

更新脚本和 cron 安装脚本共用解释器选择逻辑：优先使用显式设置的 `PYTHON_BIN`，
未设置时依次检查项目 `.venv/bin/python`、PATH 中的 `python`、`python3.11` 和
`python3`。必须是可运行的 Python 3.11+；解释器无效时会在备份、导入或修改 cron
之前退出。显式指定的无效路径不会被静默替换。安装器将实际解释器路径写入 cron，
定时运行无需依赖交互式 shell 的 pyenv 初始化。也可手动指定：

```bash
PYTHON_BIN="$(command -v python)" bash scripts/ac2026/install_crontab.sh
```

备份保存在
`data/db/backups/ittf-before-ac2026-*.db`，由运维按现有备份策略保留。
定时任务使用 `CRON_TZ=Asia/Shanghai`：2026 年 10 月 19–25 日每五分钟刷新，
23:30 全量核对，26 日 04:55 执行独立的最终全量刷新，05:00 尝试本地归档。
刷新任务负责更新 `current_event_*`；
归档任务负责校验本地数据并写入历史表。模块使用文件锁防止刷新重叠；归档
全程持有同一锁。cron 会创建日志目录，失败可查 `data/ac2026/3474/logs/`。

安装器自动生成最终刷新和 `finalize --skip-refresh` 两条任务，无需手工编辑。
归档校验要求最近一次已导入快照来自全量核对；若 05:00 最终刷新仍未完成，
归档会等待刷新释放锁，再读取快照。刷新失败或数据校验不通过时，不强制归档；
根据日志处理并在数据补齐后重试。重复安装只替换自身标记区块，保留其他任务。

## 赛事结束归档

正常流程：**定时抓取更新 current 表 → 赛事结束 → cron 执行归档 → 完成。**

归档成功后，不需要再执行其他命令。以下命令按场景选用，不是依次执行。

### 正常归档：cron 执行一次即可

```bash
python -m scripts.ac2026.finalize --skip-refresh
```

该命令检查本地数据，通过后将 `current_event_matches`、`current_event_team_ties`
及关联数据写入 `matches`、`team_ties` 等历史表，并将赛事标记为已结束。
配置好上一节的 cron 后，由 cron 自动执行；成功后无需再手动运行。

归档现在默认不联网，省略 `--skip-refresh` 也只读取本地数据。
该参数为兼容旧命令保留，cron 显式带上它以表达本地归档的用途。

### 可选：人工预览归档

```bash
python -m scripts.ac2026.finalize --skip-refresh --dry-run
```

只检查数据并预览将执行的归档，不写历史表。仅供人工检查，不是正常归档的必做步骤。

### 异常修复：重建本届赛事的历史记录

```bash
python -m scripts.ac2026.finalize --skip-refresh --replace
```

仅在归档后发现历史记录有误，并已核对用于重建的 current 数据时使用。
该命令删除**本届赛事（3474）**已有的历史记录，再根据 current 数据重新生成，
不影响其他赛事。正常归档成功后不要再执行它。

已归档赛事的普通刷新会拒绝写入；重建前需先核对并修正 current 数据及对应快照。
重建时还会检查保留的 current 行是否属于同一批次。

### 归档条件与失败处理

归档要求已保存的官方元数据中 `isFinished=true`、全部七个项目和 19–25 日资源齐全、七项决赛完成、
没有源数据 error、没有未结束实际比赛、双方和报名名单完整，且数据库同步时间
与核查快照一致，七项决赛还必须有实际比赛/团体结果。未发布的空模板签表不会
作为真实未赛比赛导入。校验失败时保留 current 数据并输出原因；由刷新任务补齐
数据后，再重试归档。没有强制绕过参数。

最近一次已导入快照还必须来自全量核对，由独立刷新任务完成，安排方式见上一节。

## 开发者测试（不属于赛事归档操作）

以下命令用于开发或修改抓取代码后验证实现。赛事归档成功后无需执行。

```bash
python -m unittest discover -s scripts/ac2026/tests -v
```

fixture 是从官方 JSON 裁剪并去掉统计大字段的样本，包含方向冲突、退赛、双打和轮空。
验证使用内存/临时数据库，不修改项目正式库。
