# Mapping 修复总结（已完成）

## 问题分析

### 1. Continental 和 Regional 赛事不完整（已验证）

#### Continental 有 5 种 kind，目前的映射：
- ✓ Senior Championships → CONTINENTAL_CHAMPS
- ✓ Senior Cup → CONTINENTAL_CUP
- ✓ U21 Championships → U21_CONTINENTAL_CHAMPS
- ✓ Youth Championships → YOUTH_CONTINENTAL_CHAMPS
- ✓ Youth Cup → YOUTH_CONTINENTAL_CUP

#### Regional 有 3 种 kind，目前的映射：
- ✓ Senior Championships → REGIONAL_CHAMPS
- ✓ Senior Cup → REGIONAL_CUP
- ✓ Youth Championships → REGIONAL_YOUTH_CHAMPS
- ❌ **缺失**: U21 Championships → 需要新增 REGIONAL_U21_CHAMPS

### 2. ITTF World Junior Circuit 需要分离

当前原始数据中有多种 kind：
- `--` (主赛事)
- `Finals` (总决赛)
- `Golden` (黄金系列)
- `Premium` (高级系列)

当前 mapping 未分离，需要分为：
- ITTF_WORLD_JUNIOR_CIRCUIT (主赛)
- ITTF_WORLD_JUNIOR_CIRCUIT_FINALS (总决赛) — 已有
- ITTF_WORLD_JUNIOR_CIRCUIT_PREMIUM (高级) — 已有
- ITTF_WORLD_JUNIOR_CIRCUIT_GOLDEN (黄金) — 已有

### 3. WTT Youth 系列已正确分离 ✓

- WTT Youth Grand Smash
- WTT Youth Star Contender
- WTT Youth Contender

## 修复方案

需要修改 `data/event_category_mapping.json`：

### 新增分类：REGIONAL_U21_CHAMPS

```json
{
  "category_id": "REGIONAL_U21_CHAMPS",
  "category_name": "Regional U21 Championships",
  "category_name_zh": "U21地区锦标赛",
  "event_type": "Regional",
  "event_kind": "U21 Championships",
  "ittf_rule_name": "U21 Regional Championships",
  "json_code": null,
  "points_tier": "Low",
  "points_eligible": true,
  "filtering_only": false,
  "applicable_formats": ["Singles", "Doubles", "Mixed Doubles"]
}
```

插入位置：在 REGIONAL_YOUTH_CHAMPS 之前（保持 Regional 系列聚在一起）

## 修复状态：✅ 已完成

### 修改的文件
1. `data/event_category_mapping.json` - 新增 REGIONAL_U21_CHAMPS
2. `scripts/data/translation_dict_v2.json` - 新增词条 u21 regional championships
3. `data/db/ittf.db` - SQLite 数据库已自动导入更新

### 验证结果

✅ **Continental: 6 个分类**
- CONTINENTAL_CHAMPS (Senior Championships)
- CONTINENTAL_CUP (Senior Cup)
- CONTINENTAL_GAMES
- U21_CONTINENTAL_CHAMPS (U21 Championships)
- YOUTH_CONTINENTAL_CHAMPS (Youth Championships)
- YOUTH_CONTINENTAL_CUP (Youth Cup)

✅ **Regional: 4 个分类**
- REGIONAL_CHAMPS (Senior Championships)
- REGIONAL_CUP (Senior Cup)
- REGIONAL_U21_CHAMPS (U21 Championships) ← 新增
- REGIONAL_YOUTH_CHAMPS (Youth Championships)

✅ **ITTF World Junior Circuit: 4 个分类**
- ITTF_WORLD_JUNIOR_CIRCUIT (主赛事)
- ITTF_WORLD_JUNIOR_CIRCUIT_FINALS (总决赛)
- ITTF_WORLD_JUNIOR_CIRCUIT_PREMIUM (高级)
- ITTF_WORLD_JUNIOR_CIRCUIT_GOLDEN (黄金)

### 导入统计
- 总分类数：46
- 总映射数：47（因为 ITTF_WTTC 有 aliases）
