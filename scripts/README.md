# ITTF Scripts

本文档是 `scripts/` 目录的统一说明，按当前代码行为维护。

## 运行前提

- Python 3.10+
- 安装依赖：`pip install -r requirements.txt`
- 在仓库根目录配置 `.env`（如需 API 翻译，提供 `MINIMAX_API_KEY`）

以下命令默认在仓库根目录执行；若在 `scripts/` 目录执行，请去掉 `scripts/` 前缀。

## 翻译系统（当前标准）

- 词典只使用 V2：`scripts/data/translation_dict_v2.json`
- 不再支持旧词典：`translation_dict.json`
- 分类固定为：`players / terms / events / locations / others`
- `locations` 未命中时会回退 `others`（例如 `TBD -> 待定`）

### 词典校验

```bash
python scripts/validate_translation_dict.py --input scripts/data/translation_dict_v2.json
```

通过标准：
- `errors: 0`
- `warnings: 0`

### 翻译结果校验（events_calendar）

```bash
python scripts/validate_events_translation.py --translated data/events_calendar/events_calendar_2026_cn.json
```

严格对照原始文件：

```bash
python scripts/validate_events_translation.py --translated data/events_calendar/events_calendar_2026_cn.json --raw data/events_calendar/events_calendar_2026.json
```

## Events Calendar 流程

### 1) 抓取（可选内置翻译）

```bash
python scripts/scrape_events_calendar.py --year 2026
```

常用参数：
- `--apply`：执行实际翻译（默认 dry-run 仅词典）
- `--skip-translate`：只抓取，不翻译
- `--force`：忽略 checkpoint 重新抓取

checkpoint 已拆分：
- `data/events_calendar/checkpoint_scrape_{year}.json`
- `data/events_calendar/checkpoint_translate_{year}.json`

### 2) 独立翻译（推荐）

```bash
python scripts/translate_events_calendar.py --year 2026
```

常用参数：
- `--force`：从头翻译
- `--no-resume`：禁用断点续跑
- `--batch-size 10`：设置批量大小

说明：
- 成功定义是“全部事件翻译成功”。
- 若存在未翻译项，脚本会返回非 0，并保留已翻译结果。
- 输出文件会记录 `progress` 和 `source_hash` 以支持续跑一致性检查。

## Matches 抓取与翻译

抓取比赛数据：

```bash
python scripts/scrape_matches.py
```

常用参数：
- `--player-name "DOO Hoi Kem"`：只抓单个球员
- `--cdp-port 9222`：复用已启动浏览器
- `--init-session`：初始化登录态
- `--no-translate`：只抓英文，不做翻译

翻译比赛文件：

```bash
python scripts/translate_matches.py --file data/matches_complete/xxx.json
```

## Rankings 抓取

从 https://www.ittf.com/rankings/ 抓取 Women's Singles 排名 + points breakdown：

```bash
python scripts/run_rankings.py --top 100 --headless
```

常用参数：
- `--top N`：抓取前 N 名（默认 100）
- `--force`：忽略 checkpoint 重新抓取
- `--output-dir`：输出目录（默认 `data/rankings/orig`）

输出：`data/rankings/orig/women_singles_top{N}_week{W}.json`

## Player Profiles 抓取

从 results.ittf.link 抓取运动员详情档案：

```bash
python scripts/run_profiles.py --category women --top 50 --headless
```

输出：
- `data/player_profiles/orig/` — 原始档案
- `data/player_profiles/cn/` — 中文翻译版
- `data/player_avatars/` — 头像

## Rankings 翻译

翻译排名文件：

```bash
python scripts/translate_rankings.py --file data/rankings/orig/women_singles_top100_week16.json
```

## Regulations（规则文档）

入口脚本：

```bash
python scripts/regulations_manager.py
```

常用参数：
- `--force`
- `--translate`
- `--api --api-key YOUR_KEY`
- `--daemon`

底层抓取模块：

```bash
python scripts/scrape_regulations.py
```

## 翻译模块示例

```bash
python scripts/translate_example.py --basic
python scripts/translate_example.py --batch-test
python scripts/translate_example.py --api-key YOUR_KEY
```
