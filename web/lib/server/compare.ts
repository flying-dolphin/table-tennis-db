import { db } from '@/lib/server/db';
import { getPlayerAggregateStats } from '@/lib/server/stats';
import { getPlayerBySlug } from '@/lib/server/players';

export function getCompareData(playerASlug: string, playerBSlug: string) {
  const playerA = getPlayerBySlug(playerASlug);
  const playerB = getPlayerBySlug(playerBSlug);

  if (!playerA || !playerB) {
    return null;
  }

  const statsMap = getPlayerAggregateStats([playerA.playerId, playerB.playerId]);
  const playerAStats = statsMap.get(playerA.playerId);
  const playerBStats = statsMap.get(playerB.playerId);

  const h2hMatches = db
    .prepare(
      `
        SELECT
          m.match_id AS matchId,
          m.event_id AS eventId,
          m.event_name AS eventName,
          m.event_name_zh AS eventNameZh,
          m.event_year AS eventYear,
          m.round,
          m.round_zh AS roundZh,
          m.match_score AS matchScore,
          m.winner_id AS winnerId,
          e.start_date AS startDate
        FROM matches m
        LEFT JOIN events e ON e.event_id = m.event_id
        WHERE (m.player_a_id = ? AND m.player_b_id = ?)
           OR (m.player_a_id = ? AND m.player_b_id = ?)
        ORDER BY COALESCE(e.start_date, '') DESC, COALESCE(m.event_year, 0) DESC, m.match_id DESC
      `,
    )
    .all(playerA.playerId, playerB.playerId, playerB.playerId, playerA.playerId) as Array<{
      matchId: number;
      eventId: number | null;
      eventName: string | null;
      eventNameZh: string | null;
      eventYear: number | null;
      round: string | null;
      roundZh: string | null;
      matchScore: string | null;
      winnerId: number | null;
      startDate: string | null;
    }>;

  const playerAWins = h2hMatches.filter((match) => match.winnerId === playerA.playerId).length;
  const playerBWins = h2hMatches.filter((match) => match.winnerId === playerB.playerId).length;
  const total = h2hMatches.length;

  return {
    players: [
      {
        ...playerA,
        stats: playerAStats ?? null,
      },
      {
        ...playerB,
        stats: playerBStats ?? null,
      },
    ],
    headToHeadSummary: {
      totalMatches: total,
      playerA: {
        playerId: playerA.playerId,
        wins: playerAWins,
        winRate: total ? Number(((playerAWins / total) * 100).toFixed(2)) : 0,
      },
      playerB: {
        playerId: playerB.playerId,
        wins: playerBWins,
        winRate: total ? Number(((playerBWins / total) * 100).toFixed(2)) : 0,
      },
    },
    headToHeadMatches: h2hMatches,
  };
}
