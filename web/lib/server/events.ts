import { db } from '@/lib/server/db';
import { expandEventQuery } from '@/lib/server/query-rewrite';
import { filterAvatarFile } from '@/lib/server/avatarManifest';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

const CORE_SUB_EVENT_CODES = ['WS', 'MS', 'WD', 'MD', 'WT', 'MT', 'XD', 'XT', 'JWS', 'JWD', 'JWT'] as const;

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

function loadPlayersByIds(playerIds: number[]): ChampionPlayer[] {
  if (playerIds.length === 0) return [];

  const rows = db
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
    .all(...playerIds) as ChampionPlayer[];

  const rowMap = new Map(
    rows.map((player) => [player.playerId, { ...player, avatarFile: filterAvatarFile(player.avatarFile) }]),
  );
  return playerIds.map((playerId) => rowMap.get(playerId)).filter((player): player is ChampionPlayer => Boolean(player));
}

function loadPlayerDisplayMap(playerIds: number[]) {
  if (playerIds.length === 0) return new Map<number, { slug: string | null; nameZh: string | null; avatarFile: string | null }>();

  const rows = db
    .prepare(
      `
        SELECT
          player_id AS playerId,
          slug,
          name_zh AS nameZh,
          REPLACE(REPLACE(avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile
        FROM players
        WHERE player_id IN (${playerIds.map(() => '?').join(', ')})
      `,
    )
    .all(...playerIds) as Array<{
    playerId: number;
    slug: string | null;
    nameZh: string | null;
    avatarFile: string | null;
  }>;

  return new Map(
    rows.map((row) => [
      row.playerId,
      {
        slug: row.slug,
        nameZh: row.nameZh,
        avatarFile: filterAvatarFile(row.avatarFile),
      },
    ]),
  );
}

function loadTeamChampionPlayers(eventId: number, subEventCode: string, championCountryCode: string | null): ChampionPlayer[] {
  if (!championCountryCode) return [];

  const rows = db
    .prepare(
      `
        SELECT
          p.player_id AS playerId,
          p.slug AS slug,
          p.name AS name,
          p.name_zh AS nameZh,
          p.country_code AS countryCode,
          REPLACE(REPLACE(p.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile,
          COUNT(*) AS appearances
        FROM matches m
        JOIN match_sides ms ON ms.match_id = m.match_id
        JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
        JOIN players p ON p.player_id = msp.player_id
        WHERE m.event_id = ?
          AND m.sub_event_type_code = ?
          AND p.country_code = ?
        GROUP BY p.player_id, p.slug, p.name, p.name_zh, p.country_code, p.avatar_file
        ORDER BY appearances DESC, p.player_id ASC
      `,
    )
    .all(eventId, subEventCode, championCountryCode) as ChampionPlayer[];

  return rows.map((row) => ({ ...row, avatarFile: filterAvatarFile(row.avatarFile) }));
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
  const normalizedRound = round?.trim() ?? '';
  const normalizedRoundZh = roundZh?.trim() ?? '';
  const labels: Record<string, string> = {
    Final: '决赛',
    Bronze: '铜牌赛',
    SemiFinal: '半决赛',
    QuarterFinal: '四分之一决赛',
    R16: '16 强',
    R32: '32 强',
    R64: '64 强',
    R128: '128 强',
  };

  if (labels[normalizedRound]) return labels[normalizedRound];
  if (normalizedRoundZh) return normalizedRoundZh;
  return normalizedRound || '轮次待补';
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

type ChampionPlayer = EventChampion['players'][number];

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

type EventSessionScheduleRow = {
  id: number;
  dayIndex: number;
  localDate: string;
  startLocalTime: string | null;
  endLocalTime: string | null;
  venueRaw: string | null;
  tableCount: number | null;
  rawSubEventsText: string | null;
  parsedRoundsJson: string | null;
};

type EventScheduleDay = {
  localDate: string;
  matches: EventScheduleMatch[];
};

type EventScheduleMatch = {
  scheduleMatchId: number;
  externalMatchCode: string | null;
  subEventTypeCode: string;
  subEventNameZh: string | null;
  stageCode: string;
  stageNameZh: string | null;
  roundCode: string;
  roundNameZh: string | null;
  groupCode: string | null;
  scheduledLocalAt: string | null;
  scheduledUtcAt: string | null;
  tableNo: string | null;
  sessionLabel: string | null;
  status: string;
  rawScheduleStatus: string | null;
  matchScore: string | null;
  games: Array<{ player: number; opponent: number }>;
  winnerSide: string | null;
  sides: Array<{
    sideNo: number;
    entryId: number | null;
    placeholderText: string | null;
    teamCode: string | null;
    seed: number | null;
    qualifier: boolean | null;
    isWinner: boolean;
    players: SidePlayer[];
  }>;
};

function scheduleMatchStatusPriority(status: string) {
  switch (status) {
    case 'completed':
    case 'walkover':
      return 4;
    case 'live':
      return 3;
    case 'scheduled':
      return 2;
    case 'cancelled':
      return 1;
    default:
      return 0;
  }
}

function scheduleSideCompleteness(side: EventScheduleMatch['sides'][number]) {
  return side.players.length * 10 + (side.teamCode ? 2 : 0) + (side.placeholderText ? 1 : 0);
}

function scheduleMatchCompleteness(match: EventScheduleMatch) {
  return (
    (match.matchScore ? 100 : 0) +
    match.games.length * 5 +
    match.sides.reduce((sum, side) => sum + scheduleSideCompleteness(side), 0) +
    (match.tableNo ? 2 : 0) +
    (match.sessionLabel ? 1 : 0)
  );
}

function pickPreferredScheduleMatch(left: EventScheduleMatch, right: EventScheduleMatch) {
  const statusDiff = scheduleMatchStatusPriority(left.status) - scheduleMatchStatusPriority(right.status);
  if (statusDiff !== 0) return statusDiff > 0 ? left : right;

  const completenessDiff = scheduleMatchCompleteness(left) - scheduleMatchCompleteness(right);
  if (completenessDiff !== 0) return completenessDiff > 0 ? left : right;

  return left.scheduleMatchId >= right.scheduleMatchId ? left : right;
}

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
  matches?: number;
  wins?: number;
  losses?: number;
  tiePoints?: number;
  scoreFor?: number;
  scoreAgainst?: number;
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

type EventTeamKnockoutView = {
  mode: 'team_knockout_with_bronze';
  rounds: Array<{
    code: string;
    label: string;
    order: number;
    ties: TeamTie[];
  }>;
  finalStandings: StageStanding[];
  podium: {
    champion: StageStanding | null;
    runnerUp: StageStanding | null;
    thirdPlace: StageStanding | null;
    thirdPlaceSecond: StageStanding | null;
  };
  finalTie: TeamTie | null;
  bronzeTie: TeamTie | null;
};

type RoundRobinEventOverride = {
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

type TeamKnockoutEventOverride = {
  event_id: number;
  presentation_mode: 'team_knockout_with_bronze';
  sub_event_type_code: string;
  final_standings: Array<{
    rank: number;
    team_code: string;
  }>;
  podium: {
    champion: string;
    runner_up: string;
    third_place: string;
  };
  ties: {
    final: {
      team_codes: [string, string];
    };
    bronze: {
      team_codes: [string, string];
    };
  };
};

type ManualEventOverride = RoundRobinEventOverride | TeamKnockoutEventOverride;

type EventPresentationMode = 'knockout' | 'staged_round_robin' | 'team_knockout_with_bronze';

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
  lifecycleStatus: string | null;
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

type OfficialScheduleResult = {
  externalMatchCode: string;
  teamCodes: [string, string] | null;
  scoreA: number | null;
  scoreB: number | null;
  winnerCode: string | null;
  matchScore: string | null;
  games: Array<{ player: number; opponent: number }>;
  rubbers: Array<{
    externalMatchCode: string | null;
    matchScore: string | null;
    games: Array<{ player: number; opponent: number }>;
    winnerSide: string | null;
    sides: Array<{
      sideNo: number;
      teamCode: string | null;
      players: Array<{
        playerId: number | null;
        name: string;
        countryCode: string | null;
      }>;
    }>;
  }>;
};

function normalizeExternalMatchCode(value: string | null | undefined) {
  return value?.replace(/-+$/g, '').trim() ?? '';
}

function parseTieScore(value: string | null | undefined) {
  if (!value) return null;
  const match = value.match(/(\d+)\s*-\s*(\d+)/);
  if (!match) return null;
  return {
    scoreA: Number(match[1]),
    scoreB: Number(match[2]),
  };
}

function parseScoreSequence(value: string | null | undefined) {
  if (!value) return [];
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const match = item.match(/(-?\d+)\s*-\s*(-?\d+)/);
      if (!match) return null;
      return { player: Number(match[1]), opponent: Number(match[2]) };
    })
    .filter((item): item is { player: number; opponent: number } => item != null && !(item.player === 0 && item.opponent === 0));
}

