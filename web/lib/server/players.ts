import { db } from '@/lib/server/db';
import { isChampionRecord } from '@/lib/server/event-outcomes';
import { getPlayerAggregateStats } from '@/lib/server/stats';

type OpponentAggregate = {
  playerId: number | null;
  slug: string | null;
  name: string;
  nameZh: string | null;
  countryCode: string | null;
  matches: number;
  wins: number;
  latestDate: string | null;
};

type OpponentSortField = 'matches' | 'winRate';

function roundWeight(round: string | null) {
  const weights: Record<string, number> = {
    Final: 8,
    SemiFinal: 7,
    QuarterFinal: 6,
    R16: 5,
    R32: 4,
    R64: 3,
    R128: 2,
  };
  return weights[round ?? ''] ?? 1;
}

export function getPlayerBySlug(slug: string) {
  return db
    .prepare(
      `
        SELECT
          p.player_id AS playerId,
          p.name,
          p.name_zh AS nameZh,
          p.slug,
          p.country,
          p.country_code AS countryCode,
          p.gender,
          p.birth_year AS birthYear,
          p.age,
          p.style_zh AS styleZh,
          p.career_best_rank AS careerBestRank,
          p.career_best_month AS careerBestMonth,
          p.career_matches AS careerMatches,
          p.career_wins AS careerWins,
          p.year_events AS yearEvents,
          p.year_matches AS yearMatches,
          p.year_wins AS yearWins,
          REPLACE(REPLACE(p.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile,
          p.avatar_url AS avatarUrl,
          rs.ranking_date AS rankingDate,
          rs.ranking_week AS rankingWeek,
          re.rank,
          re.points,
          re.rank_change AS rankChange
        FROM players p
        LEFT JOIN ranking_entries re ON re.player_id = p.player_id
        LEFT JOIN ranking_snapshots rs ON rs.snapshot_id = re.snapshot_id
        WHERE p.slug = ?
        ORDER BY rs.ranking_date DESC, rs.snapshot_id DESC
        LIMIT 1
      `,
    )
    .get(slug) as
    | {
        playerId: number;
        name: string;
        nameZh: string | null;
        slug: string;
        country: string | null;
        countryCode: string;
        gender: string | null;
        birthYear: number | null;
        age: number | null;
        styleZh: string | null;
        careerBestRank: number | null;
        careerBestMonth: string | null;
        careerMatches: number | null;
        careerWins: number | null;
        yearEvents: number | null;
        yearMatches: number | null;
        yearWins: number | null;
        avatarFile: string | null;
        avatarUrl: string | null;
        rankingDate: string | null;
        rankingWeek: string | null;
        rank: number | null;
        points: number | null;
        rankChange: number | null;
      }
    | undefined;
}

