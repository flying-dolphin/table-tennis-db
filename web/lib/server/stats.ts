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
  sevenFinals: number;
};

type MutablePlayerAggregateStats = PlayerAggregateStats & {
  eventIds: Set<number>;
  sevenFinalEventKeys: Set<string>;
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
    sevenFinals: 0,
    eventIds: new Set<number>(),
    sevenFinalEventKeys: new Set<string>(),
  };
}

function finalizeStats(stats: MutablePlayerAggregateStats): PlayerAggregateStats {
  stats.headToHeadCount = stats.totalMatches;
  stats.eventsTotal = stats.eventIds.size;
  stats.winRate = rate(stats.totalWins, stats.totalMatches);
  stats.foreignWinRate = rate(stats.foreignWins, stats.foreignMatches);
  stats.domesticWinRate = rate(stats.domesticWins, stats.domesticMatches);

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
    sevenFinals: stats.sevenFinals,
  };
}

function parseChampionIds(raw: string | null) {
  if (!raw) return [];
  return raw.split(',').map((value) => value.trim()).filter(Boolean).map(Number);
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
          ec.sort_order
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
    }>;

  for (const row of matchRows) {
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

      stats.totalMatches += 1;
      if (row.winner_id != null && row.winner_id === side.playerId) {
        stats.totalWins += 1;
      }

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
      } else {
        stats.foreignMatches += 1;
        if (row.winner_id != null && row.winner_id === side.playerId) {
          stats.foreignWins += 1;
        }
      }

      if (
        row.event_id != null &&
        row.stage === 'Main Draw' &&
        row.round === 'Final' &&
        row.sort_order != null &&
        row.sort_order >= 1 &&
        row.sort_order <= 7
      ) {
        stats.sevenFinalEventKeys.add(`${row.event_id}:${row.sub_event_type_code ?? ''}`);
      }
    }
  }

  const titleRows = db
    .prepare(
      `
        SELECT
          se.event_id,
          se.sub_event_type_code,
          se.champion_player_ids,
          ec.sort_order
        FROM sub_events se
        JOIN events e ON e.event_id = se.event_id
        JOIN event_categories ec ON ec.id = e.event_category_id
        WHERE ec.sort_order >= 1
          AND ec.sort_order <= 7
      `,
    )
    .all() as Array<{
      event_id: number;
      sub_event_type_code: string;
      champion_player_ids: string | null;
      sort_order: number;
    }>;

  for (const row of titleRows) {
    const championIds = parseChampionIds(row.champion_player_ids);
    for (const championId of championIds) {
      const stats = statsMap.get(championId);
      if (!stats) continue;

      stats.sevenTitles += 1;
      if (row.sort_order <= 3) {
        stats.threeTitles += 1;
      }
    }
  }

  const finalized = new Map<number, PlayerAggregateStats>();
  for (const [playerId, stats] of statsMap.entries()) {
    stats.sevenFinals = stats.sevenFinalEventKeys.size;
    finalized.set(playerId, finalizeStats(stats));
  }

  return finalized;
}
