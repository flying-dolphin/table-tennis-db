import { ok } from '@/lib/server/api';
import { searchPlayers } from '@/lib/server/players';

export function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get('q') ?? '';
  const excludeSlug = searchParams.get('exclude_slug') ?? '';
  const limit = Math.min(Math.max(parseInt(searchParams.get('limit') ?? '12', 10) || 12, 1), 20);

  return ok({
    items: searchPlayers(query, limit, excludeSlug || undefined),
    query,
  });
}
