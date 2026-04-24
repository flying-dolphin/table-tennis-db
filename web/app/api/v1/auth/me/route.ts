import { type NextRequest } from 'next/server';
import { ok, error } from '@/lib/server/api';
import { SESSION_COOKIE, getSessionUser } from '@/lib/server/auth';

export async function GET(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return error(401, 4011, '未登录');

  const user = getSessionUser(token);
  if (!user) return error(401, 4012, '登录已过期，请重新登录');

  return ok({
    user_id: user.user_id,
    username: user.username,
    email: user.email,
    created_at: user.created_at,
  });
}
