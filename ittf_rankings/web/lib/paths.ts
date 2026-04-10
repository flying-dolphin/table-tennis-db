import path from 'node:path';

export const ROOT_DIR = path.resolve(process.cwd(), '..');
export const DATA_DIR = path.join(ROOT_DIR, 'data');
export const MATCHES_DIR = path.join(DATA_DIR, 'matches_complete');
export const RANKING_FILE = path.join(DATA_DIR, 'women_singles_top50.json');
export const DB_FILE = path.join(process.cwd(), 'db', 'ittf_rankings.sqlite');
