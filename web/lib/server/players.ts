import { db } from '@/lib/server/db';
import { getPlayerAggregateStats } from '@/lib/server/stats';

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
          m.sub_event_type_code AS subEventTypeCode,
          sety.name_zh AS subEventNameZh,
          m.stage,
          m.round,
          m.round_zh AS roundZh,
          m.match_score AS matchScore,
          m.winner_id AS winnerId,
          m.player_a_id AS playerAId,
          m.player_a_name AS playerAName,
          m.player_a_country AS playerACountry,
          m.player_b_id AS playerBId,
          m.player_b_name AS playerBName,
          m.player_b_country AS playerBCountry,
          e.start_date AS startDate
        FROM matches m
        LEFT JOIN events e ON e.event_id = m.event_id
        LEFT JOIN sub_event_types sety ON sety.code = m.sub_event_type_code
        WHERE m.player_a_id = ? OR m.player_b_id = ?
        ORDER BY COALESCE(e.start_date, '') DESC, COALESCE(m.event_year, 0) DESC, m.match_id DESC
      `,
    )
    .all(player.playerId, player.playerId) as Array<{
      matchId: number;
      eventId: number | null;
      eventName: string | null;
      eventNameZh: string | null;
      eventYear: number | null;
      subEventTypeCode: string | null;
      subEventNameZh: string | null;
      stage: string | null;
      round: string | null;
      roundZh: string | null;
      matchScore: string | null;
      winnerId: number | null;
      playerAId: number | null;
      playerAName: string;
      playerACountry: string | null;
      playerBId: number | null;
      playerBName: string | null;
      playerBCountry: string | null;
      startDate: string | null;
    }>;

  const recentMatches = matchRows.slice(0, 3).map((row) => {
    const isPlayerA = row.playerAId === player.playerId;
    const opponentName = isPlayerA ? row.playerBName : row.playerAName;
    const opponentCountry = isPlayerA ? row.playerBCountry : row.playerACountry;
    return {
      matchId: row.matchId,
      eventId: row.eventId,
      eventName: row.eventName,
      eventNameZh: row.eventNameZh,
      date: row.startDate ?? row.eventYear?.toString() ?? null,
      opponentName,
      opponentCountry,
      matchScore: row.matchScore,
      didWin: row.winnerId != null && row.winnerId === player.playerId,
    };
  });

  const eventMap = new Map<
    number,
    {
      eventId: number;
      eventName: string | null;
      eventNameZh: string | null;
      date: string | null;
      subEventTypeCode: string | null;
      subEventNameZh: string | null;
      result: string | null;
      weight: number;
      isChampion: boolean;
    }
  >();

  for (const row of matchRows) {
    if (row.eventId == null) continue;
    const current = eventMap.get(row.eventId);
    const weight = roundWeight(row.round);
    const isChampion = row.stage === 'Main Draw' && row.round === 'Final' && row.winnerId === player.playerId;

    if (!current || weight > current.weight || (isChampion && !current.isChampion)) {
      eventMap.set(row.eventId, {
        eventId: row.eventId,
        eventName: row.eventName,
        eventNameZh: row.eventNameZh,
        date: row.startDate ?? row.eventYear?.toString() ?? null,
        subEventTypeCode: row.subEventTypeCode,
        subEventNameZh: row.subEventNameZh,
        result: isChampion ? '冠军' : row.roundZh ?? row.round,
        weight,
        isChampion,
      });
    }
  }

  const events = Array.from(eventMap.values())
    .sort((left, right) => (right.date ?? '').localeCompare(left.date ?? ''))
    .map(({ weight: _weight, isChampion: _isChampion, ...event }) => event);

  const opponentMap = new Map<
    string,
    {
      playerId: number | null;
      slug: string | null;
      name: string;
      nameZh: string | null;
      countryCode: string | null;
      matches: number;
      wins: number;
      latestDate: string | null;
    }
  >();

  const relatedPlayerIds = new Set<number>();
  for (const row of matchRows) {
    const opponentId = row.playerAId === player.playerId ? row.playerBId : row.playerAId;
    if (opponentId != null) relatedPlayerIds.add(opponentId);
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

  for (const row of matchRows) {
    const isPlayerA = row.playerAId === player.playerId;
    const opponentId = isPlayerA ? row.playerBId : row.playerAId;
    const opponentName = isPlayerA ? row.playerBName : row.playerAName;
    const opponentCountry = isPlayerA ? row.playerBCountry : row.playerACountry;
    if (!opponentName) continue;

    const key = `${opponentId ?? 'unknown'}:${opponentName}`;
    const current =
      opponentMap.get(key) ??
      {
        playerId: opponentId,
        slug: opponentId != null ? relatedPlayerMap.get(opponentId)?.slug ?? null : null,
        name: opponentName,
        nameZh: opponentId != null ? relatedPlayerMap.get(opponentId)?.nameZh ?? null : null,
        countryCode: opponentCountry,
        matches: 0,
        wins: 0,
        latestDate: null,
      };

    current.matches += 1;
    if (row.winnerId != null && row.winnerId === player.playerId) {
      current.wins += 1;
    }
    current.latestDate =
      current.latestDate && row.startDate
        ? (current.latestDate > row.startDate ? current.latestDate : row.startDate)
        : current.latestDate ?? row.startDate ?? null;

    opponentMap.set(key, current);
  }

  const topOpponents = Array.from(opponentMap.values())
    .map((item) => ({
      ...item,
      winRate: item.matches ? Number(((item.wins / item.matches) * 100).toFixed(2)) : 0,
    }))
    .sort((left, right) => right.matches - left.matches || (right.latestDate ?? '').localeCompare(left.latestDate ?? ''))
    .slice(0, 3);

  return {
    player,
    stats,
    recentMatches,
    events,
    topOpponents,
  };
}
