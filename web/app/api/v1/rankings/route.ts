import { ok } from '@/lib/server/api';
import { getRankings } from '@/lib/server/rankings';

export function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const category = searchParams.get('category') ?? 'women_singles';
  const sortBy = searchParams.get('sort_by') ?? 'points';

  return ok(getRankings(category, sortBy));
}
