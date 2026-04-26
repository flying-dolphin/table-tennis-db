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
    href                TEXT,
    scraped_at          TEXT,
    FOREIGN KEY (event_category_id) REFERENCES event_categories(id)
);

CREATE INDEX IF NOT EXISTS idx_events_year ON events(year);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(start_date);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(event_category_id);

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
    round               TEXT,
    round_zh            TEXT,
    side_a_key          TEXT NOT NULL,
    side_b_key          TEXT NOT NULL,
    match_score         TEXT,
    games               TEXT,
    winner_side         TEXT,
    winner_name         TEXT NOT NULL,
    raw_row_text        TEXT NOT NULL,
    scraped_at          TEXT,
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

CREATE TABLE IF NOT EXISTS event_draw_matches (
    draw_match_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id            INTEGER NOT NULL,
    event_id            INTEGER NOT NULL,
    sub_event_type_code TEXT NOT NULL,
    draw_stage          TEXT NOT NULL DEFAULT 'Main Draw',
    draw_round          TEXT NOT NULL,
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
