import { db } from '@/lib/server/db';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

const CORE_SUB_EVENT_CODES = ['WS', 'WD', 'WT', 'XD', 'XT'] as const;

type SidePlayer = {
  playerId: number | null;
  slug: string | null;
  name: string;
  nameZh: string | null;
  countryCode: string | null;
};

function isTeamEvent(event: { name: string; nameZh: string | null; eventKind: string | null; eventKindZh: string | null }) {
  const text = [event.name, event.nameZh, event.eventKind, event.eventKindZh].filter(Boolean).join(' ').toLowerCase();
  return text.includes('team') || text.includes('团体');
}

function parseChampionIds(value: string | null) {
  if (!value) return [];
  return value
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item));
}

function parseGames(value: string | null) {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((game) => {
        if (!game || typeof game !== 'object') return null;
        const record = game as { player?: unknown; opponent?: unknown };
        const player = Number(record.player);
        const opponent = Number(record.opponent);
        if (!Number.isFinite(player) || !Number.isFinite(opponent)) return null;
        return { player, opponent };
      })
      .filter((game): game is { player: number; opponent: number } => game != null);
  } catch {
    return [];
  }
}

function roundLabel(round: string | null, roundZh: string | null) {
  if (roundZh?.trim()) return roundZh;
  const labels: Record<string, string> = {
    Final: '决赛',
    SemiFinal: '半决赛',
    QuarterFinal: '四分之一决赛',
    R16: '16 强',
    R32: '32 强',
    R64: '64 强',
    R128: '128 强',
  };
  return labels[round ?? ''] ?? round ?? '轮次待补';
}

type EventChampion = {
  championName: string | null;
  championCountryCode: string | null;
  players: Array<{
    playerId: number;
    slug: string;
    name: string;
    nameZh: string | null;
    countryCode: string | null;
    avatarFile: string | null;
  }>;
};

type EventBracketRound = {
  code: string;
  label: string;
  order: number;
  matches: Array<{
    matchId: number;
    drawRound: string;
    roundLabel: string;
    roundOrder: number;
    matchScore: string | null;
    games: Array<{ player: number; opponent: number }>;
    sides: Array<{ sideNo: number; isWinner: boolean; players: SidePlayer[] }>;
  }>;
};

type TeamTie = {
  tieId: string;
  stage: string;
  stageZh: string | null;
  round: string;
  roundZh: string | null;
  teamA: { code: string; name: string; nameZh: string | null };
  teamB: { code: string; name: string; nameZh: string | null };
  scoreA: number;
  scoreB: number;
  winnerCode: string | null;
  rubbers: Array<{
    matchId: number;
    matchScore: string | null;
    winnerSide: string | null;
    sides: Array<{ sideNo: number; isWinner: boolean; players: SidePlayer[] }>;
  }>;
};

type StageStanding = {
  rank: number;
  teamCode: string;
  teamName: string;
  teamNameZh: string | null;
};

type RoundRobinStageGroup = {
  code: string;
  nameZh: string | null;
  teams: string[];
  ties: TeamTie[];
  standings?: StageStanding[];
};

type RoundRobinStage = {
  code: string;
  name: string;
  nameZh: string | null;
  format: 'group_round_robin' | 'round_robin';
  groups?: RoundRobinStageGroup[];
  ties?: TeamTie[];
  standings?: StageStanding[];
};

type EventRoundRobinView = {
  mode: 'staged_round_robin';
  stages: RoundRobinStage[];
  finalStandings: StageStanding[];
  podium: {
    champion: StageStanding | null;
    runnerUp: StageStanding | null;
    thirdPlace: StageStanding | null;
  };
};

type ManualEventOverride = {
  event_id: number;
  presentation_mode: 'staged_round_robin';
  sub_event_type_code: string;
  stages: Array<{
    code: string;
    name: string;
    name_zh: string | null;
    format: 'group_round_robin' | 'round_robin';
    groups?: Array<{
      code: string;
      name_zh: string | null;
      teams: string[];
    }>;
    qualified_teams?: string[];
  }>;
  final_standings: Array<{
    rank: number;
    team_code: string;
  }>;
  podium: {
    champion: string;
    runner_up: string;
    third_place: string;
  };
};

type EventPresentationMode = 'knockout' | 'staged_round_robin';

