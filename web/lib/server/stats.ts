import { db } from '@/lib/server/db';

export type PlayerAggregateStats = {
  totalMatches: number;
  totalWins: number;
  winRate: number;
  headToHeadCount: number;
  foreignMatches: number;
  foreignWins: number;
  foreignWinRate: number;
  domesticMatches: number;
  domesticWins: number;
  domesticWinRate: number;
  eventsTotal: number;
  threeTitles: number;
  sevenTitles: number;
  singleThreeTitles: number;
  singleSevenTitles: number;
  allThreeTitles: number;
  allSevenTitles: number;
  sevenFinals: number;
};

type MutablePlayerAggregateStats = PlayerAggregateStats & {
  eventIds: Set<number>;
  sevenFinalEventKeys: Set<string>;
  singleThreeTitleKeys: Set<string>;
  singleSevenTitleKeys: Set<string>;
  allThreeTitleKeys: Set<string>;
  allSevenTitleKeys: Set<string>;
};

function placeholders(count: number) {
  return Array.from({ length: count }, () => '?').join(', ');
}

function rate(wins: number, total: number) {
  if (!total) return 0;
  return Number(((wins / total) * 100).toFixed(2));
}

function createStats(): MutablePlayerAggregateStats {
  return {
    totalMatches: 0,
    totalWins: 0,
    winRate: 0,
    headToHeadCount: 0,
    foreignMatches: 0,
    foreignWins: 0,
    foreignWinRate: 0,
    domesticMatches: 0,
    domesticWins: 0,
    domesticWinRate: 0,
    eventsTotal: 0,
    threeTitles: 0,
    sevenTitles: 0,
    singleThreeTitles: 0,
    singleSevenTitles: 0,
    allThreeTitles: 0,
    allSevenTitles: 0,
    sevenFinals: 0,
    eventIds: new Set<number>(),
    sevenFinalEventKeys: new Set<string>(),
    singleThreeTitleKeys: new Set<string>(),
    singleSevenTitleKeys: new Set<string>(),
    allThreeTitleKeys: new Set<string>(),
    allSevenTitleKeys: new Set<string>(),
  };
}

function finalizeStats(stats: MutablePlayerAggregateStats): PlayerAggregateStats {
  stats.eventsTotal = stats.eventIds.size;
  stats.winRate = rate(stats.totalWins, stats.totalMatches);
  stats.foreignWinRate = rate(stats.foreignWins, stats.foreignMatches);
  stats.domesticWinRate = rate(stats.domesticWins, stats.domesticMatches);
  stats.singleThreeTitles = stats.singleThreeTitleKeys.size;
  stats.singleSevenTitles = stats.singleSevenTitleKeys.size;
  stats.allThreeTitles = stats.allThreeTitleKeys.size;
  stats.allSevenTitles = stats.allSevenTitleKeys.size;
  stats.threeTitles = stats.singleThreeTitles;
  stats.sevenTitles = stats.singleSevenTitles;
  stats.sevenFinals = stats.sevenFinalEventKeys.size;

  return {
    totalMatches: stats.totalMatches,
    totalWins: stats.totalWins,
    winRate: stats.winRate,
    headToHeadCount: stats.headToHeadCount,
    foreignMatches: stats.foreignMatches,
    foreignWins: stats.foreignWins,
    foreignWinRate: stats.foreignWinRate,
    domesticMatches: stats.domesticMatches,
    domesticWins: stats.domesticWins,
    domesticWinRate: stats.domesticWinRate,
    eventsTotal: stats.eventsTotal,
    threeTitles: stats.threeTitles,
    sevenTitles: stats.sevenTitles,
    singleThreeTitles: stats.singleThreeTitles,
    singleSevenTitles: stats.singleSevenTitles,
    allThreeTitles: stats.allThreeTitles,
    allSevenTitles: stats.allSevenTitles,
    sevenFinals: stats.sevenFinals,
  };
}

