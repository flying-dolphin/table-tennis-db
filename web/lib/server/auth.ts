import crypto from 'node:crypto';
import { db } from '@/lib/server/db';

export const SESSION_COOKIE = 'ittf_session';
export const SESSION_DAYS = 30;

function shouldUseSecureSessionCookie(): boolean {
  const override = process.env.SESSION_COOKIE_SECURE;
  if (override === 'true') return true;
  if (override === 'false') return false;
  return process.env.NODE_ENV === 'production';
}

export function getSessionCookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: shouldUseSecureSessionCookie(),
    maxAge,
    path: '/',
  };
}

export function getExpiredSessionCookieOptions() {
  return {
    ...getSessionCookieOptions(0),
    maxAge: 0,
  };
}

export function hashPassword(password: string): { hash: string; salt: string } {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.scryptSync(password, salt, 64).toString('hex');
  return { hash, salt };
}

export function verifyPassword(password: string, hash: string, salt: string): boolean {
  try {
    const verify = crypto.scryptSync(password, salt, 64).toString('hex');
    return crypto.timingSafeEqual(Buffer.from(hash, 'hex'), Buffer.from(verify, 'hex'));
  } catch {
    return false;
  }
}

export interface SessionUser {
  user_id: number;
  username: string;
  email: string;
  created_at: string;
}

export function getSessionUser(token: string): SessionUser | null {
  return db.prepare(`
    SELECT u.user_id, u.username, u.email, u.created_at
    FROM user_sessions s
    JOIN users u ON u.user_id = s.user_id
    WHERE s.token = ? AND s.expires_at > datetime('now')
  `).get(token) as SessionUser | null;
}

export function createSession(userId: number): { token: string; maxAge: number } {
  const token = crypto.randomBytes(32).toString('hex');
  const maxAge = SESSION_DAYS * 24 * 60 * 60;
  const expiresAt = new Date(Date.now() + maxAge * 1000).toISOString();
  db.prepare(`
    INSERT INTO user_sessions (user_id, token, expires_at) VALUES (?, ?, ?)
  `).run(userId, token, expiresAt);
  return { token, maxAge };
}

export function deleteSession(token: string): void {
  db.prepare('DELETE FROM user_sessions WHERE token = ?').run(token);
}

export const VERIFY_CODE_TTL_MS = 10 * 60 * 1000; // 10 minutes

export function createEmailCode(email: string): string {
  const code = String(Math.floor(100000 + Math.random() * 900000));
  const expiresAt = new Date(Date.now() + VERIFY_CODE_TTL_MS).toISOString();
  // Invalidate any prior unused codes for this email
  db.prepare("UPDATE email_verifications SET used = 1 WHERE email = ? COLLATE NOCASE AND used = 0").run(email);
  db.prepare("INSERT INTO email_verifications (email, code, expires_at) VALUES (?, ?, ?)").run(email.toLowerCase(), code, expiresAt);
  return code;
}

export function verifyEmailCode(email: string, code: string): boolean {
  const row = db.prepare(`
    SELECT id FROM email_verifications
    WHERE email = ? COLLATE NOCASE
      AND code = ?
      AND used = 0
      AND expires_at > datetime('now')
    ORDER BY id DESC LIMIT 1
  `).get(email.trim().toLowerCase(), code.trim()) as { id: number } | undefined;
  if (!row) return false;
  db.prepare("UPDATE email_verifications SET used = 1 WHERE id = ?").run(row.id);
  return true;
}