type EventListRow = {
  eventId: number;
  year: number;
  name: string;
  nameZh: string | null;
  eventTypeName: string | null;
  eventKind: string | null;
  eventKindZh: string | null;
  categoryCode: string | null;
  categoryNameZh: string | null;
  ageGroup: string | null;
  eventSeries: string | null;
  totalMatches: number | null;
  startDate: string | null;
  endDate: string | null;
  location: string | null;
  drawMatches: number;
  importedMatches: number;
};

function readManualEventOverride(eventId: number): ManualEventOverride | null {
  const file = path.join(process.cwd(), 'data', 'manual_event_overrides', `${eventId}.json`);
  if (!existsSync(file)) return null;
  try {
    return JSON.parse(readFileSync(file, 'utf-8')) as ManualEventOverride;
  } catch {
    return null;
  }
}

function dedupeCountryCodes(players: SidePlayer[]) {
  return Array.from(new Set(players.map((player) => player.countryCode).filter(Boolean))) as string[];
}

function teamCodeFromPlayers(players: SidePlayer[]) {
  const codes = dedupeCountryCodes(players);
  return codes.length === 1 ? codes[0] : null;
}

function teamLabelFromCode(code: string) {
  return { code, name: code, nameZh: null as string | null };
}

function buildStageStanding(teamCode: string, rank: number): StageStanding {
  return {
    rank,
    teamCode,
    teamName: teamCode,
    teamNameZh: null,
  };
}

function buildTeamTiesForSubEvent(eventId: number, subEventCode: string): TeamTie[] {
  const rows = db
    .prepare(
      `
        SELECT
          m.match_id AS matchId,
          COALESCE(m.stage, '') AS stage,
          m.stage_zh AS stageZh,
          COALESCE(m.round, '') AS round,
          m.round_zh AS roundZh,
          m.match_score AS matchScore,
          m.winner_side AS winnerSide,
          ms.side_no AS sideNo,
          ms.is_winner AS isWinner,
          msp.player_order AS playerOrder,
          msp.player_id AS playerId,
          msp.player_name AS playerName,
          msp.player_country AS playerCountry,
          p.slug,
          p.name_zh AS playerNameZh
        FROM matches m
        JOIN match_sides ms ON ms.match_id = m.match_id
        JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
        LEFT JOIN players p ON p.player_id = msp.player_id
        WHERE m.event_id = ?
          AND m.sub_event_type_code = ?
        ORDER BY m.stage ASC, m.round ASC, m.match_id ASC, ms.side_no ASC, msp.player_order ASC
      `,
    )
    .all(eventId, subEventCode) as Array<{
    matchId: number;
    stage: string;
    stageZh: string | null;
    round: string;
    roundZh: string | null;
    matchScore: string | null;
    winnerSide: string | null;
    sideNo: number;
    isWinner: number;
    playerOrder: number;
    playerId: number | null;
    playerName: string;
    playerCountry: string | null;
    slug: string | null;
    playerNameZh: string | null;
  }>;

  const matchMap = new Map<
    number,
    {
      matchId: number;
      stage: string;
      stageZh: string | null;
      round: string;
      roundZh: string | null;
      matchScore: string | null;
      winnerSide: string | null;
      sides: Array<{ sideNo: number; isWinner: boolean; players: SidePlayer[] }>;
    }
  >();

  for (const row of rows) {
    const current =
      matchMap.get(row.matchId) ??
      {
        matchId: row.matchId,
        stage: row.stage,
        stageZh: row.stageZh,
        round: row.round,
        roundZh: row.roundZh,
        matchScore: row.matchScore,
        winnerSide: row.winnerSide,
        sides: [],
      };

    let side = current.sides.find((item) => item.sideNo === row.sideNo);
    if (!side) {
      side = { sideNo: row.sideNo, isWinner: row.isWinner === 1, players: [] };
      current.sides.push(side);
    }

    side.players.push({
      playerId: row.playerId,
      slug: row.slug,
      name: row.playerName,
      nameZh: row.playerNameZh,
      countryCode: row.playerCountry,
    });
    matchMap.set(row.matchId, current);
  }

  const tieMap = new Map<string, TeamTie>();
  for (const match of matchMap.values()) {
    const [sideA, sideB] = [...match.sides].sort((left, right) => left.sideNo - right.sideNo);
    if (!sideA || !sideB) continue;

    const teamACode = teamCodeFromPlayers(sideA.players);
    const teamBCode = teamCodeFromPlayers(sideB.players);
    if (!teamACode || !teamBCode) continue;

    const key = [match.stage, match.round, teamACode, teamBCode].join('|');
    const current =
      tieMap.get(key) ??
      {
        tieId: key,
        stage: match.stage,
        stageZh: match.stageZh,
        round: match.round,
        roundZh: match.roundZh,
        teamA: teamLabelFromCode(teamACode),
        teamB: teamLabelFromCode(teamBCode),
        scoreA: 0,
        scoreB: 0,
        winnerCode: null,
        rubbers: [],
      };

    if (match.winnerSide === 'A') current.scoreA += 1;
    if (match.winnerSide === 'B') current.scoreB += 1;
    current.rubbers.push({
      matchId: match.matchId,
      matchScore: match.matchScore,
      winnerSide: match.winnerSide,
      sides: [sideA, sideB],
    });
    current.winnerCode =
      current.scoreA === current.scoreB ? null : current.scoreA > current.scoreB ? current.teamA.code : current.teamB.code;
    tieMap.set(key, current);
  }

  return Array.from(tieMap.values()).sort((left, right) => {
    const leftId = Math.min(...left.rubbers.map((rubber) => rubber.matchId));
    const rightId = Math.min(...right.rubbers.map((rubber) => rubber.matchId));
    return leftId - rightId;
  });
}

