PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ranking_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category TEXT NOT NULL,
  week TEXT,
  update_date TEXT NOT NULL,
  total_players INTEGER NOT NULL,
  source_file TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS players (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_external_id TEXT UNIQUE,
  slug TEXT NOT NULL UNIQUE,
  chinese_name TEXT NOT NULL,
  english_name TEXT NOT NULL,
  country TEXT,
  country_code TEXT,
  continent TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rankings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id INTEGER NOT NULL,
  player_id INTEGER NOT NULL,
  rank INTEGER NOT NULL,
  points INTEGER NOT NULL,
  rank_change INTEGER NOT NULL DEFAULT 0,
  UNIQUE(snapshot_id, player_id),
  FOREIGN KEY (snapshot_id) REFERENCES ranking_snapshots(id) ON DELETE CASCADE,
  FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_match_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id INTEGER NOT NULL,
  source_file TEXT NOT NULL,
  captured_at TEXT,
  from_date TEXT,
  raw_payload JSON,
  UNIQUE(player_id, source_file),
  FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id INTEGER NOT NULL,
  source_id INTEGER,
  season INTEGER NOT NULL,
  event_name TEXT NOT NULL,
  event_type TEXT,
  detail_url TEXT,
  match_count INTEGER NOT NULL DEFAULT 0,
  raw_capture_file TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
  FOREIGN KEY (source_id) REFERENCES player_match_sources(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id INTEGER NOT NULL,
  player_id INTEGER NOT NULL,
  stage TEXT,
  round TEXT,
  sub_event TEXT,
  result TEXT,
  winner TEXT,
  perspective TEXT,
  match_score TEXT,
  opponents_json JSON,
  teammates_json JSON,
  games_json JSON,
  raw_row_text TEXT,
  side_a TEXT,
  side_b TEXT,
  all_players_json JSON,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
  FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rankings_snapshot_rank ON rankings(snapshot_id, rank);
CREATE INDEX IF NOT EXISTS idx_events_player_season ON events(player_id, season DESC);
CREATE INDEX IF NOT EXISTS idx_matches_player_result ON matches(player_id, result);
CREATE INDEX IF NOT EXISTS idx_matches_event ON matches(event_id);
