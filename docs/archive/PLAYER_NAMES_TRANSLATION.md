# 乒乓球运动员名字 LLM 翻译

## 概述

`translate_player_names.py` 是一个基于 LLM 的运动员名字翻译脚本，可以将英文的乒乓球运动员名字翻译成遵循官方规范的中文译名。

## 特点

- ✅ 支持多个 LLM 提供商（MiniMax、Kimi、Qwen、GLM、DeepSeek）
- ✅ 自动批处理，防止单次请求过大
- ✅ 遵循 ITTF 官方的中文人名译名规范
- ✅ 支持断点续传（`--start` 和 `--end` 参数）
- ✅ 实时进度显示和统计

## 使用方式

### 基础用法

```bash
cd scripts
python translate_player_names.py
```

这将：
1. 读取 `tmp/update_players.txt`
2. 使用默认的 MiniMax API 翻译
3. 输出到 `tmp/update_players_translated.txt`

### 指定 LLM 提供商

```bash
# 使用 Kimi (Moonshot AI)
python translate_player_names.py --provider kimi --model kimi-k2.5

# 使用通义千问
python translate_player_names.py --provider qwen --model qwen3.5-plus

# 使用 GLM
python translate_player_names.py --provider glm --model glm-5

# 使用 DeepSeek
python translate_player_names.py --provider deepseek --model deepseek-v3.2
```

### 指定输入/输出文件

```bash
python translate_player_names.py \
  --input /path/to/names.txt \
  --output /path/to/output.txt
```

### 翻译特定范围

```bash
# 翻译第 100-200 行
python translate_player_names.py --start 100 --end 200

# 翻译从第 500 行开始的所有内容
python translate_player_names.py --start 500
```

### 指定 API Key

```bash
# 如果 API Key 不在环境变量中
python translate_player_names.py \
  --provider kimi \
  --api-key "your-api-key-here"
```

## 环境配置

确保在 `.env` 文件中配置了相应的 API Key：

```env
# MiniMax
MINIMAX_API_KEY=your-minimax-key

# Kimi
KIMI_API_KEY=your-kimi-key

# Qwen
DASHSCOPE_API_KEY=your-qwen-key

# GLM
ZHIPU_API_KEY=your-glm-key

# DeepSeek
DEEPSEEK_API_KEY=your-deepseek-key
```

## 输出格式

输出文件中每行的格式为：
```
英文名:中文名:players
```

例如：
```
Ma Long:马龙:players
Fan Zhendong:樊振东:players
ABARAVICIUTE Laura:阿巴拉维丘特·劳拉:players
```

## 翻译规则

LLM 在翻译时遵循以下规则：

1. **参考 ITTF 官方的中文人名译名**
   - 对于知名运动员，使用其官方通用的中文译名
   - 例如："Ma Long" → "马龙"（而不是"马·隆"）

2. **中文姓名格式**
   - 一般采用 "姓 名" 的格式
   - 中文名置于后面

3. **欧洲名字处理**
   - 保持传统的音译方式
   - 例如："Laura" → "劳拉"

4. **亚洲名字处理**
   - 按照该国家或地区的官方翻译标准
   - 日文名字使用日语音读
   - 韩文名字使用韩语标准音

5. **多语言兼容**
   - 葡萄牙语、西班牙语、法语等使用标准的中文音译

## 常见 API 提供商选择

| 提供商 | 模型 | 优点 | 成本 |
|--------|------|------|------|
| MiniMax | MiniMax-M2.7 | 默认配置，速度快 | 较低 |
| Kimi | kimi-k2.5 | 上下文窗口大，理解好 | 中等 |
| Qwen | qwen3.5-plus | 多语言支持好，速度快 | 较低 |
| GLM | glm-5 | 国产模型，稳定 | 中等 |
| DeepSeek | deepseek-v3.2 | 性价比高，能力强 | 较低 |

## Token 消耗

脚本会在运行时输出 token 消耗情况：
```
[INFO] Token 累计 [minimax MiniMax-M2.7]: prompt=1234, completion=567, total=1801
```

## 故障排除

### API 连接失败

```
[ERROR] API 调用失败 [minimax MiniMax-M2.7]: ...
```

检查：
1. API Key 是否正确配置在 `.env` 中
2. 网络连接是否正常
3. API 服务是否可用

### 输出为空或保持原名

这种情况是正常的，表示：
- LLM 可能没有返回有效的翻译
- 或者某些名字本身就应该保持英文（如某些特殊情况）

## 脚本架构

脚本基于 `lib.translator.LLMTranslator`，支持：
- 自动批处理（按提供商的限制拆分批次）
- 错误重试机制
- 进度回调
- 多提供商支持

## 相关文件

- `scripts/lib/translator.py` - LLM 翻译核心模块
- `scripts/translate_player_names.py` - 人名翻译脚本
- `tmp/update_players.txt` - 输入：原始英文人名列表
- `tmp/update_players_translated.txt` - 输出：翻译后的人名列表
