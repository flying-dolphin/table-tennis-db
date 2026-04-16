-- ============================================================================
-- Event Categories Data Import
-- Generated: 2026-04-16T16:42:43.580363
-- Source: data/event_category_mapping.json
-- ============================================================================

-- Generated INSERT statements for event_categories
-- Generated at: 2026-04-16T16:42:43.580384

INSERT INTO event_categories (
    category_id, category_name, category_name_zh, json_code,
    points_tier, points_eligible, filtering_only, ittf_rule_name,
    applicable_formats
) VALUES
('WTT_GRAND_SMASH', 'WTT Grand Smash', 'WTT大满贯', 'GS', 'Premium', 1, 0, 'WTT Grand Smash', '["Singles", "Doubles", "Mixed Doubles"]'),
('ITTF_WTTC', 'ITTF World Table Tennis Championships Finals', '国际乒联世界乒乓球锦标赛', 'WTTC', 'Premium', 1, 0, 'ITTF World Table Tennis Championships Finals', '["Singles", "Doubles", "Mixed Doubles"]'),
('ITTF_WORLD_CUP', 'ITTF World Cup', '国际乒联世界杯', 'WC', 'Premium', 1, 0, 'ITTF World Cup', '["Singles"]'),
('WTT_FINALS', 'WTT Finals', 'WTT总决赛', 'CF', 'Premium', 1, 0, 'WTT Finals', '["Singles", "Mixed Doubles"]'),
('WTT_CHAMPIONS', 'WTT Champions', 'WTT冠军赛', 'CHAMP', 'High', 1, 0, 'WTT Champions', '["Singles", "Doubles", "Mixed Doubles"]'),
('WTT_STAR_CONTENDER', 'WTT Star Contender', 'WTT球星挑战赛', 'SCT', 'Medium', 1, 0, 'WTT Star Contender', '["Singles", "Doubles", "Mixed Doubles"]'),
('WTT_CONTENDER', 'WTT Contender', 'WTT挑战赛', 'CS', 'Medium', 1, 0, 'WTT Contender', '["Singles", "Doubles", "Mixed Doubles"]'),
('WTT_FEEDER', 'WTT Feeder', 'WTT支线赛', 'FEED', 'Low', 1, 0, 'WTT Feeder', '["Singles", "Doubles", "Mixed Doubles"]'),
('CONTINENTAL_CUP', 'Continental Cup', '洲际杯', 'CCUP', 'Medium', 1, 0, 'Continental Cups', '["Singles"]'),
('CONTINENTAL_CHAMPS', 'Continental Championships', '洲际锦标赛', 'CC', 'Medium', 1, 0, 'Continental Championships', '["Singles", "Doubles", "Mixed Doubles"]'),
('CONTINENTAL_GAMES', 'Continental Games', '洲际运动会', 'CT', 'Medium', 1, 0, 'Continental Games', '["Singles", "Doubles", "Mixed Doubles"]'),
('OLYMPIC_GAMES', 'Olympic Games', '奥运会', 'OLY', 'Premium', 1, 0, 'Olympic Games', '["Singles", "Doubles", "Mixed Doubles", "Teams"]'),
('OLYMPIC_QUALIFICATION', 'Olympic Qualification', '奥运资格赛', NULL, 'None', 0, 1, NULL, '[]'),
('MULTI_SPORT_GAMES', 'Multi-Sport Games', '综合运动会', 'MULTI', 'Low', 1, 0, 'Multi-Sport Games', '["Singles", "Doubles", "Mixed Doubles"]'),
('ITTF_WORLD_TEAM_CHAMPS', 'ITTF World Team Table Tennis Championships', '国际乒联世界乒乓球团体锦标赛', NULL, 'Premium', 1, 0, 'ITTF World Team Table Tennis Championships', '["Teams"]'),
('ITTF_MIXED_TEAM_WORLD_CUP', 'ITTF Mixed Team World Cup', '国际乒联混合团体世界杯', NULL, 'Premium', 1, 0, 'ITTF Mixed Team World Cup', '["Teams"]'),
('YOUTH_GRAND_SMASH', 'U19 WTT Youth Grand Smash', 'U19 WTT青年大满贯', 'YGS', 'Low', 1, 0, 'U19 WTT Youth Grand Smash', '["Singles"]'),
('YOUTH_STAR_CONTENDER', 'U19 WTT Youth Star Contender', 'U19 WTT青年球星挑战赛', 'YSC', 'Low', 1, 0, 'U19 WTT Youth Star Contender', '["Singles"]'),
('YOUTH_CONTENDER', 'U19 WTT Youth Contender', 'U19 WTT青年挑战赛', 'YC', 'Low', 1, 0, 'U19 WTT Youth Contender', '["Singles"]'),
('YOUTH_WORLD_CHAMPS', 'U19 ITTF World Youth Table Tennis Championships', 'U19 国际乒联世界青年乒乓球锦标赛', 'YWC', 'Low', 1, 0, 'U19 ITTF World Youth Table Tennis Championships', '["Singles", "Doubles", "Mixed Doubles"]'),
('REGIONAL_CHAMPS', 'Regional Championships', '地区锦标赛', 'RCH', 'Low', 1, 0, 'Regional Championships', '["Singles"]'),
('REGIONAL_CUP', 'Regional Cup', '地区杯', 'RCUP', 'Low', 0, 1, NULL, '[]'),
('U21_CONTINENTAL_CHAMPS', 'U21 Continental Championships', 'U21洲际锦标赛', 'U21CH', 'Low', 1, 0, 'U21 Continental Championships / Games', '["Singles", "Doubles", "Mixed Doubles"]'),
('YOUTH_CONTINENTAL_CHAMPS', 'Youth Continental Championships', '青年洲际锦标赛', NULL, 'None', 0, 1, NULL, '[]'),
('YOUTH_CONTINENTAL_CUP', 'Youth Continental Cup', '青年洲际杯', NULL, 'None', 0, 1, NULL, '[]'),
('REGIONAL_YOUTH_CHAMPS', 'Regional Youth Championships', '地区青年锦标赛', NULL, 'None', 0, 1, NULL, '[]'),
('ITTF_CHALLENGE', 'ITTF Challenge', '国际乒联挑战赛', NULL, 'None', 0, 1, NULL, '[]'),
('ITTF_CHALLENGE_SERIES', 'ITTF Challenge Series', '国际乒联挑战赛系列', NULL, 'None', 0, 1, NULL, '[]'),
('ITTF_CHALLENGE_PLUS', 'ITTF Challenge Plus', '国际乒联挑战赛+', NULL, 'None', 0, 1, NULL, '[]'),
('ITTF_WORLD_JUNIOR_CIRCUIT', 'ITTF World Junior Circuit', '国际乒联世界少年巡回赛', NULL, 'None', 0, 1, NULL, '[]'),
('ITTF_WORLD_JUNIOR_CIRCUIT_FINALS', 'ITTF World Junior Circuit Finals', '国际乒联世界少年巡回赛总决赛', NULL, 'None', 0, 1, NULL, '[]'),
('ITTF_WORLD_JUNIOR_CIRCUIT_PREMIUM', 'ITTF World Junior Circuit Premium', '国际乒联世界少年巡回赛高级', NULL, 'None', 0, 1, NULL, '[]'),
('ITTF_WORLD_JUNIOR_CIRCUIT_GOLDEN', 'ITTF World Junior Circuit Golden', '国际乒联世界少年巡回赛黄金', NULL, 'None', 0, 1, NULL, '[]'),
('ITTF_WORLD_CADET_CHALLENGE', 'ITTF World Cadet Challenge', '国际乒联世界少年挑战赛', NULL, 'None', 0, 1, NULL, '[]'),
('T2_DIAMOND', 'T2 Diamond', 'T2钻石赛', NULL, 'None', 0, 1, NULL, '[]'),
('YOUTH_OLYMPIC_GAMES', 'Youth Olympic Games', '青年奥运会', 'YOG', 'None', 0, 1, NULL, '[]'),
('YOUTH_OLYMPIC_GAMES_QUALIFICATION', 'Youth Olympic Games Qualification', '青年奥运会资格赛', NULL, 'None', 0, 1, NULL, '[]'),
('WORLD_TOUR_PRO_TOUR', 'ITTF World Tour / Pro Tour', '国际乒联世界巡回赛/专业巡回赛', NULL, 'None', 0, 1, NULL, '[]'),
('WORLD_TOUR_CHALLENGE_SERIES', 'ITTF World Tour Challenge Series', '国际乒联世界巡回赛挑战赛系列', NULL, 'None', 0, 1, NULL, '[]'),
('WORLD_TOUR_FINALS', 'ITTF World Tour Finals', '国际乒联世界巡回赛总决赛', NULL, 'None', 0, 1, NULL, '[]'),
('WORLD_TOUR_GRAND_FINALS', 'ITTF World Tour Grand Finals', '国际乒联世界巡回赛大总决赛', NULL, 'None', 0, 1, NULL, '[]'),
('WORLD_TOUR_MAJOR_SERIES', 'ITTF World Tour Major Series', '国际乒联世界巡回赛主赛系列', NULL, 'None', 0, 1, NULL, '[]'),
('WORLD_TOUR_PLATINUM', 'ITTF World Tour Platinum', '国际乒联世界巡回赛铂金', NULL, 'None', 0, 1, NULL, '[]'),
('WORLD_TOUR_SUPER_SERIES', 'ITTF World Tour Super Series', '国际乒联世界巡回赛超级系列', NULL, 'None', 0, 1, NULL, '[]'),
('OTHER_EVENTS', 'Other Events', '其他赛事', NULL, 'None', 0, 1, NULL, '[]')
ON DUPLICATE KEY UPDATE
    category_name=VALUES(category_name),
    category_name_zh=VALUES(category_name_zh),
    json_code=VALUES(json_code),
    points_tier=VALUES(points_tier),
    points_eligible=VALUES(points_eligible),
    filtering_only=VALUES(filtering_only),
    ittf_rule_name=VALUES(ittf_rule_name),
    applicable_formats=VALUES(applicable_formats);


