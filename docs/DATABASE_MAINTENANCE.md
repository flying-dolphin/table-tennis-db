# 数据库使用与维护

## 部署

```bash
# 1. 建表
mysql -u root -p ittf < scripts/db/create_event_category_tables.sql

# 2. 导入数据
mysql -u root -p ittf < scripts/db/import_event_categories_data.sql
```

验证：

```sql
SELECT COUNT(*) FROM event_categories;        -- 预期 46
SELECT COUNT(*) FROM event_type_mapping;      -- 预期 46
SELECT * FROM v_points_eligible_events LIMIT 5;
```

---

## 常用查询

### 根据 event_type/event_kind 查分类

```sql
SELECT category_name_zh, json_code, points_tier
FROM v_event_type_category_mapping
WHERE event_type = 'WTT Grand Smash'
  AND is_active = TRUE;
```

### 查所有参与积分的赛事

```sql
SELECT category_id, category_name_zh, points_tier, json_code
FROM v_points_eligible_events;
```

### 查某赛事的积分规则

```sql
SELECT format_type, w_points, f_points, sf_points, qf_points
FROM points_rules_by_category
WHERE category_id = (
    SELECT id FROM event_categories WHERE category_id = 'WTT_GRAND_SMASH'
);
```

### 检查 event_type 覆盖情况

```sql
-- 查看所有活跃映射
SELECT event_type, event_kind, category_name_zh
FROM v_event_type_category_mapping
WHERE is_active = TRUE
ORDER BY event_type;
```

---

## 数据更新

### 修改中文名称

```sql
UPDATE event_categories
SET category_name_zh = '新名称'
WHERE category_id = 'WTT_GRAND_SMASH';
```

**注意**：同时更新 `scripts/data/translation_dict_v2.json` 和 `data/event_category_mapping.json`，保持三处同步。

### 新增赛事分类

1. 在 `data/event_category_mapping.json` 中添加新条目
2. 在 `scripts/data/translation_dict_v2.json` 中添加翻译
3. 重新生成 SQL：
   ```bash
   python scripts/db/import_event_categories.py
   ```
4. 导入：
   ```bash
   mysql -u root -p ittf < scripts/db/import_event_categories_data.sql
   ```

### 新增积分规则

```sql
INSERT INTO points_rules_by_category
  (category_id, format_type, w_points, f_points, sf_points, qf_points, r16_points)
VALUES (
    (SELECT id FROM event_categories WHERE category_id = 'WTT_GRAND_SMASH'),
    'Singles', 2000, 1400, 900, 580, 380
);
```

### 停用过期映射

```sql
UPDATE event_type_mapping
SET is_active = FALSE
WHERE event_type = 'Old Event Type';
```

---

## 备份与恢复

```bash
# 备份
mysqldump -u root -p --single-transaction ittf > backup_$(date +%Y%m%d).sql

# 恢复
mysql -u root -p ittf < backup_20260416.sql
```

---

## 故障排除

**外键约束报错**（删除分类时）

```sql
-- 先查看哪些映射引用了该分类
SELECT * FROM event_type_mapping
WHERE category_id = (SELECT id FROM event_categories WHERE category_id = 'XXX');

-- 停用映射后再删除分类
UPDATE event_type_mapping SET is_active = FALSE WHERE ...;
```

**字符编码错误**

```sql
ALTER DATABASE ittf CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

**数据不一致检查**

```sql
-- 孤立映射（无对应分类）
SELECT * FROM event_type_mapping etm
WHERE NOT EXISTS (SELECT 1 FROM event_categories ec WHERE ec.id = etm.category_id);

-- 重复映射
SELECT event_type, event_kind, COUNT(*)
FROM event_type_mapping
GROUP BY event_type, event_kind
HAVING COUNT(*) > 1;
```
