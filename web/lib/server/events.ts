import { db } from '@/lib/server/db';
import { expandEventQuery } from '@/lib/server/query-rewrite';
import { filterAvatarFile } from '@/lib/server/avatarManifest';
import { DATA_DIR } from '@/lib/paths';
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

type PlayerCountryHistoryEntry = {
  player_name: string;
  current_country: string;
  historical_country: string;
};

let cachedPlayerCountryHistory: Map<string, PlayerCountryHistoryEntry> | null = null;

function normalizePlayerCountryHistoryKey(playerName: string, currentCountry: string | null | undefined) {
  return `${playerName.trim().toLowerCase()}|${(currentCountry ?? '').trim().toUpperCase()}`;
}

function loadPlayerCountryHistory() {
  if (cachedPlayerCountryHistory) return cachedPlayerCountryHistory;

  const filePath = path.join(DATA_DIR, 'player_country_history.json');
  const history = new Map<string, PlayerCountryHistoryEntry>();
  if (!existsSync(filePath)) {
    cachedPlayerCountryHistory = history;
    return history;
  }

  try {
    const payload = JSON.parse(readFileSync(filePath, 'utf8')) as unknown;
    if (Array.isArray(payload)) {
      for (const item of payload) {
        if (!item || typeof item !== 'object') continue;
        const entry = item as Partial<PlayerCountryHistoryEntry>;
        const playerName = entry.player_name?.trim();
        const currentCountry = entry.current_country?.trim().toUpperCase();
        const historicalCountry = entry.historical_country?.trim().toUpperCase();
        if (!playerName || !currentCountry || !historicalCountry) continue;
        history.set(normalizePlayerCountryHistoryKey(playerName, currentCountry), {
          player_name: playerName,
          current_country: currentCountry,
          historical_country: historicalCountry,
        });
      }
    }
  } catch (err) {
    console.warn('Failed to load player country history:', err);
  }

  cachedPlayerCountryHistory = history;
  return history;
}

function historicalCountryForPlayer(playerName: string, countryCode: string | null | undefined) {
  return loadPlayerCountryHistory().get(normalizePlayerCountryHistoryKey(playerName, countryCode))?.historical_country ?? null;
}

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