export function getPlayerAggregateStats(playerIds: number[]) {
  const uniqueIds = Array.from(new Set(playerIds.filter((value) => Number.isFinite(value))));
  const statsMap = new Map<number, MutablePlayerAggregateStats>();

  for (const playerId of uniqueIds) {
    statsMap.set(playerId, createStats());
  }

  if (!uniqueIds.length) {
    return new Map<number, PlayerAggregateStats>();
  }

  const inClause = placeholders(uniqueIds.length);
  const playerRows = db
    .prepare(
      `
        SELECT
          player_id,
          career_matches,
          career_wins
        FROM players
        WHERE player_id IN (${inClause})
      `,
    )
    .all(...uniqueIds) as Array<{
      player_id: number;
      career_matches: number | null;
      career_wins: number | null;
    }>;

  for (const row of playerRows) {
    const stats = statsMap.get(row.player_id);
    if (!stats) continue;

    stats.totalMatches = row.career_matches ?? 0;
    stats.totalWins = row.career_wins ?? 0;
    stats.headToHeadCount = row.career_matches ?? 0;
  }

  const matchRows = db
    .prepare(
      `
        SELECT
          m.event_id,
          m.stage,
          m.round,
          m.player_a_id,
          m.player_a_country,
          m.player_b_id,
          m.player_b_country,
          m.winner_id,
          m.sub_event_type_code,
          ec.sort_order,
          ec.category_id
        FROM matches m
        LEFT JOIN events e ON e.event_id = m.event_id
        LEFT JOIN event_categories ec ON ec.id = e.event_category_id
        WHERE m.player_a_id IN (${inClause}) OR m.player_b_id IN (${inClause})
      `,
    )
    .all(...uniqueIds, ...uniqueIds) as Array<{
      event_id: number | null;
      stage: string | null;
      round: string | null;
      player_a_id: number | null;
      player_a_country: string | null;
      player_b_id: number | null;
      player_b_country: string | null;
      winner_id: number | null;
      sub_event_type_code: string | null;
      sort_order: number | null;
      category_id: string | null;
    }>;

  for (const row of matchRows) {
    const categoryId = row.category_id?.toUpperCase() ?? '';
    if (categoryId.includes('YOUTH') || categoryId.includes('JUNIOR') || categoryId.includes('CADET')) {
      continue;
    }

    const sides = [
      {
        playerId: row.player_a_id,
        opponentCountry: row.player_b_country,
      },
      {
        playerId: row.player_b_id,
        opponentCountry: row.player_a_country,
      },
    ];

    for (const side of sides) {
      if (side.playerId == null || !statsMap.has(side.playerId)) continue;
      const stats = statsMap.get(side.playerId)!;

      if (row.event_id != null) {
        stats.eventIds.add(row.event_id);
      }

      const playerCountry =
        side.playerId === row.player_a_id ? row.player_a_country ?? null : row.player_b_country ?? null;
      const opponentCountry = side.opponentCountry ?? null;

      if (playerCountry && opponentCountry && playerCountry === opponentCountry) {
        stats.domesticMatches += 1;
        if (row.winner_id != null && row.winner_id === side.playerId) {
          stats.domesticWins += 1;
        }
      } else if (playerCountry && opponentCountry) {
        stats.foreignMatches += 1;
        if (row.winner_id != null && row.winner_id === side.playerId) {
          stats.foreignWins += 1;
        }
      }

      const eventKey =
        row.event_id != null ? `${row.event_id}:${row.sub_event_type_code ?? ''}` : null;

      if (
        eventKey &&
        row.stage === 'Main Draw' &&
        row.round === 'Final' &&
        row.sort_order != null &&
        row.sort_order >= 1 &&
        row.sort_order <= 9
      ) {
        stats.sevenFinalEventKeys.add(eventKey);
        if (row.winner_id === side.playerId) {
          stats.allSevenTitleKeys.add(eventKey);
          if (row.sort_order <= 5) {
            stats.allThreeTitleKeys.add(eventKey);
          }
          if (row.sub_event_type_code === 'WS') {
            stats.singleSevenTitleKeys.add(eventKey);
            if (row.sort_order <= 5) {
              stats.singleThreeTitleKeys.add(eventKey);
            }
          }
        }
      }
    }
  }

  const finalized = new Map<number, PlayerAggregateStats>();
  for (const [playerId, stats] of statsMap.entries()) {
    finalized.set(playerId, finalizeStats(stats));
  }

  return finalized;
}
