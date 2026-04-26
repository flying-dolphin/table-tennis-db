import { type NextRequest } from 'next/server';
import { ok, error } from '@/lib/server/api';
import { assertTrustedOrigin } from '@/lib/server/csrf';
import { db } from '@/lib/server/db';
import { hashPassword, createSession, SESSION_COOKIE, verifyEmailCode, getSessionCookieOptions } from '@/lib/server/auth';
import { getClientIp, rateLimit } from '@/lib/server/ratelimit';

const USERNAME_RE = /^[a-zA-Z0-9][a-zA-Z0-9_]{2,19}$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export async function POST(request: NextRequest) {
  const originCheck = assertTrustedOrigin(request);
  if (!originCheck.ok) {
    return error(403, 4031, originCheck.message);
  }

  const ip = getClientIp(request);
  if (!rateLimit(`register:${ip}`, 5, 15 * 60 * 1000)) {
    return error(429, 4290, '注册请求过于频繁，请 15 分钟后再试');
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return error(400, 4001, '请求格式错误');
  }

  const { username, email, password, code } = body as Record<string, unknown>;

  if (!username || typeof username !== 'string' || username.trim() === '') {
    return error(400, 4002, '请输入用户名');
  }
  const trimmedUsername = username.trim();
  if (trimmedUsername.length < 3 || trimmedUsername.length > 20) {
    return error(400, 4003, '用户名长度需在 3-20 个字符之间');
  }
  if (!USERNAME_RE.test(trimmedUsername)) {
    return error(400, 4004, '用户名只能包含字母、数字和下划线，且须以字母或数字开头');
  }

  if (!email || typeof email !== 'string' || !EMAIL_RE.test(email.trim())) {
    return error(400, 4005, '请输入有效的邮箱地址');
  }
  const trimmedEmail = email.trim().toLowerCase();

  if (!password || typeof password !== 'string' || password.length < 8) {
    return error(400, 4006, '密码长度不能少于 8 个字符');
  }
  if (password.length > 50) {
    return error(400, 4007, '密码长度不能超过 50 个字符');
  }

  const existingEmail = db.prepare(
    'SELECT user_id FROM users WHERE email = ? COLLATE NOCASE'
  ).get(trimmedEmail);
  if (existingEmail) return error(409, 4091, '该邮箱已被注册');

  if (!code || typeof code !== 'string' || code.trim() === '') {
    return error(400, 4008, '请输入邮箱验证码');
  }
  if (!rateLimit(`verify-code-email:${trimmedEmail}`, 10, 10 * 60 * 1000)) {
    return error(429, 4292, '验证码校验过于频繁，请稍后再试');
  }
  if (!verifyEmailCode(trimmedEmail, code.trim())) {
    return error(400, 4009, '验证码错误或已过期');
  }

  const existingUsername = db.prepare(
    'SELECT user_id FROM users WHERE username = ? COLLATE NOCASE'
  ).get(trimmedUsername);
  if (existingUsername) return error(409, 4092, '该用户名已被使用');

  const { hash, salt } = hashPassword(password);
  const result = db.prepare(
    'INSERT INTO users (username, email, password_hash, salt) VALUES (?, ?, ?, ?)'
  ).run(trimmedUsername, trimmedEmail, hash, salt) as { lastInsertRowid: number | bigint };

  const userId = Number(result.lastInsertRowid);
  const { token, maxAge } = createSession(userId);

  const response = ok({ user_id: userId, username: trimmedUsername, email: trimmedEmail });
  response.cookies.set(SESSION_COOKIE, token, getSessionCookieOptions(maxAge));
  return response;
}
