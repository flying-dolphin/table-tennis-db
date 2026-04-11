# ITTF scripts

当前脚本已重构为“共享 Playwright 基础设施 + 独立业务抓取器”的结构，比赛抓取与排名抓取目前都已跑通，规则文件抓取链路也已具备下载、提取和翻译提示生成能力。

## 当前状态总结

### 已经稳定可用

#### 1. `scrape_matches.py`

当前主力脚本，负责比赛抓取。

能力：
- 基于 Playwright / 现有 Chrome CDP 会话抓取
- 支持断点续抓
- 支持增量写入
- 支持手动登录 / 复用已登录浏览器
- 已修复 autocomplete 真实站点 DOM 适配问题
- 已修复 CDP 首跳不必要的 sleep
- 已补齐更清晰的 match schema 顶层字段

当前已确认有效的关键点：
- autocomplete 真实下拉结构是：
  - `ul.dropdown-menu[role='menu']`
  - `li > a[data-value]`
- 候选项点击必须命中 `a[data-value]` 本身，不能只点外层 `li`
- CDP 连接后第一页导航应直接进行，不需要先 sleep

#### 2. `scrape_rankings.py`

负责公开 ranking 页面抓取。

能力：
- 直接抓公开 ranking 页面，不依赖登录
- 支持 `women / men / women_doubles / men_doubles / mixed`
- 输出结构化 JSON
- 保存 HTML snapshot 便于调试
- 已和现有 `women_singles_top50.json` 做过实际对比校验，核心字段对齐

#### 3. `regulations_manager.py`

规则文件管理入口脚本，负责完整的规则文件生命周期管理。

当前能力：
- 调用 `scrape_regulations` 模块获取最新规则 PDF
- 将 PDF 转换为 Markdown 格式
- 翻译成中文（支持 MiniMax API 或生成翻译提示文件）
- 状态管理，避免重复处理
- 支持守护进程模式，每3天自动检查更新

使用方法：
```bash
python regulations_manager.py              # 运行一次检查
python regulations_manager.py --force      # 强制重新处理
python regulations_manager.py --daemon     # 持续运行，每3天检查
python regulations_manager.py --translate  # 仅翻译已有PDF
python regulations_manager.py --api --api-key YOUR_KEY  # 使用API翻译
```

#### 4. `scrape_regulations.py`

规则文件抓取模块，提供底层抓取能力。

当前能力：
- 优先通过 requests 发现 PDF 链接
- 失败时 fallback 到 Playwright
- 下载最新 PDF
- 提供 `fetch_regulations()` 函数供外部调用

当前限制：
- ITTF 规则入口仍可能受 403 / Cloudflare 影响
- 因此这条线在真实站点上仍可能需要半自动辅助

通常不直接调用，而是通过 `regulations_manager.py` 使用。

---

## 推荐入口

### 比赛抓取

```bash
python scrape_matches.py
```

常见场景：

```bash
# 使用默认 players 文件抓取
python scrape_matches.py

# 仅抓某一个球员
python scrape_matches.py --player-name "DOO Hoi Kem"

# 复用已开启的 Chrome CDP
python scrape_matches.py --cdp-port 9222 --player-name "DOO Hoi Kem"

# 初始化 session（手动登录一次）
python scrape_matches.py --init-session
```

兼容入口仍保留：

```bash
python ittf_matches_playwright.py
```

它现在只是转调到 `scrape_matches.py`。

### 排名抓取

```bash
python scrape_rankings.py --category women --top 50
```

### 规则文件管理

完整生命周期管理（推荐）：

```bash
python regulations_manager.py
```

可选参数示例：

```bash
# 强制重新处理
python regulations_manager.py --force

# 仅翻译已有PDF
python regulations_manager.py --translate

# 使用 MiniMax API 翻译
python regulations_manager.py --api --api-key YOUR_KEY

# 显示浏览器窗口（调试用）
python regulations_manager.py --no-headless

# 守护进程模式
python regulations_manager.py --daemon
```

底层抓取模块（通常不直接使用）：

```bash
python scrape_regulations.py
```

---

## 共享模块

位于 `scripts/lib/`：

- `anti_bot.py`：风控检测、拟人化操作、延迟控制
- `browser_session.py`：登录态复用与 session 初始化
- `page_ops.py`：安全 goto / 翻页等 page 操作封装
- `checkpoint.py`：断点续抓
- `capture.py`：JSON 保存、原始响应抓取、文件名清洗
- `translator.py`：**通用翻译模块**（人名、术语、赛事、文档翻译）

### 翻译模块 (`lib/translator.py`)

