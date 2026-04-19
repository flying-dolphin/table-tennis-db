-- SQL UPDATE statements for events_calendar 2026
-- Generated at: 2026-04-19 10:47:41
-- Updates event_type, event_kind, and event_category_id for all 2026 calendar events
-- Total events: 205

-- NOTE: This SQL uses a subquery to lookup category_id from event_categories table

UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Vadodara 2026' AND href LIKE '%eventId=3273%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender San Francisco 2026' AND href LIKE '%eventId=3274%';
UPDATE events_calendar SET 
    event_type = 'WTT Champions', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CHAMPIONS')
WHERE year = 2026 AND name = 'WTT Champions Doha 2026' AND href LIKE '%eventId=3231%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Vadodara 2026' AND href LIKE '%eventId=3353%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Linz 2026' AND href LIKE '%eventId=3275%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Star Contender Doha 2026' AND href LIKE '%eventId=3232%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Manama 2026' AND href LIKE '%eventId=3276%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Doha 2026' AND href LIKE '%eventId=3278%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CONTENDER')
WHERE year = 2026 AND name = 'WTT Contender Muscat 2026' AND href LIKE '%eventId=3251%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Star Contender Doha 2026' AND href LIKE '%eventId=3277%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Doha 2026' AND href LIKE '%eventId=3354%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Lille 2026' AND href LIKE '%eventId=3355%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Cappadocia 2026' AND href LIKE '%eventId=3279%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Cup', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CUP')
WHERE year = 2026 AND name = 'ITTF-Americas Cup San Francisco 2026' AND href LIKE '%eventId=3398%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Cup', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CUP')
WHERE year = 2026 AND name = 'ITTF-Oceania Cup Christchurch 2026' AND href LIKE '%eventId=3300%';
UPDATE events_calendar SET 
    event_type = 'Regional', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'REGIONAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Americas North American Championships San Francisco 2026' AND href LIKE '%eventId=3470%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Tunis 2026' AND href LIKE '%eventId=3280%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Cappadocia 2026' AND href LIKE '%eventId=3266%';
UPDATE events_calendar SET 
    event_type = 'ITTF Masters', 
    event_kind = '--', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF-Americas Masters Championships Asuncion 2026' AND href LIKE '%eventId=3388%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Cup', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CUP')
WHERE year = 2026 AND name = 'ITTF-ATTU Asian Cup Haikou 2026' AND href LIKE '%eventId=3471%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Cup', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CUP')
WHERE year = 2026 AND name = 'ETTU Europe Top 16 Cup Montreux 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Star Contender Tunis 2026' AND href LIKE '%eventId=3281%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Cup', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CUP')
WHERE year = 2026 AND name = 'ITTF-Africa Cup Benghazi 2026' AND href LIKE '%eventId=3485%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Vila Real 2026' AND href LIKE '%eventId=3284%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Star Contender Chennai 2026' AND href LIKE '%eventId=3233%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Future', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Future Gold Coast 2026' AND href LIKE '%eventId=3418%';
UPDATE events_calendar SET 
    event_type = 'WTT Grand Smash', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_GRAND_SMASH')
WHERE year = 2026 AND name = 'Singapore Smash 2026' AND href LIKE '%eventId=3234%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Grand Smash', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_GRAND_SMASH')
WHERE year = 2026 AND name = 'Singapore Youth Smash 2026' AND href LIKE '%eventId=3285%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Düsseldorf 2026' AND href LIKE '%eventId=3267%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Buenos Aires 2026' AND href LIKE '%eventId=3286%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Wladyslawowo 2026' AND href LIKE '%eventId=3291%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Otocec 2026' AND href LIKE '%eventId=3268%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Asunción 2026' AND href LIKE '%eventId=3292%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Berlin 2026' AND href LIKE '%eventId=3293%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Havirov 2026' AND href LIKE '%eventId=3294%';
UPDATE events_calendar SET 
    event_type = 'WTT Champions', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CHAMPIONS')
