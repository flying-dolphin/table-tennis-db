import { error, ok } from '@/lib/server/api';
import { getCompareData } from '@/lib/server/compare';

export function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const playerA = searchParams.get('player_a');
  const playerB = searchParams.get('player_b');

  if (!playerA || !playerB) {
    return error(400, 40001, 'player_a and player_b are required');
  }

  const result = getCompareData(playerA, playerB);
  if (!result) {
    return error(404, 40402, 'One or more players not found');
  }

  return ok(result);
}