export function searchPlayers(query?: string, limit = 12, excludeSlug?: string) {
  const resolvedLimit = Math.min(Math.max(limit, 1), 20);
  const keyword = query?.trim().toLowerCase() ?? '';
  const like = `%${keyword}%`;

  const latestSnapshot = db
    .prepare(
      `
        SELECT snapshot_id AS snapshotId
        FROM ranking_snapshots
        WHERE category = 'women_singles'
        ORDER BY ranking_date DESC, snapshot_id DESC
        LIMIT 1
      `,
    )
    .get() as { snapshotId: number } | undefined;

  if (!latestSnapshot) {
    return [];
  }

  const rows = db
    .prepare(
      `
        SELECT
          p.player_id AS playerId,
          p.slug,
          p.name,
          p.name_zh AS nameZh,
          p.country,
          p.country_code AS countryCode,
          REPLACE(REPLACE(p.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile,
          p.avatar_url AS avatarUrl,
          re.rank,
          re.points
        FROM players p
        LEFT JOIN ranking_entries re
          ON re.player_id = p.player_id
          AND re.snapshot_id = ?
        WHERE (? = '' OR LOWER(p.name) LIKE ? OR LOWER(COALESCE(p.name_zh, '')) LIKE ? OR LOWER(p.slug) LIKE ?)
          AND (? = '' OR p.slug <> ?)
        ORDER BY
          CASE
            WHEN ? <> '' AND LOWER(COALESCE(p.name_zh, '')) = ? THEN 0
            WHEN ? <> '' AND LOWER(p.name) = ? THEN 1
            WHEN ? <> '' AND LOWER(p.slug) = ? THEN 2
            WHEN ? <> '' AND LOWER(COALESCE(p.name_zh, '')) LIKE ? THEN 3
            WHEN ? <> '' AND LOWER(p.name) LIKE ? THEN 4
            WHEN ? <> '' AND LOWER(p.slug) LIKE ? THEN 5
            WHEN re.rank IS NOT NULL THEN 6
            ELSE 7
          END,
          CASE WHEN re.rank IS NULL THEN 999999 ELSE re.rank END ASC,
          p.name ASC
        LIMIT ?
      `,
    )
    .all(
      latestSnapshot.snapshotId,
      keyword,
      like,
      like,
      like,
      excludeSlug ?? '',
      excludeSlug ?? '',
      keyword,
      keyword,
      keyword,
      keyword,
      keyword,
      keyword,
      keyword,
      `${keyword}%`,
      keyword,
      `${keyword}%`,
      keyword,
      `${keyword}%`,
      resolvedLimit,
    ) as Array<{
      playerId: number;
      slug: string;
      name: string;
      nameZh: string | null;
      country: string | null;
      countryCode: string;
      avatarFile: string | null;
      avatarUrl: string | null;
      rank: number | null;
      points: number | null;
    }>;

  return rows;
}

function getPlayerOpponentAggregates(playerId: number) {
  const opponentRows = db
    .prepare(
      `
        SELECT
          m.match_id AS matchId,
          m.winner_side AS winnerSide,
          ms.side_no AS playerSideNo,
          e.start_date AS startDate,
          opp.player_id AS opponentId,
          opp.player_name AS opponentName,
          opp.player_country AS opponentCountry
        FROM matches m
        JOIN match_sides ms ON ms.match_id = m.match_id
        JOIN match_side_players self ON self.match_side_id = ms.match_side_id
        LEFT JOIN match_sides opps ON opps.match_id = m.match_id AND opps.side_no <> ms.side_no
        LEFT JOIN match_side_players opp ON opp.match_side_id = opps.match_side_id
        LEFT JOIN events e ON e.event_id = m.event_id
        WHERE self.player_id = ?
          AND m.sub_event_type_code = 'WS'
      `,
    )
    .all(playerId) as Array<{
    matchId: number;
    winnerSide: string | null;
    playerSideNo: number;
    startDate: string | null;
    opponentId: number | null;
    opponentName: string | null;
    opponentCountry: string | null;
  }>;

  const opponentMap = new Map<string, OpponentAggregate>();

  const relatedPlayerIds = new Set<number>();
  for (const row of opponentRows) {
    if (row.opponentId != null) {
      relatedPlayerIds.add(row.opponentId);
    }
  }

  const relatedPlayers = relatedPlayerIds.size
    ? (db
        .prepare(
          `
            SELECT player_id AS playerId, slug, name_zh AS nameZh
            FROM players
            WHERE player_id IN (${Array.from({ length: relatedPlayerIds.size }, () => '?').join(', ')})
          `,
        )
        .all(...Array.from(relatedPlayerIds)) as Array<{
        playerId: number;
        slug: string;
        nameZh: string | null;
      }>)
    : [];
  const relatedPlayerMap = new Map(relatedPlayers.map((item) => [item.playerId, item]));

  for (const row of opponentRows) {
    if (!row.opponentName) continue;

    const key = `${row.opponentId ?? 'unknown'}:${row.opponentName}`;
    const current =
      opponentMap.get(key) ??
      {
        playerId: row.opponentId,
        slug: row.opponentId != null ? relatedPlayerMap.get(row.opponentId)?.slug ?? null : null,
        name: row.opponentName,
        nameZh: row.opponentId != null ? relatedPlayerMap.get(row.opponentId)?.nameZh ?? null : null,
        countryCode: row.opponentCountry,
        matches: 0,
        wins: 0,
        latestDate: null,
      };

    current.matches += 1;
    const didWin =
      (row.winnerSide === 'A' && row.playerSideNo === 1) ||
      (row.winnerSide === 'B' && row.playerSideNo === 2);

    if (didWin) {
      current.wins += 1;
    }

    current.latestDate =
      current.latestDate && row.startDate
        ? (current.latestDate > row.startDate ? current.latestDate : row.startDate)
        : current.latestDate ?? row.startDate ?? null;

    opponentMap.set(key, current);
  }

  return Array.from(opponentMap.values()).map((item) => ({
    ...item,
    winRate: item.matches ? Number(((item.wins / item.matches) * 100).toFixed(2)) : 0,
  }));
}