WHERE year = 2026 AND name = 'WTT Champions Chongqing 2026' AND href LIKE '%eventId=3235%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Challenger', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Challenger Wladyslawowo 2026' AND href LIKE '%eventId=3419%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Varazdin 2026' AND href LIKE '%eventId=3356%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Americas South American U11&U13 Championships Asuncion 2026' AND href LIKE '%eventId=3399%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Challenger', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Challenger Lignano 2026' AND href LIKE '%eventId=3420%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Houston 2026' AND href LIKE '%eventId=3316%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CONTENDER')
WHERE year = 2026 AND name = 'WTT Contender Tunisia 2026' AND href LIKE '%eventId=3236%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Youth Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-ATTU West Asia Youth Championships Amman 2026' AND href LIKE '%eventId=3499%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Panagyurishte 2026' AND href LIKE '%eventId=3296%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Humacao 2026' AND href LIKE '%eventId=3299%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Future', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Future Costa Brava 2026' AND href LIKE '%eventId=3421%';
UPDATE events_calendar SET 
    event_type = 'Regional', 
    event_kind = 'Youth Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'REGIONAL_YOUTH_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Americas South American Youth Championships Chapeco 2026' AND href LIKE '%eventId=3404%';
UPDATE events_calendar SET 
    event_type = 'ITTF Masters', 
    event_kind = '--', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF-Americas South American Masters Championships Lima 2026';
UPDATE events_calendar SET 
    event_type = 'ITTF World Cup', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'ITTF_WORLD_CUP')
WHERE year = 2026 AND name = 'ITTF Men’s & Women’s World Cup Macao 2026' AND href LIKE '%eventId=3379%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Novi Sad 2026' AND href LIKE '%eventId=3297%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Future', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Future Yalova 2026' AND href LIKE '%eventId=3422%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Youth Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-ATTU Central Asia Youth Championships Almaty 2026' AND href LIKE '%eventId=3498%';
UPDATE events_calendar SET 
    event_type = 'Regional', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'REGIONAL_CHAMPS')
WHERE year = 2026 AND name = 'Central American and Caribbean Special Event Qualifier – Santo Domingo 2026';
UPDATE events_calendar SET 
    event_type = 'Regional', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'REGIONAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Africa North Regional Championships Benghazi 2026' AND href LIKE '%eventId=3489%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Cappadocia II 2026' AND href LIKE '%eventId=3373%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CONTENDER')
WHERE year = 2026 AND name = 'WTT Contender Taiyuan 2026' AND href LIKE '%eventId=3237%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Luxembourg 2026' AND href LIKE '%eventId=3298%';
UPDATE events_calendar SET 
    event_type = 'Regional', 
    event_kind = 'Youth Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'REGIONAL_YOUTH_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-ATTU South Asia Youth Championships Shimla 2026' AND href LIKE '%eventId=3500%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Americas Central American & Caribbean Championships Santo Domingo 2026' AND href LIKE '%eventId=3403%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Metz 2026' AND href LIKE '%eventId=3301%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Havirov 2026' AND href LIKE '%eventId=3270%';
UPDATE events_calendar SET 
    event_type = 'Multi sport events', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'MULTI_SPORT_GAMES')
WHERE year = 2026 AND name = 'IV South American Youth Games Panama 2026';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Youth Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-ATTU South East Asian Youth Championships Singapore 2026' AND href LIKE '%eventId=3475%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Star Contender Metz 2026' AND href LIKE '%eventId=3302%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Youth Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Americas Caribbean Youth Championships Santo Domingo 2026' AND href LIKE '%eventId=3402%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Future', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Future Santiago 2026' AND href LIKE '%eventId=3423%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Future', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Future Buenos Aires 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Senec 2026' AND href LIKE '%eventId=3357%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Challenger', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Challenger Sao Paulo 2026' AND href LIKE '%eventId=3430%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Sarajevo 2026' AND href LIKE '%eventId=3304%';
UPDATE events_calendar SET 
    event_type = 'ITTF WTTC', 
    event_kind = 'WTTC Finals', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'ITTF_WTTC')
WHERE year = 2026 AND name = 'ITTF World Team Championships Finals London 2026' AND href LIKE '%eventId=3216%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Challenger', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Challenger Podgorica 2026' AND href LIKE '%eventId=3431%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Challenger', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Challenger Lasko 2026 presented by I FEEL SLOVENIA' AND href LIKE '%eventId=3432%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Platja D’Aro 2026' AND href LIKE '%eventId=3305%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Istanbul 2026' AND href LIKE '%eventId=3358%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Elite', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Elite Lasko 2026 presented by I FEEL SLOVENIA' AND href LIKE '%eventId=3433%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Tashkent 2026' AND href LIKE '%eventId=3320%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Mississauga 2026' AND href LIKE '%eventId=3307%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Lagos 2026' AND href LIKE '%eventId=3360%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Elite', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Elite Taipei City 2026' AND href LIKE '%eventId=3434%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Bangkok 2026' AND href LIKE '%eventId=3308%';
UPDATE events_calendar SET 
    event_type = 'Regional', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'REGIONAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Africa East Regional Championships Port Sudan 2026' AND href LIKE '%eventId=3490%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CONTENDER')
