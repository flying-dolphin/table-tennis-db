import fs from 'node:fs';
import { db } from '@/lib/server/db';
import { SCHEMA_FILE } from '@/lib/paths';

db.pragma('journal_mode = WAL');

const sql = fs.readFileSync(SCHEMA_FILE, 'utf-8');
db.exec(sql);
console.log('Database schema applied:', SCHEMA_FILE);
