import { ok } from '@/lib/server/api';
import { getRankings } from '@/lib/server/rankings';

export function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const category = searchParams.get('category') ?? 'women_singles';
  const sortBy = searchParams.get('sort_by') ?? 'points';
  const limit = Math.min(parseInt(searchParams.get('limit') ?? '20', 10), 100);
  const offset = parseInt(searchParams.get('offset') ?? '0', 10);

  return ok(getRankings(category, sortBy, limit, offset));
}
