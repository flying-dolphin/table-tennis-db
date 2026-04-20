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
          m.winner_side AS winnerSide,
          sa.side_no AS playerASideNo,
          e.start_date AS startDate
        FROM matches m
        JOIN match_sides sa ON sa.match_id = m.match_id
        JOIN match_side_players spa ON spa.match_side_id = sa.match_side_id
        JOIN match_sides sb ON sb.match_id = m.match_id AND sb.side_no <> sa.side_no
        JOIN match_side_players spb ON spb.match_side_id = sb.match_side_id
        LEFT JOIN events e ON e.event_id = m.event_id
        WHERE spa.player_id = ?
          AND spb.player_id = ?
        ORDER BY COALESCE(e.start_date, '') DESC, COALESCE(m.event_year, 0) DESC, m.match_id DESC
      `,
    )
    .all(playerA.playerId, playerB.playerId) as Array<{
      matchId: number;
      eventId: number | null;
      eventName: string | null;
      eventNameZh: string | null;
      eventYear: number | null;
      round: string | null;
      roundZh: string | null;
      matchScore: string | null;
      winnerSide: string | null;
      playerASideNo: number;
      startDate: string | null;
    }>;

  const h2hMatchesWithWinner = h2hMatches.map((match) => {
    const playerAWin =
      (match.winnerSide === 'A' && match.playerASideNo === 1) ||
      (match.winnerSide === 'B' && match.playerASideNo === 2);
    const playerBWin =
      (match.winnerSide === 'A' && match.playerASideNo === 2) ||
      (match.winnerSide === 'B' && match.playerASideNo === 1);
    return {
      ...match,
      winnerId: playerAWin ? playerA.playerId : playerBWin ? playerB.playerId : null,
    };
  });

  const playerAWins = h2hMatches.filter((match) => {
    return (
      (match.winnerSide === 'A' && match.playerASideNo === 1) ||
      (match.winnerSide === 'B' && match.playerASideNo === 2)
    );
  }).length;
  const playerBWins = h2hMatches.filter((match) => {
    return (
      (match.winnerSide === 'A' && match.playerASideNo === 2) ||
      (match.winnerSide === 'B' && match.playerASideNo === 1)
    );
  }).length;
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
    headToHeadMatches: h2hMatchesWithWinner,
  };
}
