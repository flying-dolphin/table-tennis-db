import { ok } from '@/lib/server/api';
import { getHomeRankings } from '@/lib/server/home';

export function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const limitParam = Number(searchParams.get('limit') ?? '10');
  const category = searchParams.get('category') ?? 'women_singles';

  return ok(getHomeRankings(Number.isFinite(limitParam) ? limitParam : 10, category));
}
