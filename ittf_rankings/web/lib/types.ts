export type RankingPlayer = {
  rank: number;
  change: number;
  name: string;
  english_name: string;
  country: string;
  country_code: string;
  continent: string;
  points: number;
};

export type RankingFile = {
  update_date: string;
  week: string;
  category: string;
  total_players: number;
  rankings: RankingPlayer[];
};

export type MatchRow = {
  round?: string;
  stage?: string;
  sub_event?: string;
  result_for_player?: string;
  match_score?: string;
  opponents?: string[];
  teammates?: string[];
  winner?: string;
  games?: Array<{ [key: string]: unknown }>;
  perspective?: string;
  raw_row_text?: string;
  side_a?: string;
  side_b?: string;
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
  player_id: string;
  player_name: string;
  country_code?: string;
  rank?: number;
  from_date?: string;
  captured_at?: string;
  created_at?: string;
  updated_at?: string;
  years: Record<string, { captured_at?: string; events: EventRow[] }>;
};
