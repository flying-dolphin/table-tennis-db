import { type NextRequest } from 'next/server';
import { ok, error } from '@/lib/server/api';
import { db } from '@/lib/server/db';
import { verifyPassword, createSession, SESSION_COOKIE } from '@/lib/server/auth';
import { rateLimit } from '@/lib/server/ratelimit';

export async function POST(request: NextRequest) {
  const ip = request.headers.get('x-forwarded-for') ?? 'local';
  if (!rateLimit(`login:${ip}`, 10, 15 * 60 * 1000)) {
    return error(429, 4290, '登录请求过于频繁，请 15 分钟后再试');
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return error(400, 4001, '请求格式错误');
  }

  const { email, password } = body as Record<string, unknown>;

  if (!email || typeof email !== 'string' || !password || typeof password !== 'string') {
    return error(400, 4002, '请填写邮箱和密码');
  }

  const user = db.prepare(`
    SELECT user_id, username, email, password_hash, salt
    FROM users WHERE email = ? COLLATE NOCASE
  `).get(email.trim()) as {
    user_id: number;
    username: string;
    email: string;
    password_hash: string;
    salt: string;
  } | null;

  if (!user || !verifyPassword(password, user.password_hash, user.salt)) {
    return error(401, 4011, '邮箱或密码错误');
  }

  const { token, maxAge } = createSession(user.user_id);

  const response = ok({ user_id: user.user_id, username: user.username, email: user.email });
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: 'lax',
    maxAge,
    path: '/',
  });
  return response;
}
