import { error, ok } from '@/lib/server/api';
import { getPlayerOpponents } from '@/lib/server/players';

export async function GET(request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const { searchParams } = new URL(request.url);

  const limit = Number(searchParams.get('limit') ?? '10');
  const offset = Number(searchParams.get('offset') ?? '0');
  const query = searchParams.get('q') ?? '';
  const sortByParam = searchParams.get('sortBy');
  const sortOrderParam = searchParams.get('sortOrder');
  const sortBy = sortByParam === 'winRate' ? 'winRate' : 'matches';
  const sortOrder = sortOrderParam === 'asc' ? 'asc' : 'desc';

  const result = getPlayerOpponents(slug, {
    limit: Number.isFinite(limit) ? limit : 10,
    offset: Number.isFinite(offset) ? offset : 0,
    query,
    sortBy,
    sortOrder,
  });

  if (!result) {
    return error(404, 40401, 'Player not found');
  }

  return ok(result);
}
