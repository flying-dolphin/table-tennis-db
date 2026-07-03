# 全量历史 Events/Matches/Players 补全流程计划

## Summary

目标是新增一次性历史补全流水线：以 `results.ittf.link` events 页面能返回的全部赛事为边界，补齐 events、event matches、由 matches 反推的 player profiles、同名球员消歧证据、翻译和数据库导入。

命令阶段命名为：

- `scrape-events`
- `scrape-matches`
- `scrape-players`
- `translate`
- `import`

players 全部入库；只有 `career_best_rank <= 50` 的新增 profile 补中文字段。

## Key Changes

- 新增编排入口，例如 `scripts/backfill_historical_data.py`：
  - `plan`：生成缺口统计、批次清单、预计请求量。
  - `scrape-events`：抓全量 events，进入 events 页面后强制切到 Display 100。
  - `scrape-matches`：抓缺失 event matches，进入每个 event matches 页面后强制切到 Display 100。
  - `scrape-players`：从 event matches 提取 player，执行 profile search、抓缺失 profile、更新同名名单。
  - `translate`：翻译新增 events/matches/profiles。
  - `import`：调用现有 `run_import_wtt_events.sh --event-file ...` 或 `--event-id ...`。
  - 所有抓取阶段必须支持中断恢复和断点续跑，重跑时只处理 pending/failed 项，不重复抓取 completed 项。
  - `plan` 输出必须展示 completed / pending / failed 数量，便于中断后确认续跑范围。

- event matches URL 生成：
  - 从 `data/events_list/orig/*.json` 的 `matches_href` 生成待抓 URL。
  - 不过滤 `filtering_only=1` 的 event。
  - 只按“是否已有 event_matches 输出文件/problematic 文件”跳过。
  - 输出批次文件，如 `data/backfill/historical/event_match_urls_YYYYMMDD.txt`。

- `filtering_only` 策略：
  - 抓取层包含 `filtering_only`，保存原始 JSON，保证源数据全量归档。
  - 导入层默认保持现状：`import_matches.py` 继续跳过 `filtering_only`，避免影响正式统计。
  - 如果未来开启导入，会影响 DB `matches/match_sides/match_side_players`，并改变球员胜负、H2H、赛事详情、签表和冠军派生数据。
  - 当前前端 events 列表已过滤 `filtering_only`，但直接访问 event detail 或统计查询仍可能受导入影响。

- profile search candidate cache：
  - 首次全量前，先合并去重：
    - event matches 中出现过的唯一英文名。
    - DB 现有 player name。
  - 对去重后的 name 集合做 profile search 枚举，写入 `data/player_profiles/profile_search_candidates.json`。
  - cache 记录 `name_key -> candidates[] + last_checked_at`，候选包含 `player_id/display_name/country_code`。
  - cache 默认永不过期，不做自动周期复查。

- 后续增量 profile search：
  - 只搜索：
    - 新增 matches 中出现、但 candidate cache 里没有的 `name_key`。
    - import 后产生的 `unmatched_players`。
    - import 后产生的 `same_name_unresolved` / `ambiguous_players`。
    - 人工指定 `--refresh-name` / `--refresh-from-file` 的名字。
  - 对 cache 已有且候选唯一的 `name + country_code`，默认继续使用现有映射。
  - 明确代价：无法主动发现“DB 已有唯一 player A，后续出现同名同协会新 player”的情况；只能通过导入异常、人工抽查或手动 refresh 发现。
  - 好处：请求量最低，风控风险最低。

- 同名消歧：
  - 从本地 `data/player_profiles/orig/player_*.json` 离线生成 same-name entries。
  - 合并写入 `scripts/data/same_name_players.txt`，保留已有人工条目。
  - 导入 matches 前运行 `prepare_same_name_player_matches.py`，为同名候选补 player-centric matches 证据。
  - 对仍无法关联的 player，记录 unresolved，不强行映射。

- 翻译：
  - events：复用 `translate_events.py`。
  - event matches：复用 `translate_matches.py`。
  - profiles：改造 `translate_profiles.py`，新增 `--career-best-rank-lte 50`；非前 50 profile 仍生成可导入 CN JSON，但不补中文名/中文字段。
  - 所有可能调用 LLM 的翻译流程必须支持中断恢复和断点续跑。
  - 已经完整翻译的 event/match/profile 不重新翻译；词典已命中的内容不调用 LLM。
  - LLM 翻译完成并写入结果或词典后，重跑应直接复用已完成内容。
  - 翻译失败项单独记录，后续只重试失败或缺失项。
  - 翻译输出应按文件或条目增量保存，避免中途断电丢失整批进度。

## Test Plan

- 单元测试：
  - events scraper 确认会调用 Display 100。
  - URL 生成不排除 `filtering_only`。
  - scrape-matches 可抓取并保存 `filtering_only` event 文件。
  - import 默认仍跳过 `filtering_only` matches。
  - profile search 首次全量会对 matches name 与 DB name 合并去重。
  - 增量 profile search 按 candidate cache 缺失或人工 refresh 判断，不按 DB 缺失判断。
  - same-name 离线审计从 profile JSON 生成名单并保留人工条目。

- Dry-run 验证：
  - `backfill_historical_data.py plan` 输出 events 总数、待抓 matches、`filtering_only` 数量、待 search name 数、缺失 profile 数。
  - `backfill_historical_data.py plan` 输出每个阶段的 completed / pending / failed 数量。
  - `prepare_same_name_player_matches.py --dry-run` 输出需要补抓的 player-centric evidence。

- 断点续跑验证：
  - 人工中断 `scrape-events` / `scrape-matches` / `scrape-players` 后重跑，只处理未完成或失败项。
  - 人工中断 LLM 翻译后重跑，已完成条目不重新调用 LLM，只处理失败或缺失项。

- 小批次端到端：
  - 选 2-3 个普通 event 和 1 个 `filtering_only` event。
  - 验证普通 event 可导入，`filtering_only` event 只归档不进入正式 matches。
  - 检查 `import_matches.json` 中 unmatched/same-name unresolved 项。

## Assumptions

- “全量历史”定义为 `results.ittf.link/index.php/events` 当前可返回的全部 events。
- `filtering_only` 数据本次只抓取归档，不默认进入正式统计表。
- profile search candidate cache 默认永不过期，只手动或异常触发刷新。
- 新增 profile 全部入库；只有历史最佳排名进过前 50 的新增球员补中文翻译。
- 修改任何代码或配置前，执行者需要先说明修改内容和原因，并等待明确确认。
