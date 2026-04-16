-- ITTF 数据库 Schema
-- 日期: 2026-04-16
-- 数据库: SQLite

-- ============================================================================
-- 字典表
-- ============================================================================

CREATE TABLE IF NOT EXISTS event_types (
    event_type_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    name_zh         TEXT,
    code            TEXT,
    is_selected     INTEGER DEFAULT 0,
    sort_order      INTEGER DEFAULT 0
);

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
    json_code           TEXT,                   -- ranking JSON 中的缩写，如 "GS"
    points_tier         TEXT,                   -- Premium / High / Medium / Low / None
    points_eligible     INTEGER DEFAULT 0,
    filtering_only      INTEGER DEFAULT 0,
    applicable_formats  TEXT,                   -- JSON 数组
    ittf_rule_name      TEXT,
    notes               TEXT,
    sort_order          INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_event_categories_json_code ON event_categories(json_code);

CREATE TABLE IF NOT EXISTS event_type_mapping (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    event_kind      TEXT,
    event_kind_aliases TEXT,
    category_id     INTEGER NOT NULL,
    priority        INTEGER DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (category_id) REFERENCES event_categories(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_event_type_mapping_lookup ON event_type_mapping(event_type, event_kind, is_active, priority);

CREATE TABLE IF NOT EXISTS points_rules (
    rule_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_category      TEXT NOT NULL,
    event_category_zh   TEXT,
    sub_event_category  TEXT NOT NULL,
    draw_qualifier      TEXT,
    stage_type          TEXT NOT NULL,
    position            TEXT NOT NULL,
    points              INTEGER NOT NULL,
    effective_date      TEXT NOT NULL,
    UNIQUE(event_category, sub_event_category, draw_qualifier, stage_type, position, effective_date)
);

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
    career_best_week    TEXT,
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
    event_type_id       INTEGER,
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
    FOREIGN KEY (event_type_id) REFERENCES event_types(event_type_id),
    FOREIGN KEY (event_category_id) REFERENCES event_categories(id)
);

CREATE INDEX IF NOT EXISTS idx_events_year ON events(year);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type_id);
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
    player_a_id         INTEGER,
    player_a_name       TEXT NOT NULL,
    player_a_country    TEXT,
    player_b_id         INTEGER,
    player_b_name       TEXT,
    player_b_country    TEXT,
    match_score         TEXT,
    games               TEXT,
    winner_id           INTEGER,
    winner_name         TEXT NOT NULL,
    raw_row_text        TEXT NOT NULL,
    scraped_at          TEXT,
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (player_a_id) REFERENCES players(player_id),
    FOREIGN KEY (player_b_id) REFERENCES players(player_id),
    UNIQUE(event_id, sub_event_type_code, stage, round, player_a_id, player_b_id)
);

CREATE INDEX IF NOT EXISTS idx_matches_event ON matches(event_id);
CREATE INDEX IF NOT EXISTS idx_matches_player_a ON matches(player_a_id);
CREATE INDEX IF NOT EXISTS idx_matches_player_b ON matches(player_b_id);
CREATE INDEX IF NOT EXISTS idx_matches_winner ON matches(winner_id);
CREATE INDEX IF NOT EXISTS idx_matches_sub_event ON matches(sub_event_type_code);
CREATE INDEX IF NOT EXISTS idx_matches_year ON matches(event_year);

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
    event_type_code_zh TEXT,
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