function buildRoundRobinView(eventId: number, subEventCode: string, override: ManualEventOverride): EventRoundRobinView {
  const ties = buildTeamTiesForSubEvent(eventId, subEventCode);
  const finalStandings = override.final_standings
    .slice()
    .sort((left, right) => left.rank - right.rank)
    .map((item) => buildStageStanding(item.team_code, item.rank));

  const podiumByCode = new Map(finalStandings.map((item) => [item.teamCode, item]));
  const stages: RoundRobinStage[] = override.stages.map((stage) => {
    if (stage.format === 'group_round_robin') {
      const groups: RoundRobinStageGroup[] = (stage.groups ?? []).map((group) => ({
        code: group.code,
        nameZh: group.name_zh,
        teams: group.teams,
        ties: ties.filter((tie) => tie.stage === stage.name && tie.round === group.code),
      }));
      return {
        code: stage.code,
        name: stage.name,
        nameZh: stage.name_zh,
        format: stage.format,
        groups,
      };
    }

    return {
      code: stage.code,
      name: stage.name,
      nameZh: stage.name_zh,
      format: stage.format,
      ties: ties.filter((tie) => tie.stage === stage.name),
      standings: finalStandings,
    };
  });

  return {
    mode: 'staged_round_robin',
    stages,
    finalStandings,
    podium: {
      champion: podiumByCode.get(override.podium.champion) ?? null,
      runnerUp: podiumByCode.get(override.podium.runner_up) ?? null,
      thirdPlace: podiumByCode.get(override.podium.third_place) ?? null,
    },
  };
}

