interface Bucket {
  count: number;
  resetAt: number;
}

const store = new Map<string, Bucket>();

/** Returns true if the request is allowed, false if rate-limited. */
export function rateLimit(key: string, maxCount: number, windowMs: number): boolean {
  const now = Date.now();
  const entry = store.get(key);

  if (!entry || entry.resetAt <= now) {
    store.set(key, { count: 1, resetAt: now + windowMs });
    return true;
  }

  if (entry.count >= maxCount) return false;
  entry.count += 1;
  return true;
}
