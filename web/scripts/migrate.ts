import fs from 'node:fs';
import path from 'node:path';
import { db } from '@/db/client';

const schemaPath = path.join(process.cwd(), 'db', 'schema.sql');
const sql = fs.readFileSync(schemaPath, 'utf-8');
db.exec(sql);
console.log('Database schema applied:', schemaPath);
