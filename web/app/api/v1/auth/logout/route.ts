import { type NextRequest } from 'next/server';
import { ok } from '@/lib/server/api';
import { SESSION_COOKIE, deleteSession } from '@/lib/server/auth';

export async function POST(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) deleteSession(token);

  const response = ok(null);
  response.cookies.set(SESSION_COOKIE, '', {
    httpOnly: true,
    sameSite: 'lax',
    maxAge: 0,
    path: '/',
  });
  return response;
}
