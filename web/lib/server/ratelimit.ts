import { type NextRequest } from 'next/server';

interface Bucket {
  count: number;
  resetAt: number;
}

interface RateLimitStore {
  get(key: string): Bucket | undefined;
  set(key: string, value: Bucket): void;
  delete(key: string): void;
  entries(): IterableIterator<[string, Bucket]>;
}

class MemoryRateLimitStore implements RateLimitStore {
  private readonly store = new Map<string, Bucket>();

  get(key: string) {
    return this.store.get(key);
  }

  set(key: string, value: Bucket) {
    this.store.set(key, value);
  }

  delete(key: string) {
    this.store.delete(key);
  }

  entries() {
    return this.store.entries();
  }
}

const store: RateLimitStore = new MemoryRateLimitStore();
let lastSweepAt = 0;
const SWEEP_INTERVAL_MS = 60 * 1000;

function sweepExpiredBuckets(now: number) {
  if (now - lastSweepAt < SWEEP_INTERVAL_MS) return;
  lastSweepAt = now;

  for (const [key, entry] of store.entries()) {
    if (entry.resetAt <= now) {
      store.delete(key);
    }
  }
}

function getTrustedProxyHeader(): string {
  return (process.env.TRUSTED_PROXY_IP_HEADER ?? 'cf-connecting-ip').trim().toLowerCase();
}

function isProxyHeaderTrusted(): boolean {
  return process.env.TRUST_PROXY_HEADERS === 'true';
}

function normalizeIp(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;

  const withoutPort = trimmed.startsWith('[')
    ? trimmed.replace(/^\[([^\]]+)\](?::\d+)?$/, '$1')
    : trimmed.replace(/:\d+$/, '');

  return withoutPort || null;
}

export function getClientIp(request: NextRequest): string {
  if (isProxyHeaderTrusted()) {
    const proxyHeader = getTrustedProxyHeader();
    const trustedValue = normalizeIp(request.headers.get(proxyHeader));
    if (trustedValue) return trustedValue;

    const forwardedFor = request.headers.get('x-forwarded-for');
    if (forwardedFor) {
      const firstHop = forwardedFor.split(',')[0];
      const forwardedIp = normalizeIp(firstHop);
      if (forwardedIp) return forwardedIp;
    }
  }

  return 'local';
}

/** Returns true if the request is allowed, false if rate-limited. */
export function rateLimit(key: string, maxCount: number, windowMs: number): boolean {
  const now = Date.now();
  sweepExpiredBuckets(now);
  const entry = store.get(key);

  if (!entry || entry.resetAt <= now) {
    store.set(key, { count: 1, resetAt: now + windowMs });
    return true;
  }

  if (entry.count >= maxCount) return false;
  entry.count += 1;
  return true;
}