-- Generated INSERT statements for event_type_mapping
-- Generated at: 2026-04-16T16:42:43.580484

-- Map event_type/event_kind to categories
INSERT INTO event_type_mapping (event_type, event_kind, category_id, priority)
SELECT
    em.event_type,
    em.event_kind,
    ec.id,
    em.priority
FROM (
  SELECT 'WTT Grand Smash' as event_type, '--' as event_kind, 'WTT_GRAND_SMASH' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF WTTC' as event_type, '--' as event_kind, 'ITTF_WTTC' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF WTTC' as event_type, 'WTTC Finals' as event_kind, 'ITTF_WTTC' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Cup' as event_type, '--' as event_kind, 'ITTF_WORLD_CUP' as category_id, 10 as priority
  UNION ALL
  SELECT 'WTT Finals' as event_type, '--' as event_kind, 'WTT_FINALS' as category_id, 10 as priority
  UNION ALL
  SELECT 'WTT Champions' as event_type, '--' as event_kind, 'WTT_CHAMPIONS' as category_id, 10 as priority
  UNION ALL
  SELECT 'WTT Contender Series' as event_type, 'WTT Star Contender' as event_kind, 'WTT_STAR_CONTENDER' as category_id, 10 as priority
  UNION ALL
  SELECT 'WTT Contender Series' as event_type, 'WTT Contender' as event_kind, 'WTT_CONTENDER' as category_id, 10 as priority
  UNION ALL
  SELECT 'WTT Feeder Series' as event_type, '--' as event_kind, 'WTT_FEEDER' as category_id, 10 as priority
  UNION ALL
  SELECT 'Continental' as event_type, 'Senior Cup' as event_kind, 'CONTINENTAL_CUP' as category_id, 10 as priority
  UNION ALL
  SELECT 'Continental' as event_type, 'Senior Championships' as event_kind, 'CONTINENTAL_CHAMPS' as category_id, 10 as priority
  UNION ALL
  SELECT 'Continental Games' as event_type, '--' as event_kind, 'CONTINENTAL_GAMES' as category_id, 10 as priority
  UNION ALL
  SELECT 'Olympic Games' as event_type, '--' as event_kind, 'OLYMPIC_GAMES' as category_id, 10 as priority
  UNION ALL
  SELECT 'Olympic Qualification' as event_type, '--' as event_kind, 'OLYMPIC_QUALIFICATION' as category_id, 10 as priority
  UNION ALL
  SELECT 'Multi sport events' as event_type, '--' as event_kind, 'MULTI_SPORT_GAMES' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF WJTTC' as event_type, '--' as event_kind, 'ITTF_WORLD_TEAM_CHAMPS' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF Mixed Team World Cup' as event_type, '--' as event_kind, 'ITTF_MIXED_TEAM_WORLD_CUP' as category_id, 10 as priority
  UNION ALL
  SELECT 'WTT Youth Grand Smash' as event_type, '--' as event_kind, 'YOUTH_GRAND_SMASH' as category_id, 10 as priority
  UNION ALL
  SELECT 'WTT Youth Contender Series' as event_type, 'WTT Youth Star Contender' as event_kind, 'YOUTH_STAR_CONTENDER' as category_id, 10 as priority
  UNION ALL
  SELECT 'WTT Youth Contender Series' as event_type, 'WTT Youth Contender' as event_kind, 'YOUTH_CONTENDER' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Youth Championships' as event_type, '--' as event_kind, 'YOUTH_WORLD_CHAMPS' as category_id, 10 as priority
  UNION ALL
  SELECT 'Regional' as event_type, 'Senior Championships' as event_kind, 'REGIONAL_CHAMPS' as category_id, 10 as priority
  UNION ALL
  SELECT 'Regional' as event_type, 'Senior Cup' as event_kind, 'REGIONAL_CUP' as category_id, 10 as priority
  UNION ALL
  SELECT 'Continental' as event_type, 'U21 Championships' as event_kind, 'U21_CONTINENTAL_CHAMPS' as category_id, 10 as priority
  UNION ALL
  SELECT 'Continental' as event_type, 'Youth Championships' as event_kind, 'YOUTH_CONTINENTAL_CHAMPS' as category_id, 10 as priority
  UNION ALL
  SELECT 'Continental' as event_type, 'Youth Cup' as event_kind, 'YOUTH_CONTINENTAL_CUP' as category_id, 10 as priority
  UNION ALL
  SELECT 'Regional' as event_type, 'Youth Championships' as event_kind, 'REGIONAL_YOUTH_CHAMPS' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF Challenge' as event_type, '--' as event_kind, 'ITTF_CHALLENGE' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF Challenge' as event_type, 'Challenge Series' as event_kind, 'ITTF_CHALLENGE_SERIES' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF Challenge' as event_type, 'Plus' as event_kind, 'ITTF_CHALLENGE_PLUS' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Junior Circuit' as event_type, '--' as event_kind, 'ITTF_WORLD_JUNIOR_CIRCUIT' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Junior Circuit' as event_type, 'Finals' as event_kind, 'ITTF_WORLD_JUNIOR_CIRCUIT_FINALS' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Junior Circuit' as event_type, 'Premium' as event_kind, 'ITTF_WORLD_JUNIOR_CIRCUIT_PREMIUM' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Junior Circuit' as event_type, 'Golden' as event_kind, 'ITTF_WORLD_JUNIOR_CIRCUIT_GOLDEN' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Cadet Challenge' as event_type, '--' as event_kind, 'ITTF_WORLD_CADET_CHALLENGE' as category_id, 10 as priority
  UNION ALL
  SELECT 'T2 Diamond' as event_type, '--' as event_kind, 'T2_DIAMOND' as category_id, 10 as priority
  UNION ALL
  SELECT 'Youth Olympic Games' as event_type, '--' as event_kind, 'YOUTH_OLYMPIC_GAMES' as category_id, 10 as priority
  UNION ALL
  SELECT 'Youth Olympic Games Qualification' as event_type, '--' as event_kind, 'YOUTH_OLYMPIC_GAMES_QUALIFICATION' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Tour / Pro Tour' as event_type, '--' as event_kind, 'WORLD_TOUR_PRO_TOUR' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Tour / Pro Tour' as event_type, 'Challenge Series' as event_kind, 'WORLD_TOUR_CHALLENGE_SERIES' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Tour / Pro Tour' as event_type, 'Finals' as event_kind, 'WORLD_TOUR_FINALS' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Tour / Pro Tour' as event_type, 'Grand Finals' as event_kind, 'WORLD_TOUR_GRAND_FINALS' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Tour / Pro Tour' as event_type, 'Major Series' as event_kind, 'WORLD_TOUR_MAJOR_SERIES' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Tour / Pro Tour' as event_type, 'Platinum' as event_kind, 'WORLD_TOUR_PLATINUM' as category_id, 10 as priority
  UNION ALL
  SELECT 'ITTF World Tour / Pro Tour' as event_type, 'Super Series' as event_kind, 'WORLD_TOUR_SUPER_SERIES' as category_id, 10 as priority
  UNION ALL
  SELECT 'Other events' as event_type, '--' as event_kind, 'OTHER_EVENTS' as category_id, 10 as priority
) em
JOIN event_categories ec ON em.category_id = ec.category_id
ON DUPLICATE KEY UPDATE priority=VALUES(priority);
