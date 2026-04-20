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
          p.gender,
          p.birth_year AS birthYear,
          p.age,
          p.style_zh AS styleZh,
          p.career_best_rank AS careerBestRank,
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
          m.winner_side AS winnerSide,
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
      subEventTypeCode: string | null;
      subEventNameZh: string | null;
      stage: string | null;
      round: string | null;
      roundZh: string | null;
      matchScore: string | null;
      winnerSide: string | null;
      playerSideNo: number;
      opponentNames: string | null;
      opponentCountries: string | null;
      startDate: string | null;
    }>;

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
      `,
    )
    .all(player.playerId) as Array<{
    matchId: number;
    winnerSide: string | null;
    playerSideNo: number;
    startDate: string | null;
    opponentId: number | null;
    opponentName: string | null;
    opponentCountry: string | null;
  }>;

  const seenEventIds = new Set<number>();
  const recentMatches: Array<{
    matchId: number;
    eventId: number | null;
    eventName: string | null;
    eventNameZh: string | null;
    date: string | null;
    opponentName: string | null;
    opponentCountry: string | null;
    matchScore: string | null;
    didWin: boolean;
  }> = [];

  for (const row of matchRows) {
    if (row.eventId != null && seenEventIds.has(row.eventId)) continue;
    if (row.eventId != null) seenEventIds.add(row.eventId);

    const opponentName = row.opponentNames ? row.opponentNames.split(',').join(' / ') : null;
    const opponentCountry = row.opponentCountries ? row.opponentCountries.split(',').join(' / ') : null;
    const didWin =
      (row.winnerSide === 'A' && row.playerSideNo === 1) ||
      (row.winnerSide === 'B' && row.playerSideNo === 2);
    recentMatches.push({
      matchId: row.matchId,
      eventId: row.eventId,
      eventName: row.eventName,
      eventNameZh: row.eventNameZh,
      date: row.startDate ?? row.eventYear?.toString() ?? null,
      opponentName,
      opponentCountry,
      matchScore: row.matchScore,
      didWin,
    });

    if (recentMatches.length >= 3) break;
  }

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
    const isChampion =
      row.stage === 'Main Draw' &&
      row.round === 'Final' &&
      ((row.winnerSide === 'A' && row.playerSideNo === 1) || (row.winnerSide === 'B' && row.playerSideNo === 2));

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
  for (const row of opponentRows) {
    const opponentId = row.opponentId;
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

  for (const row of opponentRows) {
    const opponentId = row.opponentId;
    const opponentName = row.opponentName;
    const opponentCountry = row.opponentCountry;
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
