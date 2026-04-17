import path from 'node:path';

export const ROOT_DIR = path.resolve(process.cwd(), '..');
export const DATA_DIR = path.join(ROOT_DIR, 'data');
export const MATCHES_DIR = path.join(DATA_DIR, 'matches_complete');
export const RANKING_FILE = path.join(DATA_DIR, 'women_singles_top50.json');
export const DB_FILE = path.join(DATA_DIR, 'db', 'ittf.db');
export const SCHEMA_FILE = path.join(ROOT_DIR, 'scripts', 'db', 'schema.sql');