WHERE year = 2026 AND name = 'WTT Contender Lagos 2026' AND href LIKE '%eventId=3238%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Hennebont 2026' AND href LIKE '%eventId=3361%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Star Contender Bangkok 2026' AND href LIKE '%eventId=3306%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Prishtina 2026' AND href LIKE '%eventId=3309%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender San Francisco II 2026' AND href LIKE '%eventId=3478%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Prishtina 2026' AND href LIKE '%eventId=3271%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Sandefjord 2026' AND href LIKE '%eventId=3310%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CONTENDER')
WHERE year = 2026 AND name = 'WTT Contender Skopje 2026' AND href LIKE '%eventId=3239%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Americas Central America Youth Championships Tegucigalpa 2026' AND href LIKE '%eventId=3406%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Helsingborg 2026' AND href LIKE '%eventId=3311%';
UPDATE events_calendar SET 
    event_type = 'ITTF Masters', 
    event_kind = '--', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Masters Championships Gangneung 2026' AND href LIKE '%eventId=3225%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Rio De Janeiro 2026' AND href LIKE '%eventId=3312%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CONTENDER')
WHERE year = 2026 AND name = 'WTT Contender Zagreb 2026' AND href LIKE '%eventId=3240%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Star Contender Rio De Janeiro 2026' AND href LIKE '%eventId=3313%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Americas South American Championships Santiago 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Star Contender Ljubljana 2026' AND href LIKE '%eventId=3241%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'U21 Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'U21_CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ETTU European U21 Championships Cluj-Napoca 2026';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Future', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Future Ostrava 2026' AND href LIKE '%eventId=3437%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Youth Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-ATTU Asian Youth Championships Muscat 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Caracas 2026' AND href LIKE '%eventId=3315%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Elite', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Elite Beijing 2026' AND href LIKE '%eventId=3438%';
UPDATE events_calendar SET 
    event_type = 'WTT Grand Smash', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_GRAND_SMASH')
WHERE year = 2026 AND name = 'United States Smash 2026' AND href LIKE '%eventId=3242%';
UPDATE events_calendar SET 
    event_type = 'Regional', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'REGIONAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Africa Central Regional Championships Kinshasa 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Istanbul II 2026' AND href LIKE '%eventId=3359%';
UPDATE events_calendar SET 
    event_type = 'Multi sport events', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'MULTI_SPORT_GAMES')
WHERE year = 2026 AND name = 'Parasouth American Games Valledupar 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Hong Kong 2026' AND href LIKE '%eventId=3318%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Asunción 2026' AND href LIKE '%eventId=3363%';
UPDATE events_calendar SET 
    event_type = 'Regional', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'REGIONAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Africa Southern Africa Regional Championships Harare 2026';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Youth Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ETTU European Youth Championships Gondomar 2026';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Future', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Future Nakhon Ratchasima 2026' AND href LIKE '%eventId=3440%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Americas Central America & Caribbean U11&U13 Championships Guadalajara 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Ulaanbaatar 2026' AND href LIKE '%eventId=3319%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CONTENDER')
WHERE year = 2026 AND name = 'WTT Contender Buenos Aires 2026' AND href LIKE '%eventId=3243%';
UPDATE events_calendar SET 
    event_type = 'Regional', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'REGIONAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Africa West Regional Championships Conakry 2026' AND href LIKE '%eventId=3492%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Elite', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Elite Nakhon Ratchasima 2026' AND href LIKE '%eventId=3441%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Tashkent II 2026' AND href LIKE '%eventId=3366%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Ulaanbaatar 2026' AND href LIKE '%eventId=3364%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF Oceania Hopes Week Auckland 2026';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Youth Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Africa Youth Championships Accra 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Star Contender Brazil 2026' AND href LIKE '%eventId=3244%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender San Francisco III 2026' AND href LIKE '%eventId=3479%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Almaty 2026' AND href LIKE '%eventId=3321%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Tashkent 2026' AND href LIKE '%eventId=3365%';
