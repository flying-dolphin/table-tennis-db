-- ITTF 数据库 Schema
-- 日期: 2026-04-16
-- 数据库: SQLite

-- ============================================================================
-- 字典表
-- ============================================================================

CREATE TABLE IF NOT EXISTS sub_event_types (
    sub_event_type_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    name_zh             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_categories (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id         TEXT NOT NULL UNIQUE,   -- 唯一标识，如 "WTT_GRAND_SMASH"
    category_name       TEXT NOT NULL,
    category_name_zh    TEXT,
    age_group           TEXT NOT NULL DEFAULT 'SENIOR',   -- SENIOR / YOUTH
    event_series        TEXT NOT NULL DEFAULT 'OTHER',    -- ITTF / WTT / OLYMPIC / OTHER
    json_code           TEXT,                   -- ranking JSON 中的缩写，如 "GS"
    points_tier         TEXT,                   -- Premium / High / Medium / Low / None
    points_eligible     INTEGER DEFAULT 1,
    filtering_only      INTEGER DEFAULT 0,
    applicable_formats  TEXT,                   -- JSON 数组
    ittf_rule_name      TEXT,
    sort_order          INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_event_categories_json_code ON event_categories(json_code);
CREATE INDEX IF NOT EXISTS idx_event_categories_points_eligible ON event_categories(points_eligible);

CREATE TABLE IF NOT EXISTS event_type_mapping (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    event_kind      TEXT,
    category_id     INTEGER NOT NULL,
    priority        INTEGER DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (category_id) REFERENCES event_categories(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_event_type_mapping_lookup ON event_type_mapping(event_type, event_kind, is_active, priority);

CREATE TABLE IF NOT EXISTS points_rules (
    rule_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id         INTEGER NOT NULL,      -- -> event_categories.id
    sub_event_category  TEXT NOT NULL,         -- 子分类，如 "Q48" / "Q64" / "Singles"
    draw_qualifier      TEXT,                  -- 签表类型，如 "Main Draw" / "Qualification"
    stage_type          TEXT NOT NULL,         -- 阶段类型，如 "Main Draw" / "Qualification"
    position            TEXT NOT NULL,         -- 名次，如 "W" / "F" / "SF" / "QF" / "R16"
    points              INTEGER NOT NULL,      -- 积分值
    effective_date      TEXT NOT NULL,         -- 生效日期，如 "2026-01-27"
    FOREIGN KEY (category_id) REFERENCES event_categories(id) ON DELETE RESTRICT
);

-- SQLite 中 UNIQUE 约束对 NULL 不去重；draw_qualifier 允许为空时需要用表达式索引保证唯一性。
CREATE UNIQUE INDEX IF NOT EXISTS uq_points_rules_rule
ON points_rules (
    category_id,
    sub_event_category,
    IFNULL(draw_qualifier, ''),
    stage_type,
    position,
    effective_date
);

CREATE INDEX IF NOT EXISTS idx_points_rules_category ON points_rules(category_id);
CREATE INDEX IF NOT EXISTS idx_points_rules_lookup
ON points_rules(category_id, sub_event_category, stage_type, position, effective_date);

-- ============================================================================
-- 核心实体表
-- ============================================================================

CREATE TABLE IF NOT EXISTS players (
    player_id       INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    name_zh         TEXT,
    slug            TEXT UNIQUE NOT NULL,
    country         TEXT,
    country_code    TEXT NOT NULL,
    gender          TEXT NOT NULL DEFAULT 'Female',
    birth_year      INTEGER,
    age             INTEGER,
    style           TEXT,
    style_zh        TEXT,
    playing_hand    TEXT,
    playing_hand_zh TEXT,
    grip            TEXT,
    grip_zh         TEXT,
    avatar_url      TEXT,
    avatar_file     TEXT,
    career_events       INTEGER DEFAULT 0,
    career_matches      INTEGER DEFAULT 0,
    career_wins         INTEGER DEFAULT 0,
    career_losses       INTEGER DEFAULT 0,
    career_wtt_titles   INTEGER DEFAULT 0,
    career_all_titles   INTEGER DEFAULT 0,
    career_best_rank    INTEGER,
    career_best_month   TEXT,
    year_events         INTEGER DEFAULT 0,
    year_matches        INTEGER DEFAULT 0,
    year_wins           INTEGER DEFAULT 0,
    year_losses         INTEGER DEFAULT 0,
    year_games          INTEGER DEFAULT 0,
    year_games_won      INTEGER DEFAULT 0,
    year_games_lost     INTEGER DEFAULT 0,
    year_wtt_titles     INTEGER DEFAULT 0,
    year_all_titles     INTEGER DEFAULT 0,
    scraped_at      TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_players_country ON players(country_code);
CREATE INDEX IF NOT EXISTS idx_players_slug ON players(slug);

CREATE TABLE IF NOT EXISTS events (
    event_id            INTEGER PRIMARY KEY,
    year                INTEGER NOT NULL,
    name                TEXT NOT NULL,
    name_zh             TEXT,
    event_type_name     TEXT,                  -- 原始 event_type
    event_kind          TEXT,                  -- 原始 event_kind
    event_kind_zh       TEXT,
    event_category_id   INTEGER,               -- -> event_categories.id
    category_code       TEXT,                  -- 冗余：event_categories.category_id
    category_name_zh    TEXT,                  -- 冗余：中文分类名
    total_matches       INTEGER DEFAULT 0,
    start_date          TEXT,
    end_date            TEXT,
    location            TEXT,
    time_zone           TEXT,                  -- IANA 时区，如 Europe/London
    href                TEXT,
    lifecycle_status    TEXT NOT NULL DEFAULT 'upcoming',
                                                -- upcoming / draw_published / in_progress / completed
    last_synced_at      TEXT,
    scraped_at          TEXT,
    FOREIGN KEY (event_category_id) REFERENCES event_categories(id)
);

CREATE INDEX IF NOT EXISTS idx_events_year ON events(year);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(start_date);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(event_category_id);
CREATE INDEX IF NOT EXISTS idx_events_lifecycle ON events(lifecycle_status);

CREATE TABLE IF NOT EXISTS sub_events (
    sub_event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id            INTEGER NOT NULL,
    sub_event_type_code TEXT NOT NULL,
    champion_player_ids TEXT,
    champion_name       TEXT,
    champion_country_code TEXT,
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
    UNIQUE(event_id, sub_event_type_code)
);

CREATE INDEX IF NOT EXISTS idx_sub_events_event ON sub_events(event_id);

CREATE TABLE IF NOT EXISTS matches (
    match_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id            INTEGER NOT NULL,
    event_name          TEXT,
    event_name_zh       TEXT,
    event_year          INTEGER,
    sub_event_type_code TEXT NOT NULL,
    stage               TEXT,
    stage_zh            TEXT,
    stage_code          TEXT,                  -- -> stage_codes.code
    round               TEXT,
    round_zh            TEXT,
    round_code          TEXT,                  -- -> round_codes.code
    side_a_key          TEXT NOT NULL,
    side_b_key          TEXT NOT NULL,
    match_score         TEXT,
    games               TEXT,
    winner_side         TEXT,
    winner_name         TEXT NOT NULL,
    raw_row_text        TEXT NOT NULL,
    scraped_at          TEXT,
    team_tie_id         INTEGER,               -- 团体赛所属顶层 tie；单项赛为空
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
    CHECK (winner_side IN ('A', 'B') OR winner_side IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_matches_event ON matches(event_id);
CREATE INDEX IF NOT EXISTS idx_matches_sub_event ON matches(sub_event_type_code);
CREATE INDEX IF NOT EXISTS idx_matches_year ON matches(event_year);
CREATE INDEX IF NOT EXISTS idx_matches_winner_side ON matches(winner_side);
CREATE INDEX IF NOT EXISTS idx_matches_event_round_sides
ON matches(event_id, sub_event_type_code, stage, round, side_a_key, side_b_key);
CREATE INDEX IF NOT EXISTS idx_matches_stage_code ON matches(stage_code);
CREATE INDEX IF NOT EXISTS idx_matches_round_code ON matches(round_code);
CREATE INDEX IF NOT EXISTS idx_matches_team_tie ON matches(team_tie_id);

CREATE TABLE IF NOT EXISTS team_ties (
    team_tie_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id             INTEGER NOT NULL,
    sub_event_type_code  TEXT NOT NULL,      -- MT / WT / XT
    stage                TEXT,
    stage_zh             TEXT,
    stage_code           TEXT,
    round                TEXT,
    round_zh             TEXT,
    round_code           TEXT,
    group_code           TEXT,
    match_score          TEXT,
    winner_side          TEXT,
    winner_team_code     TEXT,
    status               TEXT NOT NULL DEFAULT 'completed',
    source_type          TEXT NOT NULL,      -- promoted_from_current / backfilled_from_matches / manual
    source_key           TEXT,
    promoted_from_event_id INTEGER,
    promoted_at          TEXT,
    created_at           TEXT DEFAULT (datetime('now')),
    updated_at           TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
    CHECK (winner_side IN ('A', 'B') OR winner_side IS NULL),
    CHECK (status IN ('scheduled', 'live', 'completed', 'walkover', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_team_ties_event
    ON team_ties(event_id, sub_event_type_code);
CREATE INDEX IF NOT EXISTS idx_team_ties_round
    ON team_ties(event_id, stage_code, round_code);
CREATE INDEX IF NOT EXISTS idx_team_ties_group
    ON team_ties(event_id, group_code);
CREATE UNIQUE INDEX IF NOT EXISTS uq_team_ties_source
    ON team_ties(event_id, sub_event_type_code, IFNULL(source_key, ''));

CREATE TABLE IF NOT EXISTS team_tie_sides (
    team_tie_side_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    team_tie_id          INTEGER NOT NULL,
    side_no              INTEGER NOT NULL,   -- 1 / 2
    team_code            TEXT,
    team_name            TEXT,
    seed                 INTEGER,
    qualifier            INTEGER,
    is_winner            INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (team_tie_id) REFERENCES team_ties(team_tie_id) ON DELETE CASCADE,
    CHECK (side_no IN (1, 2)),
    CHECK (is_winner IN (0, 1)),
    UNIQUE(team_tie_id, side_no)
);

CREATE INDEX IF NOT EXISTS idx_team_tie_sides_tie
    ON team_tie_sides(team_tie_id);
CREATE INDEX IF NOT EXISTS idx_team_tie_sides_team
    ON team_tie_sides(team_code);

CREATE TABLE IF NOT EXISTS team_tie_side_players (
    team_tie_side_player_id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_tie_side_id        INTEGER NOT NULL,
    player_order            INTEGER NOT NULL,
    player_id               INTEGER,
    player_name             TEXT NOT NULL,
    player_country          TEXT,
    FOREIGN KEY (team_tie_side_id) REFERENCES team_tie_sides(team_tie_side_id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    UNIQUE(team_tie_side_id, player_order)
);

CREATE INDEX IF NOT EXISTS idx_team_tie_side_players_side
    ON team_tie_side_players(team_tie_side_id);
CREATE INDEX IF NOT EXISTS idx_team_tie_side_players_player
    ON team_tie_side_players(player_id);

CREATE TABLE IF NOT EXISTS event_draw_matches (
    draw_match_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id            INTEGER NOT NULL,
    event_id            INTEGER NOT NULL,
    sub_event_type_code TEXT NOT NULL,
    draw_stage          TEXT NOT NULL DEFAULT 'Main Draw',
    draw_round          TEXT NOT NULL,
    stage_code          TEXT,                  -- -> stage_codes.code
    round_code          TEXT,                  -- -> round_codes.code
    round_order         INTEGER NOT NULL,
    source_stage        TEXT,
    source_round        TEXT,
    bronze_source       TEXT,
    bronze_verified     INTEGER NOT NULL DEFAULT 0,
    validation_note     TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
    CHECK (bronze_verified IN (0, 1)),
    UNIQUE(match_id)
);
CREATE INDEX IF NOT EXISTS idx_event_draw_matches_stage_code ON event_draw_matches(stage_code);
CREATE INDEX IF NOT EXISTS idx_event_draw_matches_round_code ON event_draw_matches(round_code);

CREATE INDEX IF NOT EXISTS idx_event_draw_matches_event
ON event_draw_matches(event_id, sub_event_type_code, round_order);

CREATE INDEX IF NOT EXISTS idx_event_draw_matches_match
ON event_draw_matches(match_id);

CREATE TABLE IF NOT EXISTS match_sides (
    match_side_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id             INTEGER NOT NULL,
    side_no              INTEGER NOT NULL, -- 1 / 2
    side_key             TEXT NOT NULL,
    is_winner            INTEGER NOT NULL DEFAULT 0, -- 0 / 1
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,
    CHECK (side_no IN (1, 2)),
    CHECK (is_winner IN (0, 1)),
    UNIQUE(match_id, side_no)
);

CREATE INDEX IF NOT EXISTS idx_match_sides_match ON match_sides(match_id);
CREATE INDEX IF NOT EXISTS idx_match_sides_winner ON match_sides(is_winner);

CREATE TABLE IF NOT EXISTS match_side_players (
    match_side_player_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_side_id        INTEGER NOT NULL,
    player_order         INTEGER NOT NULL, -- preserve row order for display
    player_id            INTEGER,
    player_name          TEXT NOT NULL,
    player_country       TEXT,
    FOREIGN KEY (match_side_id) REFERENCES match_sides(match_side_id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    UNIQUE(match_side_id, player_order)
);

CREATE INDEX IF NOT EXISTS idx_match_side_players_side ON match_side_players(match_side_id);
CREATE INDEX IF NOT EXISTS idx_match_side_players_player ON match_side_players(player_id);

-- ============================================================================
-- 排名数据表
-- ============================================================================

CREATE TABLE IF NOT EXISTS ranking_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,
    ranking_week    TEXT NOT NULL,
    ranking_date    TEXT NOT NULL,
    total_players   INTEGER,
    scraped_at      TEXT,
    UNIQUE(category, ranking_week)
);

CREATE TABLE IF NOT EXISTS ranking_entries (
    entry_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL,
    player_id       INTEGER NOT NULL,
    rank            INTEGER NOT NULL,
    points          INTEGER NOT NULL,
    rank_change     INTEGER DEFAULT 0,
    FOREIGN KEY (snapshot_id) REFERENCES ranking_snapshots(snapshot_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    UNIQUE(snapshot_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_ranking_entries_snapshot ON ranking_entries(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_ranking_entries_player ON ranking_entries(player_id);
CREATE INDEX IF NOT EXISTS idx_ranking_entries_rank ON ranking_entries(rank);

CREATE TABLE IF NOT EXISTS points_breakdown (
    breakdown_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL,
    player_id       INTEGER NOT NULL,
    event_name      TEXT NOT NULL,
    event_name_zh   TEXT,
    event_type_code TEXT,
    category_name_zh TEXT,
    position        TEXT,
    position_zh     TEXT,
    points          INTEGER NOT NULL,
    expires_on      TEXT,
    FOREIGN KEY (snapshot_id) REFERENCES ranking_snapshots(snapshot_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE INDEX IF NOT EXISTS idx_points_breakdown_player ON points_breakdown(player_id);
CREATE INDEX IF NOT EXISTS idx_points_breakdown_snapshot ON points_breakdown(snapshot_id);

-- ============================================================================
-- 辅助表
-- ============================================================================

CREATE TABLE IF NOT EXISTS events_calendar (
    calendar_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    year                INTEGER NOT NULL,
    name                TEXT NOT NULL,
    name_zh             TEXT,
    event_type          TEXT,                  -- 原始 event_type
    event_kind          TEXT,                  -- 原始 event_kind
    event_category_id   INTEGER,               -- -> event_categories.id
    date_range          TEXT,
    date_range_zh       TEXT,
    start_date          TEXT,
    end_date            TEXT,
    location            TEXT,
    location_zh         TEXT,
    status              TEXT,
    href                TEXT,
    event_id            INTEGER,
    scraped_at          TEXT,
    FOREIGN KEY (event_category_id) REFERENCES event_categories(id),
    FOREIGN KEY (event_id) REFERENCES events(event_id)
);

CREATE INDEX IF NOT EXISTS idx_calendar_year ON events_calendar(year);
CREATE INDEX IF NOT EXISTS idx_calendar_date ON events_calendar(start_date);
CREATE INDEX IF NOT EXISTS idx_calendar_category ON events_calendar(event_category_id);

CREATE TABLE IF NOT EXISTS unmatched_records (
    record_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type     TEXT NOT NULL,
    source_name     TEXT NOT NULL,
    source_context  TEXT,
    ingestion_run_id INTEGER,
    status          TEXT DEFAULT 'pending',
    matched_id      INTEGER,
    notes           TEXT,
    reviewed_at     TEXT,
    reviewed_by     TEXT,
    FOREIGN KEY (ingestion_run_id) REFERENCES ingestion_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_unmatched_type ON unmatched_records(record_type);
CREATE INDEX IF NOT EXISTS idx_unmatched_status ON unmatched_records(status);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running',
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    records_processed   INTEGER DEFAULT 0,
    records_matched     INTEGER DEFAULT 0,
    records_unmatched   INTEGER DEFAULT 0,
    error_message   TEXT,
    metadata        TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_task ON ingestion_runs(task_type);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_status ON ingestion_runs(status);

-- ============================================================================
-- 用户与会话
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email           TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash   TEXT NOT NULL,
    salt            TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email COLLATE NOCASE);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    token       TEXT NOT NULL UNIQUE,
    expires_at  TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);

-- ============================================================================
-- 阶段/轮次字典（normalize_stage_round.py 维护）
-- ============================================================================

CREATE TABLE IF NOT EXISTS stage_codes (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    name_zh     TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS round_codes (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    name_zh     TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'unknown',
    sort_order  INTEGER NOT NULL DEFAULT 0
);

-- ============================================================================
-- 场馆字典（用于时区推断与本地化展示）
-- ============================================================================

CREATE TABLE IF NOT EXISTS venues (
    venue_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,             -- 规范英文名（无则用原文）
    name_zh         TEXT,
    city            TEXT,
    country_code    TEXT,                      -- ISO-3
    time_zone       TEXT NOT NULL,             -- IANA，如 Europe/London
    aliases         TEXT,                      -- JSON 数组：备用名 / 中文别名
    UNIQUE(name)
);

CREATE INDEX IF NOT EXISTS idx_venues_country ON venues(country_code);

-- ============================================================================
-- current 层：完整赛事计划 / standings / team ties / matches / brackets
-- ============================================================================

CREATE TABLE IF NOT EXISTS current_event_session_schedule (
    current_session_schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id            INTEGER NOT NULL,
    day_index           INTEGER NOT NULL,
    local_date          TEXT NOT NULL,
    morning_session_start TEXT,
    afternoon_session_start TEXT,
    venue_raw           TEXT,
    venue_id            INTEGER,
    table_count         INTEGER,
    raw_sub_events_text TEXT,
    parsed_rounds_json  TEXT,
    updated_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (venue_id) REFERENCES venues(venue_id),
    UNIQUE(event_id, day_index)
);

CREATE INDEX IF NOT EXISTS idx_current_event_session_schedule_event
    ON current_event_session_schedule(event_id);
CREATE INDEX IF NOT EXISTS idx_current_event_session_schedule_date
    ON current_event_session_schedule(local_date);

CREATE TABLE IF NOT EXISTS current_event_group_standings (
    current_standing_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id              INTEGER NOT NULL,
    stage_label           TEXT NOT NULL,
    team_code             TEXT NOT NULL,
    group_code            TEXT NOT NULL,
    organization_code     TEXT NOT NULL,
    team_name             TEXT,
    qualification_mark    TEXT,
    played                INTEGER,
    won                   INTEGER,
    lost                  INTEGER,
    result                INTEGER,
    rank                  INTEGER,
    score_for             INTEGER,
    score_against         INTEGER,
    games_won             INTEGER,
    games_lost            INTEGER,
    players_json          TEXT,
    source_url            TEXT,
    updated_at            TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    UNIQUE(event_id, stage_label, team_code, group_code, organization_code)
);

CREATE INDEX IF NOT EXISTS idx_current_event_group_standings_event_team
    ON current_event_group_standings(event_id, team_code);
CREATE INDEX IF NOT EXISTS idx_current_event_group_standings_stage
    ON current_event_group_standings(event_id, stage_label, group_code, rank);

CREATE TABLE IF NOT EXISTS current_event_team_ties (
    current_team_tie_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id               INTEGER NOT NULL,
    sub_event_type_code    TEXT NOT NULL,
    stage_label            TEXT,
    stage_code             TEXT,
    round_label            TEXT,
    round_code             TEXT,
    group_code             TEXT,
    external_match_code    TEXT,
    session_label          TEXT,
    scheduled_local_at     TEXT,
    scheduled_utc_at       TEXT,
    table_no               TEXT,
    status                 TEXT NOT NULL DEFAULT 'scheduled',
    source_status          TEXT,
    source_schedule_status TEXT,
    match_score            TEXT,
    winner_side            TEXT,
    winner_team_code       TEXT,
    last_synced_at         TEXT,
    created_at             TEXT DEFAULT (datetime('now')),
    updated_at             TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
    CHECK (winner_side IN ('A', 'B') OR winner_side IS NULL),
    CHECK (status IN ('scheduled', 'live', 'completed', 'walkover', 'cancelled'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_event_team_ties_external
    ON current_event_team_ties(event_id, IFNULL(external_match_code, ''));
CREATE INDEX IF NOT EXISTS idx_current_event_team_ties_event
    ON current_event_team_ties(event_id, sub_event_type_code);
CREATE INDEX IF NOT EXISTS idx_current_event_team_ties_status
    ON current_event_team_ties(event_id, status);
CREATE INDEX IF NOT EXISTS idx_current_event_team_ties_round
    ON current_event_team_ties(event_id, stage_code, round_code);
CREATE INDEX IF NOT EXISTS idx_current_event_team_ties_group
    ON current_event_team_ties(event_id, group_code);

CREATE TABLE IF NOT EXISTS current_event_team_tie_sides (
    current_team_tie_side_id INTEGER PRIMARY KEY AUTOINCREMENT,
    current_team_tie_id      INTEGER NOT NULL,
    side_no                  INTEGER NOT NULL,
    team_code                TEXT,
    team_name                TEXT,
    seed                     INTEGER,
    qualifier                INTEGER,
    is_winner                INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (current_team_tie_id) REFERENCES current_event_team_ties(current_team_tie_id) ON DELETE CASCADE,
    CHECK (side_no IN (1, 2)),
    CHECK (is_winner IN (0, 1)),
    UNIQUE(current_team_tie_id, side_no)
);

CREATE INDEX IF NOT EXISTS idx_current_event_team_tie_sides_tie
    ON current_event_team_tie_sides(current_team_tie_id);
CREATE INDEX IF NOT EXISTS idx_current_event_team_tie_sides_team
    ON current_event_team_tie_sides(team_code);

CREATE TABLE IF NOT EXISTS current_event_team_tie_side_players (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    current_team_tie_side_id  INTEGER NOT NULL,
    player_order              INTEGER NOT NULL,
    player_id                 INTEGER,
    player_name               TEXT NOT NULL,
    player_country            TEXT,
    FOREIGN KEY (current_team_tie_side_id) REFERENCES current_event_team_tie_sides(current_team_tie_side_id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    UNIQUE(current_team_tie_side_id, player_order)
);

CREATE INDEX IF NOT EXISTS idx_current_event_team_tie_side_players_side
    ON current_event_team_tie_side_players(current_team_tie_side_id);
CREATE INDEX IF NOT EXISTS idx_current_event_team_tie_side_players_player
    ON current_event_team_tie_side_players(player_id);

CREATE TABLE IF NOT EXISTS current_event_matches (
    current_match_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id               INTEGER NOT NULL,
    current_team_tie_id    INTEGER,
    sub_event_type_code    TEXT NOT NULL,
    stage_label            TEXT,
    stage_code             TEXT,
    round_label            TEXT,
    round_code             TEXT,
    group_code             TEXT,
    external_match_code    TEXT,
    scheduled_local_at     TEXT,
    scheduled_utc_at       TEXT,
    table_no               TEXT,
    session_label          TEXT,
    status                 TEXT NOT NULL DEFAULT 'scheduled',
    source_status          TEXT,
    source_schedule_status TEXT,
    match_score            TEXT,
    games                  TEXT,
    winner_side            TEXT,
    winner_name            TEXT,
    raw_source_payload     TEXT,
    last_synced_at         TEXT,
    created_at             TEXT DEFAULT (datetime('now')),
    updated_at             TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (current_team_tie_id) REFERENCES current_event_team_ties(current_team_tie_id) ON DELETE SET NULL,
    FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
    CHECK (winner_side IN ('A', 'B') OR winner_side IS NULL),
    CHECK (status IN ('scheduled', 'live', 'completed', 'walkover', 'cancelled'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_event_matches_external
    ON current_event_matches(event_id, IFNULL(external_match_code, ''));
CREATE INDEX IF NOT EXISTS idx_current_event_matches_event
    ON current_event_matches(event_id, sub_event_type_code);
CREATE INDEX IF NOT EXISTS idx_current_event_matches_team_tie
    ON current_event_matches(current_team_tie_id);
CREATE INDEX IF NOT EXISTS idx_current_event_matches_status
    ON current_event_matches(event_id, status);
CREATE INDEX IF NOT EXISTS idx_current_event_matches_round
    ON current_event_matches(event_id, stage_code, round_code);

CREATE TABLE IF NOT EXISTS current_event_match_sides (
    current_match_side_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    current_match_id       INTEGER NOT NULL,
    side_no                INTEGER NOT NULL,
    team_code              TEXT,
    seed                   INTEGER,
    qualifier              INTEGER,
    placeholder_text       TEXT,
    is_winner              INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (current_match_id) REFERENCES current_event_matches(current_match_id) ON DELETE CASCADE,
    CHECK (side_no IN (1, 2)),
    CHECK (is_winner IN (0, 1)),
    UNIQUE(current_match_id, side_no)
);

CREATE INDEX IF NOT EXISTS idx_current_event_match_sides_match
    ON current_event_match_sides(current_match_id);

CREATE TABLE IF NOT EXISTS current_event_match_side_players (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    current_match_side_id   INTEGER NOT NULL,
    player_order            INTEGER NOT NULL,
    player_id               INTEGER,
    player_name             TEXT NOT NULL,
    player_country          TEXT,
    FOREIGN KEY (current_match_side_id) REFERENCES current_event_match_sides(current_match_side_id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    UNIQUE(current_match_side_id, player_order)
);

CREATE INDEX IF NOT EXISTS idx_current_event_match_side_players_side
    ON current_event_match_side_players(current_match_side_id);
CREATE INDEX IF NOT EXISTS idx_current_event_match_side_players_player
    ON current_event_match_side_players(player_id);

CREATE TABLE IF NOT EXISTS current_event_brackets (
    current_bracket_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id               INTEGER NOT NULL,
    sub_event_type_code    TEXT NOT NULL,
    draw_code              TEXT,
    bracket_code           TEXT,
    stage_code             TEXT,
    round_code             TEXT,
    round_order            INTEGER,
    bracket_position       INTEGER,
    external_unit_code     TEXT,
    scheduled_date         TEXT,
    scheduled_time         TEXT,
    match_score            TEXT,
    winner_side            TEXT,
    status                 TEXT,
    side_a_previous_unit   TEXT,
    side_b_previous_unit   TEXT,
    side_a_team_code       TEXT,
    side_b_team_code       TEXT,
    side_a_placeholder     TEXT,
    side_b_placeholder     TEXT,
    raw_source_payload     TEXT,
    last_synced_at         TEXT,
    created_at             TEXT DEFAULT (datetime('now')),
    updated_at             TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
    CHECK (winner_side IN ('A', 'B') OR winner_side IS NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_event_brackets_unit
    ON current_event_brackets(event_id, sub_event_type_code, IFNULL(external_unit_code, ''));
CREATE INDEX IF NOT EXISTS idx_current_event_brackets_event
    ON current_event_brackets(event_id, sub_event_type_code);
CREATE INDEX IF NOT EXISTS idx_current_event_brackets_round
    ON current_event_brackets(event_id, stage_code, round_code, round_order);

-- ============================================================================
-- 签表（来自 worldtabletennis.com Draws tab，按签位）
-- ============================================================================

CREATE TABLE IF NOT EXISTS event_draw_entries (
    entry_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id            INTEGER NOT NULL,
    sub_event_type_code TEXT NOT NULL,
    stage_code          TEXT NOT NULL,
    slot_index          INTEGER NOT NULL,      -- 在签表中的位置
    seed                INTEGER,
    group_code          TEXT,                  -- A/B/... 小组阶段
    team_code           TEXT,                  -- 团体赛 ISO-3
    placeholder_text    TEXT,                  -- 'Q1' / 'BYE' / 'TBD'
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (sub_event_type_code) REFERENCES sub_event_types(code),
    FOREIGN KEY (stage_code) REFERENCES stage_codes(code),
    UNIQUE(event_id, sub_event_type_code, stage_code, slot_index)
);

CREATE INDEX IF NOT EXISTS idx_event_draw_entries_event
    ON event_draw_entries(event_id, sub_event_type_code);

CREATE TABLE IF NOT EXISTS event_draw_entry_players (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id        INTEGER NOT NULL,
    player_order    INTEGER NOT NULL,
    player_id       INTEGER,                   -- 可空：未匹配球员
    player_name     TEXT NOT NULL,
    player_country  TEXT,
    FOREIGN KEY (entry_id) REFERENCES event_draw_entries(entry_id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    UNIQUE(entry_id, player_order)
);

CREATE INDEX IF NOT EXISTS idx_event_draw_entry_players_player
    ON event_draw_entry_players(player_id);

-- ============================================================================
-- 小组积分表（历史兼容）
-- current 赛事使用 current_event_group_standings
-- ============================================================================

CREATE TABLE IF NOT EXISTS event_group_standings (
    standing_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id             INTEGER NOT NULL,
    stage_label          TEXT NOT NULL,
    team_code            TEXT NOT NULL,       -- MTEAM / WTEAM
    group_code           TEXT NOT NULL,
    organization_code    TEXT NOT NULL,       -- ISO-3
    team_name            TEXT,
    qualification_mark   TEXT,
    played               INTEGER,
    won                  INTEGER,
    lost                 INTEGER,
    result               INTEGER,
    rank                 INTEGER,
    score_for            INTEGER,
    score_against        INTEGER,
    games_won            INTEGER,
    games_lost           INTEGER,
    players_json         TEXT,
    source_url           TEXT,
    updated_at           TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    UNIQUE(event_id, stage_label, team_code, group_code, organization_code)
);

CREATE INDEX IF NOT EXISTS idx_event_group_standings_event_team
    ON event_group_standings(event_id, team_code);
CREATE INDEX IF NOT EXISTS idx_event_group_standings_stage
    ON event_group_standings(event_id, stage_label, group_code, rank);
