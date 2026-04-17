-- ============================================================================
-- ITTF Event Category Mapping Tables
-- Created: 2026-04-16
-- Purpose: Unified event type classification system
-- ============================================================================

-- 1. Event Categories (标准事件分类表)
-- 存储标准化的赛事分类及其元数据
CREATE TABLE IF NOT EXISTS event_categories (
    id INT PRIMARY KEY AUTO_INCREMENT,
    category_id VARCHAR(50) NOT NULL UNIQUE COMMENT '唯一标识符，如 WTT_GRAND_SMASH',
    category_name VARCHAR(100) NOT NULL COMMENT '英文名称',
    category_name_zh VARCHAR(100) NOT NULL COMMENT '中文名称',
    json_code VARCHAR(20) COMMENT 'JSON展示代码，如 GS',
    points_tier ENUM('Premium', 'High', 'Medium', 'Low', 'None') DEFAULT 'None' COMMENT '积分等级',
    points_eligible BOOLEAN DEFAULT FALSE COMMENT '是否参与积分计算',
    filtering_only BOOLEAN DEFAULT FALSE COMMENT '是否仅用于过滤',
    applicable_formats JSON COMMENT '适用的比赛格式数组，如 ["Singles", "Doubles"]',
    ittf_rule_name VARCHAR(255) COMMENT '在ITTF规则中的正式名称',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_category_id (category_id),
    INDEX idx_points_eligible (points_eligible),
    INDEX idx_filtering_only (filtering_only),
    INDEX idx_points_tier (points_tier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='标准化的赛事分类表';

-- 2. Event Type Mapping (事件类型映射表)
-- 将 event_list 中的 event_type + event_kind 映射到标准分类
CREATE TABLE IF NOT EXISTS event_type_mapping (
    id INT PRIMARY KEY AUTO_INCREMENT,
    event_type VARCHAR(100) NOT NULL COMMENT '来自event_list的event_type字段',
    event_kind VARCHAR(100) COMMENT '来自event_list的event_kind字段',
    category_id INT NOT NULL COMMENT '对应的标准分类ID',
    priority INT DEFAULT 0 COMMENT '优先级，用于同一event_type有多个event_kind的情况',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用此映射',
    notes TEXT COMMENT '备注',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES event_categories(id) ON DELETE RESTRICT,
    UNIQUE KEY uk_event_type_kind (event_type, event_kind),
    INDEX idx_category_id (category_id),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='event_type/event_kind与标准分类的映射';

-- 3. Points Rules (积分规则表，行式存储)
-- 每个赛事分类 + 子分类 + 阶段 + 名次对应一条积分记录
CREATE TABLE IF NOT EXISTS points_rules (
    rule_id INT PRIMARY KEY AUTO_INCREMENT,
    category_id INT NOT NULL COMMENT '赛事分类ID（FK -> event_categories.id）',
    sub_event_category VARCHAR(50) NOT NULL COMMENT '子分类，如 Q48/Q64/Singles',
    draw_qualifier VARCHAR(50) NULL COMMENT '签表类型，如 Main Draw / Qualification',
    stage_type VARCHAR(50) NOT NULL COMMENT '阶段类型，如 Main Draw / Qualification',
    position VARCHAR(20) NOT NULL COMMENT '名次，如 W/F/SF/QF/R16/QUAL/R1',
    points INT NOT NULL COMMENT '积分值',
    effective_date DATE NOT NULL COMMENT '生效日期',
    notes TEXT COMMENT '备注',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES event_categories(id) ON DELETE RESTRICT,
    UNIQUE KEY uk_points_rule (category_id, sub_event_category, draw_qualifier, stage_type, position, effective_date),
    INDEX idx_points_rules_category (category_id),
    INDEX idx_points_rules_lookup (category_id, sub_event_category, stage_type, position, effective_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='积分规则（行式存储）';

-- ============================================================================
-- Views for easier querying
-- ============================================================================

-- 获取完整的映射信息
CREATE OR REPLACE VIEW v_event_type_category_mapping AS
SELECT
    etm.event_type,
    etm.event_kind,
    ec.category_id,
    ec.category_name,
    ec.category_name_zh,
    ec.json_code,
    ec.points_tier,
    ec.points_eligible,
    ec.filtering_only,
    ec.ittf_rule_name,
    etm.priority,
    etm.is_active
FROM event_type_mapping etm
JOIN event_categories ec ON etm.category_id = ec.id
ORDER BY etm.event_type, etm.event_kind, etm.priority DESC;

-- 获取积分相关的赛事分类
CREATE OR REPLACE VIEW v_points_eligible_events AS
SELECT
    ec.id,
    ec.category_id,
    ec.category_name,
    ec.category_name_zh,
    ec.points_tier,
    ec.ittf_rule_name
FROM event_categories ec
WHERE ec.points_eligible = TRUE
ORDER BY
    FIELD(ec.points_tier, 'Premium', 'High', 'Medium', 'Low'),
    ec.category_name;

-- ============================================================================
-- Insert initial data from mapping
-- ============================================================================

-- 插入标准分类数据
INSERT INTO event_categories (
    category_id, category_name, category_name_zh, json_code,
    points_tier, points_eligible, filtering_only, ittf_rule_name
) VALUES
('WTT_GRAND_SMASH', 'WTT Grand Smash', 'WTT大满贯', 'GS', 'Premium', TRUE, FALSE, 'WTT Grand Smash'),
('ITTF_WTTC', 'ITTF World Table Tennis Championships Finals', '国际乒联世界乒乓球锦标赛', 'WTTC', 'Premium', TRUE, FALSE, 'ITTF World Table Tennis Championships Finals'),
('ITTF_WORLD_CUP', 'ITTF World Cup', '国际乒联世界杯', 'WC', 'Premium', TRUE, FALSE, 'ITTF World Cup'),
('WTT_FINALS', 'WTT Finals', 'WTT总决赛', 'CF', 'Premium', TRUE, FALSE, 'WTT Finals'),
('WTT_CHAMPIONS', 'WTT Champions', 'WTT冠军赛', 'CHAMP', 'High', TRUE, FALSE, 'WTT Champions'),
('WTT_STAR_CONTENDER', 'WTT Star Contender', 'WTT球星挑战赛', 'SCT', 'Medium', TRUE, FALSE, 'WTT Star Contender'),
('WTT_CONTENDER', 'WTT Contender', 'WTT挑战赛', 'CS', 'Medium', TRUE, FALSE, 'WTT Contender'),
('WTT_FEEDER', 'WTT Feeder', 'WTT支线赛', 'FEED', 'Low', TRUE, FALSE, 'WTT Feeder'),
('CONTINENTAL_CUP', 'Continental Cup', '洲际杯', 'CCUP', 'Medium', TRUE, FALSE, 'Continental Cups'),
('CONTINENTAL_CHAMPS', 'Continental Championships', '洲际锦标赛', 'CC', 'Medium', TRUE, FALSE, 'Continental Championships'),
('CONTINENTAL_GAMES', 'Continental Games', '洲际运动会', 'CT', 'Medium', TRUE, FALSE, 'Continental Games'),
('OLYMPIC_GAMES', 'Olympic Games', '奥运会', 'OLY', 'Premium', TRUE, FALSE, 'Olympic Games'),
('OLYMPIC_QUALIFICATION', 'Olympic Qualification', '奥运资格赛', NULL, 'None', FALSE, TRUE, NULL),
('MULTI_SPORT_GAMES', 'Multi-Sport Games', '综合运动会', 'MULTI', 'Low', TRUE, FALSE, 'Multi-Sport Games'),
('ITTF_WORLD_TEAM_CHAMPS', 'ITTF World Team Table Tennis Championships', '国际乒联世界乒乓球团体锦标赛', NULL, 'Premium', TRUE, FALSE, 'ITTF World Team Table Tennis Championships'),
('ITTF_MIXED_TEAM_WORLD_CUP', 'ITTF Mixed Team World Cup', '国际乒联混合团体世界杯', NULL, 'Premium', TRUE, FALSE, 'ITTF Mixed Team World Cup'),
('YOUTH_GRAND_SMASH', 'U19 WTT Youth Grand Smash', 'U19 WTT青年大满贯', 'YGS', 'Low', TRUE, FALSE, 'U19 WTT Youth Grand Smash'),
('YOUTH_STAR_CONTENDER', 'U19 WTT Youth Star Contender', 'U19 WTT青年明星挑战赛', 'YSC', 'Low', TRUE, FALSE, 'U19 WTT Youth Star Contender'),
('YOUTH_CONTENDER', 'U19 WTT Youth Contender', 'U19 WTT青年挑战赛', 'YC', 'Low', TRUE, FALSE, 'U19 WTT Youth Contender'),
('YOUTH_WORLD_CHAMPS', 'U19 ITTF World Youth Table Tennis Championships', 'U19 国际乒联世界青年乒乓球锦标赛', 'YWC', 'Low', TRUE, FALSE, 'U19 ITTF World Youth Table Tennis Championships'),
('REGIONAL_CHAMPS', 'Regional Championships', '地区锦标赛', 'RCH', 'Low', TRUE, FALSE, 'Regional Championships'),
('REGIONAL_CUP', 'Regional Cup', '地区杯', 'RCUP', 'Low', FALSE, TRUE, NULL),
('U21_CONTINENTAL_CHAMPS', 'U21 Continental Championships', 'U21洲际锦标赛', 'U21CH', 'Low', TRUE, FALSE, 'U21 Continental Championships / Games'),
('YOUTH_CONTINENTAL_CHAMPS', 'Youth Continental Championships', '青年洲际锦标赛', NULL, 'None', FALSE, TRUE, NULL),
('YOUTH_CONTINENTAL_CUP', 'Youth Continental Cup', '青年洲际杯', NULL, 'None', FALSE, TRUE, NULL),
('REGIONAL_YOUTH_CHAMPS', 'Regional Youth Championships', '地区青年锦标赛', NULL, 'None', FALSE, TRUE, NULL),
('ITTF_CHALLENGE', 'ITTF Challenge', '国际乒联挑战赛', NULL, 'None', FALSE, TRUE, NULL),
('ITTF_CHALLENGE_SERIES', 'ITTF Challenge Series', '国际乒联挑战赛系列', NULL, 'None', FALSE, TRUE, NULL),
('ITTF_CHALLENGE_PLUS', 'ITTF Challenge Plus', '国际乒联挑战赛+', NULL, 'None', FALSE, TRUE, NULL),
('ITTF_WORLD_JUNIOR_CIRCUIT', 'ITTF World Junior Circuit', '国际乒联世界少年巡回赛', NULL, 'None', FALSE, TRUE, NULL),
('ITTF_WORLD_JUNIOR_CIRCUIT_FINALS', 'ITTF World Junior Circuit Finals', '国际乒联世界少年巡回赛总决赛', NULL, 'None', FALSE, TRUE, NULL),
('ITTF_WORLD_JUNIOR_CIRCUIT_PREMIUM', 'ITTF World Junior Circuit Premium', '国际乒联世界少年巡回赛高级', NULL, 'None', FALSE, TRUE, NULL),
('ITTF_WORLD_JUNIOR_CIRCUIT_GOLDEN', 'ITTF World Junior Circuit Golden', '国际乒联世界少年巡回赛黄金', NULL, 'None', FALSE, TRUE, NULL),
('ITTF_WORLD_CADET_CHALLENGE', 'ITTF World Cadet Challenge', '国际乒联世界儿童挑战赛', NULL, 'None', FALSE, TRUE, NULL),
('T2_DIAMOND', 'T2 Diamond', 'T2钻石赛', NULL, 'None', FALSE, TRUE, NULL),
('YOUTH_OLYMPIC_GAMES', 'Youth Olympic Games', '青年奥运会', 'YOG', 'None', FALSE, TRUE, NULL),
('YOUTH_OLYMPIC_GAMES_QUALIFICATION', 'Youth Olympic Games Qualification', '青年奥运会资格赛', NULL, 'None', FALSE, TRUE, NULL),
('WORLD_TOUR_PRO_TOUR', 'ITTF World Tour / Pro Tour', '国际乒联世界巡回赛/专业巡回赛', NULL, 'None', FALSE, TRUE, NULL),
('WORLD_TOUR_CHALLENGE_SERIES', 'ITTF World Tour Challenge Series', '国际乒联世界巡回赛挑战赛系列', NULL, 'None', FALSE, TRUE, NULL),
('WORLD_TOUR_FINALS', 'ITTF World Tour Finals', '国际乒联世界巡回赛总决赛', NULL, 'None', FALSE, TRUE, NULL),
('WORLD_TOUR_GRAND_FINALS', 'ITTF World Tour Grand Finals', '国际乒联世界巡回赛大总决赛', NULL, 'None', FALSE, TRUE, NULL),
('WORLD_TOUR_MAJOR_SERIES', 'ITTF World Tour Major Series', '国际乒联世界巡回赛主赛系列', NULL, 'None', FALSE, TRUE, NULL),
('WORLD_TOUR_PLATINUM', 'ITTF World Tour Platinum', '国际乒联世界巡回赛铂金', NULL, 'None', FALSE, TRUE, NULL),
('WORLD_TOUR_SUPER_SERIES', 'ITTF World Tour Super Series', '国际乒联世界巡回赛超级系列', NULL, 'None', FALSE, TRUE, NULL),
('OTHER_EVENTS', 'Other Events', '其他赛事', NULL, 'None', FALSE, TRUE, NULL)
ON DUPLICATE KEY UPDATE
    category_name=VALUES(category_name),
    category_name_zh=VALUES(category_name_zh);

-- 插入映射关系（完整列表由 scripts/db/import_event_categories.py 生成）
-- ITTF WTTC 需要手动补充 aliases：两个 kind 均指向同一分类
INSERT INTO event_type_mapping (event_type, event_kind, category_id, priority)
SELECT t.event_type, t.event_kind, ec.id, t.priority
FROM (
    SELECT 'ITTF WTTC' AS event_type, '--'           AS event_kind, 'ITTF_WTTC' AS cat, 10 AS priority
    UNION ALL
    SELECT 'ITTF WTTC',              'WTTC Finals',                 'ITTF_WTTC',         10
) t
JOIN event_categories ec ON ec.category_id = t.cat
ON DUPLICATE KEY UPDATE priority = VALUES(priority);