UPDATE events_calendar SET 
    event_type = 'Multi sport events', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'MULTI_SPORT_GAMES')
WHERE year = 2026 AND name = 'XXV Central American and Caribbean Games Santo Domingo 2026';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Youth Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Africa Youth Cup Accra 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Tunis 2026' AND href LIKE '%eventId=3372%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Vientiane 2026' AND href LIKE '%eventId=3322%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Vientiane 2026' AND href LIKE '%eventId=3272%';
UPDATE events_calendar SET 
    event_type = 'WTT Champions', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CHAMPIONS')
WHERE year = 2026 AND name = 'WTT Champions Yokohama 2026' AND href LIKE '%eventId=3245%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Amman 2026' AND href LIKE '%eventId=3323%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Spokane 2026' AND href LIKE '%eventId=3480%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Challenger', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Challenger Spokane 2026' AND href LIKE '%eventId=3476%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'Europe Smash – Sweden 2026' AND href LIKE '%eventId=3246%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Elite', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Elite Spokane 2026' AND href LIKE '%eventId=3477%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Berlin 2026' AND href LIKE '%eventId=3374%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Americas Youth Championships Guatemala City 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Olomouc 2026' AND href LIKE '%eventId=3282%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Varazdin 2026' AND href LIKE '%eventId=3326%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Otocec 2026' AND href LIKE '%eventId=3328%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Oceania Championships Ballarat 2026,' AND href LIKE '%eventId=3454%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Future', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Future Lahti 2026';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Oceania Youth Championships Ballarat 2026,' AND href LIKE '%eventId=3455%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CONTENDER')
WHERE year = 2026 AND name = 'WTT Contender Almaty 2026' AND href LIKE '%eventId=3247%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Future', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Future Ammann 2026' AND href LIKE '%eventId=3436%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Tunis II 2026' AND href LIKE '%eventId=3314%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Cuenca 2026' AND href LIKE '%eventId=3332%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Puerto Princesa 2026' AND href LIKE '%eventId=3350%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Americas U11&U13 Championships Houston 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Puerto Princesa 2026' AND href LIKE '%eventId=3415%';
UPDATE events_calendar SET 
    event_type = 'WTT Champions', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CHAMPIONS')
WHERE year = 2026 AND name = 'WTT Champions Macao 2026' AND href LIKE '%eventId=3248%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CONTENDER')
WHERE year = 2026 AND name = 'WTT Contender Panagyurishte 2026' AND href LIKE '%eventId=3253%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Bangkok II 2026' AND href LIKE '%eventId=3331%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Medellín 2026' AND href LIKE '%eventId=3337%';
UPDATE events_calendar SET 
    event_type = 'ITTF Masters', 
    event_kind = '--', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF-Americas Central American Masters Championships Tegucigalpa 2026';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Elite', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Elite Yvelines 2026';
UPDATE events_calendar SET 
    event_type = 'Multi sport events', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'MULTI_SPORT_GAMES')
WHERE year = 2026 AND name = 'XIII South American Games Santa Fe 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Gangneung 2026' AND href LIKE '%eventId=3330%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Bangkok 2026' AND href LIKE '%eventId=3371%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Star Contender London 2026' AND href LIKE '%eventId=3254%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Star Contender Gangneung 2026' AND href LIKE '%eventId=3329%';
UPDATE events_calendar SET 
    event_type = 'Multi sport events', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'MULTI_SPORT_GAMES')
WHERE year = 2026 AND name = 'Asian Games Aichi-Nagoya 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Spa 2026' AND href LIKE '%eventId=3334%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Linz 2026' AND href LIKE '%eventId=3375%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Batumi 2026' AND href LIKE '%eventId=3333%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Asunción II 2026' AND href LIKE '%eventId=3367%';
UPDATE events_calendar SET 
    event_type = 'WTT Grand Smash', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_GRAND_SMASH')
WHERE year = 2026 AND name = 'China Smash 2026' AND href LIKE '%eventId=3249%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Cup', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CUP')
WHERE year = 2026 AND name = 'ETTU Europe Youth Top 10 Antibes 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Cairo 2026' AND href LIKE '%eventId=3347%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Buenos Aires II 2026' AND href LIKE '%eventId=3368%';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Future', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Future Region De Murcia 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Doha II 2026' AND href LIKE '%eventId=3283%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ETTU European Individual Championships Ljubljana 2026';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Africa Championships 2026';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Challenger', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Challenger Kefalonia 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Doha II 2026' AND href LIKE '%eventId=3336%';
UPDATE events_calendar SET 
    event_type = 'Multi sport events', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'MULTI_SPORT_GAMES')