export function getPlayerOpponents(
  slug: string,
  options?: {
    limit?: number;
    offset?: number;
    query?: string;
    sortBy?: OpponentSortField;
    sortOrder?: 'asc' | 'desc';
  },
) {
  const player = getPlayerBySlug(slug);
  if (!player) return null;

  const limit = Math.min(Math.max(options?.limit ?? 10, 1), 50);
  const offset = Math.max(options?.offset ?? 0, 0);
  const query = options?.query?.trim().toLowerCase() ?? '';
  const sortBy = options?.sortBy ?? 'matches';
  const sortOrder = options?.sortOrder ?? 'desc';

  const filtered = getPlayerOpponentAggregates(player.playerId).filter((item) => {
    if (!query) return true;
    return `${item.nameZh ?? ''} ${item.name}`.toLowerCase().includes(query);
  });

  filtered.sort((left, right) => {
    const direction = sortOrder === 'asc' ? 1 : -1;

    if (sortBy === 'winRate') {
      if (left.winRate !== right.winRate) {
        return (left.winRate - right.winRate) * direction;
      }
      if (left.matches !== right.matches) {
        return (left.matches - right.matches) * direction;
      }
    } else if (left.matches !== right.matches) {
      return (left.matches - right.matches) * direction;
    }

    return (right.latestDate ?? '').localeCompare(left.latestDate ?? '');
  });

  const items = filtered.slice(offset, offset + limit);

  return {
    items,
    total: filtered.length,
    limit,
    offset,
    hasMore: offset + items.length < filtered.length,
    sortBy,
    sortOrder,
    query: options?.query?.trim() ?? '',
  };
}

