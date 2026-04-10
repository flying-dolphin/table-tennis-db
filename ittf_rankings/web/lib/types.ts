export type RankingPlayer = {
  rank: number;
  change: number;
  name: string;
  english_name: string;
  country: string;
  country_code: string;
  continent: string;
  points: number;
  player_id?: string | null;
  profile_url?: string | null;
};

export type RankingFile = {
  update_date: string;
  week: string;
  category: string;
  category_key?: string;
  total_players: number;
  rankings: RankingPlayer[];
};

export type MatchRow = {
  round?: string;
  stage?: string;
  sub_event?: string;
  result_for_player?: string;
  result?: string;
  match_score?: string;
  opponents?: string[];
  teammates?: string[];
  winner?: string;
  games?: Array<{ [key: string]: unknown }> | string[];
  perspective?: string;
  raw_row_text?: string;
  side_a?: string | string[];
  side_b?: string | string[];
  all_players_in_row?: string[];
};

export type EventRow = {
  event_name: string;
  event_type?: string;
  event_year: number;
  match_count: number;
  detail_url?: string;
  raw_capture_file?: string;
  matches: MatchRow[];
};

export type MatchFile = {
  player_id: string | null;
  player_name: string;
  english_name?: string;
  country?: string;
  country_code?: string;
  continent?: string;
  rank?: number;
  from_date?: string;
  captured_at?: string;
  created_at?: string;
  updated_at?: string;
  schema_version?: string;
  years: Record<string, { captured_at?: string; events: EventRow[] }>;
};

export type RegulationsFile = {
  source_url: string;
  discovery_method: string;
  pdf_links: string[];
  latest_pdf: string;
  downloaded_to?: string | null;
  pdf_hash?: string | null;
  markdown_path?: string | null;
  translation_prompt_path?: string | null;
};