function parseOfficialWinnerSide(score: string | null | undefined) {
  const parsed = parseTieScore(score);
  if (!parsed) return null;
  if (parsed.scoreA === parsed.scoreB) return null;
  return parsed.scoreA > parsed.scoreB ? 'A' : 'B';
}

function flipWinnerSide(winnerSide: string | null | undefined) {
  if (winnerSide === 'A') return 'B';
  if (winnerSide === 'B') return 'A';
  return null;
}

function reverseScoreLabel(score: string | null | undefined) {
  const parsed = parseTieScore(score);
  if (!parsed) return score ?? null;
  return `${parsed.scoreB}-${parsed.scoreA}`;
}

function reverseGames(games: Array<{ player: number; opponent: number }>) {
  return games.map((game) => ({ player: game.opponent, opponent: game.player }));
}

function shouldFlipTeamOrder(
  officialTeamCodes: [string, string] | null | undefined,
  displayTeamCodes: [string | null | undefined, string | null | undefined],
) {
  if (!officialTeamCodes) return false;
  const [officialA, officialB] = officialTeamCodes;
  const [displayA, displayB] = displayTeamCodes;
  if (!displayA || !displayB) return false;
  return officialA === displayB && officialB === displayA;
}

function parseOfficialCompetitorPlayers(
  competitor: {
    competitiorId?: string | null;
    competitiorName?: string | null;
    competitiorOrg?: string | null;
    players?: Array<{
      playerId?: string | null;
      playerName?: string | null;
      playerOrgCode?: string | null;
    }> | null;
  } | null | undefined,
) {
  const players = (competitor?.players ?? [])
    .map((player) => {
      const rawId = Number(player.playerId);
      return {
        playerId: Number.isFinite(rawId) ? rawId : null,
        name: player.playerName?.trim() || competitor?.competitiorName?.trim() || 'Unknown',
        countryCode: player.playerOrgCode?.trim() || competitor?.competitiorOrg?.trim() || null,
      };
    })
    .filter((player) => Boolean(player.name));

  if (players.length > 0) return players;

  return competitor?.competitiorName
    ? [
        {
          playerId: Number.isFinite(Number(competitor.competitiorId)) ? Number(competitor.competitiorId) : null,
          name: competitor.competitiorName.trim(),
          countryCode: competitor.competitiorOrg?.trim() || null,
        },
      ]
    : [];
}

function enrichOfficialPlayers<T extends { playerId: number | null; name: string; countryCode: string | null }>(
  players: T[],
  playerMap: Map<number, { slug: string | null; nameZh: string | null; avatarFile: string | null }>,
) {
  return players.map((player) => {
    const meta = player.playerId != null ? playerMap.get(player.playerId) : undefined;
    return {
      ...player,
      slug: meta?.slug ?? null,
      nameZh: meta?.nameZh ?? null,
      avatarFile: meta?.avatarFile ?? null,
    };
  });
}

