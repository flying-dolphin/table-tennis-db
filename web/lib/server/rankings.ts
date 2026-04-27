import { db } from '@/lib/server/db';
import { getPlayerAggregateStats } from '@/lib/server/stats';

type SortBy = 'points' | 'win_rate' | 'head_to_head_count';

type RankingRow = {
  playerId: number;
  rank: number;
  points: number;
  rankChange: number;
  slug: string;
  name: string;
  nameZh: string | null;
  country: string | null;
  countryCode: string;
  avatarFile: string | null;
  avatarUrl: string | null;
};

type RankingPlayerWithStats = RankingRow & {
  winRate: number;
  headToHeadCount: number;
};

type CachedStatsEntry = {
  snapshotId: number;
  playerCount: number;
  players: RankingPlayerWithStats[];
};

let cachedStatsEntry: CachedStatsEntry | null = null;

function resolveSortBy(sortBy?: string): SortBy {
  if (sortBy === 'win_rate' || sortBy === 'head_to_head_count') return sortBy;
  return 'points';
}

function loadRankingRows(snapshotId: number) {
  return db
    .prepare(
      `
        SELECT
          re.player_id AS playerId,
          re.rank,
          re.points,
          re.rank_change AS rankChange,
          p.slug,
          p.name,
          p.name_zh AS nameZh,
          p.country,
          p.country_code AS countryCode,
          REPLACE(REPLACE(p.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile,
          p.avatar_url AS avatarUrl
        FROM ranking_entries re
        JOIN players p ON p.player_id = re.player_id
        WHERE re.snapshot_id = ?
      `,
    )
    .all(snapshotId) as RankingRow[];
}

function loadRankingRowsWithStats(snapshotId: number) {
  const rankingRows = loadRankingRows(snapshotId);
  const cached = cachedStatsEntry;
  if (cached && cached.snapshotId === snapshotId && cached.playerCount === rankingRows.length) {
    return cached.players;
  }

  const statsMap = getPlayerAggregateStats(rankingRows.map((row) => row.playerId));
  const players = rankingRows.map((row) => {
    const stats = statsMap.get(row.playerId);
    return {
      ...row,
      winRate: stats?.winRate ?? 0,
      headToHeadCount: stats?.headToHeadCount ?? 0,
    };
  });

  cachedStatsEntry = {
    snapshotId,
    playerCount: rankingRows.length,
    players,
  };

  return players;
}

export function getRankings(category = 'women_singles', sortBy?: string, limit = 20, offset = 0) {
  const resolvedSortBy = resolveSortBy(sortBy);
  const snapshot = db
    .prepare(
      `
        SELECT snapshot_id AS snapshotId, ranking_week AS rankingWeek, ranking_date AS rankingDate
        FROM ranking_snapshots
        WHERE category = ?
        ORDER BY ranking_date DESC, snapshot_id DESC
        LIMIT 1
      `,
    )
    .get(category) as
    | {
        snapshotId: number;
        rankingWeek: string;
        rankingDate: string;
      }
    | undefined;

  if (!snapshot) {
    return {
      category,
      sortBy: resolvedSortBy,
      snapshot: null,
      players: [],
      hasMore: false,
      total: 0,
    };
  }

  const countResult = db
    .prepare('SELECT COUNT(*) as total FROM ranking_entries WHERE snapshot_id = ?')
    .get(snapshot.snapshotId) as { total: number };
  const total = countResult.total;

  if (resolvedSortBy === 'points') {
    const paginatedPlayers = db
      .prepare(
        `
          SELECT
            re.player_id AS playerId,
            re.rank,
            re.points,
            re.rank_change AS rankChange,
            p.slug,
            p.name,
            p.name_zh AS nameZh,
            p.country,
            p.country_code AS countryCode,
            REPLACE(REPLACE(p.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile,
            p.avatar_url AS avatarUrl
          FROM ranking_entries re
          JOIN players p ON p.player_id = re.player_id
          WHERE re.snapshot_id = ?
          ORDER BY re.points DESC, re.rank ASC
          LIMIT ? OFFSET ?
        `,
      )
      .all(snapshot.snapshotId, limit, offset)
      .map((row) => ({
        ...(row as {
          playerId: number;
          rank: number;
          points: number;
          rankChange: number;
          slug: string;
          name: string;
          nameZh: string | null;
          country: string | null;
          countryCode: string;
          avatarFile: string | null;
          avatarUrl: string | null;
        }),
        winRate: 0,
        headToHeadCount: 0,
      }));

    return {
      category,
      sortBy: resolvedSortBy,
      snapshot,
      players: paginatedPlayers,
      hasMore: offset + limit < total,
      total,
    };
  }

  const players = loadRankingRowsWithStats(snapshot.snapshotId).slice();

  players.sort((left, right) => {
    if (resolvedSortBy === 'win_rate') {
      return right.winRate - left.winRate || left.rank - right.rank;
    }
    return right.headToHeadCount - left.headToHeadCount || left.rank - right.rank;
  });

  const paginatedPlayers = players.slice(offset, offset + limit);
  const hasMore = offset + limit < total;

  return {
    category,
    sortBy: resolvedSortBy,
    snapshot,
    players: paginatedPlayers,
    hasMore,
    total,
  };
}
