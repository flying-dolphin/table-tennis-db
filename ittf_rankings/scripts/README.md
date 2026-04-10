# ITTF scripts

当前脚本已经开始按“共享 Playwright 基础设施 + 独立业务抓取器”重构。

## 推荐入口

### 1. 比赛抓取

```bash
python scrape_matches.py
```

- 主力脚本
- 基于 Playwright
- 支持手动登录、session 复用、风控检测、断点续抓、增量保存

兼容入口仍保留：

```bash
python ittf_matches_playwright.py
```

它现在只是转调到 `scrape_matches.py`。

### 2. 排名抓取

```bash
python scrape_rankings.py --category women --top 50
```

- 基于 Playwright
- 当前可抓取公开 ranking 页面并输出结构化 JSON
- 同时保存 HTML snapshot，方便调试解析

支持类别：
- `women`
- `men`
- `women_doubles`
- `men_doubles`
- `mixed`

### 3. 规则文件抓取

```bash
python scrape_regulations.py
```

当前流程：
- 默认优先用 requests 发现 PDF 链接
- 静态发现失败时 fallback 到 Playwright
- 下载最新 PDF
- 提取 PDF 文本为 Markdown
- 生成中文翻译 prompt 文件
- 输出处理结果 JSON

可选参数示例：

```bash
python scrape_regulations.py --skip-download
python scrape_regulations.py --skip-extract
python scrape_regulations.py --skip-translate-prompt
```

## 共享模块

位于 `scripts/lib/`：

- `anti_bot.py`：风控检测、拟人化操作、延迟控制
- `browser_session.py`：登录态复用与 session 初始化
- `page_ops.py`：安全 goto / 翻页等 page 操作封装
- `checkpoint.py`：断点续抓
- `capture.py`：JSON 保存、原始响应抓取、文件名清洗

## 旧脚本状态

以下脚本已不再是推荐入口，建议视作历史版本或过渡文件：

- `ittf_matches_playwright.py`：兼容入口
- `ittf_rankings_updater.py`：旧规则文档更新脚本
- `ittf_process.py`：已有排名 JSON 的处理/展示脚本

更早期的实验性脚本已放到 `scripts/archive/`。

## 下一步建议

- 继续增强 `scrape_matches.py` 的可复用程度
- 统一 ranking / matches / regulations 的 schema
- 再决定是否让旧 `ittf_rankings_updater.py` 完全退役