function readOfficialScheduleResults(eventId: number) {
  const candidateFiles = [
    path.join(process.cwd(), 'data', 'wtt_raw', String(eventId), 'GetOfficialResult.json'),
    path.join(process.cwd(), 'data', 'wtt_raw', String(eventId), 'GetOfficialResult_take10.json'),
    path.join(process.cwd(), '..', 'data', 'wtt_raw', String(eventId), 'GetOfficialResult.json'),
    path.join(process.cwd(), '..', 'data', 'wtt_raw', String(eventId), 'GetOfficialResult_take10.json'),
  ];
  const file = candidateFiles.find((candidate) => existsSync(candidate));
  if (!file) return new Map<string, OfficialScheduleResult>();

  try {
    const parsed = JSON.parse(readFileSync(file, 'utf-8')) as unknown;
    if (!Array.isArray(parsed)) return new Map<string, OfficialScheduleResult>();

    const results = new Map<string, OfficialScheduleResult>();
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue;
      const record = item as {
        documentCode?: string | null;
        match_card?: {
          documentCode?: string | null;
          competitiors?: Array<{ competitiorOrg?: string | null }>;
          overallScores?: string | null;
          resultOverallScores?: string | null;
          gameScores?: string | null;
          resultsGameScores?: string | null;
          teamParentData?: {
            extended_info?: {
              final_result?: Array<{ value?: string | null }>;
            } | null;
          } | null;
        } | null;
      };
      const externalMatchCode = normalizeExternalMatchCode(record.documentCode ?? record.match_card?.documentCode ?? null);
      if (!externalMatchCode) continue;

      const teamCodes = (record.match_card?.competitiors ?? [])
        .map((competitor) => competitor.competitiorOrg?.trim() ?? '')
        .filter(Boolean)
        .slice(0, 2) as string[];
      const scoreLabel =
        record.match_card?.teamParentData?.extended_info?.final_result?.[0]?.value ??
        record.match_card?.overallScores ??
        record.match_card?.resultOverallScores ??
        null;
      const parsedScore = parseTieScore(scoreLabel);
      const winnerCode =
        parsedScore && teamCodes.length === 2
          ? parsedScore.scoreA === parsedScore.scoreB
            ? null
            : parsedScore.scoreA > parsedScore.scoreB
              ? teamCodes[0]
              : teamCodes[1]
          : null;
      const topLevelGames = parseScoreSequence(record.match_card?.resultsGameScores ?? record.match_card?.gameScores ?? null);
      const rubbers = (((record.match_card?.teamParentData as {
        extended_info?: {
          matches?: Array<{
            match_result?: {
              documentCode?: string | null;
              overallScores?: string | null;
              resultOverallScores?: string | null;
              gameScores?: string | null;
              resultsGameScores?: string | null;
              competitiors?: Array<{
                competitiorId?: string | null;
                competitiorName?: string | null;
                competitiorOrg?: string | null;
                players?: Array<{
                  playerId?: string | null;
                  playerName?: string | null;
                  playerOrgCode?: string | null;
                }> | null;
              }> | null;
            } | null;
          }>;
        };
      } | null)?.extended_info?.matches) ?? [])
        .map((item) => {
          const matchResult = item?.match_result;
          if (!matchResult) return null;
          const competitors = (matchResult.competitiors ?? []).slice(0, 2);
          return {
            externalMatchCode: normalizeExternalMatchCode(matchResult.documentCode ?? null) || null,
            matchScore: matchResult.resultOverallScores ?? matchResult.overallScores ?? null,
            games: parseScoreSequence(matchResult.resultsGameScores ?? matchResult.gameScores ?? null),
            winnerSide: parseOfficialWinnerSide(matchResult.resultOverallScores ?? matchResult.overallScores ?? null),
            sides: competitors.map((competitor, index) => ({
              sideNo: index + 1,
              teamCode: competitor.competitiorOrg?.trim() || null,
              players: parseOfficialCompetitorPlayers(competitor),
            })),
          };
        })
        .filter(
          (
            rubber,
          ): rubber is {
            externalMatchCode: string | null;
            matchScore: string | null;
            games: Array<{ player: number; opponent: number }>;
            winnerSide: string | null;
            sides: Array<{
              sideNo: number;
              teamCode: string | null;
              players: Array<{
                playerId: number | null;
                name: string;
                countryCode: string | null;
              }>;
            }>;
          } => rubber != null,
        );

      results.set(externalMatchCode, {
        externalMatchCode,
        teamCodes: teamCodes.length === 2 ? [teamCodes[0], teamCodes[1]] : null,
        scoreA: parsedScore?.scoreA ?? null,
        scoreB: parsedScore?.scoreB ?? null,
        winnerCode,
        matchScore: scoreLabel,
        games: topLevelGames,
        rubbers,
      });
    }

    return results;
  } catch {
    return new Map<string, OfficialScheduleResult>();
  }
}

function isRoundRobinOverride(override: ManualEventOverride): override is RoundRobinEventOverride {
  return override.presentation_mode === 'staged_round_robin';
}

