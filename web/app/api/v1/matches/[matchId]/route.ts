import { error, ok } from '@/lib/server/api';
import { getMatchDetail } from '@/lib/server/events';

export async function GET(_: Request, { params }: { params: Promise<{ matchId: string }> }) {
  const { matchId } = await params;
  const parsedMatchId = Number(matchId);

  if (!Number.isFinite(parsedMatchId)) {
    return error(400, 40003, 'matchId must be a number');
  }

  const result = getMatchDetail(parsedMatchId);

  if (!result) {
    return error(404, 40404, 'Match not found');
  }

  return ok(result);
}
