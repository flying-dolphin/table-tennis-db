# 翻译词典重构计划（translate-refactor）

更新时间：2026-04-13

## 1. 目标

- 解决词典结构混乱、重复词项和跨分类冲突问题。
- 让翻译任务可稳定断点续跑，避免“checkpoint 显示完成但输出不完整”。
- 建立可校验、可迁移、可回滚的词典治理流程。

## 2. 当前问题

- 词典按 `players/terms/events/locations/others` 分桶，存在同 key 多处维护，容易冲突。
- `others` 中混入大量国家码条目，造成语义漂移和重复。
- `metadata.total_entries` 曾与真实总量不一致。
- 翻译脚本中批量提示词和分类绑定不严格，曾污染 `locations`。
- 抓取与翻译 checkpoint 语义耦合，完整性判断不足。

## 3. 已完成（本次）

### 3.1 词典国家码去重合并

- 已将 `others` 中 77 个国家/地区代码词条迁移/归并到 `locations`。
- 迁移结果：
  - `locations`: 64 -> 86（新增 22）
  - `others`: 77 -> 0
  - 跨分类冲突：9 -> 0
- 已重算 `metadata.total_entries`，与分类求和一致。
- `TBD` 保留在 `others`（状态占位值，不属于国家/地区）。

### 3.2 止血改造

- `LLMTranslator` 批量翻译已按 `category` 生成专用 prompt。
- `locations` 增加输出校验，拦截赛事类污染翻译。
- `scrape_events_calendar.py` 地点翻译分类已从 `others` 改为 `locations`。

### 3.3 校验脚本落地

- 已新增 `scripts/validate_translation_dict.py`
  - 仅校验 V2 `entries` 结构
  - 当前 V2 词典已校验通过（errors=0, warnings=0）

## 4. 目标结构（V2）

建议从“分桶字典”升级为“主索引 + 分类标签”，避免同 key 多副本：

```json
{
  "metadata": {
    "version": "2.0",
    "updated_at": "ISO-8601",
    "total_entries": 0
  },
  "entries": {
    "normalized_key": {
      "original": "原文",
      "translated": "译文",
      "categories": ["locations"],
      "source": "dict|api|manual",
      "review_status": "pending|verified|rejected",
      "validators": {
        "locations": "location"
      },
      "updated_at": "ISO-8601"
    }
  }
}
```

运行时与仓库均只保留 V2 `entries` 结构，不再保留旧结构文件和迁移入口。

## 5. 落地约束

1. `TranslationDict.lookup/add/add_many` 只操作 V2 `entries`
2. `validators` 为唯一有效校验配置：
   - `locations`: 拒绝 `WTT/冠军赛/公开赛/挑战赛/锦标赛/乒联/联盟`
3. 删除运行时兼容层，只保留 V2 读写路径
4. 翻译入口统一使用分类白名单
5. 词典巡检脚本 `scripts/validate_translation_dict.py` 只校验 V2

## 6. 断点续跑改造计划

1. 拆分 checkpoint：
   - `checkpoint_scrape_{year}.json`
   - `checkpoint_translate_{year}.json`
2. 翻译完成判定统一为：
   - `processed_events == total_events == len(output.events)`
3. 恢复时增加一致性校验：
   - 输入文件哈希
   - 总条数
   - 已处理条数
4. 不一致时回滚到最后一个完整批次，而不是直接 `skip`。

## 7. 验收标准

- 词典不存在“跨分类同 key 不同译文”冲突。
- `locations` 不出现赛事/组织类词汇。
- `others` 不再承载国家码类词条。
- 中断恢复后可从下一批继续，且最终总量一致。
- 迁移后 `metadata.total_entries` 与真实总量一致。

## 8. 下一步执行顺序

1. 继续强化 `translate_events_calendar.py` 的 checkpoint 完整性校验。
2. 增加翻译结果校验脚本并接入流程。