function loadPlayerDisplayMapByNames(playerNames: string[]) {
  const normalizedNames = Array.from(new Set(playerNames.map((name) => name.trim()).filter(Boolean)));
  if (normalizedNames.length === 0) {
    return new Map<string, { playerId: number; slug: string | null; nameZh: string | null; avatarFile: string | null }>();
  }

  const rows = db
    .prepare(
      `
        SELECT
          player_id AS playerId,
          name,
          slug,
          name_zh AS nameZh,
          REPLACE(REPLACE(avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile
        FROM players
        WHERE name IN (${normalizedNames.map(() => '?').join(', ')})
      `,
    )
    .all(...normalizedNames) as Array<{
    playerId: number;
    name: string;
    slug: string | null;
    nameZh: string | null;
    avatarFile: string | null;
  }>;

  return new Map(
    rows.map((row) => [
      row.name.trim(),
      {
        playerId: row.playerId,
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
        if (typeof game === 'string') {
          const match = game.trim().match(/^(\d+)\s*-\s*(\d+)$/);
          if (!match) return null;
          return { player: Number(match[1]), opponent: Number(match[2]) };
        }
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
    FNL: '决赛',
    'FNL-': '决赛',
    Bronze: '铜牌赛',
    SemiFinal: '半决赛',
    SFNL: '半决赛',
    QuarterFinal: '四分之一决赛',
    QFNL: '四分之一决赛',
    '8FNL': '16 强',
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
  drawCode?: string | null;
  label: string;
  order: number;
  matches: Array<{
    matchId: number;
    scheduleMatchId: number | string | null;
    externalUnitCode?: string | null;
    drawRound: string;
    roundLabel: string;
    roundOrder: number;
    matchScore: string | null;
    games: Array<{ player: number; opponent: number }>;
    sides: Array<{ sideNo: number; isWinner: boolean; previousUnit?: string | null; players: SidePlayer[] }>;
  }>;
};

type EventSessionScheduleRow = {
  id: number;
  dayIndex: number;
  sessionIndex: number | null;
  localDate: string;
  sessionTitle: string | null;
  startTime: string | null;
  morningSessionStart: string | null;
  afternoonSessionStart: string | null;
  venueRaw: string | null;
  tableCount: number | null;
  tableLabel: string | null;
  rawSubEventsText: string | null;
  parsedRoundsJson: string | null;
};

type EventScheduleDay = {
  localDate: string;
  matches: EventScheduleMatch[];
};

type EventScheduleMatch = {
  scheduleMatchId: number | string;
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

type WttBracketAthlete = {
  Code?: string | null;
  Description?: {
    GivenName?: string | null;
    FamilyName?: string | null;
    Organization?: string | null;
    IfId?: string | null;
  } | null;
};

type WttBracketCompetitorPlace = {
  Pos?: number | string | null;
  Code?: string | null;
  PreviousUnit?: {
    Unit?: string | null;
  } | null;
  Competitor?: {
    Code?: string | null;
    Organization?: string | null;
    Description?: {
      TeamName?: string | null;
    } | null;
    Composition?: {
      Athlete?: WttBracketAthlete[] | WttBracketAthlete | null;
    } | null;
  } | null;
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

  return scheduleMatchSortId(left.scheduleMatchId) >= scheduleMatchSortId(right.scheduleMatchId) ? left : right;
}

function scheduleMatchSortId(value: number | string | null) {
  if (typeof value === 'number') return value;
  const parsed = Number(String(value ?? '').replace(/^cm:/, ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

function scheduleStagePriority(match: EventScheduleMatch) {
  const text = `${match.stageCode ?? ''} ${match.stageNameZh ?? ''}`.trim();
  const lower = text.toLowerCase();
  const divisionMatch = text.match(/Division\s*(\d+)|第([一二三四五六七八九十\d]+)级别/i);
  const zhDigits: Record<string, number> = {
    一: 1,
    二: 2,
    三: 3,
    四: 4,
    五: 5,
    六: 6,
    七: 7,
    八: 8,
    九: 9,
    十: 10,
  };
  const divisionValue = divisionMatch?.[1] ?? divisionMatch?.[2] ?? '';
  const division = /^\d+$/.test(divisionValue) ? Number(divisionValue) : zhDigits[divisionValue] ?? 99;
  const stageType = lower.includes('main draw') || text.includes('正赛') || text.includes('主赛')
    ? 0
    : lower.includes('position') || text.includes('排位赛')
      ? 1
      : lower.includes('qualification') || text.includes('资格赛')
        ? 2
        : 3;
  return stageType * 100 + division;
}

function scheduleRoundPriority(match: EventScheduleMatch) {
  const meta = teamTieRoundMeta(match.roundCode, match.roundNameZh);
  return meta.order > 0 ? -meta.order : 0;
}

function compareScheduleMatches(left: EventScheduleMatch, right: EventScheduleMatch) {
  if (!left.scheduledLocalAt && !right.scheduledLocalAt) {
    const stageDiff = scheduleStagePriority(left) - scheduleStagePriority(right);
    if (stageDiff !== 0) return stageDiff;
    const roundDiff = scheduleRoundPriority(left) - scheduleRoundPriority(right);
    if (roundDiff !== 0) return roundDiff;
  }

  const timeDiff = (left.scheduledLocalAt ?? '').localeCompare(right.scheduledLocalAt ?? '');
  if (timeDiff !== 0) return timeDiff;
  const stageDiff = scheduleStagePriority(left) - scheduleStagePriority(right);
  if (stageDiff !== 0) return stageDiff;
  const roundDiff = scheduleRoundPriority(left) - scheduleRoundPriority(right);
  if (roundDiff !== 0) return roundDiff;
  const groupDiff = (left.groupCode ?? '').localeCompare(right.groupCode ?? '');
  if (groupDiff !== 0) return groupDiff;
  const tableDiff = (left.tableNo ?? '').localeCompare(right.tableNo ?? '');
  if (tableDiff !== 0) return tableDiff;
  const sessionDiff = (left.sessionLabel ?? '').localeCompare(right.sessionLabel ?? '');
  if (sessionDiff !== 0) return sessionDiff;
  return scheduleMatchSortId(left.scheduleMatchId) - scheduleMatchSortId(right.scheduleMatchId);
}

function normalizeHistoricalSidePlayerCountry(player: SidePlayer): { player: SidePlayer; changed: boolean } {
  const historicalCountry = historicalCountryForPlayer(player.name, player.countryCode);
  if (!historicalCountry || historicalCountry === player.countryCode) {
    return { player, changed: false };
  }
  return { player: { ...player, countryCode: historicalCountry }, changed: true };
}

function normalizeHistoricalTeamSide(
  side: EventScheduleMatch['sides'][number],
): { side: EventScheduleMatch['sides'][number]; changed: boolean } {
  let changed = false;
  const players = side.players.map((player) => {
    const normalized = normalizeHistoricalSidePlayerCountry(player);
    changed ||= normalized.changed;
    return normalized.player;
  });
  const mappedCountries = Array.from(new Set(players.map((player) => player.countryCode).filter(Boolean))) as string[];
  const teamCode = changed && mappedCountries.length === 1 ? mappedCountries[0] : side.teamCode;
  return {
    side: {
      ...side,
      teamCode,
      players,
    },
    changed: changed || teamCode !== side.teamCode,
  };
}

function scheduleTeamPairKey(match: EventScheduleMatch) {
  const teamCodes = match.sides.map((side) => side.teamCode).filter((code): code is string => Boolean(code));
  if (teamCodes.length < 2) return null;
  return teamCodes.slice().sort().join('|');
}

function scheduleMatchMergeKey(match: EventScheduleMatch) {
  const teamPair = scheduleTeamPairKey(match);
  if (!teamPair) return null;
  return [
    match.subEventTypeCode,
    match.stageCode,
    match.roundCode,
    match.groupCode ?? '',
    match.scheduledLocalAt ?? '',
    teamPair,
  ].join('::');
}

function mergeHistoricalScheduleMatches(matches: EventScheduleMatch[]) {
  const normalized = matches.map((match) => {
    let changed = false;
    const sides = match.sides.map((side) => {
      const normalizedSide = normalizeHistoricalTeamSide(side);
      changed ||= normalizedSide.changed;
      return normalizedSide.side;
    });
    return { match: { ...match, sides }, changed };
  });

  const groups = new Map<string, Array<{ match: EventScheduleMatch; changed: boolean }>>();
  const passthrough: EventScheduleMatch[] = [];
  for (const item of normalized) {
    const key = scheduleMatchMergeKey(item.match);
    if (!key) {
      passthrough.push(item.match);
      continue;
    }
    const current = groups.get(key) ?? [];
    current.push(item);
    groups.set(key, current);
  }

  const merged: EventScheduleMatch[] = [...passthrough];
  for (const group of groups.values()) {
    if (group.length === 1 || !group.some((item) => item.changed)) {
      merged.push(...group.map((item) => item.match));
      continue;
    }

    const base = group
      .map((item) => item.match)
      .sort((left, right) => Math.abs(scheduleMatchSortId(left.scheduleMatchId)) - Math.abs(scheduleMatchSortId(right.scheduleMatchId)))[0];
    const sideMap = new Map<string, EventScheduleMatch['sides'][number]>();
    for (const item of group) {
      for (const side of item.match.sides) {
        const key = side.teamCode ?? String(side.sideNo);
        const current = sideMap.get(key) ?? { ...side, players: [] };
        const seen = new Set(current.players.map((player) => `${player.name}|${player.countryCode ?? ''}`));
        for (const player of side.players) {
          const playerKey = `${player.name}|${player.countryCode ?? ''}`;
          if (seen.has(playerKey)) continue;
          seen.add(playerKey);
          current.players.push(player);
        }
        current.isWinner ||= side.isWinner;
        sideMap.set(key, current);
      }
    }
    const baseTeamOrder = base.sides.map((side) => side.teamCode).filter((code): code is string => Boolean(code));
    const sides = Array.from(sideMap.values())
      .sort((left, right) => {
        const leftIdx = baseTeamOrder.indexOf(left.teamCode ?? '');
        const rightIdx = baseTeamOrder.indexOf(right.teamCode ?? '');
        return (leftIdx < 0 ? 99 : leftIdx) - (rightIdx < 0 ? 99 : rightIdx);
      })
      .slice(0, 2)
      .map((side, index) => ({ ...side, sideNo: index + 1 }))
      .sort((left, right) => left.sideNo - right.sideNo);
    const scoreByTeam = new Map(sides.map((side) => [side.teamCode ?? String(side.sideNo), 0]));
    for (const item of group) {
      const parsed = parseTieScore(item.match.matchScore);
      if (!parsed) continue;
      const [sideA, sideB] = [...item.match.sides].sort((left, right) => left.sideNo - right.sideNo);
      if (sideA?.teamCode && scoreByTeam.has(sideA.teamCode)) {
        scoreByTeam.set(sideA.teamCode, (scoreByTeam.get(sideA.teamCode) ?? 0) + parsed.scoreA);
      }
      if (sideB?.teamCode && scoreByTeam.has(sideB.teamCode)) {
        scoreByTeam.set(sideB.teamCode, (scoreByTeam.get(sideB.teamCode) ?? 0) + parsed.scoreB);
      }
    }
    const [mergedSideA, mergedSideB] = sides;
    const scoreA = mergedSideA?.teamCode ? scoreByTeam.get(mergedSideA.teamCode) ?? 0 : 0;
    const scoreB = mergedSideB?.teamCode ? scoreByTeam.get(mergedSideB.teamCode) ?? 0 : 0;
    const matchScore = scoreA || scoreB ? `${scoreA}-${scoreB}` : base.matchScore;
    const winnerSide = scoreA === scoreB ? base.winnerSide : scoreA > scoreB ? 'A' : 'B';
    merged.push({
      ...base,
      scheduleMatchId: base.scheduleMatchId,
      matchScore,
      winnerSide,
      sides: sides.map((side) => ({ ...side, isWinner: side.sideNo === (winnerSide === 'A' ? 1 : winnerSide === 'B' ? 2 : -1) })),
    });
  }

  return merged.sort(compareScheduleMatches);
}

function buildCurrentScheduleMatches(eventId: number) {
  const scheduleRows = db
    .prepare(
      `
        SELECT
          t.current_team_tie_id AS scheduleMatchId,
          t.external_match_code AS externalMatchCode,
          t.sub_event_type_code AS subEventTypeCode,
          st.name_zh AS subEventNameZh,
          t.stage_code AS stageCode,
          COALESCE(sc.name_zh, t.stage_label) AS stageNameZh,
          t.round_code AS roundCode,
          COALESCE(rc.name_zh, t.round_label) AS roundNameZh,
          t.group_code AS groupCode,
          t.scheduled_local_at AS scheduledLocalAt,
          t.scheduled_utc_at AS scheduledUtcAt,
          t.table_no AS tableNo,
          t.session_label AS sessionLabel,
          t.status,
          t.source_schedule_status AS rawScheduleStatus,
          t.match_score AS matchScore,
          NULL AS games,
          t.winner_side AS winnerSide,
          s.current_team_tie_side_id AS scheduleSideId,
          s.side_no AS sideNo,
          NULL AS entryId,
          NULL AS placeholderText,
          s.team_code AS teamCode,
          s.seed,
          s.qualifier,
          s.is_winner AS isWinner,
          p.player_order AS playerOrder,
          p.player_id AS playerId,
          p.player_name AS playerName,
          p.player_country AS playerCountry,
          pl.slug,
          pl.name_zh AS playerNameZh
        FROM current_event_team_ties t
        LEFT JOIN sub_event_types st ON st.code = t.sub_event_type_code
        LEFT JOIN stage_codes sc ON sc.code = t.stage_code
        LEFT JOIN round_codes rc ON rc.code = t.round_code
        LEFT JOIN current_event_team_tie_sides s ON s.current_team_tie_id = t.current_team_tie_id
        LEFT JOIN current_event_team_tie_side_players p ON p.current_team_tie_side_id = s.current_team_tie_side_id
        LEFT JOIN players pl ON pl.player_id = p.player_id
        WHERE t.event_id = ?
        UNION ALL
        SELECT
          'cm:' || m.current_match_id AS scheduleMatchId,
          m.external_match_code AS externalMatchCode,
          m.sub_event_type_code AS subEventTypeCode,
          st.name_zh AS subEventNameZh,
          m.stage_code AS stageCode,
          COALESCE(sc.name_zh, m.stage_label) AS stageNameZh,
          m.round_code AS roundCode,
          COALESCE(rc.name_zh, m.round_label) AS roundNameZh,
          m.group_code AS groupCode,
          m.scheduled_local_at AS scheduledLocalAt,
          m.scheduled_utc_at AS scheduledUtcAt,
          m.table_no AS tableNo,
          m.session_label AS sessionLabel,
          m.status,
          m.source_schedule_status AS rawScheduleStatus,
          m.match_score AS matchScore,
          m.games,
          m.winner_side AS winnerSide,
          s.current_match_side_id AS scheduleSideId,
          s.side_no AS sideNo,
          NULL AS entryId,
          s.placeholder_text AS placeholderText,
          s.team_code AS teamCode,
          s.seed,
          s.qualifier,
          s.is_winner AS isWinner,
          p.player_order AS playerOrder,
          p.player_id AS playerId,
          p.player_name AS playerName,
          p.player_country AS playerCountry,
          pl.slug,
          pl.name_zh AS playerNameZh
        FROM current_event_matches m
        LEFT JOIN sub_event_types st ON st.code = m.sub_event_type_code
        LEFT JOIN stage_codes sc ON sc.code = m.stage_code
        LEFT JOIN round_codes rc ON rc.code = m.round_code
        LEFT JOIN current_event_match_sides s ON s.current_match_id = m.current_match_id
        LEFT JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
        LEFT JOIN players pl ON pl.player_id = p.player_id
        WHERE m.event_id = ?
          AND m.current_team_tie_id IS NULL
        ORDER BY scheduledLocalAt ASC, scheduleMatchId ASC, sideNo ASC, playerOrder ASC
      `,
    )
    .all(eventId, eventId) as Array<{
    scheduleMatchId: number | string;
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

  const scheduleMatchMap = new Map<number | string, EventScheduleMatch>();
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

  return Array.from(scheduleMatchMap.values())
    .map((match) => ({
      ...match,
      sides: [...match.sides].sort((left, right) => left.sideNo - right.sideNo),
    }))
    .sort(compareScheduleMatches);
}

function buildHistoricalTeamTieScheduleMatches(eventId: number) {
  const scheduleRows = db
    .prepare(
      `
        SELECT
          -t.team_tie_id AS scheduleMatchId,
          t.source_key AS externalMatchCode,
          t.sub_event_type_code AS subEventTypeCode,
          st.name_zh AS subEventNameZh,
          COALESCE(t.stage_code, t.stage, '') AS stageCode,
          COALESCE(sc.name_zh, t.stage_zh, t.stage) AS stageNameZh,
          COALESCE(t.round_code, t.round, '') AS roundCode,
          COALESCE(rc.name_zh, t.round_zh, t.round) AS roundNameZh,
          t.group_code AS groupCode,
          NULL AS scheduledLocalAt,
          NULL AS scheduledUtcAt,
          NULL AS tableNo,
          NULL AS sessionLabel,
          t.status,
          t.source_type AS rawScheduleStatus,
          t.match_score AS matchScore,
          NULL AS games,
          t.winner_side AS winnerSide,
          s.team_tie_side_id AS scheduleSideId,
          s.side_no AS sideNo,
          NULL AS entryId,
          NULL AS placeholderText,
          s.team_code AS teamCode,
          s.seed,
          s.qualifier,
          s.is_winner AS isWinner,
          p.player_order AS playerOrder,
          p.player_id AS playerId,
          p.player_name AS playerName,
          p.player_country AS playerCountry,
          pl.slug,
          pl.name_zh AS playerNameZh
        FROM team_ties t
        LEFT JOIN sub_event_types st ON st.code = t.sub_event_type_code
        LEFT JOIN stage_codes sc ON sc.code = t.stage_code
        LEFT JOIN round_codes rc ON rc.code = t.round_code
        LEFT JOIN team_tie_sides s ON s.team_tie_id = t.team_tie_id
        LEFT JOIN team_tie_side_players p ON p.team_tie_side_id = s.team_tie_side_id
        LEFT JOIN players pl ON pl.player_id = p.player_id
        WHERE t.event_id = ?
        ORDER BY t.team_tie_id ASC, s.side_no ASC, p.player_order ASC
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
        games: [],
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

  return mergeHistoricalScheduleMatches(Array.from(scheduleMatchMap.values())
    .map((match) => ({
      ...match,
      sides: [...match.sides].sort((left, right) => left.sideNo - right.sideNo),
    }))
    .sort(compareScheduleMatches));
}

function buildHistoricalMergedScheduleMatchDetail(match: {
  scheduleMatchId: number;
  eventId: number;
  eventName: string | null;
  eventNameZh: string | null;
  eventYear: number | null;
  subEventTypeCode: string;
  startDate: string | null;
  endDate: string | null;
}) {
  const mergedMatch = buildHistoricalTeamTieScheduleMatches(match.eventId).find((item) => item.scheduleMatchId === match.scheduleMatchId);
  const mergedTie = buildTeamTiesForSubEvent(match.eventId, match.subEventTypeCode).find((item) => item.scheduleMatchId === match.scheduleMatchId);
  if (!mergedMatch || !mergedTie) return null;

  const playerIds = [
    ...mergedMatch.sides.flatMap((side) => side.players.map((player) => player.playerId)),
    ...mergedTie.rubbers.flatMap((rubber) => rubber.sides.flatMap((side) => side.players.map((player) => player.playerId))),
  ].filter((playerId): playerId is number => playerId != null);
  const playerDisplayMap = loadRosterPlayerDisplayMap(Array.from(new Set(playerIds)));
  const teamCodeBySideNo = new Map(mergedMatch.sides.map((side) => [side.sideNo, side.teamCode ?? null]));

  return {
    match: {
      scheduleMatchId: mergedMatch.scheduleMatchId,
      eventId: match.eventId,
      eventName: match.eventName,
      eventNameZh: match.eventNameZh,
      eventYear: match.eventYear,
      subEventTypeCode: mergedMatch.subEventTypeCode,
      subEventNameZh: mergedMatch.subEventNameZh,
      stageCode: mergedMatch.stageCode,
      stageNameZh: mergedMatch.stageNameZh,
      roundCode: mergedMatch.roundCode,
      roundNameZh: mergedMatch.roundNameZh,
      roundLabel: roundLabel(mergedMatch.roundCode, mergedMatch.roundNameZh),
      groupCode: mergedMatch.groupCode,
      scheduledLocalAt: mergedMatch.scheduledLocalAt,
      scheduledUtcAt: mergedMatch.scheduledUtcAt,
      tableNo: mergedMatch.tableNo,
      sessionLabel: mergedMatch.sessionLabel,
      status: mergedMatch.status,
      rawScheduleStatus: mergedMatch.rawScheduleStatus,
      matchScore: mergedMatch.matchScore,
      games: parseGames(null),
      winnerSide: mergedMatch.winnerSide,
      startDate: match.startDate,
      endDate: match.endDate,
      externalMatchCode: mergedMatch.externalMatchCode,
    },
    sides: mergedMatch.sides
      .map((side) => ({
        sideNo: side.sideNo,
        isWinner: side.isWinner,
        teamCode: side.teamCode,
        seed: side.seed,
        qualifier: side.qualifier,
        placeholderText: side.placeholderText,
        players: side.players.map((player) => {
          const display = player.playerId == null ? null : playerDisplayMap.get(player.playerId);
          return {
            ...player,
            avatarFile: display?.avatarFile ?? null,
          };
        }),
      }))
      .sort((left, right) => left.sideNo - right.sideNo),
    rubbers: mergedTie.rubbers.map((rubber) => ({
      matchId: rubber.matchId,
      matchScore: rubber.matchScore,
      games: parseGames(null),
      winnerSide: rubber.winnerSide,
      sides: rubber.sides
        .map((side) => ({
          sideNo: side.sideNo,
          teamCode: teamCodeBySideNo.get(side.sideNo) ?? null,
          players: side.players.map((player) => {
            const display = player.playerId == null ? null : playerDisplayMap.get(player.playerId);
            return {
              ...player,
              avatarFile: display?.avatarFile ?? null,
            };
          }),
        }))
        .sort((left, right) => left.sideNo - right.sideNo),
    })),
  };
}

function buildTeamTieScheduleMatchDetail(
  matchMeta: {
    scheduleMatchId: number | string;
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
    status: string;
    rawScheduleStatus: string | null;
    startDate: string | null;
    endDate: string | null;
    externalMatchCode: string | null;
  },
  tie: TeamTie,
) {
  const rosterPlayerIds = [
    ...tie.rubbers.flatMap((rubber) => rubber.sides.flatMap((side) => side.players.map((player) => player.playerId))),
  ].filter((playerId): playerId is number => playerId != null);
  const playerDisplayMap = loadRosterPlayerDisplayMap(Array.from(new Set(rosterPlayerIds)));

  const sides = [
    {
      sideNo: 1,
      isWinner: tie.winnerCode === tie.teamA.code,
      teamCode: tie.teamA.code,
      seed: null,
      qualifier: null,
      placeholderText: null,
      players: Array.from(
        new Map(
          tie.rubbers
            .flatMap((rubber) => rubber.sides.find((side) => side.sideNo === 1)?.players ?? [])
            .map((player) => {
              const display = player.playerId == null ? null : playerDisplayMap.get(player.playerId);
              return [
                `${player.name}|${player.countryCode ?? ''}`,
                {
                  ...player,
                  avatarFile: display?.avatarFile ?? null,
                },
              ];
            }),
        ).values(),
      ),
    },
    {
      sideNo: 2,
      isWinner: tie.winnerCode === tie.teamB.code,
      teamCode: tie.teamB.code,
      seed: null,
      qualifier: null,
      placeholderText: null,
      players: Array.from(
        new Map(
          tie.rubbers
            .flatMap((rubber) => rubber.sides.find((side) => side.sideNo === 2)?.players ?? [])
            .map((player) => {
              const display = player.playerId == null ? null : playerDisplayMap.get(player.playerId);
              return [
                `${player.name}|${player.countryCode ?? ''}`,
                {
                  ...player,
                  avatarFile: display?.avatarFile ?? null,
                },
              ];
            }),
        ).values(),
      ),
    },
  ];

  return {
    match: {
      scheduleMatchId: matchMeta.scheduleMatchId,
      eventId: matchMeta.eventId,
      eventName: matchMeta.eventName,
      eventNameZh: matchMeta.eventNameZh,
      eventYear: matchMeta.eventYear,
      subEventTypeCode: matchMeta.subEventTypeCode,
      subEventNameZh: matchMeta.subEventNameZh,
      stageCode: matchMeta.stageCode,
      stageNameZh: matchMeta.stageNameZh,
      roundCode: matchMeta.roundCode,
      roundNameZh: matchMeta.roundNameZh,
      roundLabel: roundLabel(matchMeta.roundCode, matchMeta.roundNameZh),
      groupCode: matchMeta.groupCode,
      scheduledLocalAt: null,
      scheduledUtcAt: null,
      tableNo: null,
      sessionLabel: null,
      status: matchMeta.status,
      rawScheduleStatus: matchMeta.rawScheduleStatus,
      matchScore: `${tie.scoreA}-${tie.scoreB}`,
      games: parseGames(null),
      winnerSide: tie.winnerCode === tie.teamA.code ? 'A' : tie.winnerCode === tie.teamB.code ? 'B' : null,
      startDate: matchMeta.startDate,
      endDate: matchMeta.endDate,
      externalMatchCode: matchMeta.externalMatchCode,
    },
    sides,
    rubbers: tie.rubbers.map((rubber) => ({
      matchId: rubber.matchId,
      externalMatchCode: null,
      matchScore: rubber.matchScore,
      games: parseGames(null),
      winnerSide: rubber.winnerSide,
      sides: rubber.sides
        .map((side) => ({
          sideNo: side.sideNo,
          teamCode: side.sideNo === 1 ? tie.teamA.code : side.sideNo === 2 ? tie.teamB.code : null,
          players: side.players.map((player) => {
            const display = player.playerId == null ? null : playerDisplayMap.get(player.playerId);
            return {
              ...player,
              avatarFile: display?.avatarFile ?? null,
            };
          }),
        }))
        .sort((left, right) => left.sideNo - right.sideNo),
    })),
  };
}

function buildOverrideScheduleMatchDetail(scheduleMatchId: string) {
  const parts = scheduleMatchId.split(':');
  if (parts.length < 4 || parts[0] !== 'override') return null;
  const eventId = Number(parts[1]);
  const subEventTypeCode = parts[2];
  if (!Number.isFinite(eventId)) return null;

  const override = readManualEventOverride(eventId);
  if (!override || !isTeamKnockoutOverride(override) || override.sub_event_type_code !== subEventTypeCode) {
    return null;
  }

  const overrideRoundTie = override.display_rounds
    ?.flatMap((round) =>
      round.ties.map((tie) => ({
        round,
        tie,
      })),
    )
    .find((item) => item.tie.schedule_match_id === scheduleMatchId);
  if (!overrideRoundTie) return null;

  const eventRow = db
    .prepare(
      `
        SELECT
          event_id AS eventId,
          name AS eventName,
          name_zh AS eventNameZh,
          year AS eventYear,
          start_date AS startDate,
          end_date AS endDate
        FROM events
        WHERE event_id = ?
      `,
    )
    .get(eventId) as
    | {
        eventId: number;
        eventName: string | null;
        eventNameZh: string | null;
        eventYear: number | null;
        startDate: string | null;
        endDate: string | null;
      }
    | undefined;
  if (!eventRow) return null;

  const subEventNameZh = db
    .prepare(
      `
        SELECT name_zh AS nameZh
        FROM sub_event_types
        WHERE code = ?
      `,
    )
    .get(subEventTypeCode) as { nameZh: string | null } | undefined;

  const ties = buildTeamTiesForSubEvent(eventId, subEventTypeCode);
  const tieById = new Map(ties.map((tie) => [String(tie.tieId), tie]));
  const syntheticTie = buildOverrideTeamTie(overrideRoundTie.tie, tieById);
  if (!syntheticTie) return null;

  return buildTeamTieScheduleMatchDetail(
    {
      scheduleMatchId,
      eventId: eventRow.eventId,
      eventName: eventRow.eventName,
      eventNameZh: eventRow.eventNameZh,
      eventYear: eventRow.eventYear,
      subEventTypeCode,
      subEventNameZh: subEventNameZh?.nameZh ?? null,
      stageCode: syntheticTie.stage,
      stageNameZh: syntheticTie.stageZh,
      roundCode: overrideRoundTie.round.code.includes(':')
        ? overrideRoundTie.round.code.slice(overrideRoundTie.round.code.lastIndexOf(':') + 1)
        : overrideRoundTie.round.code,
      roundNameZh: syntheticTie.roundZh,
      groupCode: null,
      status: 'finished',
      rawScheduleStatus: 'override_aggregate',
      startDate: eventRow.startDate,
      endDate: eventRow.endDate,
      externalMatchCode: syntheticTie.externalMatchCode,
    },
    syntheticTie,
  );
}

type TeamTie = {
  tieId: string;
  scheduleMatchId: number | string | null;
  externalMatchCode: string | null;
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
  qualificationMark?: string | null;
};

type ImportedGroupStandingRow = {
  stageLabel: string;
  teamCode: string;
  groupCode: string;
  organizationCode: string;
  qualificationMark: string | null;
  played: number | null;
  won: number | null;
  lost: number | null;
  result: number | null;
  rank: number | null;
  scoreFor: number | null;
  scoreAgainst: number | null;
  gamesWon: number | null;
  gamesLost: number | null;
  playersJson: string | null;
};

type TeamRosterPlayer = {
  playerId: number | null;
  slug: string | null;
  name: string;
  nameZh: string | null;
  countryCode: string | null;
  avatarFile: string | null;
  order: number | null;
};

type TeamRoster = {
  eventId: number;
  subEventCode: string;
  teamCode: string;
  teamName: string;
  teamNameZh: string | null;
  source: 'group_standings' | 'draw_entries' | 'historical_matches';
  players: TeamRosterPlayer[];
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
    third_place_second?: string | null;
  };
  ties: {
    final: {
      team_codes: [string, string];
    };
    bronze?: {
      team_codes: [string, string];
    } | null;
  };
  display_rounds?: Array<{
    code: string;
    label?: string;
    order?: number;
    ties: Array<{
      source_tie_ids: Array<number | string>;
      tie_id?: string;
      schedule_match_id?: number | string | null;
      team_a_code?: string;
      team_b_code?: string;
      team_a_name?: string;
      team_b_name?: string;
      score_a?: number;
      score_b?: number;
      winner_code?: string | null;
      side_code_map?: Record<string, string>;
    }>;
  }>;
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
    qualificationMark: null,
  };
}

function loadRosterPlayerDisplayMap(playerIds: number[]) {
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

function parseRosterPlayersJson(value: string | null) {
  if (!value) return [] as Array<{ playerId: number | null; name: string; countryCode: string | null; order: number | null }>;
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => {
        if (!item || typeof item !== 'object') return null;
        const record = item as {
          if_id?: unknown;
          code?: unknown;
          name?: unknown;
          organization?: unknown;
          order?: unknown;
        };
        const playerIdSource = record.if_id ?? record.code;
        const playerId = Number(playerIdSource);
        const name = typeof record.name === 'string' ? record.name.trim() : '';
        if (!name) return null;
        const order = Number(record.order);
        return {
          playerId: Number.isFinite(playerId) ? playerId : null,
          name,
          countryCode: typeof record.organization === 'string' && record.organization.trim() ? record.organization.trim() : null,
          order: Number.isFinite(order) ? order : null,
        };
      })
      .filter((item): item is { playerId: number | null; name: string; countryCode: string | null; order: number | null } => item != null);
  } catch {
    return [];
  }
}

function buildRosterPlayers(
  players: Array<{ playerId: number | null; name: string; countryCode: string | null; order: number | null }>,
): TeamRosterPlayer[] {
  const displayMap = loadRosterPlayerDisplayMap(
    Array.from(new Set(players.map((player) => player.playerId).filter((playerId): playerId is number => playerId != null))),
  );

  return players
    .map((player) => {
      const display = player.playerId != null ? displayMap.get(player.playerId) : null;
      return {
        playerId: player.playerId,
        slug: display?.slug ?? null,
        name: player.name,
        nameZh: display?.nameZh ?? null,
        countryCode: player.countryCode,
        avatarFile: display?.avatarFile ?? null,
        order: player.order,
      };
    })
    .sort((left, right) => {
      const orderDiff = (left.order ?? 999) - (right.order ?? 999);
      if (orderDiff !== 0) return orderDiff;
      if (left.playerId != null && right.playerId != null) return left.playerId - right.playerId;
      return left.name.localeCompare(right.name);
    });
}

function normalizeImportedGroupStageLabel(stageLabel: string) {
  return /groups/i.test(stageLabel) ? 'Groups' : stageLabel;
}

function displayImportedGroupStageLabel(stageLabel: string) {
  return stageLabel === 'Groups' ? '小组赛' : stageLabel;
}

function hasTable(name: string) {
  const row = db
    .prepare(
      `
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
      `,
    )
    .get(name) as { 1?: number } | undefined;
  return Boolean(row);
}

function hasEventGroupStandingsTable() {
  return hasTable('event_group_standings');
}

function hasCurrentEventGroupStandingsTable() {
  return hasTable('current_event_group_standings');
}

function eventTeamCodeFromSubEventCode(subEventCode: string) {
  switch (subEventCode) {
    case 'MT':
      return 'MTEAM';
    case 'WT':
      return 'WTEAM';
    default:
      return null;
  }
}

function loadImportedGroupStandings(eventId: number, subEventCode: string, useCurrent = false) {
  const teamCode = eventTeamCodeFromSubEventCode(subEventCode);
  const tableName = useCurrent ? 'current_event_group_standings' : 'event_group_standings';
  const tableExists = useCurrent ? hasCurrentEventGroupStandingsTable() : hasEventGroupStandingsTable();
  if (!teamCode || !tableExists) return [] as ImportedGroupStandingRow[];

  return db
    .prepare(
      `
        SELECT
          stage_label AS stageLabel,
          team_code AS teamCode,
          group_code AS groupCode,
          organization_code AS organizationCode,
          qualification_mark AS qualificationMark,
          qualification_mark AS qualification_mark,
          played,
          won,
          lost,
          result,
          rank,
          score_for AS scoreFor,
          score_against AS scoreAgainst,
          games_won AS gamesWon,
          games_lost AS gamesLost,
          players_json AS playersJson
        FROM ${tableName}
        WHERE event_id = ?
          AND team_code = ?
        ORDER BY stage_label ASC, group_code ASC, rank ASC, organization_code ASC
      `,
    )
    .all(eventId, teamCode) as ImportedGroupStandingRow[];
}

function loadTeamRosterFromGroupStandings(eventId: number, subEventCode: string, teamCode: string, useCurrent = false): TeamRoster | null {
  const standings = loadImportedGroupStandings(eventId, subEventCode, useCurrent);
  const matched = standings.find((row) => row.organizationCode === teamCode && parseRosterPlayersJson(row.playersJson).length > 0);
  if (!matched) return null;

  return {
    eventId,
    subEventCode,
    teamCode,
    teamName: matched.organizationCode,
    teamNameZh: null,
    source: 'group_standings',
    players: buildRosterPlayers(parseRosterPlayersJson(matched.playersJson)),
  };
}

function loadTeamRosterFromCurrentTeamTies(eventId: number, subEventCode: string, teamCode: string): TeamRoster | null {
  if (!hasTable('current_event_team_tie_side_players')) return null;

  const rows = db
    .prepare(
      `
        SELECT
          MIN(p.player_order) AS playerOrder,
          MAX(p.player_id) AS playerId,
          p.player_name AS playerName,
          p.player_country AS playerCountry
        FROM current_event_team_ties t
        JOIN current_event_team_tie_sides s ON s.current_team_tie_id = t.current_team_tie_id
        JOIN current_event_team_tie_side_players p ON p.current_team_tie_side_id = s.current_team_tie_side_id
        WHERE t.event_id = ?
          AND t.sub_event_type_code = ?
          AND s.team_code = ?
        GROUP BY p.player_name, p.player_country
        ORDER BY playerOrder ASC
      `,
    )
    .all(eventId, subEventCode, teamCode) as Array<{
    playerOrder: number | null;
    playerId: number | null;
    playerName: string;
    playerCountry: string | null;
  }>;

  if (rows.length === 0) return null;

  return {
    eventId,
    subEventCode,
    teamCode,
    teamName: teamCode,
    teamNameZh: null,
    source: 'group_standings',
    players: buildRosterPlayers(
      rows.map((row) => ({
        playerId: row.playerId,
        name: row.playerName,
        countryCode: row.playerCountry,
        order: row.playerOrder,
      })),
    ),
  };
}

function isHistoricalEvent(endDate: string | null) {
  if (!endDate) return false;
  const today = new Date();
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  return endDate < todayIso;
}

function loadTeamRosterFromHistoricalMatches(eventId: number, subEventCode: string, teamCode: string): TeamRoster | null {
  const rows = db
    .prepare(
      `
        SELECT
          COALESCE(p.player_id, msp.player_id) AS playerId,
          msp.player_name AS playerName,
          COALESCE(p.name_zh, NULL) AS playerNameZh,
          COALESCE(p.country_code, msp.player_country) AS countryCode,
          MIN(msp.player_order) AS firstOrder,
          COUNT(*) AS appearances
        FROM matches m
        JOIN match_sides ms ON ms.match_id = m.match_id
        JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
        LEFT JOIN players p ON p.player_id = msp.player_id
        WHERE m.event_id = ?
          AND m.sub_event_type_code = ?
          AND COALESCE(p.country_code, msp.player_country) = ?
        GROUP BY COALESCE(p.player_id, msp.player_id), msp.player_name, COALESCE(p.name_zh, NULL), COALESCE(p.country_code, msp.player_country)
        ORDER BY firstOrder ASC, appearances DESC, playerId ASC, playerName ASC
      `,
    )
    .all(eventId, subEventCode, teamCode) as Array<{
    playerId: number | null;
    playerName: string;
    playerNameZh: string | null;
    countryCode: string | null;
    firstOrder: number | null;
    appearances: number;
  }>;

  if (rows.length === 0) return null;

  return {
    eventId,
    subEventCode,
    teamCode,
    teamName: teamCode,
    teamNameZh: null,
    source: 'historical_matches',
    players: buildRosterPlayers(
      rows.map((row) => ({
        playerId: row.playerId,
        name: row.playerName,
        countryCode: row.countryCode,
        order: row.firstOrder,
      })),
    ),
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

function parseBracketPayload(rawSourcePayload: string | null): { competitorPlaces: WttBracketCompetitorPlace[] } {
  if (!rawSourcePayload) return { competitorPlaces: [] };
  try {
    const payload = JSON.parse(rawSourcePayload) as { CompetitorPlace?: unknown };
    const places = Array.isArray(payload.CompetitorPlace) ? payload.CompetitorPlace : [];
    return { competitorPlaces: places as WttBracketCompetitorPlace[] };
  } catch {
    return { competitorPlaces: [] };
  }
}

function formatBracketAthleteName(athlete: WttBracketAthlete) {
  const description = athlete.Description;
  const familyName = description?.FamilyName?.trim();
  const givenName = description?.GivenName?.trim();
  return [familyName, givenName].filter(Boolean).join(' ').trim();
}

function playerIdFromBracketAthlete(athlete: WttBracketAthlete) {
  const rawId = athlete.Description?.IfId ?? athlete.Code;
  const parsed = Number(String(rawId ?? '').trim());
  return Number.isFinite(parsed) ? parsed : null;
}

function collectBracketPlayerIds(rawSourcePayload: string | null) {
  const { competitorPlaces } = parseBracketPayload(rawSourcePayload);
  const ids: number[] = [];
  for (const place of competitorPlaces) {
    const athletesRaw = place.Competitor?.Composition?.Athlete;
    const athletes = Array.isArray(athletesRaw) ? athletesRaw : athletesRaw ? [athletesRaw] : [];
    for (const athlete of athletes) {
      const playerId = playerIdFromBracketAthlete(athlete);
      if (playerId != null) ids.push(playerId);
    }
  }
  return ids;
}

function playersFromCurrentBracketPayload(
  rawSourcePayload: string | null,
  sideNo: 1 | 2,
  fallbackTeamCode: string | null,
  fallbackPlaceholder: string | null,
  playerMap: Map<number, { slug: string | null; nameZh: string | null; avatarFile: string | null }>,
): SidePlayer[] {
  const { competitorPlaces } = parseBracketPayload(rawSourcePayload);
  const place =
    competitorPlaces.find((item) => Number(item.Pos) === sideNo) ??
    competitorPlaces[sideNo - 1] ??
    null;
  const competitor = place?.Competitor ?? null;
  const teamCode = competitor?.Organization?.trim() || fallbackTeamCode;
  const athletesRaw = competitor?.Composition?.Athlete;
  const athletes = Array.isArray(athletesRaw) ? athletesRaw : athletesRaw ? [athletesRaw] : [];
  const players = athletes
    .map((athlete): SidePlayer | null => {
      const name = formatBracketAthleteName(athlete);
      if (!name) return null;
      const playerId = playerIdFromBracketAthlete(athlete);
      const playerMeta = playerId != null ? playerMap.get(playerId) : undefined;
      return {
        playerId,
        slug: playerMeta?.slug ?? null,
        name,
        nameZh: playerMeta?.nameZh ?? null,
        countryCode: athlete.Description?.Organization?.trim() || teamCode,
      };
    })
    .filter((player): player is SidePlayer => Boolean(player));

  if (players.length > 0) return players;

  const teamName = competitor?.Description?.TeamName?.trim();
  const fallbackName = teamName || fallbackPlaceholder || fallbackTeamCode;
  return fallbackName
    ? [
        {
          playerId: null,
          slug: null,
          name: fallbackName,
          nameZh: null,
          countryCode: teamCode,
        },
      ]
    : [];
}

function buildCurrentBracketForSubEvent(eventId: number, subEventCode: string): EventBracketRound[] {
  const rows = db
    .prepare(
      `
        SELECT
          b.current_bracket_id AS matchId,
          b.external_unit_code AS externalUnitCode,
          CASE
            WHEN m.current_match_id IS NOT NULL THEN 'cm:' || m.current_match_id
            ELSE t.current_team_tie_id
          END AS scheduleMatchId,
          b.draw_code AS drawCode,
          COALESCE(b.round_code, b.bracket_code, 'UNKNOWN') AS drawRound,
          COALESCE(b.round_order, 0) AS roundOrder,
          b.match_score AS matchScore,
          b.winner_side AS winnerSide,
          b.side_a_team_code AS sideATeamCode,
          b.side_b_team_code AS sideBTeamCode,
          b.side_a_placeholder AS sideAPlaceholder,
          b.side_b_placeholder AS sideBPlaceholder,
          b.side_a_previous_unit AS sideAPreviousUnit,
          b.side_b_previous_unit AS sideBPreviousUnit,
          b.raw_source_payload AS rawSourcePayload
        FROM current_event_brackets b
        LEFT JOIN current_event_team_ties t ON t.event_id = b.event_id AND t.external_match_code = b.external_unit_code
        LEFT JOIN current_event_matches m ON m.event_id = b.event_id AND m.external_match_code = b.external_unit_code
        WHERE b.event_id = ?
          AND b.sub_event_type_code = ?
        ORDER BY COALESCE(b.round_order, 9999) ASC, b.bracket_position ASC, b.current_bracket_id ASC
      `,
    )
    .all(eventId, subEventCode) as Array<{
    matchId: number;
    externalUnitCode: string | null;
    scheduleMatchId: number | string | null;
    drawCode: string | null;
    drawRound: string;
    roundOrder: number;
    matchScore: string | null;
    winnerSide: string | null;
    sideATeamCode: string | null;
    sideBTeamCode: string | null;
    sideAPlaceholder: string | null;
    sideBPlaceholder: string | null;
    sideAPreviousUnit: string | null;
    sideBPreviousUnit: string | null;
    rawSourcePayload: string | null;
  }>;

  const playerMap = loadPlayerDisplayMap(
    Array.from(new Set(rows.flatMap((row) => collectBracketPlayerIds(row.rawSourcePayload)))),
  );

  return Array.from(
    rows.reduce((map, row) => {
      const meta = teamTieRoundMeta(row.drawRound, null);
      const mapKey = `${row.drawCode ?? 'UNKNOWN'}:${row.drawRound}`;
      const current = map.get(mapKey) ?? {
        code: row.drawRound,
        drawCode: row.drawCode,
        label: meta.label,
        order: row.roundOrder || meta.order,
        matches: [] as EventBracketRound['matches'],
      };
      current.matches.push({
        matchId: row.matchId,
        externalUnitCode: row.externalUnitCode,
        scheduleMatchId: row.scheduleMatchId,
        drawRound: row.drawRound,
        roundLabel: meta.label,
        roundOrder: row.roundOrder || meta.order,
        matchScore: row.matchScore,
        games: [],
        sides: [
          {
            sideNo: 1,
            isWinner: row.winnerSide === 'A',
            previousUnit: row.sideAPreviousUnit,
            players: playersFromCurrentBracketPayload(row.rawSourcePayload, 1, row.sideATeamCode, row.sideAPlaceholder, playerMap),
          },
          {
            sideNo: 2,
            isWinner: row.winnerSide === 'B',
            previousUnit: row.sideBPreviousUnit,
            players: playersFromCurrentBracketPayload(row.rawSourcePayload, 2, row.sideBTeamCode, row.sideBPlaceholder, playerMap),
          },
        ],
      });
      map.set(mapKey, current);
      return map;
    }, new Map<string, { code: string; drawCode: string | null; label: string; order: number; matches: EventBracketRound['matches'] }>())
      .values(),
  ).sort((left, right) => right.order - left.order);
}

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
  const tieRows = db
    .prepare(
      `
        SELECT
          t.team_tie_id AS tieId,
          COALESCE(t.stage_code, t.stage, '') AS stage,
          COALESCE(t.stage_zh, t.stage) AS stageZh,
          COALESCE(t.round_code, t.round, '') AS round,
          COALESCE(t.round_zh, t.round) AS roundZh,
          t.match_score AS matchScore,
          t.winner_team_code AS winnerTeamCode,
          s.side_no AS sideNo,
          s.team_code AS teamCode,
          s.team_name AS teamName
        FROM team_ties t
        JOIN team_tie_sides s ON s.team_tie_id = t.team_tie_id
        WHERE t.event_id = ?
          AND t.sub_event_type_code = ?
        ORDER BY t.team_tie_id ASC, s.side_no ASC
      `,
    )
    .all(eventId, subEventCode) as Array<{
    tieId: number;
    stage: string;
    stageZh: string | null;
    round: string;
    roundZh: string | null;
    matchScore: string | null;
    winnerTeamCode: string | null;
    sideNo: number;
    teamCode: string | null;
    teamName: string | null;
  }>;

  const rubberRows = db
    .prepare(
      `
        SELECT
          m.match_id AS matchId,
          m.team_tie_id AS tieId,
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
          AND m.team_tie_id IS NOT NULL
        ORDER BY m.team_tie_id ASC, m.match_id ASC, ms.side_no ASC, msp.player_order ASC
      `,
    )
    .all(eventId, subEventCode) as Array<{
    matchId: number;
    tieId: number;
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

  const rubberMap = new Map<
    number,
    Array<{
      matchId: number;
      matchScore: string | null;
      winnerSide: string | null;
      sides: Array<{ sideNo: number; isWinner: boolean; players: SidePlayer[] }>;
    }>
  >();
  const currentRubberMap = new Map<
    number,
    {
      matchId: number;
      tieId: number;
      matchScore: string | null;
      winnerSide: string | null;
      sides: Array<{ sideNo: number; isWinner: boolean; players: SidePlayer[] }>;
    }
  >();

  for (const row of rubberRows) {
    const current =
      currentRubberMap.get(row.matchId) ??
      {
        matchId: row.matchId,
        tieId: row.tieId,
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
    currentRubberMap.set(row.matchId, current);
  }

  for (const rubber of currentRubberMap.values()) {
    const current = rubberMap.get(rubber.tieId) ?? [];
    current.push({
      matchId: rubber.matchId,
      matchScore: rubber.matchScore,
      winnerSide: rubber.winnerSide,
      sides: rubber.sides.sort((left, right) => left.sideNo - right.sideNo),
    });
    rubberMap.set(rubber.tieId, current);
  }

  const ties = new Map<string, TeamTie>();
  for (const row of tieRows) {
    const key = String(row.tieId);
    const current =
      ties.get(key) ??
      {
        tieId: key,
        scheduleMatchId: -row.tieId,
        externalMatchCode: null,
        stage: row.stage,
        stageZh: row.stageZh,
        round: row.round,
        roundZh: row.roundZh,
        teamA: { code: '', name: '', nameZh: null },
        teamB: { code: '', name: '', nameZh: null },
        scoreA: 0,
        scoreB: 0,
        winnerCode: row.winnerTeamCode,
        rubbers: rubberMap.get(row.tieId) ?? [],
      };
    if (row.sideNo === 1) {
      current.teamA = { code: row.teamCode ?? 'TBD', name: row.teamName ?? row.teamCode ?? 'TBD', nameZh: null };
    } else if (row.sideNo === 2) {
      current.teamB = { code: row.teamCode ?? 'TBD', name: row.teamName ?? row.teamCode ?? 'TBD', nameZh: null };
    }
    const parsed = parseTieScore(row.matchScore);
    current.scoreA = parsed?.scoreA ?? 0;
    current.scoreB = parsed?.scoreB ?? 0;
    ties.set(key, current);
  }

  return mergeHistoricalTeamTies(Array.from(ties.values()).sort((left, right) => Number(left.tieId) - Number(right.tieId)));
}

function normalizeHistoricalTeamTieCountries(tie: TeamTie): { tie: TeamTie; changed: boolean } {
  let changed = false;
  const sideCountryCandidates = new Map<number, string[]>();
  const rubbers = tie.rubbers.map((rubber) => ({
    ...rubber,
    sides: rubber.sides.map((side) => {
      const players = side.players.map((player) => {
        const normalized = normalizeHistoricalSidePlayerCountry(player);
        changed ||= normalized.changed;
        if (normalized.player.countryCode) {
          const countries = sideCountryCandidates.get(side.sideNo) ?? [];
          countries.push(normalized.player.countryCode);
          sideCountryCandidates.set(side.sideNo, countries);
        }
        return normalized.player;
      });
      return { ...side, players };
    }),
  }));

  const teamForSide = (sideNo: number, team: TeamTie['teamA']) => {
    const countries = Array.from(new Set(sideCountryCandidates.get(sideNo) ?? []));
    if (changed && countries.length === 1 && countries[0] !== team.code) {
      return { code: countries[0], name: countries[0], nameZh: team.nameZh };
    }
    return team;
  };
  const teamA = teamForSide(1, tie.teamA);
  const teamB = teamForSide(2, tie.teamB);

  return {
    tie: {
      ...tie,
      teamA,
      teamB,
      winnerCode: tie.winnerCode === tie.teamA.code ? teamA.code : tie.winnerCode === tie.teamB.code ? teamB.code : tie.winnerCode,
      rubbers,
    },
    changed: changed || teamA.code !== tie.teamA.code || teamB.code !== tie.teamB.code,
  };
}

function teamTieMergeKey(tie: TeamTie) {
  const teamPair = [tie.teamA.code, tie.teamB.code].filter(Boolean).sort().join('|');
  if (!teamPair) return null;
  return [tie.stage, tie.round, teamPair].join('::');
}

function mergeHistoricalTeamTies(ties: TeamTie[]) {
  const normalized = ties.map((tie) => normalizeHistoricalTeamTieCountries(tie));
  const groups = new Map<string, Array<{ tie: TeamTie; changed: boolean }>>();
  const passthrough: TeamTie[] = [];
  for (const item of normalized) {
    const key = teamTieMergeKey(item.tie);
    if (!key) {
      passthrough.push(item.tie);
      continue;
    }
    const current = groups.get(key) ?? [];
    current.push(item);
    groups.set(key, current);
  }

  const merged: TeamTie[] = [...passthrough];
  for (const group of groups.values()) {
    if (group.length === 1 || !group.some((item) => item.changed)) {
      merged.push(...group.map((item) => item.tie));
      continue;
    }

    const base = group
      .map((item) => item.tie)
      .sort((left, right) => Math.abs(Number(left.tieId)) - Math.abs(Number(right.tieId)))[0];
    const teamOrder = [base.teamA.code, base.teamB.code];
    const scoreByTeam = new Map(teamOrder.map((code) => [code, 0]));
    const rubbersById = new Map<number, TeamTie['rubbers'][number]>();

    for (const item of group) {
      scoreByTeam.set(item.tie.teamA.code, (scoreByTeam.get(item.tie.teamA.code) ?? 0) + item.tie.scoreA);
      scoreByTeam.set(item.tie.teamB.code, (scoreByTeam.get(item.tie.teamB.code) ?? 0) + item.tie.scoreB);
      for (const rubber of item.tie.rubbers) {
        rubbersById.set(rubber.matchId, rubber);
      }
    }

    const scoreA = scoreByTeam.get(base.teamA.code) ?? 0;
    const scoreB = scoreByTeam.get(base.teamB.code) ?? 0;
    const winnerCode = scoreA === scoreB ? base.winnerCode : scoreA > scoreB ? base.teamA.code : base.teamB.code;

    merged.push({
      ...base,
      scoreA,
      scoreB,
      winnerCode,
      rubbers: Array.from(rubbersById.values()).sort((left, right) => left.matchId - right.matchId),
    });
  }

  return merged.sort((left, right) => Number(left.tieId) - Number(right.tieId));
}

function buildCurrentTeamTiesForSubEvent(eventId: number, subEventCode: string): TeamTie[] {
  const tieRows = db
    .prepare(
      `
        SELECT
          t.current_team_tie_id AS tieId,
          t.external_match_code AS externalMatchCode,
          COALESCE(t.stage_code, t.stage_label, '') AS stage,
          t.stage_label AS stageZh,
          COALESCE(t.round_code, t.round_label, '') AS round,
          t.round_label AS roundZh,
          t.match_score AS matchScore,
          t.winner_side AS winnerSide,
          t.winner_team_code AS winnerTeamCode,
          s.side_no AS sideNo,
          s.team_code AS teamCode,
          s.team_name AS teamName,
          s.is_winner AS isWinner
        FROM current_event_team_ties t
        JOIN current_event_team_tie_sides s ON s.current_team_tie_id = t.current_team_tie_id
        WHERE t.event_id = ?
          AND t.sub_event_type_code = ?
        ORDER BY t.current_team_tie_id ASC, s.side_no ASC
      `,
    )
    .all(eventId, subEventCode) as Array<{
    tieId: number;
    externalMatchCode: string | null;
    stage: string;
    stageZh: string | null;
    round: string;
    roundZh: string | null;
    matchScore: string | null;
    winnerSide: string | null;
    winnerTeamCode: string | null;
    sideNo: number;
    teamCode: string | null;
    teamName: string | null;
    isWinner: number;
  }>;

  const bracketSideMap = new Map(
    (
      db
        .prepare(
          `
            SELECT
              external_unit_code AS externalMatchCode,
              side_a_team_code AS sideATeamCode,
              side_b_team_code AS sideBTeamCode
            FROM current_event_brackets
            WHERE event_id = ?
              AND sub_event_type_code = ?
              AND external_unit_code IS NOT NULL
          `,
        )
        .all(eventId, subEventCode) as Array<{
        externalMatchCode: string;
        sideATeamCode: string | null;
        sideBTeamCode: string | null;
      }>
    ).map((row) => [
      row.externalMatchCode,
      {
        sideATeamCode: row.sideATeamCode,
        sideBTeamCode: row.sideBTeamCode,
      },
    ]),
  );

  const rubberRows = db
    .prepare(
      `
        SELECT
          m.current_match_id AS matchId,
          m.current_team_tie_id AS tieId,
          m.match_score AS matchScore,
          m.winner_side AS winnerSide,
          s.side_no AS sideNo,
          s.team_code AS teamCode,
          s.is_winner AS isWinner,
          p.player_id AS playerId,
          p.player_name AS playerName,
          p.player_country AS playerCountry,
          pl.slug,
          pl.name_zh AS playerNameZh
        FROM current_event_matches m
        JOIN current_event_match_sides s ON s.current_match_id = m.current_match_id
        LEFT JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
        LEFT JOIN players pl ON pl.player_id = p.player_id
        WHERE m.event_id = ?
          AND m.sub_event_type_code = ?
          AND m.current_team_tie_id IS NOT NULL
        ORDER BY m.current_team_tie_id ASC, m.current_match_id ASC, s.side_no ASC, p.player_order ASC
      `,
    )
    .all(eventId, subEventCode) as Array<{
    matchId: number;
    tieId: number;
    matchScore: string | null;
    winnerSide: string | null;
    sideNo: number;
    teamCode: string | null;
    isWinner: number;
    playerId: number | null;
    playerName: string | null;
    playerCountry: string | null;
    slug: string | null;
    playerNameZh: string | null;
  }>;

  const rubberMap = new Map<
    number,
    Array<{
      matchId: number;
      matchScore: string | null;
      winnerSide: string | null;
      sides: Array<{ sideNo: number; isWinner: boolean; players: SidePlayer[] }>;
    }>
  >();

  const currentRubberMap = new Map<
    number,
    {
      matchId: number;
      tieId: number;
      matchScore: string | null;
      winnerSide: string | null;
      sides: Array<{ sideNo: number; isWinner: boolean; players: SidePlayer[] }>;
    }
  >();

  for (const row of rubberRows) {
    const current =
      currentRubberMap.get(row.matchId) ??
      {
        matchId: row.matchId,
        tieId: row.tieId,
        matchScore: row.matchScore,
        winnerSide: row.winnerSide,
        sides: [],
      };
    let side = current.sides.find((item) => item.sideNo === row.sideNo);
    if (!side) {
      side = { sideNo: row.sideNo, isWinner: row.isWinner === 1, players: [] };
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
    currentRubberMap.set(row.matchId, current);
  }

  for (const rubber of currentRubberMap.values()) {
    const current = rubberMap.get(rubber.tieId) ?? [];
    current.push({
      matchId: rubber.matchId,
      matchScore: rubber.matchScore,
      winnerSide: rubber.winnerSide,
      sides: rubber.sides.sort((left, right) => left.sideNo - right.sideNo),
    });
    rubberMap.set(rubber.tieId, current);
  }

  const ties = new Map<string, TeamTie>();
  for (const row of tieRows) {
    const key = String(row.tieId);
    const current =
      ties.get(key) ??
      {
        tieId: key,
        scheduleMatchId: row.tieId,
        externalMatchCode: row.externalMatchCode,
        stage: row.stage,
        stageZh: row.stageZh,
        round: row.round,
        roundZh: row.roundZh,
        teamA: { code: '', name: '', nameZh: null },
        teamB: { code: '', name: '', nameZh: null },
        scoreA: 0,
        scoreB: 0,
        winnerCode: row.winnerTeamCode,
        rubbers: rubberMap.get(row.tieId) ?? [],
      };
    const bracketSide = row.externalMatchCode ? bracketSideMap.get(row.externalMatchCode) : null;
    if (row.sideNo === 1) {
      const teamCode = row.teamCode ?? bracketSide?.sideATeamCode ?? 'TBD';
      current.teamA = { code: teamCode, name: row.teamName ?? teamCode, nameZh: null };
    } else if (row.sideNo === 2) {
      const teamCode = row.teamCode ?? bracketSide?.sideBTeamCode ?? 'TBD';
      current.teamB = { code: teamCode, name: row.teamName ?? teamCode, nameZh: null };
    }
    const parsed = parseTieScore(row.matchScore);
    current.scoreA = parsed?.scoreA ?? 0;
    current.scoreB = parsed?.scoreB ?? 0;
    ties.set(key, current);
  }

  return Array.from(ties.values()).sort((left, right) => Number(left.tieId) - Number(right.tieId));
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

function buildCurrentIndividualScheduleMatchDetail(currentMatchId: number) {
  const currentMatch = db
    .prepare(
      `
        SELECT
          'cm:' || m.current_match_id AS scheduleMatchId,
          m.event_id AS eventId,
          e.name AS eventName,
          e.name_zh AS eventNameZh,
          e.year AS eventYear,
          m.sub_event_type_code AS subEventTypeCode,
          st.name_zh AS subEventNameZh,
          m.stage_code AS stageCode,
          COALESCE(sc.name_zh, m.stage_label) AS stageNameZh,
          m.round_code AS roundCode,
          COALESCE(rc.name_zh, m.round_label) AS roundNameZh,
          m.group_code AS groupCode,
          m.scheduled_local_at AS scheduledLocalAt,
          m.scheduled_utc_at AS scheduledUtcAt,
          m.table_no AS tableNo,
          m.session_label AS sessionLabel,
          m.status,
          m.source_schedule_status AS rawScheduleStatus,
          m.match_score AS matchScore,
          m.games,
          m.winner_side AS winnerSide,
          m.external_match_code AS externalMatchCode,
          e.start_date AS startDate,
          e.end_date AS endDate
        FROM current_event_matches m
        LEFT JOIN events e ON e.event_id = m.event_id
        LEFT JOIN sub_event_types st ON st.code = m.sub_event_type_code
        LEFT JOIN stage_codes sc ON sc.code = m.stage_code
        LEFT JOIN round_codes rc ON rc.code = m.round_code
        WHERE m.current_match_id = ?
      `,
    )
    .get(currentMatchId) as
    | {
        scheduleMatchId: string;
        eventId: number;
        eventName: string | null;
        eventNameZh: string | null;
        eventYear: number | null;
        subEventTypeCode: string;
        subEventNameZh: string | null;
        stageCode: string | null;
        stageNameZh: string | null;
        roundCode: string | null;
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

  if (!currentMatch) return null;

  const sideRows = db
    .prepare(
      `
        SELECT
          s.side_no AS sideNo,
          s.is_winner AS isWinner,
          s.team_code AS teamCode,
          s.seed,
          s.qualifier,
          s.placeholder_text AS placeholderText,
          p.player_order AS playerOrder,
          p.player_id AS playerId,
          p.player_name AS playerName,
          p.player_country AS playerCountry,
          pl.slug,
          pl.name_zh AS playerNameZh,
          REPLACE(REPLACE(pl.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile
        FROM current_event_match_sides s
        LEFT JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
        LEFT JOIN players pl ON pl.player_id = p.player_id
        WHERE s.current_match_id = ?
        ORDER BY s.side_no ASC, p.player_order ASC
      `,
    )
    .all(currentMatchId) as Array<{
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

  const fallbackPlayerDisplayMap = loadPlayerDisplayMapByNames(sideRows.map((row) => row.playerName ?? '').filter(Boolean));
  const sideMap = new Map<number, {
    sideNo: number;
    isWinner: boolean;
    teamCode: string | null;
    seed: number | null;
    qualifier: boolean | null;
    placeholderText: string | null;
    players: Array<SidePlayer & { avatarFile: string | null }>;
  }>();

  for (const row of sideRows) {
    const current =
      sideMap.get(row.sideNo) ??
      {
        sideNo: row.sideNo,
        isWinner: row.isWinner === 1,
        teamCode: row.teamCode,
        seed: row.seed,
        qualifier: row.qualifier == null ? null : row.qualifier === 1,
        placeholderText: row.placeholderText,
        players: [],
      };
    if (row.playerName) {
      const fallbackDisplay = fallbackPlayerDisplayMap.get(row.playerName.trim());
      current.players.push({
        playerId: row.playerId ?? fallbackDisplay?.playerId ?? null,
        slug: row.slug ?? fallbackDisplay?.slug ?? null,
        name: row.playerName,
        nameZh: row.playerNameZh ?? fallbackDisplay?.nameZh ?? null,
        countryCode: row.playerCountry,
        avatarFile: filterAvatarFile(row.avatarFile) ?? fallbackDisplay?.avatarFile ?? null,
      });
    }
    sideMap.set(row.sideNo, current);
  }

  return {
    match: {
      scheduleMatchId: currentMatch.scheduleMatchId,
      eventId: currentMatch.eventId,
      eventName: currentMatch.eventName,
      eventNameZh: currentMatch.eventNameZh,
      eventYear: currentMatch.eventYear,
      subEventTypeCode: currentMatch.subEventTypeCode,
      subEventNameZh: currentMatch.subEventNameZh,
      stageCode: currentMatch.stageCode ?? '',
      stageNameZh: currentMatch.stageNameZh,
      roundCode: currentMatch.roundCode ?? '',
      roundNameZh: currentMatch.roundNameZh,
      roundLabel: roundLabel(currentMatch.roundCode, currentMatch.roundNameZh),
      groupCode: currentMatch.groupCode,
      scheduledLocalAt: currentMatch.scheduledLocalAt,
      scheduledUtcAt: currentMatch.scheduledUtcAt,
      tableNo: currentMatch.tableNo,
      sessionLabel: currentMatch.sessionLabel,
      status: currentMatch.status,
      rawScheduleStatus: currentMatch.rawScheduleStatus,
      matchScore: currentMatch.matchScore,
      games: parseGames(currentMatch.games),
      winnerSide: currentMatch.winnerSide,
      startDate: currentMatch.startDate,
      endDate: currentMatch.endDate,
      externalMatchCode: currentMatch.externalMatchCode,
    },
    sides: Array.from(sideMap.values()).sort((left, right) => left.sideNo - right.sideNo),
    rubbers: [],
  };
}

export function getScheduleMatchDetail(scheduleMatchId: number | string) {
  if (typeof scheduleMatchId === 'string') {
    const currentMatchId = scheduleMatchId.match(/^cm:(\d+)$/)?.[1];
    if (currentMatchId) {
      return buildCurrentIndividualScheduleMatchDetail(Number(currentMatchId));
    }
    const parsedScheduleMatchId = Number(scheduleMatchId);
    if (Number.isFinite(parsedScheduleMatchId) && String(parsedScheduleMatchId) === scheduleMatchId) {
      return getScheduleMatchDetail(parsedScheduleMatchId);
    }
    return buildOverrideScheduleMatchDetail(scheduleMatchId);
  }

  const currentMatch = db
    .prepare(
      `
        SELECT
          t.current_team_tie_id AS scheduleMatchId,
          t.event_id AS eventId,
          e.name AS eventName,
          e.name_zh AS eventNameZh,
          e.year AS eventYear,
          t.sub_event_type_code AS subEventTypeCode,
          st.name_zh AS subEventNameZh,
          t.stage_code AS stageCode,
          COALESCE(sc.name_zh, t.stage_label) AS stageNameZh,
          t.round_code AS roundCode,
          COALESCE(rc.name_zh, t.round_label) AS roundNameZh,
          t.group_code AS groupCode,
          t.scheduled_local_at AS scheduledLocalAt,
          t.scheduled_utc_at AS scheduledUtcAt,
          t.table_no AS tableNo,
          t.session_label AS sessionLabel,
          t.status,
          t.source_schedule_status AS rawScheduleStatus,
          t.match_score AS matchScore,
          NULL AS games,
          t.winner_side AS winnerSide,
          t.external_match_code AS externalMatchCode,
          e.start_date AS startDate,
          e.end_date AS endDate
        FROM current_event_team_ties t
        LEFT JOIN events e ON e.event_id = t.event_id
        LEFT JOIN sub_event_types st ON st.code = t.sub_event_type_code
        LEFT JOIN stage_codes sc ON sc.code = t.stage_code
        LEFT JOIN round_codes rc ON rc.code = t.round_code
        WHERE t.current_team_tie_id = ?
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
        stageCode: string | null;
        stageNameZh: string | null;
        roundCode: string | null;
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

  if (currentMatch) {
    const sideRows = db
      .prepare(
        `
          SELECT
            s.side_no AS sideNo,
            s.is_winner AS isWinner,
            s.team_code AS teamCode,
            s.seed,
            s.qualifier,
            NULL AS placeholderText,
            p.player_order AS playerOrder,
            p.player_id AS playerId,
            p.player_name AS playerName,
            p.player_country AS playerCountry,
            pl.slug,
            pl.name_zh AS playerNameZh,
            REPLACE(REPLACE(pl.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile
          FROM current_event_team_tie_sides s
          LEFT JOIN current_event_team_tie_side_players p ON p.current_team_tie_side_id = s.current_team_tie_side_id
          LEFT JOIN players pl ON pl.player_id = p.player_id
          WHERE s.current_team_tie_id = ?
          ORDER BY s.side_no ASC, p.player_order ASC
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

    const rubberRows = db
      .prepare(
        `
          SELECT
            m.current_match_id AS matchId,
            m.external_match_code AS externalMatchCode,
            m.status,
            m.match_score AS matchScore,
            m.games,
            m.winner_side AS winnerSide,
            s.side_no AS sideNo,
            s.team_code AS teamCode,
            p.player_id AS playerId,
            p.player_name AS playerName,
            p.player_country AS playerCountry,
            pl.slug,
            pl.name_zh AS playerNameZh,
            REPLACE(REPLACE(pl.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile
          FROM current_event_matches m
          JOIN current_event_match_sides s ON s.current_match_id = m.current_match_id
          LEFT JOIN current_event_match_side_players p ON p.current_match_side_id = s.current_match_side_id
          LEFT JOIN players pl ON pl.player_id = p.player_id
          WHERE m.current_team_tie_id = ?
          ORDER BY m.current_match_id ASC, s.side_no ASC, p.player_order ASC
        `,
      )
      .all(scheduleMatchId) as Array<{
      matchId: number;
      externalMatchCode: string | null;
      status: string;
      matchScore: string | null;
      games: string | null;
      winnerSide: string | null;
      sideNo: number;
      teamCode: string | null;
      playerId: number | null;
      playerName: string | null;
      playerCountry: string | null;
      slug: string | null;
      playerNameZh: string | null;
      avatarFile: string | null;
    }>;

    const finalRubberStatuses = new Set(['completed', 'walkover', 'cancelled']);
    const filteredRubberRows =
      finalRubberStatuses.has(currentMatch.status)
        ? rubberRows.filter((row) => finalRubberStatuses.has(row.status))
        : rubberRows;

    const fallbackPlayerDisplayMap = loadPlayerDisplayMapByNames(
      [
        ...sideRows.map((row) => row.playerName ?? ''),
        ...filteredRubberRows.map((row) => row.playerName ?? ''),
      ].filter(Boolean),
    );

    const sideMap = new Map<number, {
      sideNo: number;
      isWinner: boolean;
      teamCode: string | null;
      seed: number | null;
      qualifier: boolean | null;
      placeholderText: string | null;
      players: Array<SidePlayer & { avatarFile: string | null }>;
    }>();
    for (const row of sideRows) {
      const current =
        sideMap.get(row.sideNo) ??
        {
          sideNo: row.sideNo,
          isWinner: row.isWinner === 1,
          teamCode: row.teamCode,
          seed: row.seed,
          qualifier: row.qualifier == null ? null : row.qualifier === 1,
          placeholderText: row.placeholderText,
          players: [],
        };
      if (row.playerName) {
        const fallbackDisplay = fallbackPlayerDisplayMap.get(row.playerName.trim());
        current.players.push({
          playerId: row.playerId ?? fallbackDisplay?.playerId ?? null,
          slug: row.slug ?? fallbackDisplay?.slug ?? null,
          name: row.playerName,
          nameZh: row.playerNameZh ?? fallbackDisplay?.nameZh ?? null,
          countryCode: row.playerCountry,
          avatarFile: filterAvatarFile(row.avatarFile) ?? fallbackDisplay?.avatarFile ?? null,
        });
      }
      sideMap.set(row.sideNo, current);
    }

    const rubberMap = new Map<
      number,
      {
        externalMatchCode: string | null;
        matchScore: string | null;
        games: Array<{ player: number; opponent: number }>;
        winnerSide: string | null;
        sides: Array<{
          sideNo: number;
          teamCode: string | null;
          players: Array<SidePlayer & { avatarFile: string | null }>;
        }>;
      }
    >();
    for (const row of filteredRubberRows) {
      const current =
        rubberMap.get(row.matchId) ??
        {
          externalMatchCode: row.externalMatchCode,
          matchScore: row.matchScore,
          games: parseGames(row.games),
          winnerSide: row.winnerSide,
          sides: [],
        };
      let side = current.sides.find((item) => item.sideNo === row.sideNo);
      if (!side) {
        side = { sideNo: row.sideNo, teamCode: row.teamCode, players: [] };
        current.sides.push(side);
      }
      if (row.playerName) {
        const fallbackDisplay = fallbackPlayerDisplayMap.get(row.playerName.trim());
        side.players.push({
          playerId: row.playerId ?? fallbackDisplay?.playerId ?? null,
          slug: row.slug ?? fallbackDisplay?.slug ?? null,
          name: row.playerName,
          nameZh: row.playerNameZh ?? fallbackDisplay?.nameZh ?? null,
          countryCode: row.playerCountry,
          avatarFile: filterAvatarFile(row.avatarFile) ?? fallbackDisplay?.avatarFile ?? null,
        });
      }
      rubberMap.set(row.matchId, current);
    }

    return {
      match: {
        scheduleMatchId: currentMatch.scheduleMatchId,
        eventId: currentMatch.eventId,
        eventName: currentMatch.eventName,
        eventNameZh: currentMatch.eventNameZh,
        eventYear: currentMatch.eventYear,
        subEventTypeCode: currentMatch.subEventTypeCode,
        subEventNameZh: currentMatch.subEventNameZh,
        stageCode: currentMatch.stageCode ?? '',
        stageNameZh: currentMatch.stageNameZh,
        roundCode: currentMatch.roundCode ?? '',
        roundNameZh: currentMatch.roundNameZh,
        roundLabel: roundLabel(currentMatch.roundCode, currentMatch.roundNameZh),
        groupCode: currentMatch.groupCode,
        scheduledLocalAt: currentMatch.scheduledLocalAt,
        scheduledUtcAt: currentMatch.scheduledUtcAt,
        tableNo: currentMatch.tableNo,
        sessionLabel: currentMatch.sessionLabel,
        status: currentMatch.status,
        rawScheduleStatus: currentMatch.rawScheduleStatus,
        matchScore: currentMatch.matchScore,
        games: [],
        winnerSide: currentMatch.winnerSide,
        startDate: currentMatch.startDate,
        endDate: currentMatch.endDate,
        externalMatchCode: currentMatch.externalMatchCode,
      },
      sides: Array.from(sideMap.values()).sort((left, right) => left.sideNo - right.sideNo),
      rubbers: Array.from(rubberMap.values()).sort((left, right) =>
        (left.externalMatchCode ?? '').localeCompare(right.externalMatchCode ?? ''),
      ),
    };
  }

  if (scheduleMatchId >= 0) return null;

  const teamTieId = Math.abs(scheduleMatchId);
  const match = db
    .prepare(
      `
        SELECT
          -t.team_tie_id AS scheduleMatchId,
          t.event_id AS eventId,
          e.name AS eventName,
          e.name_zh AS eventNameZh,
          e.year AS eventYear,
          t.sub_event_type_code AS subEventTypeCode,
          st.name_zh AS subEventNameZh,
          COALESCE(t.stage_code, t.stage, '') AS stageCode,
          COALESCE(sc.name_zh, t.stage_zh, t.stage) AS stageNameZh,
          COALESCE(t.round_code, t.round, '') AS roundCode,
          COALESCE(rc.name_zh, t.round_zh, t.round) AS roundNameZh,
          t.group_code AS groupCode,
          NULL AS scheduledLocalAt,
          NULL AS scheduledUtcAt,
          NULL AS tableNo,
          NULL AS sessionLabel,
          t.status,
          t.source_type AS rawScheduleStatus,
          t.match_score AS matchScore,
          NULL AS games,
          t.winner_side AS winnerSide,
          t.source_key AS externalMatchCode,
          e.start_date AS startDate,
          e.end_date AS endDate
        FROM team_ties t
        LEFT JOIN events e ON e.event_id = t.event_id
        LEFT JOIN sub_event_types st ON st.code = t.sub_event_type_code
        LEFT JOIN stage_codes sc ON sc.code = t.stage_code
        LEFT JOIN round_codes rc ON rc.code = t.round_code
        WHERE t.team_tie_id = ?
      `,
    )
    .get(teamTieId) as
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

  const mergedHistoricalDetail = buildHistoricalMergedScheduleMatchDetail(match);
  if (mergedHistoricalDetail) {
    return mergedHistoricalDetail;
  }

  const sideRows = db
    .prepare(
      `
        SELECT
          s.side_no AS sideNo,
          s.is_winner AS isWinner,
          s.team_code AS teamCode,
          s.seed,
          s.qualifier,
          NULL AS placeholderText,
          p.player_order AS playerOrder,
          p.player_id AS playerId,
          p.player_name AS playerName,
          p.player_country AS playerCountry,
          pl.slug,
          pl.name_zh AS playerNameZh,
          REPLACE(REPLACE(pl.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile
        FROM team_tie_sides s
        LEFT JOIN team_tie_side_players p ON p.team_tie_side_id = s.team_tie_side_id
        LEFT JOIN players pl ON pl.player_id = p.player_id
        WHERE s.team_tie_id = ?
        ORDER BY s.side_no ASC, p.player_order ASC
      `,
    )
    .all(teamTieId) as Array<{
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

  const rubberRows = db
    .prepare(
      `
        SELECT
          m.match_id AS matchId,
          m.match_score AS matchScore,
          m.games,
          m.winner_side AS winnerSide,
          ms.side_no AS sideNo,
          ms.is_winner AS isWinner,
          msp.player_id AS playerId,
          msp.player_name AS playerName,
          msp.player_country AS playerCountry,
          p.slug,
          p.name_zh AS playerNameZh,
          REPLACE(REPLACE(p.avatar_file, 'data\\player_avatars\\', ''), 'data/player_avatars/', '') AS avatarFile
        FROM matches m
        JOIN match_sides ms ON ms.match_id = m.match_id
        LEFT JOIN match_side_players msp ON msp.match_side_id = ms.match_side_id
        LEFT JOIN players p ON p.player_id = msp.player_id
        WHERE m.team_tie_id = ?
        ORDER BY m.match_id ASC, ms.side_no ASC, msp.player_order ASC
      `,
    )
    .all(teamTieId) as Array<{
    matchId: number;
    matchScore: string | null;
    games: string | null;
    winnerSide: string | null;
    sideNo: number;
    isWinner: number;
    playerId: number | null;
    playerName: string | null;
    playerCountry: string | null;
    slug: string | null;
    playerNameZh: string | null;
    avatarFile: string | null;
  }>;

  const rubberMap = new Map<
    number,
    {
      matchId: number;
      matchScore: string | null;
      games: Array<{ player: number; opponent: number }>;
      winnerSide: string | null;
      sides: Array<{
        sideNo: number;
        teamCode: string | null;
        players: Array<SidePlayer & { avatarFile: string | null }>;
      }>;
    }
  >();

  for (const row of rubberRows) {
    const current =
      rubberMap.get(row.matchId) ??
      {
        matchId: row.matchId,
        matchScore: row.matchScore,
        games: parseGames(row.games),
        winnerSide: row.winnerSide,
        sides: [],
      };
    let side = current.sides.find((item) => item.sideNo === row.sideNo);
    if (!side) {
      side = { sideNo: row.sideNo, teamCode: row.playerCountry, players: [] };
      current.sides.push(side);
    }
    if (row.playerName) {
      side.players.push({
        playerId: row.playerId,
        slug: row.slug,
        name: row.playerName,
        nameZh: row.playerNameZh,
        countryCode: row.playerCountry,
        avatarFile: filterAvatarFile(row.avatarFile),
      });
    }
    rubberMap.set(row.matchId, current);
  }

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
      status: match.status,
      rawScheduleStatus: match.rawScheduleStatus,
      matchScore: match.matchScore,
      games: parseGames(match.games),
      winnerSide: match.winnerSide,
      startDate: match.startDate,
      endDate: match.endDate,
      externalMatchCode: match.externalMatchCode,
    },
    sides: Array.from(sideMap.values()).sort((left, right) => left.sideNo - right.sideNo),
    rubbers: Array.from(rubberMap.values()).sort((left, right) => left.matchId - right.matchId),
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

function normalizeTeamStageToken(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function displayTeamStageQualifier(value: string | null) {
  const trimmed = value?.trim() ?? '';
  if (!trimmed) return '';

  const divisionMatch = trimmed.match(/^Division\s+(\d+)$/i);
  if (divisionMatch) return `第${divisionMatch[1]}级别`;

  return trimmed;
}

function teamTieBracketStageMeta(stage: string, stageZh: string | null) {
  const trimmed = stage.trim();
  if (trimmed === 'MAIN') {
    return { codePrefix: 'main', labelPrefix: '', orderOffset: 0 };
  }

  const mainDrawMatch = trimmed.match(/^Main Draw(?:\s*-\s*(.+))?$/i);
  if (mainDrawMatch) {
    const stageZhRest = stageZh?.replace(/^(主赛|正赛)\s*-\s*/u, '') ?? null;
    const qualifier = displayTeamStageQualifier(
      (stageZhRest !== stageZh ? stageZhRest : null) ?? mainDrawMatch[1] ?? null,
    );
    return {
      codePrefix: qualifier ? `main-${normalizeTeamStageToken(mainDrawMatch[1] ?? qualifier)}` : 'main',
      labelPrefix: qualifier,
      orderOffset: 0,
    };
  }

  if (/^Position matches\b/i.test(trimmed)) {
    const rest = trimmed.replace(/^Position matches/i, '').trim();
    const restMatch = rest.match(/^(.*?)\s*-\s*(Division\s+\d+)$/i);
    const range = restMatch?.[1]?.trim() ?? rest;
    const division = displayTeamStageQualifier(restMatch?.[2] ?? null);
    const labelParts = ['排位赛', range, division].filter(Boolean);
    const codeParts = ['position', range ? normalizeTeamStageToken(range) : '', division ? normalizeTeamStageToken(restMatch?.[2] ?? division) : '']
      .filter(Boolean)
      .join('-');
    return {
      codePrefix: codeParts,
      labelPrefix: labelParts.join(' '),
      orderOffset: -1000,
    };
  }

  return null;
}

function baseTeamRoundCode(code: string) {
  return code.includes(':') ? code.slice(code.lastIndexOf(':') + 1) : code;
}

function isMainTeamRoundCode(code: string) {
  return !code.includes(':') || code.startsWith('main:') || code.startsWith('main-');
}

function teamTieRoundMeta(round: string, roundZh: string | null) {
  const trimmed = round?.trim() ?? '';
  const rawRoundAliases: Record<string, string> = {
    F: 'Final',
    FNL: 'Final',
    'FNL-': 'Final',
    SF: 'SemiFinal',
    SFNL: 'SemiFinal',
    QF: 'QuarterFinal',
    QFNL: 'QuarterFinal',
    '8FNL': 'R16',
  };
  const normalized = rawRoundAliases[trimmed] ?? NUMERIC_TEAM_ROUND_ALIAS[trimmed] ?? trimmed;
  const meta = TEAM_ROUND_META[normalized];
  if (meta) {
    const trimmedZh = roundZh?.trim() ?? '';
    const useStandardLabel =
      !trimmedZh ||
      /^\d+$/.test(trimmedZh) ||
      Boolean(rawRoundAliases[trimmedZh.toUpperCase()]);
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

  const stageMeta = teamTieBracketStageMeta(tie.stage, tie.stageZh);
  if (!stageMeta) return null;

  const fallback = teamTieRoundMeta(tie.round, tie.roundZh);
  if (fallback.order <= 0) return null;

  return {
    code: stageMeta.codePrefix ? `${stageMeta.codePrefix}:${fallback.code}` : fallback.code,
    label: [stageMeta.labelPrefix, fallback.label].filter(Boolean).join(' '),
    order: fallback.order + stageMeta.orderOffset,
  };
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

function buildOverrideTeamTie(
  overrideTie: NonNullable<TeamKnockoutEventOverride['display_rounds']>[number]['ties'][number],
  tieById: Map<string, TeamTie>,
): TeamTie | null {
  const sourceTies = overrideTie.source_tie_ids
    .map((tieId) => tieById.get(String(tieId)))
    .filter((tie): tie is TeamTie => tie != null);
  if (sourceTies.length === 0) return null;

  const base = sourceTies[0];
  const codeMap = new Map(Object.entries(overrideTie.side_code_map ?? {}));
  const mapTeamCode = (code: string) => codeMap.get(code) ?? code;
  const teamA: TeamTie['teamA'] = {
    code: overrideTie.team_a_code ?? mapTeamCode(base.teamA.code),
    name: overrideTie.team_a_name ?? overrideTie.team_a_code ?? mapTeamCode(base.teamA.name),
    nameZh: null,
  };
  const teamB: TeamTie['teamB'] = {
    code: overrideTie.team_b_code ?? mapTeamCode(base.teamB.code),
    name: overrideTie.team_b_name ?? overrideTie.team_b_code ?? mapTeamCode(base.teamB.name),
    nameZh: null,
  };

  return {
    ...base,
    tieId: overrideTie.tie_id ?? (sourceTies.length === 1 ? base.tieId : `${base.tieId}:${sourceTies[sourceTies.length - 1].tieId}`),
    scheduleMatchId: overrideTie.schedule_match_id === undefined ? (sourceTies.length === 1 ? base.scheduleMatchId : null) : overrideTie.schedule_match_id,
    teamA,
    teamB,
    scoreA: overrideTie.score_a ?? base.scoreA,
    scoreB: overrideTie.score_b ?? base.scoreB,
    winnerCode: overrideTie.winner_code === undefined ? base.winnerCode : overrideTie.winner_code,
    rubbers: sourceTies.flatMap((tie) =>
      tie.rubbers.map((rubber) => ({
        ...rubber,
        sides: rubber.sides.map((side) => {
          const sourceCode = side.sideNo === 1 ? tie.teamA.code : tie.teamB.code;
          const mappedCode = mapTeamCode(sourceCode);
          return {
            ...side,
            players: side.players,
            sideNo: mappedCode === teamA.code ? 1 : mappedCode === teamB.code ? 2 : side.sideNo,
          };
        }),
      })),
    ),
  };
}

function buildOverrideTeamKnockoutRounds(
  override: TeamKnockoutEventOverride,
  defaultRounds: EventTeamKnockoutView['rounds'],
  ties: TeamTie[],
): EventTeamKnockoutView['rounds'] {
  if (!override.display_rounds?.length) return defaultRounds;

  const defaultRoundByCode = new Map(defaultRounds.map((round) => [round.code, round]));
  const tieById = new Map(ties.map((tie) => [String(tie.tieId), tie]));

  return override.display_rounds
    .map((round) => {
      const fallback = defaultRoundByCode.get(round.code);
      const tiesForRound = round.ties
        .map((overrideTie) => buildOverrideTeamTie(overrideTie, tieById))
        .filter((tie): tie is TeamTie => tie != null);
      if (tiesForRound.length === 0) return null;
      return {
        code: round.code,
        label: round.label ?? fallback?.label ?? round.code,
        order: round.order ?? fallback?.order ?? 0,
        ties: tiesForRound,
      };
    })
    .filter((round): round is EventTeamKnockoutView['rounds'][number] => round != null)
    .sort((left, right) => right.order - left.order);
}

const AUTO_TEAM_SUB_EVENT_CODES = new Set(['WT', 'MT', 'XT']);

function isAutoTeamSubEvent(code: string) {
  return AUTO_TEAM_SUB_EVENT_CODES.has(code);
}

function buildCurrentBracketTeamTiesForSubEvent(eventId: number, subEventCode: string): TeamTie[] {
  const rows = db
    .prepare(
      `
        SELECT
          current_bracket_id AS tieId,
          external_unit_code AS externalMatchCode,
          COALESCE(stage_code, 'MAIN_DRAW') AS stage,
          COALESCE(round_code, bracket_code, '') AS round,
          match_score AS matchScore,
          winner_side AS winnerSide,
          side_a_team_code AS sideATeamCode,
          side_b_team_code AS sideBTeamCode
        FROM current_event_brackets
        WHERE event_id = ?
          AND sub_event_type_code = ?
          AND external_unit_code IS NOT NULL
          AND external_unit_code LIKE '%0000'
        ORDER BY COALESCE(round_order, 9999) ASC, bracket_position ASC, current_bracket_id ASC
      `,
    )
    .all(eventId, subEventCode) as Array<{
    tieId: number;
    externalMatchCode: string | null;
    stage: string;
    round: string;
    matchScore: string | null;
    winnerSide: string | null;
    sideATeamCode: string | null;
    sideBTeamCode: string | null;
  }>;

  return rows
    .map((row): TeamTie | null => {
      const meta = teamTieRoundMeta(row.round, null);
      if (meta.order <= 0 || !row.sideATeamCode || !row.sideBTeamCode) return null;

      const parsed = parseTieScore(row.matchScore);
      const winnerCode =
        row.winnerSide === 'A' ? row.sideATeamCode : row.winnerSide === 'B' ? row.sideBTeamCode : null;

      return {
        tieId: `bracket:${row.tieId}`,
        scheduleMatchId: null,
        externalMatchCode: row.externalMatchCode,
        stage: row.stage,
        stageZh: row.stage,
        round: row.round,
        roundZh: meta.label,
        teamA: teamLabelFromCode(row.sideATeamCode),
        teamB: teamLabelFromCode(row.sideBTeamCode),
        scoreA: parsed?.scoreA ?? 0,
        scoreB: parsed?.scoreB ?? 0,
        winnerCode,
        rubbers: [],
      };
    })
    .filter((tie): tie is TeamTie => tie != null);
}

function buildAutoTeamKnockoutView(eventId: number, subEventCode: string): EventTeamKnockoutView | null {
  const ties = buildTeamTiesForSubEvent(eventId, subEventCode);
  if (ties.length === 0) return null;

  const rounds = buildTeamKnockoutRounds(eventId, subEventCode, ties);
  if (rounds.length === 0) return null;

  const finalTie = rounds.find((r) => baseTeamRoundCode(r.code) === 'Final' && isMainTeamRoundCode(r.code))?.ties[0] ?? null;
  const bronzeTie = rounds.find((r) => baseTeamRoundCode(r.code) === 'Bronze' && isMainTeamRoundCode(r.code))?.ties[0] ?? null;
  const semiFinalTies =
    rounds.find((r) => baseTeamRoundCode(r.code) === 'SemiFinal' && isMainTeamRoundCode(r.code))?.ties ?? [];

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

function buildCurrentTeamKnockoutView(eventId: number, subEventCode: string): EventTeamKnockoutView | null {
  const importedTies = buildCurrentTeamTiesForSubEvent(eventId, subEventCode).filter((tie) => !/^GP\d+/i.test(tie.round));
  const importedExternalCodes = new Set(
    importedTies.map((tie) => normalizeExternalMatchCode(tie.externalMatchCode)).filter(Boolean),
  );
  const bracketFallbackTies = buildCurrentBracketTeamTiesForSubEvent(eventId, subEventCode).filter(
    (tie) => !importedExternalCodes.has(normalizeExternalMatchCode(tie.externalMatchCode)),
  );
  const ties = [...importedTies, ...bracketFallbackTies];
  if (ties.length === 0) return null;

  const rounds = Array.from(
    ties.reduce((map, tie) => {
      const meta = teamTieRoundMeta(tie.round, tie.roundZh);
      if (meta.order <= 0) return map;
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

  if (rounds.length === 0) return null;
  const finalTie = rounds.find((r) => r.code === 'Final' || r.code === 'F')?.ties[0] ?? null;
  const bronzeTie = rounds.find((r) => r.code === 'Bronze')?.ties[0] ?? null;
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
  } else if (!bronzeTie) {
    const semiFinalTies = rounds.find((r) => r.code === 'SemiFinal')?.ties ?? [];
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
      thirdPlaceSecond: !bronzeTie ? thirdPlaces[1] ?? null : null,
    },
    finalTie,
    bronzeTie,
  };
}

function buildLiveGroupStageView(
  eventId: number,
  subEventCode: string,
  scheduleMatches: EventScheduleMatch[],
  officialResults: Map<string, OfficialScheduleResult>,
  useCurrentStandings = false,
): EventRoundRobinView | null {
  const importedRows = loadImportedGroupStandings(eventId, subEventCode, useCurrentStandings);
  const groupStageMatches = scheduleMatches.filter(
    (match) =>
      match.subEventTypeCode === subEventCode && (match.groupCode != null || /^G\d+$/i.test(match.roundCode ?? '')),
  );
  if (groupStageMatches.length === 0 && importedRows.length === 0) return null;

  const tiesByGroup = new Map<string, TeamTie[]>();
  for (const match of groupStageMatches) {
    const [sideA, sideB] = [...match.sides].sort((left, right) => left.sideNo - right.sideNo);
    if (!sideA?.teamCode || !sideB?.teamCode) continue;

    const scheduleScore = parseTieScore(match.matchScore);
    const official = officialResults.get(normalizeExternalMatchCode(match.externalMatchCode));
    const officialScores = official?.teamCodes ? new Map([[official.teamCodes[0], official.scoreA], [official.teamCodes[1], official.scoreB]]) : null;
    const scoreA = scheduleScore?.scoreA ?? officialScores?.get(sideA.teamCode) ?? null;
    const scoreB = scheduleScore?.scoreB ?? officialScores?.get(sideB.teamCode) ?? null;
    const winnerCode =
      match.winnerSide === 'A'
        ? sideA.teamCode
        : match.winnerSide === 'B'
          ? sideB.teamCode
          : official?.winnerCode && (official.winnerCode === sideA.teamCode || official.winnerCode === sideB.teamCode)
        ? official.winnerCode
        : null;
    const tie: TeamTie = {
      tieId: match.externalMatchCode || String(match.scheduleMatchId),
      scheduleMatchId: match.scheduleMatchId,
      externalMatchCode: null,
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

  if (importedRows.length > 0) {
    const rowsByStage = new Map<string, Map<string, ImportedGroupStandingRow[]>>();
    for (const row of importedRows) {
      const normalizedStageLabel = normalizeImportedGroupStageLabel(row.stageLabel);
      const stageGroups = rowsByStage.get(normalizedStageLabel) ?? new Map<string, ImportedGroupStandingRow[]>();
      const groupRows = stageGroups.get(row.groupCode) ?? [];
      groupRows.push(row);
      stageGroups.set(row.groupCode, groupRows);
      rowsByStage.set(normalizedStageLabel, stageGroups);
    }

    const stages: RoundRobinStage[] = Array.from(rowsByStage.entries()).map(([stageLabel, groupRows], stageIndex) => ({
      code:
        stageLabel.replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').toUpperCase() ||
        `PRELIMINARY_${stageIndex + 1}`,
      name: stageLabel,
      nameZh: displayImportedGroupStageLabel(stageLabel),
      format: 'group_round_robin',
      groups: Array.from(groupRows.entries())
        .sort((left, right) => left[0].localeCompare(right[0]))
        .map(([groupCode, rows]) => {
          const standings = rows
            .slice()
            .sort((left, right) => (left.rank ?? 999) - (right.rank ?? 999) || left.organizationCode.localeCompare(right.organizationCode))
            .map((row) => ({
              ...buildStageStanding(row.organizationCode, row.rank ?? 0),
              rank: row.rank ?? 0,
              matches: row.played ?? 0,
              wins: row.won ?? 0,
              losses: row.lost ?? 0,
              tiePoints: row.result ?? 0,
              scoreFor: row.scoreFor ?? 0,
              scoreAgainst: row.scoreAgainst ?? 0,
              qualificationMark: (row.rank ?? 0) === 0 ? null : row.qualificationMark ?? (row as any).qualification_mark ?? null,
            }));

          return {
            code: groupCode,
            nameZh: `第 ${groupCode.replace(/^GP/, '')} 组`,
            teams: standings.map((standing) => standing.teamCode),
            ties: tiesByGroup.get(groupCode) ?? [],
            standings,
          };
        }),
    }));

    return {
      mode: 'staged_round_robin',
      stages,
      finalStandings: [],
      podium: {
        champion: null,
        runnerUp: null,
        thirdPlace: null,
      },
    };
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
  const rounds = buildOverrideTeamKnockoutRounds(override, buildTeamKnockoutRounds(eventId, subEventCode, ties), ties);
  const finalStandings = override.final_standings
    .slice()
    .sort((left, right) => left.rank - right.rank)
    .map((item) => buildStageStanding(item.team_code, item.rank));
  const podiumByCode = new Map(finalStandings.map((item) => [item.teamCode, item]));
  const bronzeTie = override.ties.bronze ? ties.find((tie) => teamCodesMatch(tie, override.ties.bronze!.team_codes)) ?? null : null;

  return {
    mode: 'team_knockout_with_bronze',
    rounds,
    finalStandings,
    podium: {
      champion: podiumByCode.get(override.podium.champion) ?? null,
      runnerUp: podiumByCode.get(override.podium.runner_up) ?? null,
      thirdPlace: podiumByCode.get(override.podium.third_place) ?? null,
      thirdPlaceSecond: override.podium.third_place_second ? podiumByCode.get(override.podium.third_place_second) ?? null : null,
    },
    finalTie: ties.find((tie) => teamCodesMatch(tie, override.ties.final.team_codes)) ?? null,
    bronzeTie,
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
    `(
      EXISTS (SELECT 1 FROM matches m WHERE m.event_id = e.event_id)
      OR EXISTS (SELECT 1 FROM team_ties tt WHERE tt.event_id = e.event_id)
      OR EXISTS (SELECT 1 FROM current_event_team_ties ctt WHERE ctt.event_id = e.event_id)
      OR EXISTS (SELECT 1 FROM current_event_session_schedule cess WHERE cess.event_id = e.event_id)
    )`
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

/**
 * 判断当前赛事在 current_event_* 表里是否还有展示态数据。
 *
 * 用于决定详情页是否继续走 "current" 数据源：
 * - 比赛进行中 → 必然为 true
 * - 比赛已完结 → 看 promote 之后 current 表是否被清理（目前策略是保留不动）
 * - 历史赛事（从未进过 current 流水线）→ false，详情页落回 historical 数据源
 */
function hasCurrentEventPresentationData(eventId: number): boolean {
  const row = db
    .prepare(
      `
        SELECT 1 AS present
        FROM (
          SELECT 1 FROM current_event_matches WHERE event_id = ?
          UNION ALL
          SELECT 1 FROM current_event_team_ties WHERE event_id = ?
          UNION ALL
          SELECT 1 FROM current_event_brackets WHERE event_id = ?
          UNION ALL
          SELECT 1 FROM current_event_session_schedule WHERE event_id = ?
        )
        LIMIT 1
      `,
    )
    .get(eventId, eventId, eventId, eventId) as { present: number } | undefined;
  return Boolean(row);
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
  // 详情页数据源选择：in_progress 必读 current；其它状态（含 completed）
  // 只要 current_event_* 还有数据就继续用，以保留 session/台号/scheduled_utc_at 等
  // 历史表没有的字段。promote 后两套数据并存，此处保持 current 优先。
  const useCurrentEventModel =
    event.lifecycleStatus === 'in_progress' || hasCurrentEventPresentationData(eventId);

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
        FROM ${useCurrentEventModel ? 'current_event_brackets' : 'event_draw_matches'}
        WHERE event_id = ?
        GROUP BY sub_event_type_code
      `,
    )
    .all(eventId) as Array<{ code: string; matches: number }>;

  const matchCounts = db
    .prepare(
      `
        SELECT sub_event_type_code AS code, COUNT(*) AS matches
        FROM ${useCurrentEventModel ? 'current_event_matches' : 'matches'}
        WHERE event_id = ?
        GROUP BY sub_event_type_code
      `,
    )
    .all(eventId) as Array<{ code: string; matches: number }>;

  const scheduleCounts = db
    .prepare(
      `
        SELECT sub_event_type_code AS code, COUNT(*) AS matches
        FROM ${useCurrentEventModel ? 'current_event_team_ties' : 'team_ties'}
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
      const teamPlayers = code === 'WT' || code === 'MT' || code === 'XT'
        ? loadTeamChampionPlayers(eventId, code, record?.championCountryCode ?? null)
        : [];
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

  const officialScheduleResults = useCurrentEventModel
    ? new Map<string, OfficialScheduleResult>()
    : readOfficialScheduleResults(eventId);

  const sessionSchedule = useCurrentEventModel
    ? db
        .prepare(
          `
            SELECT
              current_session_schedule_id AS id,
              day_index AS dayIndex,
              session_index AS sessionIndex,
              local_date AS localDate,
              session_title AS sessionTitle,
              start_time AS startTime,
              morning_session_start AS morningSessionStart,
              afternoon_session_start AS afternoonSessionStart,
              venue_raw AS venueRaw,
              table_count AS tableCount,
              table_label AS tableLabel,
              raw_sub_events_text AS rawSubEventsText,
              parsed_rounds_json AS parsedRoundsJson
            FROM current_event_session_schedule
            WHERE event_id = ?
            ORDER BY COALESCE(session_index, day_index) ASC
          `,
        )
        .all(eventId) as EventSessionScheduleRow[]
    : [];
  const scheduleMatches = useCurrentEventModel
    ? buildCurrentScheduleMatches(eventId)
    : buildHistoricalTeamTieScheduleMatches(eventId);

  const orderedScheduleMatches = [...scheduleMatches].sort(compareScheduleMatches);

  const scheduleDays = orderedScheduleMatches.reduce((days, match) => {
    const localDate = match.scheduledLocalAt?.slice(0, 10) ?? '日期待定';
    const current = days.get(localDate) ?? { localDate, matches: [] as EventScheduleMatch[] };
    current.matches.push(match);
    days.set(localDate, current);
    return days;
  }, new Map<string, EventScheduleDay>());

  const championForSubEvent = (
    subEventCode: string,
    teamKnockoutView: EventTeamKnockoutView | null,
  ): EventChampion | null => {
    const se = subEvents.find((item) => item.code === subEventCode);
    const champion = se?.champion;
    const players = champion?.players ?? [];

    const overrideChampionCountry =
      override && subEventCode === override.sub_event_type_code ? override.podium.champion : null;
    const inferredTeamChampion =
      isAutoTeamSubEvent(subEventCode) ? teamKnockoutView?.podium.champion ?? null : null;
    const inferredChampionCountry = inferredTeamChampion?.teamCode ?? null;
    const inferredChampionName = inferredTeamChampion?.teamNameZh ?? inferredTeamChampion?.teamName ?? inferredChampionCountry;

    if (!se && !overrideChampionCountry && !inferredChampionCountry) return null;
    if (!champion?.championName && players.length === 0 && !overrideChampionCountry && !inferredChampionCountry) return null;

    return {
      championName: champion?.championName ?? overrideChampionCountry ?? inferredChampionName,
      championCountryCode: champion?.championCountryCode ?? overrideChampionCountry ?? inferredChampionCountry,
      players,
    };
  };

  const bracketForSubEvent = (subEventCode: string): EventBracketRound[] => {
    if (useCurrentEventModel) {
      return buildCurrentBracketForSubEvent(eventId, subEventCode);
    }

    const drawRows = db
      .prepare(
        `
          SELECT
            edm.match_id AS matchId,
            m.team_tie_id AS scheduleMatchId,
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
      scheduleMatchId: number | null;
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
        scheduleMatchId: number | null;
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
          scheduleMatchId: row.scheduleMatchId,
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
    // 之前：completed 直接隐藏小组赛视图。现在改成根据 current 数据是否存在判定，
    // 这样 promote 后已完结赛事仍能展示完整小组赛分组。
    if (!useCurrentEventModel) return null;
    return buildLiveGroupStageView(
      eventId,
      subEventCode,
      scheduleMatches,
      officialScheduleResults,
      useCurrentEventModel,
    );
  };

  const teamKnockoutViewForSubEvent = (subEventCode: string): EventTeamKnockoutView | null => {
    if (override && isTeamKnockoutOverride(override) && subEventCode === override.sub_event_type_code) {
      return buildTeamKnockoutView(eventId, subEventCode, override);
    }
    if (override && subEventCode === override.sub_event_type_code) return null;
    if (!isAutoTeamSubEvent(subEventCode)) return null;
    return useCurrentEventModel
      ? buildCurrentTeamKnockoutView(eventId, subEventCode)
      : buildAutoTeamKnockoutView(eventId, subEventCode);
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
        : teamKnockoutView
          ? 'team_knockout_with_bronze'
        : roundRobinView
          ? 'staged_round_robin'
          : 'knockout';

    return {
      code: subEventCode,
      champion: championForSubEvent(subEventCode, teamKnockoutView),
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
    scheduleDays: Array.from(scheduleDays.values()).sort((left, right) => left.localDate.localeCompare(right.localDate)),
    selectedSubEvent,
    subEventDetails,
    champion: dataForSelected?.champion ?? null,
    bracket: dataForSelected?.bracket ?? [],
    roundRobinView: dataForSelected?.roundRobinView ?? null,
    teamKnockoutView: dataForSelected?.teamKnockoutView ?? null,
    presentationMode: dataForSelected?.presentationMode ?? 'knockout',
  };
}

export function getEventTeamRoster(eventId: number, subEventCode: string, teamCode: string) {
  const event = db
    .prepare(
      `
        SELECT
          event_id AS eventId,
          name,
          name_zh AS nameZh,
          end_date AS endDate,
          lifecycle_status AS lifecycleStatus
        FROM events
        WHERE event_id = ?
      `,
    )
    .get(eventId) as
    | {
        eventId: number;
        name: string;
        nameZh: string | null;
        endDate: string | null;
        lifecycleStatus: string;
      }
    | undefined;

  if (!event) return null;

  const normalizedTeamCode = teamCode.trim().toUpperCase();
  const normalizedSubEventCode = subEventCode.trim().toUpperCase();
  const fromCurrentTeamTies =
    event.lifecycleStatus === 'in_progress'
      ? loadTeamRosterFromCurrentTeamTies(eventId, normalizedSubEventCode, normalizedTeamCode)
      : null;
  const fromGroupStandings =
    event.lifecycleStatus === 'in_progress'
      ? loadTeamRosterFromGroupStandings(eventId, normalizedSubEventCode, normalizedTeamCode, true)
      : null;
  const fromHistoricalMatches =
    !fromCurrentTeamTies && !fromGroupStandings && isHistoricalEvent(event.endDate)
      ? loadTeamRosterFromHistoricalMatches(eventId, normalizedSubEventCode, normalizedTeamCode)
      : null;
  const roster = fromCurrentTeamTies ?? fromGroupStandings ?? fromHistoricalMatches;

  if (!roster) return null;

  return {
    event: {
      eventId: event.eventId,
      name: event.name,
      nameZh: event.nameZh,
      lifecycleStatus: event.lifecycleStatus,
    },
    roster,
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