export function getEvents(options?: {
  year?: number;
  includeAllYears?: boolean;
  keyword?: string;
  ageGroup?: 'senior' | 'non_senior' | 'all';
  limit?: number;
  offset?: number;
}) {
  const includeAllYears = options?.includeAllYears === true;
  const year = options?.year;
  const keyword = options?.keyword?.trim().toLowerCase() ?? '';
  const ageGroup = options?.ageGroup ?? 'senior';
  const limit = Math.max(1, Math.min(100, Math.floor(options?.limit ?? 20)));
  const offset = Math.max(0, Math.floor(options?.offset ?? 0));
  const ageGroupWhere: string[] = [];

  if (ageGroup === 'senior') {
    ageGroupWhere.push("UPPER(COALESCE(ec.age_group, 'SENIOR')) = 'SENIOR'");
  } else if (ageGroup === 'non_senior') {
    ageGroupWhere.push("UPPER(COALESCE(ec.age_group, 'SENIOR')) <> 'SENIOR'");
  }

  const availableYearsWhere = ['e.year >= 2014', '(ec.filtering_only IS NULL OR ec.filtering_only = 0)', ...ageGroupWhere];
  const availableYears = db
    .prepare(
      `
        SELECT DISTINCT e.year AS year
        FROM events e
        LEFT JOIN event_categories ec ON ec.id = e.event_category_id
        WHERE ${availableYearsWhere.join(' AND ')}
        ORDER BY e.year DESC
      `,
    )
    .all() as Array<{ year: number }>;
  const fallbackYear = availableYears[0]?.year ?? new Date().getFullYear();
  const requestedYear = year && year >= 2014 ? year : fallbackYear;
  const resolvedYear = availableYears.some((item) => item.year === requestedYear) ? requestedYear : fallbackYear;
  const where: string[] = ['e.year >= 2014', '(ec.filtering_only IS NULL OR ec.filtering_only = 0)'];
  const params: Array<number | string> = [];

  if (!includeAllYears) {
    where.push('e.year = ?');
    params.push(resolvedYear);
  }

  if (keyword) {
    where.push("(LOWER(e.name) LIKE ? OR LOWER(COALESCE(e.name_zh, '')) LIKE ?)");
    const like = `%${keyword}%`;
    params.push(like, like);
  }

  where.push(...ageGroupWhere);

  where.push(
    "NOT ((LOWER(e.name) LIKE '%男子%' OR LOWER(COALESCE(e.name_zh, '')) LIKE '%男子%') AND NOT (LOWER(e.name) LIKE '%女子%' OR LOWER(COALESCE(e.name_zh, '')) LIKE '%女子%'))"
  );

  const whereClause = where.join(' AND ');
  const totalRow = db
    .prepare(
      `
        SELECT COUNT(*) AS total
        FROM events e
        LEFT JOIN event_categories ec ON ec.id = e.event_category_id
        WHERE ${whereClause}
      `,
    )
    .get(...params) as { total: number };
  const total = totalRow?.total ?? 0;

  const events = db
    .prepare(
      `
        SELECT
          e.event_id AS eventId,
          e.year,
          e.name,
          e.name_zh AS nameZh,
          e.event_type_name AS eventTypeName,
          e.event_kind AS eventKind,
          e.event_kind_zh AS eventKindZh,
          e.category_code AS categoryCode,
          e.category_name_zh AS categoryNameZh,
          ec.age_group AS ageGroup,
          ec.event_series AS eventSeries,
          e.total_matches AS totalMatches,
          e.start_date AS startDate,
          e.end_date AS endDate,
          e.location,
          (
            SELECT COUNT(*)
            FROM event_draw_matches edm
            WHERE edm.event_id = e.event_id
          ) AS drawMatches,
          (
            SELECT COUNT(*)
            FROM matches m
            WHERE m.event_id = e.event_id
          ) AS importedMatches
        FROM events e
        LEFT JOIN event_categories ec ON ec.id = e.event_category_id
        WHERE ${whereClause}
        ORDER BY e.year DESC, COALESCE(e.start_date, '' ) DESC, e.event_id DESC
        LIMIT ? OFFSET ?
      `,
    )
    .all(...params, limit, offset) as EventListRow[];
  const eventsWithPresentation = events.map((event) => {
    const override = readManualEventOverride(event.eventId);
    const presentationMode: EventPresentationMode | null = override?.presentation_mode ?? (event.drawMatches > 0 ? 'knockout' : null);
    return {
      ...event,
      presentationMode,
      hasPresentation: presentationMode != null,
    };
  });
  const hasMore = offset + events.length < total;

  return {
    year: includeAllYears ? null : resolvedYear,
    minYear: 2014,
    availableYears: availableYears.map((item) => item.year),
    events: eventsWithPresentation,
    total,
    hasMore,
  };
}

