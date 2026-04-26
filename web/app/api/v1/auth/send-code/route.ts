import { type NextRequest } from 'next/server';
import { ok, error } from '@/lib/server/api';
import { assertTrustedOrigin } from '@/lib/server/csrf';
import { db } from '@/lib/server/db';
import { createEmailCode } from '@/lib/server/auth';
import { sendVerificationCode } from '@/lib/server/mailer';
import { getClientIp, rateLimit } from '@/lib/server/ratelimit';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export async function POST(request: NextRequest) {
  const originCheck = assertTrustedOrigin(request);
  if (!originCheck.ok) {
    return error(403, 4031, originCheck.message);
  }

  const ip = getClientIp(request);
  if (!rateLimit(`send-code:${ip}`, 5, 60 * 1000)) {
    return error(429, 4290, '发送过于频繁，请稍后再试');
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return error(400, 4001, '请求格式错误');
  }

  const { email } = body as Record<string, unknown>;
  if (!email || typeof email !== 'string' || !EMAIL_RE.test(email.trim())) {
    return error(400, 4005, '请输入有效的邮箱地址');
  }
  const trimmedEmail = email.trim().toLowerCase();

  // Per-email rate limit: 3 codes per 10 minutes
  if (!rateLimit(`send-code-email:${trimmedEmail}`, 3, 10 * 60 * 1000)) {
    return error(429, 4291, '该邮箱发送验证码过于频繁，请 10 分钟后再试');
  }

  // Check if email is already registered
  const existing = db.prepare('SELECT user_id FROM users WHERE email = ? COLLATE NOCASE').get(trimmedEmail);
  if (existing) {
    return ok({ sent: true });
  }

  const code = createEmailCode(trimmedEmail);

  try {
    await sendVerificationCode(trimmedEmail, code);
  } catch (err) {
    const detail = err instanceof Error ? err.message : 'unknown';
    console.error('[send-code] mail error:', detail);
    return error(500, 5001, '验证码发送失败，请检查邮箱地址或稍后重试');
  }

  return ok({ sent: true });
}
