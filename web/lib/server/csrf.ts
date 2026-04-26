import { type NextRequest } from 'next/server';

function normalizeOrigin(value: string): string | null {
  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

function getAllowedOrigin(request: NextRequest): string | null {
  const configuredOrigin = process.env.APP_ORIGIN?.trim();
  if (configuredOrigin) {
    return normalizeOrigin(configuredOrigin);
  }

  if (process.env.NODE_ENV !== 'production') {
    return normalizeOrigin(request.nextUrl.origin);
  }

  return null;
}

export function assertTrustedOrigin(request: NextRequest): { ok: true } | { ok: false; message: string } {
  const requestOrigin = request.headers.get('origin')?.trim();
  if (!requestOrigin) {
    return process.env.NODE_ENV === 'production'
      ? { ok: false, message: '缺少 Origin 请求头' }
      : { ok: true };
  }

  const normalizedRequestOrigin = normalizeOrigin(requestOrigin);
  const allowedOrigin = getAllowedOrigin(request);

  if (!normalizedRequestOrigin || !allowedOrigin) {
    return { ok: false, message: '非法的请求来源' };
  }

  if (normalizedRequestOrigin !== allowedOrigin) {
    return { ok: false, message: '跨站请求被拒绝' };
  }

  return { ok: true };
}
