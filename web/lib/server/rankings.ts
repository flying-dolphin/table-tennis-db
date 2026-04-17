import { db } from '@/lib/server/db';
import { getPlayerAggregateStats } from '@/lib/server/stats';

type SortBy = 'points' | 'win_rate' | 'head_to_head_count';

function resolveSortBy(sortBy?: string): SortBy {
  if (sortBy === 'win_rate' || sortBy === 'head_to_head_count') return sortBy;
  return 'points';
}

export function getRankings(category = 'women_singles', sortBy?: string) {
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
    };
  }

  const rankingRows = db
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
          p.avatar_file AS avatarFile,
          p.avatar_url AS avatarUrl
        FROM ranking_entries re
        JOIN players p ON p.player_id = re.player_id
        WHERE re.snapshot_id = ?
      `,
    )
    .all(snapshot.snapshotId) as Array<{
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
    }>;

  const statsMap = getPlayerAggregateStats(rankingRows.map((row) => row.playerId));
  const players = rankingRows.map((row) => {
    const stats = statsMap.get(row.playerId);
    return {
      ...row,
      winRate: stats?.winRate ?? 0,
      headToHeadCount: stats?.headToHeadCount ?? 0,
    };
  });

  players.sort((left, right) => {
    if (resolvedSortBy === 'win_rate') {
      return right.winRate - left.winRate || left.rank - right.rank;
    }
    if (resolvedSortBy === 'head_to_head_count') {
      return right.headToHeadCount - left.headToHeadCount || left.rank - right.rank;
    }
    return right.points - left.points || left.rank - right.rank;
  });

  return {
    category,
    sortBy: resolvedSortBy,
    snapshot,
    players,
  };
}