export function getPlayerDetail(slug: string) {
  const player = getPlayerBySlug(slug);
  if (!player) return null;

  const statsMap = getPlayerAggregateStats([player.playerId]);
  const stats = statsMap.get(player.playerId) ?? {
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
    sevenEvents: 0,
    sevenFinals: 0,
  };

  const matchRows = db
    .prepare(
      `
        SELECT
          m.match_id AS matchId,
          m.event_id AS eventId,
          m.event_name AS eventName,
          m.event_name_zh AS eventNameZh,
          m.event_year AS eventYear,
          ec.sort_order AS eventCategorySortOrder,
          ec.event_series AS eventSeries,
          e.category_name_zh AS categoryNameZh,
          m.sub_event_type_code AS subEventTypeCode,
          sety.name_zh AS subEventNameZh,
          m.stage,
          m.round,
          m.round_zh AS roundZh,
          m.match_score AS matchScore,
          m.winner_side AS winnerSide,
          self.player_country AS playerCountry,
          ms.side_no AS playerSideNo,
          GROUP_CONCAT(DISTINCT opp.player_name) AS opponentNames,
          GROUP_CONCAT(DISTINCT opp.player_country) AS opponentCountries,
          e.start_date AS startDate
        FROM matches m
        JOIN match_sides ms ON ms.match_id = m.match_id
        JOIN match_side_players self ON self.match_side_id = ms.match_side_id
        LEFT JOIN match_sides opps ON opps.match_id = m.match_id AND opps.side_no <> ms.side_no
        LEFT JOIN match_side_players opp ON opp.match_side_id = opps.match_side_id
        LEFT JOIN events e ON e.event_id = m.event_id
        LEFT JOIN event_categories ec ON ec.id = e.event_category_id
        LEFT JOIN sub_event_types sety ON sety.code = m.sub_event_type_code
        WHERE self.player_id = ?
        GROUP BY m.match_id, ms.side_no
        ORDER BY COALESCE(e.start_date, '') DESC, COALESCE(m.event_year, 0) DESC, m.match_id DESC
      `,
    )
    .all(player.playerId) as Array<{
      matchId: number;
      eventId: number | null;
      eventName: string | null;
      eventNameZh: string | null;
      eventYear: number | null;
      eventCategorySortOrder: number | null;
      eventSeries: string | null;
      categoryNameZh: string | null;
      subEventTypeCode: string | null;
      subEventNameZh: string | null;
      stage: string | null;
      round: string | null;
      roundZh: string | null;
      matchScore: string | null;
      winnerSide: string | null;
      playerCountry: string | null;
      playerSideNo: number;
      opponentNames: string | null;
      opponentCountries: string | null;
      startDate: string | null;
    }>;

  const eventMap = new Map<
    number,
    {
      eventId: number;
      eventName: string | null;
      eventNameZh: string | null;
      date: string | null;
      eventCategorySortOrder: number | null;
      eventSeries: string | null;
      categoryNameZh: string | null;
      subEvents: Map<
        string,
        {
          subEventTypeCode: string | null;
          subEventNameZh: string | null;
          result: string | null;
          weight: number;
          isChampion: boolean;
        }
      >;
    }
  >();

  for (const row of matchRows) {
    if (row.eventId == null) continue;
    const current =
      eventMap.get(row.eventId) ??
      {
        eventId: row.eventId,
        eventName: row.eventName,
        eventNameZh: row.eventNameZh,
        date: row.startDate ?? row.eventYear?.toString() ?? null,
        eventCategorySortOrder: row.eventCategorySortOrder,
        eventSeries: row.eventSeries,
        categoryNameZh: row.categoryNameZh,
        subEvents: new Map(),
      };
    const subEventKey = row.subEventTypeCode ?? 'unknown';
    const currentSubEvent = current.subEvents.get(subEventKey);
    const weight = roundWeight(row.round);
    const didWin =
      (row.winnerSide === 'A' && row.playerSideNo === 1) ||
      (row.winnerSide === 'B' && row.playerSideNo === 2);
    const isChampion = isChampionRecord({
      eventId: row.eventId,
      subEventTypeCode: row.subEventTypeCode,
      stage: row.stage,
      round: row.round,
      didWin,
      playerCountry: row.playerCountry,
    });

    if (!currentSubEvent || weight > currentSubEvent.weight || (isChampion && !currentSubEvent.isChampion)) {
      current.subEvents.set(subEventKey, {
        subEventTypeCode: row.subEventTypeCode,
        subEventNameZh: row.subEventNameZh,
        result: isChampion ? '冠军' : row.roundZh ?? row.round,
        weight,
        isChampion,
      });
    }

    eventMap.set(row.eventId, current);
  }

  const events = Array.from(eventMap.values())
    .sort((left, right) => (right.date ?? '').localeCompare(left.date ?? ''))
    .map((event) => ({
      eventId: event.eventId,
      eventName: event.eventName,
      eventNameZh: event.eventNameZh,
      date: event.date,
      eventCategorySortOrder: event.eventCategorySortOrder,
      eventSeries: event.eventSeries,
      categoryNameZh: event.categoryNameZh,
      subEvents: Array.from(event.subEvents.values())
        .sort((left, right) => right.weight - left.weight || Number(right.isChampion) - Number(left.isChampion))
        .map(({ weight: _weight, ...subEvent }) => subEvent),
    }));

  return {
    player,
    stats,
    events,
  };
}
