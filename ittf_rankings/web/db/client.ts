import fs from 'node:fs';
import path from 'node:path';
import Database from 'better-sqlite3';
import { DB_FILE } from '@/lib/paths';

const dbDir = path.dirname(DB_FILE);
if (!fs.existsSync(dbDir)) {
  fs.mkdirSync(dbDir, { recursive: true });
}

export const db = new Database(DB_FILE);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');