function isTeamKnockoutOverride(override: ManualEventOverride): override is TeamKnockoutEventOverride {
  return override.presentation_mode === 'team_knockout_with_bronze';
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
  if (!isRoundRobinOverride(override)) {
    throw new Error(`Expected staged_round_robin override for event ${eventId}`);
  }
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

export function getScheduleMatchDetail(scheduleMatchId: number) {
  const match = db
    .prepare(
      `
        SELECT
          esm.schedule_match_id AS scheduleMatchId,
          esm.event_id AS eventId,
          e.name AS eventName,
          e.name_zh AS eventNameZh,
          e.year AS eventYear,
          esm.sub_event_type_code AS subEventTypeCode,
          st.name_zh AS subEventNameZh,
          esm.stage_code AS stageCode,
          sc.name_zh AS stageNameZh,
          esm.round_code AS roundCode,
          rc.name_zh AS roundNameZh,
          esm.group_code AS groupCode,
          esm.scheduled_local_at AS scheduledLocalAt,
          esm.scheduled_utc_at AS scheduledUtcAt,
          esm.table_no AS tableNo,
          esm.session_label AS sessionLabel,
          esm.status,
          esm.raw_schedule_status AS rawScheduleStatus,
          esm.match_score AS matchScore,
          esm.games,
          esm.winner_side AS winnerSide,
          esm.external_match_code AS externalMatchCode,
          e.start_date AS startDate,
          e.end_date AS endDate
        FROM event_schedule_matches esm
        LEFT JOIN events e ON e.event_id = esm.event_id
        LEFT JOIN sub_event_types st ON st.code = esm.sub_event_type_code
        LEFT JOIN stage_codes sc ON sc.code = esm.stage_code
        LEFT JOIN round_codes rc ON rc.code = esm.round_code
        WHERE esm.schedule_match_id = ?
      `,
    )
    .get(scheduleMatchId) as
    | {
        scheduleMatchId: number;
        eventId: number;
        eventName: string | null;
        eventNameZh: string | null;
        eventYear: number | null;
        subEventTypeCode: string;
        subEventNameZh: string | null;
        stageCode: string;
        stageNameZh: string | null;
        roundCode: string;
        roundNameZh: string | null;
        groupCode: string | null;
        scheduledLocalAt: string | null;
        scheduledUtcAt: string | null;
        tableNo: string | null;
        sessionLabel: string | null;
        status: string;
        rawScheduleStatus: string | null;
        matchScore: string | null;
        games: string | null;
        winnerSide: string | null;
        externalMatchCode: string | null;
        startDate: string | null;
        endDate: string | null;
      }
    | undefined;

  if (!match) return null;

  const sideRows = db
    .prepare(
      `
        SELECT
          esms.side_no AS sideNo,
          esms.is_winner AS isWinner,
          esms.team_code AS teamCode,
          esms.seed,
          esms.qualifier,
          esms.placeholder_text AS placeholderText,
          esmsp.player_order AS playerOrder,
          esmsp.player_id AS playerId,
          esmsp.player_name AS playerName,
          esmsp.player_country AS playerCountry,
          p.slug,
          p.name_zh AS playerNameZh,
          REPLACE(REPLACE(p.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile
        FROM event_schedule_match_sides esms
        LEFT JOIN event_schedule_match_side_players esmsp ON esmsp.schedule_side_id = esms.schedule_side_id
        LEFT JOIN players p ON p.player_id = esmsp.player_id
        WHERE esms.schedule_match_id = ?
        ORDER BY esms.side_no ASC, esmsp.player_order ASC
      `,
    )
    .all(scheduleMatchId) as Array<{
    sideNo: number;
    isWinner: number;
    teamCode: string | null;
    seed: number | null;
    qualifier: number | null;
    placeholderText: string | null;
    playerOrder: number | null;
    playerId: number | null;
    playerName: string | null;
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
      teamCode: string | null;
      seed: number | null;
      qualifier: boolean | null;
      placeholderText: string | null;
      players: Array<SidePlayer & { avatarFile: string | null }>;
    }
  >();

  for (const row of sideRows) {
    const current = sideMap.get(row.sideNo) ?? {
      sideNo: row.sideNo,
      isWinner: row.isWinner === 1,
      teamCode: row.teamCode,
      seed: row.seed,
      qualifier: row.qualifier == null ? null : row.qualifier === 1,
      placeholderText: row.placeholderText,
      players: [],
    };
    if (row.playerName) {
      current.players.push({
        playerId: row.playerId,
        slug: row.slug,
        name: row.playerName,
        nameZh: row.playerNameZh,
        countryCode: row.playerCountry,
        avatarFile: filterAvatarFile(row.avatarFile),
      });
    }
    sideMap.set(row.sideNo, current);
  }

  const official = readOfficialScheduleResults(match.eventId).get(normalizeExternalMatchCode(match.externalMatchCode));
  const displayTeamCodes: [string | null | undefined, string | null | undefined] = [
    sideMap.get(1)?.teamCode,
    sideMap.get(2)?.teamCode,
  ];
  const flipTopLevelScore = shouldFlipTeamOrder(official?.teamCodes, displayTeamCodes);
  const topLevelGames = official?.games.length ? official.games : parseGames(match.games);
  const topLevelMatchScore = official?.matchScore
    ? flipTopLevelScore
      ? reverseScoreLabel(official.matchScore)
      : official.matchScore
    : match.matchScore;
  const topLevelWinnerSide =
    official?.winnerCode && official.teamCodes
      ? sideMap.get(1)?.teamCode === official.winnerCode
        ? 'A'
        : sideMap.get(2)?.teamCode === official.winnerCode
          ? 'B'
          : match.winnerSide
      : match.winnerSide;
  const sides = Array.from(sideMap.values()).map((side) => ({
    ...side,
    isWinner: official?.winnerCode != null && side.teamCode ? side.teamCode === official.winnerCode : side.isWinner,
  }));
  const officialPlayerIds = (official?.rubbers ?? [])
    .flatMap((rubber) => rubber.sides)
    .flatMap((side) => side.players)
    .map((player) => player.playerId)
    .filter((playerId): playerId is number => playerId != null);
  const officialPlayerMap = loadPlayerDisplayMap(Array.from(new Set(officialPlayerIds)));

  return {
    match: {
      scheduleMatchId: match.scheduleMatchId,
      eventId: match.eventId,
      eventName: match.eventName,
      eventNameZh: match.eventNameZh,
      eventYear: match.eventYear,
      subEventTypeCode: match.subEventTypeCode,
      subEventNameZh: match.subEventNameZh,
      stageCode: match.stageCode,
      stageNameZh: match.stageNameZh,
      roundCode: match.roundCode,
      roundNameZh: match.roundNameZh,
      roundLabel: roundLabel(match.roundCode, match.roundNameZh),
      groupCode: match.groupCode,
      scheduledLocalAt: match.scheduledLocalAt,
      scheduledUtcAt: match.scheduledUtcAt,
      tableNo: match.tableNo,
      sessionLabel: match.sessionLabel,
      status: official?.matchScore ? 'completed' : match.status,
      rawScheduleStatus: official?.matchScore ? 'Official' : match.rawScheduleStatus,
      matchScore: topLevelMatchScore,
      games: topLevelGames,
      winnerSide: topLevelWinnerSide,
      startDate: match.startDate,
      endDate: match.endDate,
      externalMatchCode: match.externalMatchCode,
    },
    sides,
    rubbers: (official?.rubbers ?? []).map((rubber) => {
      const rubberTeamCodes =
        rubber.sides.length === 2 ? ([rubber.sides[0].teamCode ?? '', rubber.sides[1].teamCode ?? ''] as [string, string]) : null;
      const flipRubber = shouldFlipTeamOrder(rubberTeamCodes, displayTeamCodes);
      const orientedSides = flipRubber ? [...rubber.sides].reverse() : rubber.sides;

      return {
        ...rubber,
        matchScore: flipRubber ? reverseScoreLabel(rubber.matchScore) : rubber.matchScore,
        games: flipRubber ? reverseGames(rubber.games) : rubber.games,
        winnerSide: flipRubber ? flipWinnerSide(rubber.winnerSide) : rubber.winnerSide,
        sides: orientedSides.map((side, index) => ({
          ...side,
          sideNo: index + 1,
          players: enrichOfficialPlayers(side.players, officialPlayerMap),
        })),
      };
    }),
  };
}

function teamCodesMatch(tie: TeamTie, teamCodes: [string, string]) {
  return new Set([tie.teamA.code, tie.teamB.code]).size === new Set(teamCodes).size &&
    teamCodes.every((code) => code === tie.teamA.code || code === tie.teamB.code);
}

const TEAM_ROUND_META: Record<string, { code: string; label: string; order: number }> = {
  Final: { code: 'Final', label: '决赛', order: 80 },
  Bronze: { code: 'Bronze', label: '铜牌赛', order: 75 },
  SemiFinal: { code: 'SemiFinal', label: '半决赛', order: 60 },
  QuarterFinal: { code: 'QuarterFinal', label: '四分之一决赛', order: 50 },
  R16: { code: 'R16', label: '16 强', order: 40 },
  R32: { code: 'R32', label: '32 强', order: 30 },
  R64: { code: 'R64', label: '64 强', order: 20 },
  R128: { code: 'R128', label: '128 强', order: 10 },
};

const NUMERIC_TEAM_ROUND_ALIAS: Record<string, string> = {
  '2': 'Final',
  '4': 'SemiFinal',
  '8': 'QuarterFinal',
  '16': 'R16',
  '32': 'R32',
  '64': 'R64',
  '128': 'R128',
};

const TEAM_BRACKET_STAGES = new Set(['Main Draw', 'MAIN']);

function teamTieRoundMeta(round: string, roundZh: string | null) {
  const trimmed = round?.trim() ?? '';
  const normalized = NUMERIC_TEAM_ROUND_ALIAS[trimmed] ?? trimmed;
  const meta = TEAM_ROUND_META[normalized];
  if (meta) {
    const trimmedZh = roundZh?.trim() ?? '';
    const useStandardLabel = !trimmedZh || /^\d+$/.test(trimmedZh);
    return { code: meta.code, label: useStandardLabel ? meta.label : trimmedZh, order: meta.order };
  }
  return { code: round || 'unknown', label: roundZh?.trim() || round || '轮次待补', order: 0 };
}

type TeamDrawRoundRecord = {
  drawRound: string;
  roundOrder: number;
};

function loadTeamDrawRoundMap(eventId: number, subEventCode: string) {
  const rows = db
    .prepare(
      `
        SELECT
          match_id AS matchId,
          draw_round AS drawRound,
          round_order AS roundOrder
        FROM event_draw_matches
        WHERE event_id = ?
          AND sub_event_type_code = ?
      `,
    )
    .all(eventId, subEventCode) as Array<{
    matchId: number;
    drawRound: string;
    roundOrder: number;
  }>;

  return new Map(rows.map((row) => [row.matchId, { drawRound: row.drawRound, roundOrder: row.roundOrder }]));
}

function teamTieRoundMetaFromDrawRound(drawRound: string, roundOrder: number) {
  const meta = TEAM_ROUND_META[drawRound];
  if (meta) {
    return { code: meta.code, label: meta.label, order: roundOrder || meta.order };
  }
  const fallback = teamTieRoundMeta(drawRound, null);
  return { code: fallback.code, label: fallback.label, order: roundOrder || fallback.order };
}

function resolveTeamTieRoundMeta(tie: TeamTie, drawRoundMap: Map<number, TeamDrawRoundRecord>) {
  const grouped = new Map<string, { count: number; roundOrder: number }>();
  for (const rubber of tie.rubbers) {
    const record = drawRoundMap.get(rubber.matchId);
    if (!record) continue;
    const current = grouped.get(record.drawRound) ?? { count: 0, roundOrder: record.roundOrder };
    current.count += 1;
    current.roundOrder = Math.max(current.roundOrder, record.roundOrder);
    grouped.set(record.drawRound, current);
  }

  const resolved = Array.from(grouped.entries())
    .sort((left, right) => right[1].count - left[1].count || right[1].roundOrder - left[1].roundOrder)[0];
  if (resolved) {
    return teamTieRoundMetaFromDrawRound(resolved[0], resolved[1].roundOrder);
  }

  if (!TEAM_BRACKET_STAGES.has(tie.stage)) return null;
  const fallback = teamTieRoundMeta(tie.round, tie.roundZh);
  return fallback.order > 0 ? fallback : null;
}

function buildTeamKnockoutRounds(eventId: number, subEventCode: string, ties: TeamTie[]) {
  const drawRoundMap = loadTeamDrawRoundMap(eventId, subEventCode);
  return Array.from(
    ties
      .reduce((map, tie) => {
        const meta = resolveTeamTieRoundMeta(tie, drawRoundMap);
        if (!meta) return map;
        const current = map.get(meta.code) ?? {
          code: meta.code,
          label: meta.label,
          order: meta.order,
          ties: [] as TeamTie[],
        };
        current.ties.push(tie);
        map.set(meta.code, current);
        return map;
      }, new Map<string, { code: string; label: string; order: number; ties: TeamTie[] }>())
      .values(),
  ).sort((left, right) => right.order - left.order);
}

const AUTO_TEAM_SUB_EVENT_CODES = new Set(['WT', 'MT', 'XT']);

function isAutoTeamSubEvent(code: string) {
  return AUTO_TEAM_SUB_EVENT_CODES.has(code);
}

function buildAutoTeamKnockoutView(eventId: number, subEventCode: string): EventTeamKnockoutView | null {
  const ties = buildTeamTiesForSubEvent(eventId, subEventCode);
  if (ties.length === 0) return null;

  const rounds = buildTeamKnockoutRounds(eventId, subEventCode, ties);
  if (rounds.length === 0) return null;

  const finalTie = rounds.find((r) => r.code === 'Final')?.ties[0] ?? null;
  const bronzeTie = rounds.find((r) => r.code === 'Bronze')?.ties[0] ?? null;
  const semiFinalTies = rounds.find((r) => r.code === 'SemiFinal')?.ties ?? [];

  const standings: StageStanding[] = [];
  const seen = new Set<string>();
  const pushStanding = (code: string | null | undefined, rank: number) => {
    if (!code || seen.has(code)) return;
    seen.add(code);
    standings.push(buildStageStanding(code, rank));
  };

  if (finalTie?.winnerCode) {
    const champion = finalTie.winnerCode;
    const runnerUp = champion === finalTie.teamA.code ? finalTie.teamB.code : finalTie.teamA.code;
    pushStanding(champion, 1);
    pushStanding(runnerUp, 2);
  }

  if (bronzeTie?.winnerCode) {
    const third = bronzeTie.winnerCode;
    const fourth = third === bronzeTie.teamA.code ? bronzeTie.teamB.code : bronzeTie.teamA.code;
    pushStanding(third, 3);
    pushStanding(fourth, 4);
  } else {
    for (const tie of semiFinalTies) {
      if (!tie.winnerCode) continue;
      const loser = tie.winnerCode === tie.teamA.code ? tie.teamB.code : tie.teamA.code;
      if (loser === finalTie?.teamA.code || loser === finalTie?.teamB.code) continue;
      pushStanding(loser, 3);
    }
  }

  const thirdPlaces = standings.filter((s) => s.rank === 3);
  return {
    mode: 'team_knockout_with_bronze',
    rounds,
    finalStandings: standings,
    podium: {
      champion: standings.find((s) => s.rank === 1) ?? null,
      runnerUp: standings.find((s) => s.rank === 2) ?? null,
      thirdPlace: thirdPlaces[0] ?? null,
      thirdPlaceSecond: !bronzeTie?.winnerCode ? thirdPlaces[1] ?? null : null,
    },
    finalTie,
    bronzeTie,
  };
}

function buildLiveGroupStageView(
  subEventCode: string,
  scheduleMatches: EventScheduleMatch[],
  officialResults: Map<string, OfficialScheduleResult>,
): EventRoundRobinView | null {
  const groupStageMatches = scheduleMatches.filter(
    (match) =>
      match.subEventTypeCode === subEventCode &&
      (match.groupCode != null || match.stageCode === 'PRELIMINARY' || match.roundCode.startsWith('G')),
  );
  if (groupStageMatches.length === 0) return null;

  const tiesByGroup = new Map<string, TeamTie[]>();
  for (const match of groupStageMatches) {
    const [sideA, sideB] = [...match.sides].sort((left, right) => left.sideNo - right.sideNo);
    if (!sideA?.teamCode || !sideB?.teamCode) continue;

    const official = officialResults.get(normalizeExternalMatchCode(match.externalMatchCode));
    const officialScores = official?.teamCodes ? new Map([[official.teamCodes[0], official.scoreA], [official.teamCodes[1], official.scoreB]]) : null;
    const scoreA = officialScores?.get(sideA.teamCode) ?? null;
    const scoreB = officialScores?.get(sideB.teamCode) ?? null;
    const winnerCode =
      official?.winnerCode && (official.winnerCode === sideA.teamCode || official.winnerCode === sideB.teamCode)
        ? official.winnerCode
        : null;
    const tie: TeamTie = {
      tieId: match.externalMatchCode || String(match.scheduleMatchId),
      stage: match.stageCode,
      stageZh: match.stageNameZh,
      round: match.roundCode,
      roundZh: match.roundNameZh,
      teamA: teamLabelFromCode(sideA.teamCode),
      teamB: teamLabelFromCode(sideB.teamCode),
      scoreA: scoreA ?? 0,
      scoreB: scoreB ?? 0,
      winnerCode,
      rubbers: [],
    };
    const groupCode = match.groupCode ?? match.roundCode;
    const current = tiesByGroup.get(groupCode) ?? [];
    current.push(tie);
    tiesByGroup.set(groupCode, current);
  }

  if (tiesByGroup.size === 0) return null;

  const groups: RoundRobinStageGroup[] = Array.from(tiesByGroup.entries())
    .sort((left, right) => left[0].localeCompare(right[0]))
    .map(([groupCode, ties]) => {
      const teamCodes = Array.from(new Set(ties.flatMap((tie) => [tie.teamA.code, tie.teamB.code]))).sort((left, right) =>
        left.localeCompare(right),
      );

      const standingsMap = new Map<string, StageStanding>();
      for (const teamCode of teamCodes) {
        standingsMap.set(teamCode, {
          ...buildStageStanding(teamCode, 0),
          matches: 0,
          wins: 0,
          losses: 0,
          tiePoints: 0,
          scoreFor: 0,
          scoreAgainst: 0,
        });
      }

      for (const tie of ties) {
        if (!tie.winnerCode) continue;
        const left = standingsMap.get(tie.teamA.code);
        const right = standingsMap.get(tie.teamB.code);
        if (!left || !right) continue;

        left.matches = (left.matches ?? 0) + 1;
        right.matches = (right.matches ?? 0) + 1;
        left.scoreFor = (left.scoreFor ?? 0) + tie.scoreA;
        left.scoreAgainst = (left.scoreAgainst ?? 0) + tie.scoreB;
        right.scoreFor = (right.scoreFor ?? 0) + tie.scoreB;
        right.scoreAgainst = (right.scoreAgainst ?? 0) + tie.scoreA;

        if (tie.winnerCode === tie.teamA.code) {
          left.wins = (left.wins ?? 0) + 1;
          left.tiePoints = (left.tiePoints ?? 0) + 1;
          right.losses = (right.losses ?? 0) + 1;
        } else {
          right.wins = (right.wins ?? 0) + 1;
          right.tiePoints = (right.tiePoints ?? 0) + 1;
          left.losses = (left.losses ?? 0) + 1;
        }
      }

      const standings = Array.from(standingsMap.values())
        .sort((left, right) => {
          const pointDiff = (right.tiePoints ?? 0) - (left.tiePoints ?? 0);
          if (pointDiff !== 0) return pointDiff;
          const winDiff = (right.wins ?? 0) - (left.wins ?? 0);
          if (winDiff !== 0) return winDiff;
          const ratioDiff = (right.scoreFor ?? 0) - (right.scoreAgainst ?? 0) - ((left.scoreFor ?? 0) - (left.scoreAgainst ?? 0));
          if (ratioDiff !== 0) return ratioDiff;
          const scoreDiff = (right.scoreFor ?? 0) - (left.scoreFor ?? 0);
          if (scoreDiff !== 0) return scoreDiff;
          return left.teamCode.localeCompare(right.teamCode);
        })
        .map((standing, index) => ({
          ...standing,
          rank: index + 1,
        }));

      return {
        code: groupCode,
        nameZh: `第 ${groupCode.replace(/^GP/, '')} 组`,
        teams: teamCodes,
        ties,
        standings,
      };
    });

  return {
    mode: 'staged_round_robin',
    stages: [
      {
        code: 'PRELIMINARY',
        name: 'PRELIMINARY',
        nameZh: '小组赛积分表',
        format: 'group_round_robin',
        groups,
      },
    ],
    finalStandings: [],
    podium: {
      champion: null,
      runnerUp: null,
      thirdPlace: null,
    },
  };
}

function buildTeamKnockoutView(eventId: number, subEventCode: string, override: ManualEventOverride): EventTeamKnockoutView {
  if (!isTeamKnockoutOverride(override)) {
    throw new Error(`Expected team_knockout_with_bronze override for event ${eventId}`);
  }

  const ties = buildTeamTiesForSubEvent(eventId, subEventCode);
  const rounds = buildTeamKnockoutRounds(eventId, subEventCode, ties);
  const finalStandings = override.final_standings
    .slice()
    .sort((left, right) => left.rank - right.rank)
    .map((item) => buildStageStanding(item.team_code, item.rank));
  const podiumByCode = new Map(finalStandings.map((item) => [item.teamCode, item]));

  return {
    mode: 'team_knockout_with_bronze',
    rounds,
    finalStandings,
    podium: {
      champion: podiumByCode.get(override.podium.champion) ?? null,
      runnerUp: podiumByCode.get(override.podium.runner_up) ?? null,
      thirdPlace: podiumByCode.get(override.podium.third_place) ?? null,
      thirdPlaceSecond: null,
    },
    finalTie: ties.find((tie) => teamCodesMatch(tie, override.ties.final.team_codes)) ?? null,
    bronzeTie: ties.find((tie) => teamCodesMatch(tie, override.ties.bronze.team_codes)) ?? null,
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
  const keyword = options?.keyword?.trim() ?? '';
  const expandedKeywords = keyword ? expandEventQuery(keyword) : [];
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

  if (expandedKeywords.length > 0) {
    const keywordClauses = expandedKeywords.map(() => "(LOWER(e.name) LIKE ? OR LOWER(COALESCE(e.name_zh, '')) LIKE ?)");
    where.push(`(${keywordClauses.join(' OR ')})`);

    for (const expandedKeyword of expandedKeywords) {
      const like = `%${expandedKeyword}%`;
      params.push(like, like);
    }
  }

  where.push(...ageGroupWhere);

  // 过滤尚未开始的赛事（保留 startDate 为空的记录，因为无法判断）
  where.push("(e.start_date IS NULL OR e.start_date <= date('now'))");

  // 过滤没有比赛记录且没有赛程安排的赛事
  where.push(
    "(EXISTS (SELECT 1 FROM matches m WHERE m.event_id = e.event_id) OR EXISTS (SELECT 1 FROM event_session_schedule ess WHERE ess.event_id = e.event_id))"
  );

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
          e.lifecycle_status AS lifecycleStatus,
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
    const presentationMode: EventPresentationMode | null =
      override?.presentation_mode === 'staged_round_robin'
        ? 'staged_round_robin'
        : override?.presentation_mode === 'team_knockout_with_bronze'
          ? 'team_knockout_with_bronze'
          : event.drawMatches > 0
            ? 'knockout'
            : null;
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
          lifecycle_status AS lifecycleStatus,
          time_zone AS timeZone,
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
        lifecycleStatus: string | null;
        timeZone: string | null;
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

  const scheduleCounts = db
    .prepare(
      `
        SELECT sub_event_type_code AS code, COUNT(*) AS matches
        FROM event_schedule_matches
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
  const scheduleCountMap = new Map(scheduleCounts.map((item) => [item.code, item.matches]));
  const validCodes = new Set<string>(CORE_SUB_EVENT_CODES);
  const codesWithData = new Set<string>(
    [
      ...drawCounts.map((item) => item.code),
      ...matchCounts.map((item) => item.code),
      ...scheduleCounts.map((item) => item.code),
      ...existingSubEvents.map((item) => item.code),
    ].filter(
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

  const subEvents = orderedCodes
    .map((code) => {
      const record = existingMap.get(code);
      const drawMatches = drawCountMap.get(code) ?? 0;
      const importedMatches = matchCountMap.get(code) ?? 0;
      const scheduleMatches = scheduleCountMap.get(code) ?? 0;
      const hasMatchData = drawMatches > 0 || importedMatches > 0 || scheduleMatches > 0;

      if (!hasMatchData) return null;

      const playerIds = parseChampionIds(record?.championPlayerIds ?? null);
      const hasChampion = Boolean(record?.championName || record?.championCountryCode || playerIds.length > 0);
      const fallbackPlayers = loadPlayersByIds(playerIds);
      const teamPlayers = code === 'WT' || code === 'XT' ? loadTeamChampionPlayers(eventId, code, record?.championCountryCode ?? null) : [];
      const players = teamPlayers.length > 0 ? teamPlayers : fallbackPlayers;

      return {
        code,
        nameZh: nameMap.get(code) ?? code,
        disabled: false,
        hasDraw: drawMatches > 0,
        drawMatches,
        importedMatches,
        scheduleMatches,
        champion:
          hasChampion
            ? {
                championName: record?.championName ?? null,
                championCountryCode: record?.championCountryCode ?? null,
                players,
              }
            : null,
      };
    })
    .filter((item): item is NonNullable<typeof item> => item !== null);

  const override = readManualEventOverride(eventId);
  const preferredDefault = override?.sub_event_type_code ?? 'WS';
  const selectedSubEvent =
    requestedSubEvent && subEvents.some((item) => item.code === requestedSubEvent)
      ? requestedSubEvent
      : subEvents.find((item) => item.code === preferredDefault && !item.disabled)?.code ??
        subEvents.find((item) => !item.disabled)?.code ??
        preferredDefault;

  const officialScheduleResults = readOfficialScheduleResults(eventId);

  const sessionSchedule = db
    .prepare(
      `
        SELECT
          id,
          day_index AS dayIndex,
          local_date AS localDate,
          start_local_time AS startLocalTime,
          end_local_time AS endLocalTime,
          venue_raw AS venueRaw,
          table_count AS tableCount,
          raw_sub_events_text AS rawSubEventsText,
          parsed_rounds_json AS parsedRoundsJson
        FROM event_session_schedule
        WHERE event_id = ?
        ORDER BY day_index ASC
      `,
    )
    .all(eventId) as EventSessionScheduleRow[];

  const scheduleRows = db
    .prepare(
      `
        SELECT
          esm.schedule_match_id AS scheduleMatchId,
          esm.external_match_code AS externalMatchCode,
          esm.sub_event_type_code AS subEventTypeCode,
          st.name_zh AS subEventNameZh,
          esm.stage_code AS stageCode,
          sc.name_zh AS stageNameZh,
          esm.round_code AS roundCode,
          rc.name_zh AS roundNameZh,
          esm.group_code AS groupCode,
          esm.scheduled_local_at AS scheduledLocalAt,
          esm.scheduled_utc_at AS scheduledUtcAt,
          esm.table_no AS tableNo,
          esm.session_label AS sessionLabel,
          esm.status,
          esm.raw_schedule_status AS rawScheduleStatus,
          esm.match_score AS matchScore,
          esm.games,
          esm.winner_side AS winnerSide,
          esms.schedule_side_id AS scheduleSideId,
          esms.side_no AS sideNo,
          esms.entry_id AS entryId,
          esms.placeholder_text AS placeholderText,
          esms.team_code AS teamCode,
          esms.seed,
          esms.qualifier,
          esms.is_winner AS isWinner,
          esmsp.player_order AS playerOrder,
          esmsp.player_id AS playerId,
          esmsp.player_name AS playerName,
          esmsp.player_country AS playerCountry,
          p.slug,
          p.name_zh AS playerNameZh
        FROM event_schedule_matches esm
        LEFT JOIN sub_event_types st ON st.code = esm.sub_event_type_code
        LEFT JOIN stage_codes sc ON sc.code = esm.stage_code
        LEFT JOIN round_codes rc ON rc.code = esm.round_code
        LEFT JOIN event_schedule_match_sides esms ON esms.schedule_match_id = esm.schedule_match_id
        LEFT JOIN event_schedule_match_side_players esmsp ON esmsp.schedule_side_id = esms.schedule_side_id
        LEFT JOIN players p ON p.player_id = esmsp.player_id
        WHERE esm.event_id = ?
        ORDER BY esm.scheduled_local_at ASC, esm.schedule_match_id ASC, esms.side_no ASC, esmsp.player_order ASC
      `,
    )
    .all(eventId) as Array<{
    scheduleMatchId: number;
    externalMatchCode: string | null;
    subEventTypeCode: string;
    subEventNameZh: string | null;
    stageCode: string;
    stageNameZh: string | null;
    roundCode: string;
    roundNameZh: string | null;
    groupCode: string | null;
    scheduledLocalAt: string | null;
    scheduledUtcAt: string | null;
    tableNo: string | null;
    sessionLabel: string | null;
    status: string;
    rawScheduleStatus: string | null;
    matchScore: string | null;
    games: string | null;
    winnerSide: string | null;
    scheduleSideId: number | null;
    sideNo: number | null;
    entryId: number | null;
    placeholderText: string | null;
    teamCode: string | null;
    seed: number | null;
    qualifier: number | null;
    isWinner: number | null;
    playerOrder: number | null;
    playerId: number | null;
    playerName: string | null;
    playerCountry: string | null;
    slug: string | null;
    playerNameZh: string | null;
  }>;

  const scheduleMatchMap = new Map<number, EventScheduleMatch>();
  for (const row of scheduleRows) {
    const current =
      scheduleMatchMap.get(row.scheduleMatchId) ??
      {
        scheduleMatchId: row.scheduleMatchId,
        externalMatchCode: row.externalMatchCode,
        subEventTypeCode: row.subEventTypeCode,
        subEventNameZh: row.subEventNameZh,
        stageCode: row.stageCode,
        stageNameZh: row.stageNameZh,
        roundCode: row.roundCode,
        roundNameZh: row.roundNameZh,
        groupCode: row.groupCode,
        scheduledLocalAt: row.scheduledLocalAt,
        scheduledUtcAt: row.scheduledUtcAt,
        tableNo: row.tableNo,
        sessionLabel: row.sessionLabel,
        status: row.status,
        rawScheduleStatus: row.rawScheduleStatus,
        matchScore: row.matchScore,
        games: parseGames(row.games),
        winnerSide: row.winnerSide,
        sides: [],
      };

    if (row.sideNo != null) {
      let side = current.sides.find((item) => item.sideNo === row.sideNo);
      if (!side) {
        side = {
          sideNo: row.sideNo,
          entryId: row.entryId,
          placeholderText: row.placeholderText,
          teamCode: row.teamCode,
          seed: row.seed,
          qualifier: row.qualifier == null ? null : row.qualifier === 1,
          isWinner: row.isWinner === 1,
          players: [],
        };
        current.sides.push(side);
      }

      if (row.playerName) {
        side.players.push({
          playerId: row.playerId,
          slug: row.slug,
          name: row.playerName,
          nameZh: row.playerNameZh,
          countryCode: row.playerCountry,
        });
      }
    }

    scheduleMatchMap.set(row.scheduleMatchId, current);
  }

  const dedupedScheduleMatches = Array.from(scheduleMatchMap.values()).reduce((matches, match) => {
    const dedupeKey =
      match.externalMatchCode?.trim() ||
      [
        match.subEventTypeCode,
        match.groupCode ?? '',
        match.roundCode,
        match.scheduledLocalAt ?? '',
        match.tableNo ?? '',
        match.sides
          .map((side) =>
            [
              side.sideNo,
              side.teamCode ?? '',
              side.placeholderText ?? '',
              side.players.map((player) => player.playerId ?? player.name).join('/'),
            ].join(':'),
          )
          .join('|'),
      ].join('#');
    const current = matches.get(dedupeKey);
    matches.set(dedupeKey, current ? pickPreferredScheduleMatch(current, match) : match);
    return matches;
  }, new Map<string, EventScheduleMatch>());

  const scheduleMatches = Array.from(dedupedScheduleMatches.values()).map((match) => {
    const official = officialScheduleResults.get(normalizeExternalMatchCode(match.externalMatchCode));
    if (!official?.teamCodes) {
      return {
        ...match,
        sides: [...match.sides].sort((left, right) => left.sideNo - right.sideNo),
      };
    }

    const sides = [...match.sides]
      .sort((left, right) => left.sideNo - right.sideNo)
      .map((side) => ({
        ...side,
        isWinner: official.winnerCode != null && side.teamCode === official.winnerCode,
      }));
    const displayTeamCodes: [string | null | undefined, string | null | undefined] = [sides[0]?.teamCode, sides[1]?.teamCode];
    const flipScore = shouldFlipTeamOrder(official.teamCodes, displayTeamCodes);
    const winnerSide = sides.find((side) => side.teamCode === official.winnerCode)?.sideNo === 1 ? 'A' : sides.find((side) => side.teamCode === official.winnerCode)?.sideNo === 2 ? 'B' : match.winnerSide;

    return {
      ...match,
      sides,
      winnerSide,
      status: official.matchScore ? 'completed' : match.status,
      rawScheduleStatus: official.matchScore ? 'Official' : match.rawScheduleStatus,
      matchScore: official.matchScore
        ? flipScore
          ? reverseScoreLabel(official.matchScore)
          : official.matchScore
        : match.matchScore,
    };
  });

  const scheduleDays = scheduleMatches.reduce((days, match) => {
    const localDate = match.scheduledLocalAt?.slice(0, 10) ?? '日期待定';
    const current = days.get(localDate) ?? { localDate, matches: [] as EventScheduleMatch[] };
    current.matches.push(match);
    days.set(localDate, current);
    return days;
  }, new Map<string, EventScheduleDay>());

const championForSubEvent = (subEventCode: string): EventChampion | null => {
    const se = subEvents.find((item) => item.code === subEventCode);
    const champion = se?.champion;
    const players = champion?.players ?? [];

    const overrideChampionCountry =
      override && subEventCode === override.sub_event_type_code ? override.podium.champion : null;

    if (!se && !overrideChampionCountry) return null;
    if (!champion?.championName && players.length === 0 && !overrideChampionCountry) return null;

    return {
      championName: champion?.championName ?? overrideChampionCountry,
      championCountryCode: champion?.championCountryCode ?? overrideChampionCountry,
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
          roundLabel: roundLabel(row.drawRound ?? row.sourceRound, row.sourceRoundZh),
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
    if (override && isRoundRobinOverride(override) && subEventCode === override.sub_event_type_code) {
      return buildRoundRobinView(eventId, subEventCode, override);
    }
    if (override && subEventCode === override.sub_event_type_code) return null;
    if (!isAutoTeamSubEvent(subEventCode)) return null;
    if (event.lifecycleStatus === 'completed') return null;
    return buildLiveGroupStageView(subEventCode, scheduleMatches, officialScheduleResults);
  };

  const teamKnockoutViewForSubEvent = (subEventCode: string): EventTeamKnockoutView | null => {
    if (override && isTeamKnockoutOverride(override) && subEventCode === override.sub_event_type_code) {
      return buildTeamKnockoutView(eventId, subEventCode, override);
    }
    if (override && subEventCode === override.sub_event_type_code) return null;
    if (!isAutoTeamSubEvent(subEventCode)) return null;
    return buildAutoTeamKnockoutView(eventId, subEventCode);
  };

  const buildSubEventDetail = (subEventCode: string) => {
    const roundRobinView = roundRobinViewForSubEvent(subEventCode);
    const teamKnockoutView = teamKnockoutViewForSubEvent(subEventCode);
    const presentationMode: EventPresentationMode =
      override && subEventCode === override.sub_event_type_code
        ? isRoundRobinOverride(override)
          ? 'staged_round_robin'
          : isTeamKnockoutOverride(override)
            ? 'team_knockout_with_bronze'
            : 'knockout'
        : roundRobinView
          ? 'staged_round_robin'
        : teamKnockoutView
          ? 'team_knockout_with_bronze'
          : 'knockout';

    return {
      code: subEventCode,
      champion: championForSubEvent(subEventCode),
      bracket: bracketForSubEvent(subEventCode),
      roundRobinView,
      teamKnockoutView,
      presentationMode,
    };
  };

  const subEventDetails = subEvents
    .filter((subEvent) => !subEvent.disabled)
    .map((subEvent) => buildSubEventDetail(subEvent.code));
  const dataForSelected =
    subEventDetails.find((detail) => detail.code === selectedSubEvent) ?? buildSubEventDetail(selectedSubEvent);

  return {
    event,
    subEvents,
    sessionSchedule,
    scheduleDays: Array.from(scheduleDays.values()),
    selectedSubEvent,
    subEventDetails,
    champion: dataForSelected?.champion ?? null,
    bracket: dataForSelected?.bracket ?? [],
    roundRobinView: dataForSelected?.roundRobinView ?? null,
    teamKnockoutView: dataForSelected?.teamKnockoutView ?? null,
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
          edm.draw_round AS drawRound,
          e.start_date AS startDate,
          e.end_date AS endDate,
          e.name AS eventCanonicalName,
          e.name_zh AS eventCanonicalNameZh
        FROM matches m
        LEFT JOIN event_draw_matches edm ON edm.match_id = m.match_id
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
        drawRound: string | null;
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
      avatarFile: filterAvatarFile(row.avatarFile),
    });
    sideMap.set(row.sideNo, current);
  }

  return {
    match: {
      ...match,
      eventName: match.eventCanonicalName ?? match.eventName,
      eventNameZh: match.eventCanonicalNameZh ?? match.eventNameZh,
      roundLabel: roundLabel(match.drawRound ?? match.round, match.roundZh),
      games: parseGames(match.games),
    },
    sides: Array.from(sideMap.values()),
  };
}