export function getEventDetail(eventId: number, requestedSubEvent?: string | null) {
  const event = db
    .prepare(
      `
        SELECT
          event_id AS eventId,
          year,
          name,
          name_zh AS nameZh,
          event_type_name AS eventTypeName,
          event_kind AS eventKind,
          event_kind_zh AS eventKindZh,
          category_code AS categoryCode,
          category_name_zh AS categoryNameZh,
          total_matches AS totalMatches,
          start_date AS startDate,
          end_date AS endDate,
          location,
          href
        FROM events
        WHERE event_id = ?
      `,
    )
    .get(eventId) as
    | {
        eventId: number;
        year: number;
        name: string;
        nameZh: string | null;
        eventTypeName: string | null;
        eventKind: string | null;
        eventKindZh: string | null;
        categoryCode: string | null;
        categoryNameZh: string | null;
        totalMatches: number | null;
        startDate: string | null;
        endDate: string | null;
        location: string | null;
        href: string | null;
      }
    | undefined;

  if (!event) return null;

  const existingSubEvents = db
    .prepare(
      `
        SELECT
          se.sub_event_type_code AS code,
          st.name_zh AS nameZh,
          se.champion_player_ids AS championPlayerIds,
          se.champion_name AS championName,
          se.champion_country_code AS championCountryCode
        FROM sub_events se
        LEFT JOIN sub_event_types st ON st.code = se.sub_event_type_code
        WHERE se.event_id = ?
      `,
    )
    .all(eventId) as Array<{
    code: string;
    nameZh: string | null;
    championPlayerIds: string | null;
    championName: string | null;
    championCountryCode: string | null;
  }>;

  const drawCounts = db
    .prepare(
      `
        SELECT sub_event_type_code AS code, COUNT(*) AS matches
        FROM event_draw_matches
        WHERE event_id = ?
        GROUP BY sub_event_type_code
      `,
    )
    .all(eventId) as Array<{ code: string; matches: number }>;

  const matchCounts = db
    .prepare(
      `
        SELECT sub_event_type_code AS code, COUNT(*) AS matches
        FROM matches
        WHERE event_id = ?
        GROUP BY sub_event_type_code
      `,
    )
    .all(eventId) as Array<{ code: string; matches: number }>;

  const subEventNames = db
    .prepare('SELECT code, name_zh AS nameZh FROM sub_event_types')
    .all() as Array<{ code: string; nameZh: string | null }>;

  const nameMap = new Map(subEventNames.map((item) => [item.code, item.nameZh]));
  const existingMap = new Map(existingSubEvents.map((item) => [item.code, item]));
  const drawCountMap = new Map(drawCounts.map((item) => [item.code, item.matches]));
  const matchCountMap = new Map(matchCounts.map((item) => [item.code, item.matches]));
  const validCodes = new Set<string>(CORE_SUB_EVENT_CODES);
  const codesWithData = new Set<string>(
    [...drawCounts.map((item) => item.code), ...matchCounts.map((item) => item.code), ...existingSubEvents.map((item) => item.code)].filter(
      (code) => validCodes.has(code),
    ),
  );
  const preferredOrder: string[] = [...CORE_SUB_EVENT_CODES];
  const orderedCodes = Array.from(codesWithData).sort((a, b) => {
    const aIdx = preferredOrder.indexOf(a);
    const bIdx = preferredOrder.indexOf(b);
    if (aIdx >= 0 && bIdx >= 0) return aIdx - bIdx;
    if (aIdx >= 0) return -1;
    if (bIdx >= 0) return 1;
    return a.localeCompare(b);
  });

  const subEvents = orderedCodes.map((code) => {
    const record = existingMap.get(code);
    const drawMatches = drawCountMap.get(code) ?? 0;
    const importedMatches = matchCountMap.get(code) ?? 0;
    return {
      code,
      nameZh: nameMap.get(code) ?? code,
      disabled: drawMatches === 0 && importedMatches === 0,
      hasDraw: drawMatches > 0,
      drawMatches,
      importedMatches,
      championPlayerIds: parseChampionIds(record?.championPlayerIds ?? null),
      championName: record?.championName ?? null,
      championCountryCode: record?.championCountryCode ?? null,
    };
  });

  const override = readManualEventOverride(eventId);
  const preferredDefault = override?.sub_event_type_code ?? 'WS';
  const selectedSubEvent =
    requestedSubEvent && subEvents.some((item) => item.code === requestedSubEvent)
      ? requestedSubEvent
      : subEvents.find((item) => item.code === preferredDefault && !item.disabled)?.code ??
        subEvents.find((item) => !item.disabled)?.code ??
        preferredDefault;

  const championForSubEvent = (subEventCode: string): EventChampion | null => {
    const se = subEvents.find((item) => item.code === subEventCode);
    const playerIds = se?.championPlayerIds ?? [];
    const players =
      playerIds.length > 0
        ? (db
            .prepare(
              `
                SELECT
                  player_id AS playerId,
                  slug,
                  name,
                  name_zh AS nameZh,
                  country_code AS countryCode,
                  REPLACE(REPLACE(avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile
                FROM players
                WHERE player_id IN (${playerIds.map(() => '?').join(', ')})
              `,
            )
            .all(...playerIds) as Array<{
            playerId: number;
            slug: string;
            name: string;
            nameZh: string | null;
            countryCode: string | null;
            avatarFile: string | null;
          }>)
        : [];

    const overrideChampionCountry =
      override && subEventCode === override.sub_event_type_code ? override.podium.champion : null;

    if (!se && !overrideChampionCountry) return null;
    if (!se?.championName && players.length === 0 && !overrideChampionCountry) return null;

    return {
      championName: se?.championName ?? overrideChampionCountry,
      championCountryCode: se?.championCountryCode ?? overrideChampionCountry,
      players,
    };
  };

  const bracketForSubEvent = (subEventCode: string): EventBracketRound[] => {
    const drawRows = db
      .prepare(
        `
          SELECT
            edm.match_id AS matchId,
            edm.draw_round AS drawRound,
            edm.round_order AS roundOrder,
            m.round AS sourceRound,
            m.round_zh AS sourceRoundZh,
            m.match_score AS matchScore,
            m.games,
            ms.side_no AS sideNo,
            ms.is_winner AS isWinner,
            msp.player_order AS playerOrder,
            msp.player_id AS playerId,
            msp.player_name AS playerName,
            msp.player_country AS playerCountry,
            p.slug,
            p.name_zh AS playerNameZh
          FROM event_draw_matches edm
          JOIN matches m ON m.match_id = edm.match_id
          JOIN match_sides ms ON ms.match_id = m.match_id
          JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
          LEFT JOIN players p ON p.player_id = msp.player_id
          WHERE edm.event_id = ?
            AND edm.sub_event_type_code = ?
          ORDER BY edm.round_order DESC, edm.match_id ASC, ms.side_no ASC, msp.player_order ASC
        `,
      )
      .all(eventId, subEventCode) as Array<{
      matchId: number;
      drawRound: string;
      roundOrder: number;
      sourceRound: string | null;
      sourceRoundZh: string | null;
      matchScore: string | null;
      games: string | null;
      sideNo: number;
      isWinner: number;
      playerOrder: number;
      playerId: number | null;
      playerName: string;
      playerCountry: string | null;
      slug: string | null;
      playerNameZh: string | null;
    }>;

    const matchMap = new Map<
      number,
      {
        matchId: number;
        drawRound: string;
        roundLabel: string;
        roundOrder: number;
        matchScore: string | null;
        games: Array<{ player: number; opponent: number }>;
        sides: Array<{ sideNo: number; isWinner: boolean; players: SidePlayer[] }>;
      }
    >();

    for (const row of drawRows) {
      const current =
        matchMap.get(row.matchId) ??
        {
          matchId: row.matchId,
          drawRound: row.drawRound,
          roundLabel: roundLabel(row.sourceRound ?? row.drawRound, row.sourceRoundZh),
          roundOrder: row.roundOrder,
          matchScore: row.matchScore,
          games: parseGames(row.games),
          sides: [],
        };

      let side = current.sides.find((item) => item.sideNo === row.sideNo);
      if (!side) {
        side = { sideNo: row.sideNo, isWinner: row.isWinner === 1, players: [] };
        current.sides.push(side);
      }
      side.players.push({
        playerId: row.playerId,
        slug: row.slug,
        name: row.playerName,
        nameZh: row.playerNameZh,
        countryCode: row.playerCountry,
      });
      matchMap.set(row.matchId, current);
    }

    return Array.from(
      Array.from(matchMap.values())
        .reduce((map, match) => {
          const current = map.get(match.drawRound) ?? {
            code: match.drawRound,
            label: match.roundLabel,
            order: match.roundOrder,
            matches: [] as Array<(typeof match)>,
          };
          current.matches.push(match);
          map.set(match.drawRound, current);
          return map;
        }, new Map<string, { code: string; label: string; order: number; matches: Array<ReturnType<typeof matchMap.get> extends infer T ? NonNullable<T> : never> }>())
        .values(),
    ).sort((left, right) => right.order - left.order);
  };

  const roundRobinViewForSubEvent = (subEventCode: string): EventRoundRobinView | null => {
    if (!override || subEventCode !== override.sub_event_type_code) return null;
    return buildRoundRobinView(eventId, subEventCode, override);
  };

  const subEventDetails = subEvents.map((se) => ({
    code: se.code,
    champion: championForSubEvent(se.code),
    bracket: bracketForSubEvent(se.code),
    roundRobinView: roundRobinViewForSubEvent(se.code),
    presentationMode:
      override && se.code === override.sub_event_type_code ? ('staged_round_robin' as const) : ('knockout' as const),
  }));

  const dataForSelected = subEventDetails.find((item) => item.code === selectedSubEvent);

  return {
    event,
    subEvents,
    selectedSubEvent,
    subEventDetails,
    champion: dataForSelected?.champion ?? null,
    bracket: dataForSelected?.bracket ?? [],
    roundRobinView: dataForSelected?.roundRobinView ?? null,
    presentationMode: dataForSelected?.presentationMode ?? 'knockout',
  };
}

