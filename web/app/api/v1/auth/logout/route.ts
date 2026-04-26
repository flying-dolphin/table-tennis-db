import { type NextRequest } from 'next/server';
import { ok } from '@/lib/server/api';
import { error } from '@/lib/server/api';
import { SESSION_COOKIE, deleteSession, getExpiredSessionCookieOptions } from '@/lib/server/auth';
import { assertTrustedOrigin } from '@/lib/server/csrf';

export async function POST(request: NextRequest) {
  const originCheck = assertTrustedOrigin(request);
  if (!originCheck.ok) {
    return error(403, 4031, originCheck.message);
  }

  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) deleteSession(token);

  const response = ok(null);
  response.cookies.set(SESSION_COOKIE, '', getExpiredSessionCookieOptions());
  return response;
}
