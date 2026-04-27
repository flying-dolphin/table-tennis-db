import { db } from '@/lib/server/db';

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
  winRate: number;
  headToHeadCount: number;
};

function resolveSortBy(sortBy?: string): SortBy {
  if (sortBy === 'win_rate' || sortBy === 'head_to_head_count') return sortBy;
  return 'points';
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

  let orderByClause = 'ORDER BY re.points DESC, re.rank ASC';
  if (resolvedSortBy === 'win_rate') {
    orderByClause = 'ORDER BY winRate DESC, re.rank ASC';
  } else if (resolvedSortBy === 'head_to_head_count') {
    orderByClause = 'ORDER BY headToHeadCount DESC, re.rank ASC';
  }

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
          p.avatar_url AS avatarUrl,
          IFNULL(ROUND((CAST(p.career_wins AS REAL) / NULLIF(p.career_matches, 0)) * 100, 2), 0) AS winRate,
          IFNULL(p.career_matches, 0) AS headToHeadCount
        FROM ranking_entries re
        JOIN players p ON p.player_id = re.player_id
        WHERE re.snapshot_id = ?
        ${orderByClause}
        LIMIT ? OFFSET ?
      `,
    )
    .all(snapshot.snapshotId, limit, offset) as RankingRow[];

  return {
    category,
    sortBy: resolvedSortBy,
    snapshot,
    players: paginatedPlayers,
    hasMore: offset + limit < total,
    total,
  };
}