功能：
- 维护中英文词典（`data/translation_dict.json`）
- 优先查词典，未命中则调用 LLM API 翻译
- 自动将新翻译结果保存到词典
- 支持批量翻译和缓存
- 默认使用 MiniMax API

#### 使用示例

```python
from lib.translator import Translator

# 初始化翻译器
translator = Translator(api_key="your_key")

# 翻译运动员名（优先查词典）
cn_name = translator.translate("Ma Long", category="players")
# 输出: 马龙

# 翻译赛事名
event_name = translator.translate("Grand Smash", category="events")
# 输出: 大满贯

# 翻译术语
term = translator.translate("Round of 16", category="terms")
# 输出: 十六强

# 批量翻译
results = translator.translate_batch(
    ["Ma Long", "Fan Zhendong", "Sun Yingsha"], 
    category="players"
)

# 翻译完整文档
translated_doc = translator.translate_document(content, doc_type="regulations")
```

#### 词典文件 (`data/translation_dict.json`)

词典分类：
- `players`: 运动员人名（已预置30+常见球员）
- `terms`: 通用术语（积分、轮次、赛制等）
- `events`: 赛事名称（世锦赛、大满贯、WTT系列等）
- `countries`: 国家/地区代码和名称
- `others`: 其他词汇

#### 运行示例脚本

```bash
# 基础翻译演示（仅使用词典）
python translate_example.py --basic

# 完整演示（包括API翻译，需要API Key）
python translate_example.py --api-key YOUR_KEY

# 批量翻译测试
python translate_example.py --batch-test
```

#### 词典统计

```python
translator = Translator()
stats = translator.get_stats()
print(stats)
# {'total': 91, 'players': 30, 'terms': 29, 'events': 10, 'countries': 22, 'others': 0}
```

---

## 关键经验 / 已踩坑记录

### 1. 不要把 autocomplete 候选项扫成全页 `li`

真实站点里会先扫到导航菜单，比如：
- HOME
- MATCHES
- PROFILES
- RANKINGS

这会导致“看起来找到候选项，实际上命中的是菜单”。

### 2. 真实候选项必须命中 `a[data-value]`

真实 DOM 示例：

```html
<ul role="menu" class="dropdown-menu">
  <li><a href="#" data-value="115543">DOO Hoi Kem (HKG)</a></li>
</ul>
```

只有点到这个 anchor 本身，站点才会把球员真正选中。

### 3. CDP 首跳不要先 sleep

CDP 刚连接后，如果先 sleep：
- 页面会保持空白
- 一旦后续逻辑提前退出，会显得像“什么都没做就报错”

正确做法：
- CDP 连上后直接导航第一页
- 后续交互再保留 human-like delay

### 4. `click ok` 不等于站点真的选中了

Playwright 报 click 成功，只说明动作发出去了。
还要结合：
- 输入框 value 是否变化
- dropdown 是否消失
- 页面是否进入下一状态

---

## 旧脚本状态

以下脚本已不再是推荐入口，建议视作历史版本或过渡文件：

- `ittf_matches_playwright.py`：兼容入口
- `ittf_rankings_updater.py`：**旧规则文档更新脚本，已被 `regulations_manager.py` 替代**
- `ittf_process.py`：已有排名 JSON 的处理/展示脚本

更早期的实验性脚本已放到 `scripts/archive/`。

### 迁移说明

如果你之前使用 `ittf_rankings_updater.py`：
- 原有功能已迁移到 `regulations_manager.py`
- 命令行参数基本保持一致
- 新增 `--api` 参数支持直接调用 MiniMax API 翻译
- 状态文件改为 `.regulations_manager_state.json`

---

## Schema 对齐说明

当前三条数据线已经开始往统一 schema 收口。

### `scrape_rankings.py`
已产出：
- `category_key`
- `player_id`
- `profile_url`

### `scrape_matches.py`
当前顶层已补齐：
- `schema_version`
- `player_id`
- `player_name`
- `english_name`
- `country`
- `country_code`
- `continent`
- `rank`
- `from_date`

match row 当前已较统一：
- `result_for_player`
- `result`
- `games`
- `games_display`

### `scrape_regulations.py`
产出：
- `source_url`
- `discovery_method`
- `pdf_links`
- `latest_pdf`
- `downloaded_to`
- `pdf_hash`
- `markdown_path`
- `translation_prompt_path`

示例见：
- `data/regulations_schema.example.json`

web 导入层已经开始兼容这些扩展字段。

---

## 下一步建议

- 继续观察 `scrape_matches.py` 在更多球员上的稳定性
- 视需要降低 autocomplete 相关诊断日志级别
- 在 web 侧决定是否正式引入 regulations 数据表
- 再决定是否让旧 `ittf_rankings_updater.py` 完全退役
