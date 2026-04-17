# 数据库设计

## 表结构

### event_categories（赛事分类）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK | 自增主键 |
| category_id | VARCHAR(50) UNIQUE | 唯一标识，如 `WTT_GRAND_SMASH` |
| category_name | VARCHAR(100) | 英文名称 |
| category_name_zh | VARCHAR(100) | 中文名称（与词典同步） |
| json_code | VARCHAR(20) | ranking JSON 中的缩写，如 `GS` |
| points_tier | ENUM | 积分等级：Premium / High / Medium / Low / None |
| points_eligible | BOOLEAN | 是否参与积分计算 |
| filtering_only | BOOLEAN | 是否仅用于过滤（历史赛事等） |
| applicable_formats | JSON | 适用格式：`["Singles","Doubles","Mixed Doubles"]` |
| ittf_rule_name | VARCHAR(255) | 在 ITTF 规则文档中的正式名称 |

---

### event_type_mapping（原始数据映射）

将 event_list 中的 `event_type` + `event_kind` 映射到标准分类。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK | 自增主键 |
| event_type | VARCHAR(100) | 原始 event_type 字段 |
| event_kind | VARCHAR(100) | 原始 event_kind 字段 |
| category_id | INT FK | → event_categories.id |
| priority | INT | 同一 event_type 多个 kind 时的优先级 |
| is_active | BOOLEAN | 历史映射设为 FALSE 而非删除 |

外键：`ON DELETE RESTRICT`（删除分类前须先清理映射）

---

### points_rules_by_category（积分规则）

每个分类在不同比赛格式下的积分值，来源于 [ITTF 规则文档](../ITTF-Ranking-Regulations-20260127.md)。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK | 自增主键 |
| category_id | INT FK | → event_categories.id |
| format_type | VARCHAR(50) | Singles / Doubles / Mixed Doubles / Teams |
| w_points | INT | 冠军 |
| f_points | INT | 亚军 |
| sf_points | INT | 四强 |
| qf_points | INT | 八强 |
| r16_points | INT | 16强 |
| r32_points | INT | 32强 |
| r64_points | INT | 64强 |
| r128_points | INT | 128强 |
| qual_points | INT | 资格赛晋级附加积分 |
| qual_4th/3rd/2nd/1st_points | INT | 资格赛小组各名次积分 |

外键：`ON DELETE CASCADE`（删除分类时自动删除对应积分规则）

唯一约束：`(category_id, format_type)`

---

## 视图

### v_event_type_category_mapping

```sql
event_type_mapping JOIN event_categories
```

常用查询：给定 `event_type` + `event_kind`，返回 `category_name_zh`、`json_code`、`points_tier` 等。

### v_points_eligible_events

```sql
SELECT * FROM event_categories WHERE points_eligible = TRUE
```

---

## 关系图

```
event_categories (1)
    ├── (N) event_type_mapping   [ON DELETE RESTRICT]
    └── (N) points_rules_by_category  [ON DELETE CASCADE]
```

---

## 数据来源

| 文件 | 用途 |
|------|------|
| `data/event_category_mapping.json` | 46 个分类的标准定义，category_name_zh 与词典同步 |
| `data/event_type_kind.txt` | 原始 event_type/event_kind 统计 |
| `docs/ITTF-Ranking-Regulations-20260127.md` | 积分规则原始文档 |
| `scripts/data/translation_dict_v2.json` | 中文翻译词典 |
| `scripts/db/create_event_category_tables.sql` | 建表 SQL |
| `scripts/db/import_event_categories_data.sql` | 数据导入 SQL（由 Python 脚本生成） |
| `scripts/db/import_event_categories.py` | 从 JSON 重新生成导入 SQL |

---

## points_tier 说明

| 等级 | 赛事 |
|------|------|
| Premium | WTT大满贯、奥运会、ITTF世锦赛决赛、ITTF世界杯、WTT总决赛、世界团体赛 |
| High | WTT冠军赛 |
| Medium | WTT球星挑战赛、WTT挑战赛、洲际锦标赛/杯/运动会 |
| Low | WTT支线赛、青年赛事、地区赛 |
| None | 历史赛事（ITTF Challenge/World Tour 等）、奥运资格赛 |