export function getMatchDetail(matchId: number) {
  const match = db
    .prepare(
      `
        SELECT
          m.match_id AS matchId,
          m.event_id AS eventId,
          m.event_name AS eventName,
          m.event_name_zh AS eventNameZh,
          m.event_year AS eventYear,
          m.sub_event_type_code AS subEventTypeCode,
          st.name_zh AS subEventNameZh,
          m.stage,
          m.stage_zh AS stageZh,
          m.round,
          m.round_zh AS roundZh,
          m.match_score AS matchScore,
          m.games,
          m.winner_side AS winnerSide,
          m.winner_name AS winnerName,
          e.start_date AS startDate,
          e.end_date AS endDate,
          e.name AS eventCanonicalName,
          e.name_zh AS eventCanonicalNameZh
        FROM matches m
        LEFT JOIN events e ON e.event_id = m.event_id
        LEFT JOIN sub_event_types st ON st.code = m.sub_event_type_code
        WHERE m.match_id = ?
      `,
    )
    .get(matchId) as
    | {
        matchId: number;
        eventId: number;
        eventName: string | null;
        eventNameZh: string | null;
        eventYear: number | null;
        subEventTypeCode: string;
        subEventNameZh: string | null;
        stage: string | null;
        stageZh: string | null;
        round: string | null;
        roundZh: string | null;
        matchScore: string | null;
        games: string | null;
        winnerSide: string | null;
        winnerName: string | null;
        startDate: string | null;
        endDate: string | null;
        eventCanonicalName: string | null;
        eventCanonicalNameZh: string | null;
      }
    | undefined;

  if (!match) return null;

  const sideRows = db
    .prepare(
      `
        SELECT
          ms.side_no AS sideNo,
          ms.is_winner AS isWinner,
          msp.player_order AS playerOrder,
          msp.player_id AS playerId,
          msp.player_name AS playerName,
          msp.player_country AS playerCountry,
          p.slug,
          p.name_zh AS playerNameZh,
          REPLACE(REPLACE(p.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile
        FROM match_sides ms
        JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
        LEFT JOIN players p ON p.player_id = msp.player_id
        WHERE ms.match_id = ?
        ORDER BY ms.side_no ASC, msp.player_order ASC
      `,
    )
    .all(matchId) as Array<{
    sideNo: number;
    isWinner: number;
    playerOrder: number;
    playerId: number | null;
    playerName: string;
    playerCountry: string | null;
    slug: string | null;
    playerNameZh: string | null;
    avatarFile: string | null;
  }>;

  const sideMap = new Map<
    number,
    {
      sideNo: number;
      isWinner: boolean;
      players: Array<SidePlayer & { avatarFile: string | null }>;
    }
  >();

  for (const row of sideRows) {
    const current = sideMap.get(row.sideNo) ?? {
      sideNo: row.sideNo,
      isWinner: row.isWinner === 1,
      players: [],
    };
    current.players.push({
      playerId: row.playerId,
      slug: row.slug,
      name: row.playerName,
      nameZh: row.playerNameZh,
      countryCode: row.playerCountry,
      avatarFile: row.avatarFile,
    });
    sideMap.set(row.sideNo, current);
  }

  return {
    match: {
      ...match,
      eventName: match.eventCanonicalName ?? match.eventName,
      eventNameZh: match.eventCanonicalNameZh ?? match.eventNameZh,
      roundLabel: roundLabel(match.round, match.roundZh),
      games: parseGames(match.games),
    },
    sides: Array.from(sideMap.values()),
  };
}