WHERE year = 2026 AND name = 'Asian Para Games Aichi-Nagoya 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Dubai 2026' AND href LIKE '%eventId=3340%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Fort Lauderdale 2026' AND href LIKE '%eventId=3481%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-Americas Championships Lima 2026';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'Senior Championships', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'CONTINENTAL_CHAMPS')
WHERE year = 2026 AND name = 'ITTF-ATTU Asian Championships Tashkent 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Lignano 2026' AND href LIKE '%eventId=3338%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Senec 2026' AND href LIKE '%eventId=3339%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Chennai 2026' AND href LIKE '%eventId=3369%';
UPDATE events_calendar SET 
    event_type = 'WTT Champions', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CHAMPIONS')
WHERE year = 2026 AND name = 'WTT Champions Montpellier 2026' AND href LIKE '%eventId=3250%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Chennai 2026' AND href LIKE '%eventId=3376%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Szombathely 2026' AND href LIKE '%eventId=3344%';
UPDATE events_calendar SET 
    event_type = 'Youth Olympic Games', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_OLYMPIC_GAMES')
WHERE year = 2026 AND name = 'Youth Olympic Games Dakar 2026' AND href LIKE '%eventId=3219%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Podgorica 2026' AND href LIKE '%eventId=3345%';
UPDATE events_calendar SET 
    event_type = 'WTT Champions', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CHAMPIONS')
WHERE year = 2026 AND name = 'WTT Champions Frankfurt 2026' AND href LIKE '%eventId=3252%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Vila Nova de Gaia 2026' AND href LIKE '%eventId=3370%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Star Contender Podgorica 2026' AND href LIKE '%eventId=3346%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_CONTENDER')
WHERE year = 2026 AND name = 'WTT Contender Istanbul 2026' AND href LIKE '%eventId=3257%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Gaborone 2026' AND href LIKE '%eventId=3482%';
UPDATE events_calendar SET 
    event_type = 'Continental', 
    event_kind = 'U13 Championships', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ETTU European U13 Championships Nevsehir 2026';
UPDATE events_calendar SET 
    event_type = 'ITTF Para', 
    event_kind = 'World Para Championships', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF World Para Championships Pattaya 2026' AND href LIKE '%eventId=3258%';
UPDATE events_calendar SET 
    event_type = 'WTT Youth Contender Series', 
    event_kind = 'WTT Youth Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_CONTENDER')
WHERE year = 2026 AND name = 'WTT Youth Contender Perth 2026' AND href LIKE '%eventId=3469%';
UPDATE events_calendar SET 
    event_type = 'WTT Contender Series', 
    event_kind = 'WTT Star Contender', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_STAR_CONTENDER')
WHERE year = 2026 AND name = 'WTT Star Contender Muscat 2026' AND href LIKE '%eventId=3256%';
UPDATE events_calendar SET 
    event_type = 'ITTF World Youth Championships', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'YOUTH_WORLD_CHAMPS')
WHERE year = 2026 AND name = 'ITTF World Youth Championships Manama 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Düsseldorf II 2026' AND href LIKE '%eventId=3352%';
UPDATE events_calendar SET 
    event_type = 'WTT Feeder Series', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FEEDER')
WHERE year = 2026 AND name = 'WTT Feeder Gdansk 2026' AND href LIKE '%eventId=3269%';
UPDATE events_calendar SET 
    event_type = 'ITTF World Cup', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'ITTF_WORLD_CUP')
WHERE year = 2026 AND name = 'ITTF Mixed Team World Cup Chengdu 2026';
UPDATE events_calendar SET 
    event_type = 'ITTF Masters', 
    event_kind = '--', 
    event_category_id = NULL
WHERE year = 2026 AND name = 'ITTF-Americas Masters Championships 2026';
UPDATE events_calendar SET 
    event_type = 'WTT Finals', 
    event_kind = '--', 
    event_category_id = (SELECT id FROM event_categories WHERE category_id = 'WTT_FINALS')
WHERE year = 2026 AND name = 'WTT Finals Hong Kong 2026' AND href LIKE '%eventId=3255%';