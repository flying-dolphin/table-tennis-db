import { error, ok } from '@/lib/server/api';
import { getPlayerDetail } from '@/lib/server/players';

export async function GET(_: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const player = getPlayerDetail(slug);

  if (!player) {
    return error(404, 40401, 'Player not found');
  }

  return ok(player);
}
