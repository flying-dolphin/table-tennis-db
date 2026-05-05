"use client";

import React, { Suspense } from "react";
import Image from "next/image";
import Link from "next/link";
import type { Route } from "next";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  Crown,
  List,
  FolderTree,
  Trophy,
  CalendarDays,
  Clock3,
  Table2,
  ChevronLeft,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  MapPin,
} from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import { Flag } from "@/components/Flag";
import { formatSubEventLabel, getSubEventShortName } from "@/lib/sub-event-label";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function route(path: string) {
  return path as Route;
}

type SidePlayer = {
  playerId: number | null;
  slug: string | null;
  name: string;
  nameZh: string | null;
  countryCode: string | null;
};

type BracketMatch = {
  matchId: number;
  drawRound: string;
  roundLabel: string;
  roundOrder: number;
  matchScore: string | null;
  games: Array<{ player: number; opponent: number }>;
  sides: Array<{ sideNo: number; isWinner: boolean; players: SidePlayer[] }>;
};

type ChampionPlayer = {
  playerId: number;
  slug: string;
  name: string;
  nameZh: string | null;
  countryCode: string | null;
  avatarFile: string | null;
};

type EventChampion = {
  championName: string | null;
  championCountryCode: string | null;
  players: ChampionPlayer[];
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
  matches?: number;
  wins?: number;
  losses?: number;
  tiePoints?: number;
  scoreFor?: number;
  scoreAgainst?: number;
  qualificationMark?: string | null;
};

type RoundRobinStage = {
  code: string;
  name: string;
  nameZh: string | null;
  format: "group_round_robin" | "round_robin";
  groups?: Array<{
    code: string;
    nameZh: string | null;
    teams: string[];
    ties: TeamTie[];
    standings?: StageStanding[];
  }>;
  ties?: TeamTie[];
  standings?: StageStanding[];
};

type EventRoundRobinView = {
  mode: "staged_round_robin";
  stages: RoundRobinStage[];
  finalStandings: StageStanding[];
  podium: {
    champion: StageStanding | null;
    runnerUp: StageStanding | null;
    thirdPlace: StageStanding | null;
  };
};

type EventTeamKnockoutView = {
  mode: "team_knockout_with_bronze";
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

type EventDetail = {
  event: {
    eventId: number;
    year: number;
    name: string;
    nameZh: string | null;
    eventKind: string | null;
    eventKindZh: string | null;
    categoryNameZh: string | null;
    totalMatches: number | null;
    startDate: string | null;
    endDate: string | null;
    location: string | null;
    lifecycleStatus: string | null;
    timeZone: string | null;
  };
  subEvents: Array<{
    code: string;
    nameZh: string | null;
    disabled: boolean;
    hasDraw: boolean;
    drawMatches: number;
    importedMatches: number;
    scheduleMatches: number;
    champion: EventChampion | null;
  }>;
  sessionSchedule: Array<{
    id: number;
    dayIndex: number;
    localDate: string;
    morningSessionStart: string | null;
    afternoonSessionStart: string | null;
    venueRaw: string | null;
    tableCount: number | null;
    rawSubEventsText: string | null;
    parsedRoundsJson: string | null;
  }>;
  scheduleDays: Array<{
    localDate: string;
    matches: EventScheduleMatch[];
  }>;
  selectedSubEvent: string;
  subEventDetails: Array<{
    code: string;
    champion: EventChampion | null;
    bracket: Array<{ code: string; label: string; order: number; matches: BracketMatch[] }>;
    roundRobinView: EventRoundRobinView | null;
    teamKnockoutView: EventTeamKnockoutView | null;
    presentationMode: "knockout" | "staged_round_robin" | "team_knockout_with_bronze";
  }>;
  champion: EventChampion | null;
  bracket: Array<{ code: string; label: string; order: number; matches: BracketMatch[] }>;
  roundRobinView: EventRoundRobinView | null;
  teamKnockoutView: EventTeamKnockoutView | null;
  presentationMode: "knockout" | "staged_round_robin" | "team_knockout_with_bronze";
};

type EventScheduleMatch = {
  scheduleMatchId: number;
  externalMatchCode?: string | null;
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

type EventDetailResponse = {
  code: number;
  data: EventDetail;
};

type ViewMode = "session" | "draw" | "schedule" | "champions";

type EventSubEventView = EventDetail["subEvents"][number] & EventDetail["subEventDetails"][number];

function displayName(name: string, nameZh: string | null) {
  return nameZh?.trim() || name;
}

function normalizeViewMode(value: string | null): ViewMode | null {
  if (value === "session" || value === "draw" || value === "schedule" || value === "champions") {
    return value;
  }
  return null;
}

function buildEventDetailQuery({
  subEvent,
  view,
  date,
  from,
}: {
  subEvent?: string | null;
  view?: ViewMode | null;
  date?: string | null;
  from?: string | null;
}) {
  const params = new URLSearchParams();
  if (subEvent) {
    params.set("sub_event", subEvent);
  }
  if (view) {
    params.set("view", view);
  }
  if (date) {
    params.set("date", date);
  }
  if (from) {
    params.set("from", from);
  }
  return params.toString();
}

function buildEventDetailHref(
  eventId: string | number,
  state: {
    subEvent?: string | null;
    view?: ViewMode | null;
    date?: string | null;
    from?: string | null;
  },
) {
  const query = buildEventDetailQuery(state);
  return query ? `/events/${eventId}?${query}` : `/events/${eventId}`;
}

function withFromQuery(path: string, fromHref: string) {
  const params = new URLSearchParams();
  params.set("from", fromHref);
  return `${path}?${params.toString()}`;
}

function buildTeamRosterHref(eventId: string, subEventCode: string, teamCode: string, fromHref: string) {
  const params = new URLSearchParams();
  params.set("sub_event", subEventCode);
  params.set("from", fromHref);
  return `/events/${eventId}/teams/${teamCode}?${params.toString()}`;
}

function displayDateRange(startDate: string | null, endDate: string | null) {
  if (!startDate && !endDate) return "时间待补";
  if (startDate && startDate === endDate) return startDate;
  return [startDate, endDate].filter(Boolean).join(" 至 ");
}

function formatLocalDate(value: string | null) {
  if (!value || value === "日期待定") return "日期待定";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    weekday: "short",
  }).format(date);
}

function formatLocalTime(value: string | null) {
  if (!value) return "时间待定";
  const time = value.includes("T") ? value.split("T")[1]?.slice(0, 5) : value.slice(0, 5);
  return time || "时间待定";
}

function formatBeijingTimeLabel(value: string | null, scheduledLocalAt?: string | null, eventTimeZone?: string | null) {
  const date =
    value
      ? new Date(value)
      : scheduledLocalAt && eventTimeZone
        ? zonedLocalDateTimeToDate(scheduledLocalAt.slice(0, 10), scheduledLocalAt.slice(11, 16), eventTimeZone)
        : null;
  if (!date || Number.isNaN(date.getTime())) return null;

  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;
  const hour = parts.find((part) => part.type === "hour")?.value;
  const minute = parts.find((part) => part.type === "minute")?.value;

  if (!month || !day || !hour || !minute) return null;
  return `北京时间 ${month}/${day} ${hour}:${minute}`;
}

function getCurrentDateInTimeZone(timeZone: string | null) {
  const now = new Date();
  if (!timeZone) {
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  }

  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;

  if (!year || !month || !day) {
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  }

  return `${year}-${month}-${day}`;
}

function getDefaultScheduleDate(
  days: Array<{ localDate: string }>,
  eventTimeZone: string | null,
) {
  if (days.length === 0) return null;

  const today = getCurrentDateInTimeZone(eventTimeZone);
  const firstDate = days[0].localDate;
  const lastDate = days[days.length - 1].localDate;

  if (today <= firstDate) return firstDate;
  if (today >= lastDate) return lastDate;

  const todayMatch = days.find((day) => day.localDate === today);
  if (todayMatch) return todayMatch.localDate;

  const nextAvailableDate = days.find((day) => day.localDate > today);
  return nextAvailableDate?.localDate ?? lastDate;
}

function filterScheduleDaysBySubEvent(
  days: EventDetail["scheduleDays"],
  subEventCode: string,
) {
  return days
    .map((day) => ({
      ...day,
      matches: day.matches.filter((match) => match.subEventTypeCode === subEventCode),
    }))
    .filter((day) => day.matches.length > 0);
}

function resolveScheduleDateForSubEvent({
  days,
  subEventCode,
  eventTimeZone,
  preferredDate,
}: {
  days: EventDetail["scheduleDays"];
  subEventCode: string;
  eventTimeZone: string | null;
  preferredDate: string | null;
}) {
  const filteredDays = filterScheduleDaysBySubEvent(days, subEventCode);
  if (filteredDays.length === 0) {
    return null;
  }
  if (preferredDate && filteredDays.some((day) => day.localDate === preferredDate)) {
    return preferredDate;
  }
  return getDefaultScheduleDate(filteredDays, eventTimeZone);
}

function zonedLocalDateTimeToDate(localDate: string, localTime: string, timeZone: string) {
  const dateMatch = localDate.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const timeMatch = localTime.match(/^(\d{2}):(\d{2})/);
  if (!dateMatch || !timeMatch) return null;

  const targetUtcMs = Date.UTC(
    Number(dateMatch[1]),
    Number(dateMatch[2]) - 1,
    Number(dateMatch[3]),
    Number(timeMatch[1]),
    Number(timeMatch[2]),
  );

  let guessMs = targetUtcMs;
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  for (let i = 0; i < 3; i += 1) {
    const parts = formatter.formatToParts(new Date(guessMs));
    const year = Number(parts.find((part) => part.type === "year")?.value);
    const month = Number(parts.find((part) => part.type === "month")?.value);
    const day = Number(parts.find((part) => part.type === "day")?.value);
    const hour = Number(parts.find((part) => part.type === "hour")?.value);
    const minute = Number(parts.find((part) => part.type === "minute")?.value);
    if (![year, month, day, hour, minute].every(Number.isFinite)) return null;

    const zonedUtcMs = Date.UTC(year, month - 1, day, hour, minute);
    const diffMs = targetUtcMs - zonedUtcMs;
    if (diffMs === 0) return new Date(guessMs);
    guessMs += diffMs;
  }

  return new Date(guessMs);
}

function formatBeijingSessionRange(
  localDate: string,
  morningSessionStart: string | null,
  afternoonSessionStart: string | null,
  eventTimeZone: string | null,
) {
  if (!eventTimeZone || !morningSessionStart) return null;
  const startDate = zonedLocalDateTimeToDate(localDate, morningSessionStart, eventTimeZone);
  if (!startDate) return null;

  const formatDateTime = (date: Date) =>
    new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);

  const startLabel = formatDateTime(startDate);
  if (!afternoonSessionStart) return `北京时间 ${startLabel}`;

  const endDate = zonedLocalDateTimeToDate(localDate, afternoonSessionStart, eventTimeZone);
  if (!endDate) return `北京时间 ${startLabel}`;
  return `北京时间 ${startLabel} / ${formatDateTime(endDate)}`;
}

function displayPlayerName(player: { name: string; nameZh: string | null }) {
  return player.nameZh?.trim() || player.name;
}

function normalizeChampionNames(champion: EventChampion | null) {
  if (!champion) return [] as string[];
  if (champion.players.length > 0) {
    return champion.players.map(displayPlayerName);
  }
  return (champion.championName ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function dedupeCountries(players: Array<{ countryCode: string | null }>) {
  return Array.from(new Set(players.map((player) => player.countryCode).filter(Boolean))) as string[];
}

function sideName(side: BracketMatch["sides"][number], isXT: boolean = false) {
  if (isXT && side.players.length > 0) {
    return side.players[0].countryCode || side.players.map(displayPlayerName).join(" / ");
  }
  return side.players.map(displayPlayerName).join(" / ");
}

function rubberPlayersLabel(rubber: TeamTie["rubbers"][number]) {
  const [sideA, sideB] = [...rubber.sides].sort((a, b) => a.sideNo - b.sideNo);
  const left = sideA ? sideName(sideA, false) : "待补";
  const right = sideB ? sideName(sideB, false) : "待补";
  return `${left} vs ${right}`;
}

function truncateLabel(text: string, maxChars: number) {
  const chars = Array.from(text);
  if (chars.length <= maxChars) return text;
  return `${chars.slice(0, maxChars - 1).join("")}…`;
}

function compactPlayerName(player: { name: string; nameZh: string | null }) {
  const display = displayPlayerName(player);
  return /[\u4e00-\u9fa5]/.test(display) ? truncateChineseName(display, 4) : truncateLabel(display, 14);
}

function compactPlayersLabel(players: SidePlayer[]) {
  return players.map(compactPlayerName).join(" / ");
}

function compactRubberPlayersLabel(rubber: TeamTie["rubbers"][number]) {
  const [sideA, sideB] = [...rubber.sides].sort((a, b) => a.sideNo - b.sideNo);
  const left = sideA ? compactPlayersLabel(sideA.players) : "待补";
  const right = sideB ? compactPlayersLabel(sideB.players) : "待补";
  return `${left} vs ${right}`;
}

function subEventLabel(subEvent: { code: string; nameZh: string | null } | undefined) {
  return formatSubEventLabel(subEvent?.code, subEvent?.nameZh);
}

function isDoublesSubEvent(code: string, label: string) {
  const text = `${code} ${label}`.toUpperCase();
  return code === "WD" || code === "MD" || code === "XD" || code === "XT" || text.includes("双打") || text.includes("MIXED");
}

function isXTSubEvent(code: string, label: string) {
  return code === "XT";
}

function supportsChampionRosterTab(code: string) {
  return code === "WT" || code === "MT" || code === "XT";
}

function isTeamSubEvent(code: string, label: string) {
  if (code === "WT" || code === "MT" || code === "XT") return true;
  const text = `${code} ${label}`.toUpperCase();
  return text.includes("TEAM") || text.includes("团体");
}

function truncateChineseName(name: string, maxChars: number = 4) {
  const chineseMatch = name.match(/[\u4e00-\u9fa5]/g);
  const chineseCount = chineseMatch ? chineseMatch.length : 0;
  if (chineseCount <= maxChars) return name;
  let count = 0;
  let result = "";
  for (const char of name) {
    if (/[\u4e00-\u9fa5]/.test(char)) {
      count++;
    }
    result += char;
    if (count >= maxChars - 1) break;
  }
  return result + "...";
}

function makeSidePlayerKey(side: BracketMatch["sides"][number] | undefined): string | null {
  if (!side || side.players.length === 0) return null;
  return side.players
    .map((p) => (p.playerId != null ? `id:${p.playerId}` : `nm:${p.name}`))
    .sort()
    .join("|");
}

// Reorder matches in each round so that prev[2n] and prev[2n+1] feed next[n].
// Rounds are expected in left-to-right order (R1 → ... → Final).
function orderBracketByFeeders(rounds: EventDetail["bracket"]): EventDetail["bracket"] {
  if (rounds.length <= 1) return rounds;
  const result = rounds.map((r) => ({ ...r, matches: [...r.matches] }));

  for (let r = result.length - 1; r > 0; r--) {
    const nextRound = result[r];
    const prevRound = result[r - 1];
    const prevMatches = prevRound.matches;
    if (prevMatches.length !== nextRound.matches.length * 2) continue;

    const used = new Set<number>();
    const newOrder: BracketMatch[] = [];
    let allMatched = true;

    for (const nm of nextRound.matches) {
      const sortedSides = [...nm.sides].sort((a, b) => a.sideNo - b.sideNo);
      for (let s = 0; s < 2; s++) {
        const sideKey = makeSidePlayerKey(sortedSides[s]);
        let feeder: BracketMatch | undefined;
        if (sideKey) {
          feeder = prevMatches.find(
            (pm) => !used.has(pm.matchId) && pm.sides.some((ps) => makeSidePlayerKey(ps) === sideKey),
          );
        }
        if (feeder) {
          newOrder.push(feeder);
          used.add(feeder.matchId);
        } else {
          allMatched = false;
        }
      }
    }

    if (allMatched && newOrder.length === prevMatches.length) {
      result[r - 1] = { ...prevRound, matches: newOrder };
    }
  }

  return result;
}

function findChampionMatch(rounds: EventDetail["bracket"], championNames: string[]) {
  if (rounds.length === 0 || championNames.length === 0) return null;
  const finalRound = rounds[rounds.length - 1] ?? rounds[0];
  const finalMatch = finalRound.matches[0];
  if (!finalMatch) return null;
  const winningSide = finalMatch.sides.find((side) => side.isWinner) ?? finalMatch.sides[0];
  return { finalMatch, winningSide };
}

function sideGamesLabel(games: Array<{ player: number; opponent: number }>) {
  if (games.length === 0) return "局分待补";
  return games.map((game) => `${game.player}-${game.opponent}`).join(", ");
}

function scheduleStatusMeta(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "completed") {
    return { label: "已完结", className: "bg-emerald-50 text-emerald-700 ring-emerald-100" };
  }
  if (normalized === "live") {
    return { label: "进行中", className: "bg-rose-50 text-rose-700 ring-rose-100" };
  }
  if (normalized === "pending_update") {
    return { label: "待更新", className: "bg-amber-50 text-amber-700 ring-amber-100" };
  }
  if (normalized === "cancelled") {
    return { label: "已取消", className: "bg-slate-100 text-slate-500 ring-slate-200" };
  }
  if (normalized === "walkover") {
    return { label: "退赛", className: "bg-amber-50 text-amber-700 ring-amber-100" };
  }
  return { label: "未开始", className: "bg-blue-50 text-[#2d6cf6] ring-blue-100" };
}

function resolveScheduleDisplayStatus(match: EventScheduleMatch) {
  const normalized = match.status.toLowerCase();
  const isNotStarted =
    normalized === "scheduled" ||
    normalized === "not_started" ||
    normalized === "pending" ||
    normalized === "upcoming";

  if (!isNotStarted || !match.scheduledUtcAt) {
    return match.status;
  }

  const scheduledAt = new Date(match.scheduledUtcAt);
  if (Number.isNaN(scheduledAt.getTime())) {
    return match.status;
  }

  return scheduledAt.getTime() < Date.now() ? "pending_update" : match.status;
}

function scheduleRoundLabel(match: EventScheduleMatch) {
  if (match.groupCode) {
    return `${match.roundNameZh || match.roundCode}${match.groupCode ? ` · ${match.groupCode}` : ""}`;
  }
  return match.roundNameZh || match.roundCode || match.sessionLabel || "轮次待定";
}

function scheduleSideLabel(side: EventScheduleMatch["sides"][number] | undefined) {
  if (!side) return "待定";
  if (side.teamCode) return side.teamCode;
  if (side.placeholderText) return side.placeholderText;
  if (side.players.length > 0) return side.players.map(displayPlayerName).join(" / ");
  return "待定";
}

function parseDisplayMatchScore(matchScore: string | null | undefined) {
  const raw = matchScore?.trim() ?? "";
  if (!raw) {
    return {
      scoreParts: [] as string[],
      suffixLabel: null as string | null,
      suffixSideNo: null as 1 | 2 | null,
    };
  }

  const match = raw.match(/^(\d+)\s*-\s*(\d+)(?:\s+(WO))?$/i);
  if (match) {
    const scoreA = Number(match[1]);
    const scoreB = Number(match[2]);
    const hasWalkover = Boolean(match[3]);
    return {
      scoreParts: [match[1], match[2]],
      suffixLabel: hasWalkover ? "弃权" : null,
      suffixSideNo: hasWalkover ? (scoreA < scoreB ? 1 : scoreB < scoreA ? 2 : null) : null,
    };
  }

  return {
    scoreParts: raw.split("-").map((part) => part.trim()).filter(Boolean),
    suffixLabel: /\bWO\b/i.test(raw) ? "弃权" : null,
    suffixSideNo: null as 1 | 2 | null,
  };
}

function EventHeader({
  data,
  subEvents,
  currentSubEvent,
  onSelect,
  onBack,
}: {
  data: EventDetail;
  subEvents: EventDetail["subEvents"];
  currentSubEvent: string;
  onSelect: (code: string) => void;
  onBack: () => void;
}) {
  return (
    <section className="relative overflow-hidden bg-[#f0f4ff] px-4 pb-4 pt-4 ">
      <div
        className="absolute inset-0 z-0 pointer-events-none"
        style={{
          backgroundImage: "url('/images/header_bg.jpeg')",
          backgroundSize: "cover",
          backgroundPosition: "center right",
          opacity: 0.7,
        }}
      />
      <div className="relative z-10">
        <div className="flex items-start justify-between gap-2">
          <button
            type="button"
            onClick={onBack}
            className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center text-slate-900 transition-colors"
          >
            <ChevronLeft size={26} strokeWidth={2} />
          </button>

          <div className="min-w-0 flex-1 text-center pt-1.5">
            <h1 className="line-clamp-2 text-[1.2rem] font-bold leading-snug text-slate-950">
              {displayName(data.event.name, data.event.nameZh)}
            </h1>
            <div className="mt-2 text-[0.88rem] font-medium text-[#7d8fae]">
              <span>{displayDateRange(data.event.startDate, data.event.endDate).replace(" 至 ", " - ")}{data.event.location ? ` · ${data.event.location}` : ""}</span>
            </div>
          </div>

          <button
            type="button"
            className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center text-slate-900 transition-colors"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" x2="21" y1="14" y2="3" />
            </svg>
          </button>
        </div>

        <div className="relative z-10 mt-7 pb-1">
          {/* <div className="flex items-start"> */}
          <SubEventTabs subEvents={subEvents} currentSubEvent={currentSubEvent} onSelect={onSelect} />
          {/* </div> */}
        </div>
      </div>
    </section>
  );
}

function SubEventTabs({
  subEvents,
  currentSubEvent,
  onSelect,
}: {
  subEvents: EventDetail["subEvents"];
  currentSubEvent: string;
  onSelect: (code: string) => void;
}) {
  return (
    <div className="px-0.5">
      <div className="flex gap-1.5 overflow-x-auto no-scrollbar rounded-full bg-white px-1 py-[3px] shadow-[0_2px_10px_rgba(150,170,200,0.14)] justify-start">
        {subEvents.map((subEvent) => {
          const active = currentSubEvent === subEvent.code;
          return (
            <button
              key={subEvent.code}
              type="button"
              disabled={subEvent.disabled}
              onClick={() => onSelect(subEvent.code)}
              className={cn(
                "flex h-[28px] shrink-0 items-center justify-center rounded-full px-4 text-base transition disabled:opacity-30",
                active
                  ? "bg-[#3372f5] text-white font-bold shadow-[0_1px_6px_rgba(51,114,245,0.28)]"
                  : "text-slate-500 font-medium hover:text-slate-800",
              )}
            >
              {subEventLabel(subEvent)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ChampionBanner({
  champion,
  subEvent,
  rounds,
}: {
  champion: EventChampion | null;
  subEvent: EventDetail["subEvents"][number] | undefined;
  rounds: EventDetail["bracket"];
}) {
  const label = subEventLabel(subEvent);
  const championNames = normalizeChampionNames(champion);
  const countries = champion
    ? dedupeCountries(champion.players).length > 0
      ? dedupeCountries(champion.players)
      : champion.championCountryCode
        ? [champion.championCountryCode]
        : []
    : [];
  const isTeam = isTeamSubEvent(subEvent?.code ?? "", label);
  const isDoubles = !isTeam && isDoublesSubEvent(subEvent?.code ?? "", label);
  const isXT = isXTSubEvent(subEvent?.code ?? "", label);
  const championPath = findChampionMatch(rounds, championNames);
  const isTeamHeadline = isTeam
    ? countries[0] || champion?.championCountryCode || championNames[0] || "冠军待补"
    : championNames.map((name) => truncateChineseName(name, 4)).join(" / ") || "冠军待补";
  const subtitle = `${label}冠军`;

  return (
    <div className="relative pt-4">
      <div className="relative overflow-hidden rounded-[1.5rem] bg-[linear-gradient(90deg,#dfeafe_0%,#d9e7ff_55%,#d5e1ff_100%)] pl-[104px] pr-3 shadow-[0_14px_28px_rgba(144,166,201,0.16)] py-1 sm:pl-[120px]">
        <div className="absolute inset-y-0 left-0 w-32 bg-[radial-gradient(circle_at_18%_50%,rgba(255,255,255,0.95),transparent_60%)]" />
        <div className="absolute -left-6 bottom-0 h-20 w-20 rounded-full bg-[radial-gradient(circle,rgba(255,255,255,0.85),transparent_72%)]" />
        <div className="absolute right-0 top-0 h-full w-36 bg-[radial-gradient(circle_at_85%_20%,rgba(255,255,255,0.38),transparent_58%)]" />
        <div className="relative flex min-h-[64px] sm:min-h-[72px] items-center gap-3">
          {champion?.players[0] && !isDoubles && !isTeam && !isXT ? (
            <PlayerAvatar
              key={`${champion.players[0].playerId}-${champion.players[0].avatarFile ?? "no-avatar"}`}
              player={champion.players[0]}
              size="lg"
              className="h-[64px] w-[64px] sm:h-[72px] sm:w-[72px] border-none"
            />
          ) : null}

          <div className="flex min-w-0 flex-1 flex-col items-center justify-center">
            <div className="flex items-center gap-1 text-[#466cb9]">
              {!isDoubles && !isTeam && !isXT ? (
                <Image
                  src="/images/wheatear_left.png"
                  alt=""
                  width={14}
                  height={36}
                  className="h-5 w-auto shrink-0 opacity-85"
                />
              ) : null}
              <p className="whitespace-nowrap text-[0.85rem] font-bold tracking-[0.01em]">{subtitle}</p>
              {!isDoubles && !isTeam && !isXT ? (
                <Image
                  src="/images/wheatear_right.png"
                  alt=""
                  width={14}
                  height={36}
                  className="h-5 w-auto shrink-0 opacity-85"
                />
              ) : null}
            </div>

            <div className="mt-0.5 flex items-center justify-center gap-2">
              {(isTeam || isXT) && countries[0] ? <Flag code={countries[0]} className="shrink-0 scale-[1.2]" /> : null}
              <p className="truncate text-[1.45rem] font-black leading-none text-slate-950 sm:text-[1.7rem]">{isXT && countries.length > 0 ? countries.join(" / ") : isTeamHeadline}</p>
              {!isTeam && !isXT && countries[0] ? <Flag code={countries[0]} className="mb-0.5 shrink-0 scale-[1.05]" /> : null}
            </div>
          </div>
        </div>
      </div>
      <Image
        src="/images/cup.png"
        alt="冠军奖杯"
        width={120}
        height={140}
        className="pointer-events-none absolute bottom-0 left-2 z-20 h-auto w-[100px] drop-shadow-[0_6px_10px_rgba(144,166,201,0.25)] sm:left-3 sm:w-[116px]"
        priority
      />
    </div>
  );
}

function LiveViewTabs({ mode, onChange }: { mode: ViewMode; onChange: (mode: ViewMode) => void }) {
  const tabs: Array<{ mode: ViewMode; label: string; icon: React.ReactNode }> = [
    { mode: "session", label: "日程", icon: <CalendarDays size={16} /> },
    { mode: "draw", label: "签表", icon: <FolderTree size={16} /> },
    { mode: "schedule", label: "比赛", icon: <List size={16} /> },
  ];

  return (
    <div className="flex justify-around border-b border-slate-200/80 px-1 text-base">
      {tabs.map((tab) => (
        <button
          key={tab.mode}
          type="button"
          onClick={() => onChange(tab.mode)}
          className={cn(
            "relative flex h-14 items-center justify-center gap-2 px-4 font-bold transition-colors",
            mode === tab.mode ? "text-[#2d6cf6]" : "text-slate-400 hover:text-slate-700",
          )}
        >
          {tab.icon}
          {tab.label}
          <span
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute inset-x-4 bottom-0 h-[3px] rounded-full transition-all",
              mode === tab.mode ? "bg-[#2d6cf6]" : "bg-transparent",
            )}
          />
        </button>
      ))}
    </div>
  );
}

function LegacyViewTabs({ mode, onChange, showChampionsTab }: { mode: ViewMode; onChange: (mode: ViewMode) => void; showChampionsTab: boolean }) {
  return (
    <div className="flex justify-around border-b border-slate-200/80 px-1 text-base">
      <button
        type="button"
        onClick={() => onChange("schedule")}
        className={cn(
          "relative flex h-14 items-center justify-center gap-2 px-4 font-bold transition-colors",
          mode === "schedule" ? "text-[#2d6cf6]" : "text-slate-400 hover:text-slate-700",
        )}
      >
        <List size={16} />
        赛程
        <span
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute inset-x-4 bottom-0 h-[3px] rounded-full transition-all",
            mode === "schedule" ? "bg-[#2d6cf6]" : "bg-transparent",
          )}
        />
      </button>
      <button
        type="button"
        onClick={() => onChange("draw")}
        className={cn(
          "relative flex h-14 items-center justify-center gap-2 px-4 font-bold transition-colors",
          mode === "draw" ? "text-[#2d6cf6]" : "text-slate-400 hover:text-slate-700",
        )}
      >
        <FolderTree size={16} />
        签表
        <span
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute inset-x-4 bottom-0 h-[3px] rounded-full transition-all",
            mode === "draw" ? "bg-[#2d6cf6]" : "bg-transparent",
          )}
        />
      </button>
      {showChampionsTab && (
        <button
          type="button"
          onClick={() => onChange("champions")}
          className={cn(
            "relative flex h-14 items-center justify-center gap-2 px-4 font-bold transition-colors",
            mode === "champions" ? "text-[#2d6cf6]" : "text-slate-400 hover:text-slate-700",
          )}
        >
          <Crown size={16} />
          冠军成员
          <span
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute inset-x-4 bottom-0 h-[3px] rounded-full transition-all",
              mode === "champions" ? "bg-[#2d6cf6]" : "bg-transparent",
            )}
          />
        </button>
      )}
    </div>
  );
}

function MatchListCard({
  match,
  matchIndex,
  isXT,
  eventReturnHref,
}: {
  match: BracketMatch;
  matchIndex: number;
  isXT?: boolean;
  eventReturnHref: string;
}) {
  const [sideA, sideB] = [...match.sides].sort((left, right) => left.sideNo - right.sideNo);
  const sides = [sideA, sideB].filter(Boolean);
  const { scoreParts, suffixLabel, suffixSideNo } = parseDisplayMatchScore(match.matchScore);

  return (
    <Link
      href={route(withFromQuery(`/matches/${match.matchId}`, eventReturnHref))}
      className="block rounded-2xl bg-white px-4 py-3.5 ring-1 ring-slate-100 shadow-sm transition active:scale-[0.99]"
    >
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-[0.82rem] font-medium text-slate-400">已结束</span>
      </div>

      <div className="flex gap-3">
        <div className="flex-1 min-w-0 space-y-2.5">
          {sides.map((side, i) => {
            const score = scoreParts[side.sideNo - 1] ?? "-";
            const showSuffix = suffixLabel && suffixSideNo === side.sideNo;
            const flag = dedupeCountries(side.players)[0] ?? null;
            return (
              <div key={side.sideNo} className="flex items-center gap-2">
                <span className="w-5 shrink-0 text-right text-[0.8rem] font-bold text-[#9bb3e0]">
                  {i === 0 ? matchIndex : ""}
                </span>
                <Flag code={flag} className="shrink-0 scale-[1.3] origin-left" />
                <p className={cn("flex-1 min-w-0 truncate text-[0.98rem] font-bold leading-tight", side.isWinner ? "text-slate-900" : "text-slate-500")}>
                  {sideName(side, isXT)}
                </p>
                <span className="ml-1 shrink-0 flex items-center gap-1.5">
                  {showSuffix ? <span className="text-[0.7rem] font-black leading-none text-amber-700">{suffixLabel}</span> : null}
                  <span className={cn("font-numeric text-[1.5rem] font-black leading-none tabular-nums", side.isWinner ? "text-[#2d6cf6]" : "text-slate-300")}>
                    {score}
                  </span>
                </span>
                <span className="w-5 shrink-0 flex items-center justify-center">
                  {side.isWinner ? <CheckCircle2 size={18} className="text-[#2d6cf6]" strokeWidth={2.5} /> : null}
                </span>
              </div>
            );
          })}
        </div>

        <div className="w-[95px] shrink-0 border-l border-slate-100 pl-3 self-center">
          <p className="text-[0.78rem] font-medium text-slate-400 mb-1">局分</p>
          <p className="text-[0.8rem] leading-relaxed text-slate-500">{sideGamesLabel(match.games)}</p>
        </div>
      </div>
    </Link>
  );
}

function SessionScheduleView({
  sessions,
  lifecycleStatus,
  eventTimeZone,
}: {
  sessions: EventDetail["sessionSchedule"];
  lifecycleStatus: string | null;
  eventTimeZone: string | null;
}) {
  if (sessions.length === 0) {
    return (
      <div className="pt-5">
        <div className="rounded-[1.7rem] bg-white/82 p-8 text-center text-slate-500 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          赛事日程还没补齐
        </div>
      </div>
    );
  }

  return (
    <div className="pb-10 pt-4">
      <div className="space-y-3">
        {sessions.map((session) => {
          const beijingTimeLabel =
            lifecycleStatus === "in_progress"
              ? formatBeijingSessionRange(
                session.localDate,
                session.morningSessionStart,
                session.afternoonSessionStart,
                eventTimeZone,
              )
              : null;
          const subEventsLines = session.rawSubEventsText
            ? session.rawSubEventsText.split("|").map((part) => part.trim()).filter(Boolean)
            : null;

          return (
            <section
              key={session.id}
              className="rounded-[1.35rem] bg-white px-4 py-4 ring-1 ring-[#e8edf8] shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[0.78rem] font-bold text-[#7d95c7]">DAY {session.dayIndex}</p>
                  <div className="my-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                    <h2 className="text-[1.22rem] font-black leading-none text-slate-950">
                      {formatLocalDate(session.localDate)}
                    </h2>
                  </div>
                  {beijingTimeLabel ? (
                    <p className="text-[0.76rem] font-bold text-[#7d95c7]">{beijingTimeLabel}</p>
                  ) : null}
                </div>
                <div className="rounded-full bg-[#f3f6fb] px-3 py-1 text-[0.78rem] font-bold text-slate-500">
                  {session.morningSessionStart || "待定"} / {session.afternoonSessionStart || "待定"}
                </div>

              </div>

              <div className="mt-2 space-y-1">
                {subEventsLines ? (
                  subEventsLines.map((line, i) => (
                    <p key={i} className="text-[0.98rem] font-bold leading-relaxed text-slate-700">
                      {line}
                    </p>
                  ))
                ) : (
                  <p className="text-[0.98rem] font-bold leading-relaxed text-slate-700">
                    项目安排待补
                  </p>
                )}
              </div>

              <div className="mt-2 flex items-center gap-1.5 text-[0.95rem] font-black text-slate-800">
                <MapPin size={14} className="shrink-0 text-[#7d95c7]" />
                <span className="truncate">{session.venueRaw || "待定"}</span>
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function ScheduleMatchCard({
  match,
  showBeijingTime,
  eventTimeZone,
  eventReturnHref,
}: {
  match: EventScheduleMatch;
  showBeijingTime: boolean;
  eventTimeZone: string | null;
  eventReturnHref: string;
}) {
  const [sideA, sideB] = [...match.sides].sort((left, right) => left.sideNo - right.sideNo);
  const meta = scheduleStatusMeta(resolveScheduleDisplayStatus(match));
  const { scoreParts, suffixLabel, suffixSideNo } = parseDisplayMatchScore(match.matchScore);
  const sideRows = [sideA, sideB].filter(Boolean);
  const shouldShowLiveScore = match.status === "live" && scoreParts.some(Boolean);
  const beijingTimeLabel = showBeijingTime
    ? formatBeijingTimeLabel(match.scheduledUtcAt, match.scheduledLocalAt, eventTimeZone)
    : null;

  return (
    <Link href={route(withFromQuery(`/schedule-matches/${match.scheduleMatchId}`, eventReturnHref))} className="block rounded-2xl bg-white px-3.5 py-3 ring-1 ring-[#e8edf8] shadow-sm transition active:scale-[0.99]">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2 text-[0.82rem] font-bold text-slate-500">
          {match.tableNo ? <span className="rounded-full bg-[#f3f6fb] px-2">{match.tableNo}</span> : null}
          <Clock3 size={14} className="shrink-0 text-[#7d95c7]" />
          <span>{formatLocalTime(match.scheduledLocalAt)}</span>
          {beijingTimeLabel ? (
            <p className="text-[0.76rem] font-bold text-[#7d95c7]">({beijingTimeLabel})</p>
          ) : null}
        </div>
        <span className={cn("shrink-0 rounded-full px-2.5 py-1 text-[0.72rem] font-black ring-1", meta.className)}>
          {meta.label}
        </span>
      </div>

      <div className="mt-2 flex items-center justify-between gap-3">
        <p className="min-w-0 truncate text-[0.8rem] font-bold text-slate-400">
          {formatSubEventLabel(match.subEventTypeCode, match.subEventNameZh)} · {scheduleRoundLabel(match)}
        </p>
      </div>

      <div className="mt-3 space-y-2.5">
        {sideRows.map((side) => {
          const score = scoreParts[side.sideNo - 1] ?? null;
          const showSuffix = suffixLabel && suffixSideNo === side.sideNo;
          const label = scheduleSideLabel(side);
          const isWinner = side.isWinner || (match.winnerSide === (side.sideNo === 1 ? 'A' : 'B'));
          return (
            <div key={side.sideNo} className="flex items-center gap-2">
              <Flag code={side.teamCode || side.players[0]?.countryCode || null} className="shrink-0 scale-[1.18] origin-left" />
              <div className="min-w-0 flex-1">
                <p className={cn("truncate text-[1rem] font-black leading-tight", isWinner ? "text-slate-950" : "text-slate-700")}>
                  {label}
                </p>
                {side.seed ? <p className="mt-0.5 text-[0.7rem] font-bold text-slate-400">Seed {side.seed}</p> : null}
              </div>
              {score || shouldShowLiveScore ? (
                <span className="shrink-0 flex items-center gap-1.5">
                  {showSuffix ? <span className="text-[0.68rem] font-black leading-none text-amber-700">{suffixLabel}</span> : null}
                  <span className={cn("font-numeric text-[1.35rem] font-black tabular-nums", isWinner ? "text-[#2d6cf6]" : "text-slate-300")}>
                    {score ?? "0"}
                  </span>
                </span>
              ) : null}
            </div>
          );
        })}
      </div>

      {match.games.length > 0 ? (
        <p className="mt-3 border-t border-slate-100 pt-2 text-[0.78rem] font-medium text-slate-500">
          局分：{sideGamesLabel(match.games)}
        </p>
      ) : null}

    </Link>
  );
}

function ScheduleByDateView({
  days,
  selectedSubEvent,
  lifecycleStatus,
  eventTimeZone,
  selectedDate,
  onSelectDate,
  eventReturnHref,
}: {
  days: EventDetail["scheduleDays"];
  selectedSubEvent: string;
  lifecycleStatus: string | null;
  eventTimeZone: string | null;
  selectedDate: string | null;
  onSelectDate: (date: string | null) => void;
  eventReturnHref: string;
}) {
  const filteredDays = React.useMemo(
    () => filterScheduleDaysBySubEvent(days, selectedSubEvent),
    [days, selectedSubEvent],
  );

  const defaultSelectedDate = React.useMemo(
    () => getDefaultScheduleDate(filteredDays, eventTimeZone),
    [filteredDays, eventTimeZone],
  );

  React.useEffect(() => {
    if (filteredDays.length === 0) {
      if (selectedDate !== null) {
        onSelectDate(null);
      }
      return;
    }

    if (!selectedDate || !filteredDays.some((day) => day.localDate === selectedDate)) {
      onSelectDate(defaultSelectedDate);
    }
  }, [defaultSelectedDate, filteredDays, onSelectDate, selectedDate]);

  const activeDay = filteredDays.find((day) => day.localDate === selectedDate) ?? filteredDays[0];
  const tabListRef = React.useRef<HTMLDivElement | null>(null);
  const activeTabRef = React.useRef<HTMLButtonElement | null>(null);

  React.useEffect(() => {
    const container = tabListRef.current;
    const activeTab = activeTabRef.current;

    if (!container || !activeTab) return;

    const containerWidth = container.clientWidth;
    const containerScrollLeft = container.scrollLeft;
    const tabLeft = activeTab.offsetLeft;
    const tabRight = tabLeft + activeTab.offsetWidth;
    const visibleLeft = containerScrollLeft;
    const visibleRight = containerScrollLeft + containerWidth;
    const isFullyVisible = tabLeft >= visibleLeft && tabRight <= visibleRight;

    if (isFullyVisible) return;

    const targetScrollLeft = Math.max(0, tabLeft - (containerWidth - activeTab.offsetWidth) / 2);
    container.scrollTo({
      left: targetScrollLeft,
      behavior: "smooth",
    });
  }, [activeDay.localDate]);

  if (filteredDays.length === 0) {
    return (
      <div className="pt-5">
        <div className="rounded-[1.7rem] bg-white/82 p-8 text-center text-slate-500 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          这项逐场赛程还没发布
        </div>
      </div>
    );
  }
  const showBeijingTime = lifecycleStatus === "in_progress";

  return (
    <div className="pb-10 pt-4">
      <div className="space-y-4">
        <div
          ref={tabListRef}
          className="sticky top-0 z-10 -mx-2 overflow-x-auto px-2 pb-2 pt-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          <div className="flex min-w-max gap-2">
            {filteredDays.map((day) => {
              const isActive = day.localDate === activeDay.localDate;
              return (
                <button
                  key={day.localDate}
                  ref={isActive ? activeTabRef : null}
                  type="button"
                  onClick={() => onSelectDate(day.localDate)}
                  className={cn(
                    "group rounded-2xl border px-4 py-2.5 text-left transition",
                    isActive
                      ? "border-brand-primary bg-brand-primary text-white shadow-[0_10px_24px_rgba(45,108,246,0.28)]"
                      : "border-[#dce7f5] bg-white/92 text-slate-500 shadow-sm hover:border-[#b8ccf1] hover:text-slate-800",
                  )}
                >
                  <p className={cn("text-[0.95rem] font-black leading-none", isActive ? "text-white" : "text-slate-900")}>
                    {formatLocalDate(day.localDate)}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        <section key={activeDay.localDate}>
          <div className="mb-3 flex items-end justify-between px-1">
            <h2 className="text-[1.28rem] font-black leading-none text-slate-950">
              {formatLocalDate(activeDay.localDate)}
            </h2>
            <span className="text-[0.85rem] font-bold text-slate-400">{activeDay.matches.length} 场</span>
          </div>
          <div className="space-y-3">
            {activeDay.matches.map((match) => (
              <ScheduleMatchCard
                key={match.scheduleMatchId}
                match={match}
                showBeijingTime={showBeijingTime}
                eventTimeZone={eventTimeZone}
                eventReturnHref={eventReturnHref}
              />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function ScheduleView({
  rounds,
  isXT,
  eventReturnHref,
}: {
  rounds: EventDetail["bracket"];
  isXT?: boolean;
  eventReturnHref: string;
}) {
  const [collapsed, setCollapsed] = React.useState<Set<string>>(new Set());

  const toggle = React.useCallback((code: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }, []);

  if (rounds.length === 0) {
    return (
      <div className="pt-5">
        <div className="rounded-[1.7rem] bg-white/82 p-8 text-center text-slate-500 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          这项赛程还没补齐
        </div>
      </div>
    );
  }

  return (
    <div className="pb-10 pt-4">
      <div className="space-y-5">
        {rounds.map((round) => {
          const isCollapsed = collapsed.has(round.code);
          return (
            <section key={round.code}>
              <button
                type="button"
                onClick={() => toggle(round.code)}
                className="mb-3 flex w-full items-center justify-between px-1 py-0.5"
              >
                <h2 className="text-[1.25rem] font-black leading-none text-slate-950">{round.label}</h2>
                <span className="flex items-center gap-1 text-[0.9rem] font-medium text-slate-400">
                  已完成
                  {isCollapsed ? <ChevronDown size={15} strokeWidth={2.5} /> : <ChevronUp size={15} strokeWidth={2.5} />}
                </span>
              </button>
              {!isCollapsed && (
                <>
                  <div className="space-y-3">
                    {round.matches.map((match, index) => (
                      <MatchListCard key={match.matchId} match={match} matchIndex={index + 1} isXT={isXT} eventReturnHref={eventReturnHref} />
                    ))}
                  </div>
                  {round.matches.length > 1 && (
                    <button
                      type="button"
                      onClick={() => toggle(round.code)}
                      className="mt-3 flex w-full items-center justify-center gap-1.5 py-2.5 text-[0.88rem] text-slate-400 hover:text-slate-600"
                    >
                      <ChevronUp size={13} strokeWidth={2.5} />
                      收起全部
                    </button>
                  )}
                </>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function TeamTieSummaryCard({
  tie,
  tieIndex,
  eventReturnHref,
  eventId,
  subEventCode,
}: {
  tie: TeamTie;
  tieIndex?: number;
  eventReturnHref: string;
  eventId: string;
  subEventCode: string;
}) {
  const winnerA = tie.winnerCode === tie.teamA.code;
  const winnerB = tie.winnerCode === tie.teamB.code;
  return (
    <div className="rounded-[1.35rem] bg-white px-4 py-3.5 ring-1 ring-[#e8edf8]">
      <div className="flex items-center justify-between gap-2">
        <span className="shrink-0 text-[0.85rem] font-bold text-slate-500">
          {tieIndex !== undefined ? `第 ${tieIndex} 场` : "已结束"}
        </span>
        <div className="flex items-center gap-1.5 min-w-0">
          <Link href={route(buildTeamRosterHref(eventId, subEventCode, tie.teamA.code, eventReturnHref))} className="inline-flex items-center gap-1 shrink-0">
            <Flag code={tie.teamA.code} className="shrink-0 scale-[1.05]" />
            <span className={cn("text-[0.95rem] font-black leading-none", winnerA ? "text-slate-950" : "text-slate-500")}>
              {tie.teamA.code}
            </span>
          </Link>
          <span
            className={cn(
              "font-numeric ml-0.5 text-[1.25rem] font-black leading-none tabular-nums",
              winnerA ? "text-[#2d6cf6]" : "text-slate-400"
            )}
          >
            {tie.scoreA}
          </span>
          <span className="text-[0.95rem] font-black leading-none text-slate-300">-</span>
          <span
            className={cn(
              "font-numeric text-[1.25rem] font-black leading-none tabular-nums",
              winnerB ? "text-[#2d6cf6]" : "text-slate-400"
            )}
          >
            {tie.scoreB}
          </span>
          <Link href={route(buildTeamRosterHref(eventId, subEventCode, tie.teamB.code, eventReturnHref))} className="inline-flex items-center gap-1 shrink-0">
            <span className={cn("ml-0.5 text-[0.95rem] font-black leading-none", winnerB ? "text-slate-950" : "text-slate-500")}>
              {tie.teamB.code}
            </span>
            <Flag code={tie.teamB.code} className="shrink-0 scale-[1.05]" />
          </Link>
        </div>
      </div>
      <div className="mt-2 divide-y divide-slate-100">
        {tie.rubbers.map((rubber, index) => (
          <Link
            key={rubber.matchId}
            href={route(withFromQuery(`/matches/${rubber.matchId}`, eventReturnHref))}
            className="flex items-start justify-between gap-3 py-2 transition"
          >
            <div className="flex min-w-0 flex-1 items-start gap-2">
              <span className="shrink-0 text-[0.88rem] font-black leading-snug text-[#2d6cf6]">第{index + 1}盘</span>
              <span className="min-w-0 flex-1 text-[0.88rem] font-medium leading-snug text-slate-600">
                {compactRubberPlayersLabel(rubber)}
              </span>
            </div>
            <span className="font-numeric shrink-0 text-[0.95rem] font-black leading-snug tabular-nums text-[#2d6cf6]">
              {rubber.matchScore ?? "-"}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function TeamKnockoutScheduleView({
  view,
  eventReturnHref,
  eventId,
  subEventCode,
}: {
  view: EventTeamKnockoutView;
  eventReturnHref: string;
  eventId: string;
  subEventCode: string;
}) {
  const [collapsed, setCollapsed] = React.useState<Set<string>>(new Set());

  const toggle = React.useCallback((code: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }, []);

  if (view.rounds.length === 0) {
    return (
      <div className="pt-5">
        <div className="rounded-[1.7rem] bg-white/82 p-8 text-center text-slate-500 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          这项赛程还没补齐
        </div>
      </div>
    );
  }

  return (
    <div className="pb-10 pt-4">
      <div className="space-y-5">
        {view.rounds.map((round) => {
          const isCollapsed = collapsed.has(round.code);
          return (
            <section key={round.code}>
              <button
                type="button"
                onClick={() => toggle(round.code)}
                className="mb-3 flex w-full items-center justify-between px-1 py-0.5"
              >
                <h2 className="text-[1.25rem] font-black leading-none text-slate-950">{round.label}</h2>
                <span className="flex items-center gap-1 text-[0.9rem] font-medium text-slate-400">
                  已完成
                  {isCollapsed ? <ChevronDown size={15} strokeWidth={2.5} /> : <ChevronUp size={15} strokeWidth={2.5} />}
                </span>
              </button>
              {!isCollapsed && (
                <div className="space-y-3">
                  {round.ties.map((tie, index) => (
                    <TeamTieSummaryCard
                      key={tie.tieId}
                      tie={tie}
                      tieIndex={index + 1}
                      eventReturnHref={eventReturnHref}
                      eventId={eventId}
                      subEventCode={subEventCode}
                    />
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function DrawMatchCard({
  match,
  isChampionPath,
  isXT,
  matchNumber,
  eventReturnHref,
}: {
  match: BracketMatch;
  isChampionPath: boolean;
  isXT?: boolean;
  matchNumber?: number;
  eventReturnHref: string;
}) {
  const [sideA, sideB] = [...match.sides].sort((a, b) => a.sideNo - b.sideNo);
  const sides = [sideA, sideB].filter(Boolean);
  const { scoreParts, suffixLabel, suffixSideNo } = parseDisplayMatchScore(match.matchScore);

  return (
    <div className="relative">
      {matchNumber !== undefined && (
        <span className="absolute right-full top-1/2 mr-1 w-3.5 -translate-y-1/2 text-right text-[0.6rem] font-bold text-[#9bb3e0]">
          {matchNumber}
        </span>
      )}
      <Link
        href={route(withFromQuery(`/matches/${match.matchId}`, eventReturnHref))}
        className={cn(
          "block rounded-[0.6rem] border bg-white px-1.5 py-1 shadow-sm transition active:scale-[0.99]",
          isChampionPath ? "border-[#3a74f2] shadow-[0_2px_8px_rgba(58,116,242,0.14)]" : "border-[#dce7f5]",
        )}
      >
        <div className="space-y-1">
          {sides.map((side) => {
            const score = scoreParts[side.sideNo - 1] ?? "-";
            const showSuffix = suffixLabel && suffixSideNo === side.sideNo;
            const flag = dedupeCountries(side.players)[0] ?? null;
            return (
              <div key={side.sideNo} className="flex items-center gap-1">
                <Flag code={flag} className="shrink-0 scale-[0.85] origin-left" />
                <p className={cn("min-w-0 flex-1 truncate text-[0.7rem] font-bold leading-tight", side.isWinner ? "text-slate-900" : "text-slate-400")}>
                  {sideName(side, isXT)}
                </p>
                <span className="shrink-0 flex items-center gap-1">
                  {showSuffix ? <span className="text-[0.5rem] font-black leading-none text-amber-700">{suffixLabel}</span> : null}
                  <span className={cn("font-numeric text-[1rem] font-black leading-none tabular-nums", side.isWinner ? "text-[#2d6cf6]" : "text-slate-300")}>
                    {score}
                  </span>
                </span>
                <span className="flex w-3 shrink-0 items-center justify-center">
                  {side.isWinner ? <CheckCircle2 size={10} className="text-[#2d6cf6]" strokeWidth={2.5} /> : null}
                </span>
              </div>
            );
          })}
        </div>
      </Link>
    </div>
  );
}

const DRAW_CARD_W = 112;
const DRAW_CARD_H = 48;
const DRAW_COL_GAP = 16;
const DRAW_NUM_SPACE = 16;

function DrawView({
  rounds,
  selectedSubEvent,
  champion,
  isXT,
  teamKnockoutView,
  eventReturnHref,
  eventId,
}: {
  rounds: EventDetail["bracket"];
  selectedSubEvent: string;
  champion: EventChampion | null;
  isXT?: boolean;
  teamKnockoutView?: EventTeamKnockoutView | null;
  eventReturnHref: string;
  eventId: string;
}) {
  const [search, setSearch] = React.useState("");
  const highlightedNames = normalizeChampionNames(champion).map((name) => truncateChineseName(name, 4));

  const bracketPodium = React.useMemo(
    () => deriveBracketPodium(rounds, isXT ?? false),
    [rounds, isXT],
  );

  // Data is ordered latest-first (Final → SF → R1); reverse for left-to-right and
  // reorder so that prev[2n], prev[2n+1] feed next[n] (matched by player identity).
  // When a bronze match exists, place it between the semifinals and final so the
  // draw reads in match chronology even though bronze is a side branch.
  const orderedRounds = React.useMemo(() => {
    const reversed = [...rounds].reverse();
    const bronzeRound = reversed.find((round) => round.code === "Bronze");
    const roundsWithoutBronze = reversed.filter((round) => round.code !== "Bronze");

    if (!bronzeRound) {
      return orderBracketByFeeders(roundsWithoutBronze);
    }

    const bronzeInsertIndex = roundsWithoutBronze.findIndex((round) => round.code === "Final");
    if (bronzeInsertIndex === -1) {
      return orderBracketByFeeders([...roundsWithoutBronze, bronzeRound]);
    }

    const roundsWithBronze = [...roundsWithoutBronze];
    roundsWithBronze.splice(bronzeInsertIndex, 0, bronzeRound);
    return orderBracketByFeeders(roundsWithBronze);
  }, [rounds]);

  const filteredRounds = React.useMemo(() => {
    if (!search.trim()) return orderedRounds;
    const keyword = search.trim().toLowerCase();
    return orderedRounds
      .map((round) => ({
        ...round,
        matches: round.matches.filter((match) =>
          match.sides.some((side) => side.players.some((player) => displayPlayerName(player).toLowerCase().includes(keyword))),
        ),
      }))
      .filter((round) => round.matches.length > 0);
  }, [orderedRounds, search]);

  if (rounds.length === 0) {
    return (
      <div className="pt-5">
        <div className="rounded-[1.7rem] bg-white/82 p-8 text-center text-slate-500 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          这项签表还没收录
        </div>
      </div>
    );
  }

  const displayRounds = filteredRounds;

  const firstRoundCount = displayRounds[0]?.matches.length ?? 1;
  const slotH0 = Math.max(DRAW_CARD_H + 8, 60);
  const totalH = firstRoundCount * slotH0;

  const getCardInfo = (rIdx: number, mIdx: number) => {
    const count = displayRounds[rIdx]?.matches.length ?? 1;
    const slotH = totalH / count;
    return {
      top: mIdx * slotH + (slotH - DRAW_CARD_H) / 2,
      centerY: mIdx * slotH + slotH / 2,
      left: DRAW_NUM_SPACE + rIdx * (DRAW_CARD_W + DRAW_COL_GAP),
    };
  };

  const champBoxW = 76;
  const champVisible = highlightedNames.length > 0;
  const totalW =
    DRAW_NUM_SPACE +
    displayRounds.length * (DRAW_CARD_W + DRAW_COL_GAP) +
    (champVisible ? champBoxW + 8 : 0);
  const showBracketPodium = Boolean(bracketPodium) && hasCompletedBracketFinal(rounds);
  const showTeamPodium = teamKnockoutView ? isTeamTieCompleted(teamKnockoutView.finalTie) : false;

  return (
    <div className="pb-10 pt-5">
      {!teamKnockoutView && showBracketPodium && bracketPodium && (
        <section className="mb-6">
          <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">领奖台</h2>
          <Podium podium={bracketPodium} />
        </section>
      )}

      {teamKnockoutView && (
        <section className="mb-6 space-y-6">
          {showTeamPodium ? (
            <div>
              <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">领奖台</h2>
              <Podium podium={teamPodiumDisplay(teamKnockoutView.podium)} />
            </div>
          ) : null}

          {teamKnockoutView.finalTie && (
            <section>
              <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">决赛</h2>
              <TeamTieCard
                tie={teamKnockoutView.finalTie}
                title="冠军战"
                eventReturnHref={eventReturnHref}
                eventId={eventId}
                subEventCode={selectedSubEvent}
              />
            </section>
          )}

          {teamKnockoutView.bronzeTie && (
            <section>
              <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">铜牌赛</h2>
              <TeamTieCard
                tie={teamKnockoutView.bronzeTie}
                title="铜牌战"
                eventReturnHref={eventReturnHref}
                eventId={eventId}
                subEventCode={selectedSubEvent}
              />
            </section>
          )}
        </section>
      )}

      <div className="overflow-x-auto pb-2">
        {/* Round column headers */}
        <div className="mb-3 flex" style={{ paddingLeft: DRAW_NUM_SPACE, minWidth: totalW }}>
          {displayRounds.map((round) => (
            <div
              key={round.code}
              className="shrink-0 text-center"
              style={{ width: DRAW_CARD_W, marginRight: DRAW_COL_GAP }}
            >
              <p className="text-[0.78rem] font-black text-slate-900">{round.label}</p>
              <p className="mt-0.5 text-[0.65rem] font-medium text-slate-400">{round.matches.length} 场</p>
            </div>
          ))}
        </div>

        {/* Bracket area */}
        <div className="relative" style={{ height: totalH, minWidth: totalW }}>
          {/* SVG connector lines */}
          <svg
            className="pointer-events-none absolute inset-0 overflow-visible"
            style={{ width: totalW, height: totalH }}
          >
            {displayRounds.map((_, rIdx) => {
              if (rIdx >= displayRounds.length - 1) return null;
              const nextRound = displayRounds[rIdx + 1];
              return nextRound.matches.map((__, nMIdx) => {
                const f1 = getCardInfo(rIdx, nMIdx * 2);
                const f2 =
                  nMIdx * 2 + 1 < (displayRounds[rIdx]?.matches.length ?? 0)
                    ? getCardInfo(rIdx, nMIdx * 2 + 1)
                    : null;
                const fn = getCardInfo(rIdx + 1, nMIdx);
                const xR = f1.left + DRAW_CARD_W;
                const xM = xR + DRAW_COL_GAP / 2;
                const xL = fn.left;
                return (
                  <g key={`conn-${rIdx}-${nMIdx}`}>
                    <line x1={xR} y1={f1.centerY} x2={xM} y2={f1.centerY} stroke="#c5d8f2" strokeWidth={1.5} />
                    {f2 && (
                      <>
                        <line x1={xR} y1={f2.centerY} x2={xM} y2={f2.centerY} stroke="#c5d8f2" strokeWidth={1.5} />
                        <line x1={xM} y1={f1.centerY} x2={xM} y2={f2.centerY} stroke="#c5d8f2" strokeWidth={1.5} />
                      </>
                    )}
                    <line x1={xM} y1={fn.centerY} x2={xL} y2={fn.centerY} stroke="#c5d8f2" strokeWidth={1.5} />
                  </g>
                );
              });
            })}
            {/* Connector from final to champion box */}
            {champVisible && displayRounds.length > 0 && (() => {
              const lastPos = getCardInfo(displayRounds.length - 1, 0);
              const x2 = DRAW_NUM_SPACE + displayRounds.length * (DRAW_CARD_W + DRAW_COL_GAP);
              return <line x1={lastPos.left + DRAW_CARD_W} y1={lastPos.centerY} x2={x2} y2={lastPos.centerY} stroke="#c5d8f2" strokeWidth={1.5} />;
            })()}
          </svg>

          {/* Match cards */}
          {displayRounds.map((round, rIdx) =>
            round.matches.map((match, mIdx) => {
              const { top, left } = getCardInfo(rIdx, mIdx);
              const isChampionPath =
                highlightedNames.length > 0 &&
                match.sides.some((s) => s.isWinner && highlightedNames.every((n) => sideName(s, isXT).includes(n)));
              return (
                <div key={match.matchId} className="absolute" style={{ top, left, width: DRAW_CARD_W }}>
                  <DrawMatchCard
                    match={match}
                    isChampionPath={isChampionPath}
                    isXT={isXT}
                    matchNumber={rIdx === 0 ? mIdx + 1 : undefined}
                    eventReturnHref={eventReturnHref}
                  />
                </div>
              );
            }),
          )}

          {/* Champion box */}
          {champVisible && displayRounds.length > 0 && (() => {
            const lastPos = getCardInfo(displayRounds.length - 1, 0);
            const hasPlayers = champion?.players && champion.players.length > 0;
            const championName = hasPlayers
              ? champion.players.map((p) => displayPlayerName(p)).join(" / ")
              : champion?.championName ?? "";
            const showName = hasPlayers || !!championName;
            return (
              <div
                className="absolute flex flex-col items-center justify-center rounded-[0.75rem] border border-[#e8c96a] bg-[linear-gradient(160deg,#fff9e3_0%,#fffef8_100%)] px-2 py-2.5 shadow-[0_4px_14px_rgba(218,187,112,0.18)]"
                style={{
                  left: DRAW_NUM_SPACE + displayRounds.length * (DRAW_CARD_W + DRAW_COL_GAP),
                  top: lastPos.centerY - 46,
                  width: champBoxW,
                }}
              >
                <Trophy size={12} className="mt-1 text-[#d4a017]" />
                <div className="mt-0.5 flex items-center justify-center gap-1">
                  <Flag
                    code={champion?.championCountryCode ?? dedupeCountries(champion?.players ?? [])[0] ?? null}
                    className="scale-[1.0]"
                  />
                </div>
                {showName ? (
                  <p className="mt-0.5 text-center text-[0.65rem] font-black leading-tight text-slate-950">
                    {truncateChineseName(championName, 6)}
                  </p>
                ) : (
                  <p className="mt-0.5 text-center text-[0.75rem] font-black leading-tight text-slate-950">
                    {champion?.championCountryCode}
                  </p>
                )}
                <p className="mt-0.5 text-[0.62rem] font-bold text-slate-500">冠军</p>
              </div>
            );
          })()}
        </div>
      </div>

      {teamKnockoutView && (
        <div className="mt-6">
          <FinalStandingsView standings={teamKnockoutView.finalStandings} />
        </div>
      )}
    </div>
  );
}

function TeamTieNodeCard({
  tie,
  title,
  eventId,
  subEventCode,
  eventReturnHref,
}: {
  tie: TeamTie;
  title?: string;
  eventId: string;
  subEventCode: string;
  eventReturnHref: string;
}) {
  const winnerA = tie.winnerCode === tie.teamA.code;
  const winnerB = tie.winnerCode === tie.teamB.code;
  return (
    <div className="rounded-[1rem] border border-[#dce7f5] bg-white px-3 py-3 shadow-sm">
      {title ? <p className="mb-2 text-[0.72rem] font-bold uppercase tracking-[0.08em] text-[#7d95c7]">{title}</p> : null}
      <div className="space-y-2">
        {[
          { team: tie.teamA, score: tie.scoreA, isWinner: winnerA },
          { team: tie.teamB, score: tie.scoreB, isWinner: winnerB },
        ].map((item) => (
          <div key={item.team.code} className="flex items-center gap-2">
            <Link href={route(buildTeamRosterHref(eventId, subEventCode, item.team.code, eventReturnHref))} className="flex min-w-0 flex-1 items-center gap-2">
              <Flag code={item.team.code} className="shrink-0 scale-[1.0]" />
              <span className={cn("truncate text-[0.88rem] font-black leading-none", item.isWinner ? "text-slate-950" : "text-slate-500")}>
                {item.team.code}
              </span>
            </Link>
            <span className={cn("font-numeric shrink-0 text-[1.12rem] font-black leading-none tabular-nums", item.isWinner ? "text-[#2d6cf6]" : "text-slate-300")}>
              {item.score}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DrawTeamTieCard({
  tie,
  eventId,
  subEventCode,
  eventReturnHref,
}: {
  tie: TeamTie;
  eventId: string;
  subEventCode: string;
  eventReturnHref: string;
}) {
  const winnerA = tie.winnerCode === tie.teamA.code;
  const winnerB = tie.winnerCode === tie.teamB.code;
  return (
    <div className="rounded-[0.6rem] border border-[#dce7f5] bg-white px-1.5 py-1 shadow-sm">
      <div className="space-y-1">
        {[
          { team: tie.teamA, score: tie.scoreA, isWinner: winnerA },
          { team: tie.teamB, score: tie.scoreB, isWinner: winnerB },
        ].map((item) => (
          <div key={item.team.code} className="flex items-center gap-1">
            <Link href={route(buildTeamRosterHref(eventId, subEventCode, item.team.code, eventReturnHref))} className="flex min-w-0 flex-1 items-center gap-1">
              <Flag code={item.team.code} className="shrink-0 scale-[0.85] origin-left" />
              <span className={cn("min-w-0 flex-1 truncate text-[0.7rem] font-bold leading-tight", item.isWinner ? "text-slate-900" : "text-slate-400")}>
                {item.team.code}
              </span>
            </Link>
            <span className={cn("font-numeric shrink-0 text-[1rem] font-black leading-none tabular-nums", item.isWinner ? "text-[#2d6cf6]" : "text-slate-300")}>
              {item.score}
            </span>
            <span className="flex w-3 shrink-0 items-center justify-center">
              {item.isWinner ? <CheckCircle2 size={10} className="text-[#2d6cf6]" strokeWidth={2.5} /> : null}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

const TEAM_DRAW_CARD_W = 132;
const TEAM_DRAW_CARD_H = 52;
const TEAM_DRAW_COL_GAP = 16;

type TeamKnockoutRound = EventTeamKnockoutView["rounds"][number];
type TeamBracketTeam = TeamTie["teamA"] | null;
type TeamBracketNode = {
  key: string;
  tie: TeamTie | null;
  teamA: TeamBracketTeam;
  teamB: TeamBracketTeam;
};
type TeamBracketRound = {
  code: string;
  label: string;
  order: number;
  nodes: TeamBracketNode[];
};

const TEAM_MAIN_DRAW_SEQUENCE: Array<{ code: string; label: string; order: number; size: number }> = [
  { code: "R128", label: "128 强", order: 10, size: 64 },
  { code: "R64", label: "64 强", order: 20, size: 32 },
  { code: "R32", label: "32 强", order: 30, size: 16 },
  { code: "R16", label: "16 强", order: 40, size: 8 },
  { code: "QuarterFinal", label: "四分之一决赛", order: 50, size: 4 },
  { code: "SemiFinal", label: "半决赛", order: 60, size: 2 },
  { code: "Final", label: "决赛", order: 80, size: 1 },
];

const TEAM_ROUND_ALIASES: Record<string, string> = {
  F: "Final",
  Final: "Final",
  SF: "SemiFinal",
  SemiFinal: "SemiFinal",
  QF: "QuarterFinal",
  QuarterFinal: "QuarterFinal",
  R16: "R16",
  R32: "R32",
  R64: "R64",
  R128: "R128",
};

function normalizeTeamRoundCode(code: string) {
  return TEAM_ROUND_ALIASES[code] ?? code;
}

function teamTieWinner(tie: TeamTie | null): TeamBracketTeam {
  if (!tie?.winnerCode) return null;
  if (tie.winnerCode === tie.teamA.code) return tie.teamA;
  if (tie.winnerCode === tie.teamB.code) return tie.teamB;
  return { code: tie.winnerCode, name: tie.winnerCode, nameZh: null };
}

function teamTiePosition(tie: TeamTie) {
  const text = `${tie.roundZh ?? ""} ${tie.round ?? ""}`;
  const match = text.match(/Match\s+(\d+)/i) ?? text.match(/第\s*(\d+)\s*场/);
  return match ? Number(match[1]) : Number.POSITIVE_INFINITY;
}

function sortTeamTiesByBracketPosition(ties: TeamTie[]) {
  return [...ties].sort((left, right) => {
    const positionDiff = teamTiePosition(left) - teamTiePosition(right);
    if (Number.isFinite(positionDiff) && positionDiff !== 0) return positionDiff;
    return Number(left.tieId) - Number(right.tieId);
  });
}

function cleanTeamRoundLabel(label: string, fallback: string) {
  return /Match\s+\d+/i.test(label) || /第\s*\d+\s*场/.test(label) ? fallback : label;
}

function buildCompleteTeamBracketRounds(rounds: TeamKnockoutRound[]): TeamBracketRound[] {
  const roundMap = new Map(
    rounds
      .filter((round) => round.code !== "Bronze" && round.ties.length > 0)
      .map((round) => [normalizeTeamRoundCode(round.code), round]),
  );
  const earliestRound = TEAM_MAIN_DRAW_SEQUENCE.find((meta) => roundMap.has(meta.code));
  if (!earliestRound) return [];

  const sequence = TEAM_MAIN_DRAW_SEQUENCE.filter((meta) => meta.order >= earliestRound.order);
  const completed: TeamBracketRound[] = [];

  sequence.forEach((meta, roundIndex) => {
    const sourceRound = roundMap.get(meta.code);
    const realTies = sourceRound ? sortTeamTiesByBracketPosition(sourceRound.ties) : [];
    const previousRound = completed[roundIndex - 1];
    const nodes: TeamBracketNode[] = Array.from({ length: meta.size }, (_, nodeIndex) => {
      const tie = realTies[nodeIndex] ?? null;
      const feederA = previousRound?.nodes[nodeIndex * 2] ?? null;
      const feederB = previousRound?.nodes[nodeIndex * 2 + 1] ?? null;
      return {
        key: tie?.tieId ?? `${meta.code}-placeholder-${nodeIndex}`,
        tie,
        teamA: tie?.teamA ?? teamTieWinner(feederA?.tie ?? null),
        teamB: tie?.teamB ?? teamTieWinner(feederB?.tie ?? null),
      };
    });

    completed.push({
      code: meta.code,
      label: sourceRound ? cleanTeamRoundLabel(sourceRound.label, meta.label) : meta.label,
      order: sourceRound?.order ?? meta.order,
      nodes,
    });
  });

  return completed;
}

function DrawTeamPlaceholderCard({
  node,
  eventId,
  subEventCode,
  eventReturnHref,
}: {
  node: TeamBracketNode;
  eventId: string;
  subEventCode: string;
  eventReturnHref: string;
}) {
  return (
    <div className="rounded-[0.6rem] border border-dashed border-[#cbd8ea] bg-[#f8fbff] px-1.5 py-1 shadow-sm">
      <div className="space-y-1">
        {[node.teamA, node.teamB].map((team, index) => (
          <div key={`${node.key}-${index}`} className="flex items-center gap-1">
            {team?.code ? (
              <Link href={route(buildTeamRosterHref(eventId, subEventCode, team.code, eventReturnHref))} className="flex min-w-0 flex-1 items-center gap-1">
                <Flag code={team.code} className="shrink-0 scale-[0.85] origin-left" />
                <span className="min-w-0 flex-1 truncate text-[0.7rem] font-bold leading-tight text-slate-700">
                  {team.code}
                </span>
              </Link>
            ) : (
              <div className="flex min-w-0 flex-1 items-center gap-1">
                <span className="h-2.5 w-3.5 shrink-0 rounded-[0.15rem] bg-slate-200" />
                <span className="min-w-0 flex-1 truncate text-[0.7rem] font-bold leading-tight text-slate-300">
                  待定
                </span>
              </div>
            )}
            <span className="font-numeric shrink-0 text-[1rem] font-black leading-none tabular-nums text-slate-200">-</span>
            <span className="w-3 shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}

function orderTeamRoundsByFeeders(rounds: TeamKnockoutRound[]): TeamKnockoutRound[] {
  if (rounds.length <= 1) return rounds;
  const result = rounds.map((round) => ({ ...round, ties: [...round.ties] }));

  for (let r = result.length - 1; r > 0; r--) {
    const nextRound = result[r];
    const prevRound = result[r - 1];
    const used = new Set<string>();
    const ordered: TeamTie[] = [];

    for (const nt of nextRound.ties) {
      for (const teamCode of [nt.teamA.code, nt.teamB.code]) {
        const feeder = prevRound.ties.find(
          (pt) => !used.has(pt.tieId) && pt.winnerCode === teamCode,
        );
        if (feeder) {
          ordered.push(feeder);
          used.add(feeder.tieId);
        }
      }
    }
    for (const pt of prevRound.ties) {
      if (!used.has(pt.tieId)) ordered.push(pt);
    }

    result[r - 1] = { ...prevRound, ties: ordered };
  }

  return result;
}

function TeamKnockoutDrawView({
  view,
  eventId,
  subEventCode,
  eventReturnHref,
}: {
  view: EventTeamKnockoutView;
  eventId: string;
  subEventCode: string;
  eventReturnHref: string;
}) {
  const bracketRounds = React.useMemo(
    () => {
      const filtered = view.rounds
        .filter((round) => round.code !== "Bronze" && round.ties.length > 0)
        .slice()
        .sort((a, b) => a.order - b.order)
        .map((round) => ({ ...round, code: normalizeTeamRoundCode(round.code) }));
      return buildCompleteTeamBracketRounds(orderTeamRoundsByFeeders(filtered));
    },
    [view.rounds],
  );
  const bronzeTie = view.bronzeTie ?? view.rounds.find((round) => round.code === "Bronze")?.ties[0] ?? null;

  if (bracketRounds.length === 0 && !bronzeTie) {
    return (
      <div className="pt-5">
        <div className="rounded-[1.7rem] bg-white/82 p-8 text-center text-slate-500 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          这项赛事图还没收录
        </div>
      </div>
    );
  }

  const firstRoundCount = bracketRounds[0]?.nodes.length ?? 1;
  const slotH0 = Math.max(TEAM_DRAW_CARD_H + 12, 72);
  const totalH = firstRoundCount * slotH0;

  const getCardInfo = (rIdx: number, mIdx: number) => {
    const count = bracketRounds[rIdx]?.nodes.length ?? 1;
    const slotH = totalH / count;
    return {
      top: mIdx * slotH + (slotH - TEAM_DRAW_CARD_H) / 2,
      centerY: mIdx * slotH + slotH / 2,
      left: rIdx * (TEAM_DRAW_CARD_W + TEAM_DRAW_COL_GAP),
    };
  };

  const totalW = bracketRounds.length * (TEAM_DRAW_CARD_W + TEAM_DRAW_COL_GAP);

  return (
    <div className="pb-10 pt-5">
      {isTeamTieCompleted(view.finalTie) ? (
        <section className="mb-6">
          <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">领奖台</h2>
          <Podium podium={teamPodiumDisplay(view.podium)} />
        </section>
      ) : null}

      {bracketRounds.length > 0 && (
        <div className="overflow-x-auto pb-2">
          <div className="mb-3 flex" style={{ minWidth: totalW }}>
            {bracketRounds.map((round) => (
              <div
                key={round.code}
                className="shrink-0 text-center"
                style={{ width: TEAM_DRAW_CARD_W, marginRight: TEAM_DRAW_COL_GAP }}
              >
                <p className="text-[0.78rem] font-black text-slate-900">{round.label}</p>
                <p className="mt-0.5 text-[0.65rem] font-medium text-slate-400">
                  {round.nodes.filter((node) => node.tie).length}/{round.nodes.length} 场
                </p>
              </div>
            ))}
          </div>

          <div className="relative" style={{ height: totalH, minWidth: totalW }}>
            <svg
              className="pointer-events-none absolute inset-0 overflow-visible"
              style={{ width: totalW, height: totalH }}
            >
              {bracketRounds.map((_, rIdx) => {
                if (rIdx >= bracketRounds.length - 1) return null;
                const currentRound = bracketRounds[rIdx];
                const nextRound = bracketRounds[rIdx + 1];
                return nextRound.nodes.map((__, nMIdx) => {
                  const f1Idx = nMIdx * 2;
                  const f2Idx = nMIdx * 2 + 1;
                  if (f2Idx >= currentRound.nodes.length) return null;
                  const f1 = getCardInfo(rIdx, f1Idx);
                  const f2 = getCardInfo(rIdx, f2Idx);
                  const fn = getCardInfo(rIdx + 1, nMIdx);
                  const xR = f1.left + TEAM_DRAW_CARD_W;
                  const xM = xR + TEAM_DRAW_COL_GAP / 2;
                  const xL = fn.left;
                  const yTop = Math.min(f1.centerY, f2.centerY, fn.centerY);
                  const yBottom = Math.max(f1.centerY, f2.centerY, fn.centerY);
                  return (
                    <g key={`team-conn-${rIdx}-${nMIdx}`}>
                      <line x1={xR} y1={f1.centerY} x2={xM} y2={f1.centerY} stroke="#c5d8f2" strokeWidth={1.5} />
                      <line x1={xR} y1={f2.centerY} x2={xM} y2={f2.centerY} stroke="#c5d8f2" strokeWidth={1.5} />
                      <line x1={xM} y1={yTop} x2={xM} y2={yBottom} stroke="#c5d8f2" strokeWidth={1.5} />
                      <line x1={xM} y1={fn.centerY} x2={xL} y2={fn.centerY} stroke="#c5d8f2" strokeWidth={1.5} />
                    </g>
                  );
                });
              })}
            </svg>

            {bracketRounds.map((round, rIdx) =>
              round.nodes.map((node, mIdx) => {
                const { top, left } = getCardInfo(rIdx, mIdx);
                return (
                  <div
                    key={node.key}
                    className="absolute"
                    style={{ top, left, width: TEAM_DRAW_CARD_W }}
                  >
                    {node.tie ? (
                      <DrawTeamTieCard tie={node.tie} eventId={eventId} subEventCode={subEventCode} eventReturnHref={eventReturnHref} />
                    ) : (
                      <DrawTeamPlaceholderCard node={node} eventId={eventId} subEventCode={subEventCode} eventReturnHref={eventReturnHref} />
                    )}
                  </div>
                );
              }),
            )}
          </div>
        </div>
      )}

      {bronzeTie && (
        <section className="mt-6">
          <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">铜牌赛</h2>
          <TeamTieNodeCard tie={bronzeTie} eventId={eventId} subEventCode={subEventCode} eventReturnHref={eventReturnHref} />
        </section>
      )}

      {view.finalStandings.length > 0 && (
        <div className="mt-6">
          <FinalStandingsView standings={view.finalStandings} />
        </div>
      )}
    </div>
  );
}

type PodiumEntry = {
  flagCode: string | null;
  lines: string[];
};

type PodiumDisplay = {
  champion: PodiumEntry | null;
  runnerUp: PodiumEntry | null;
  thirdPlace: PodiumEntry | null;
  thirdPlaceSecond?: PodiumEntry | null;
};

function standingToPodiumEntry(standing: StageStanding | null): PodiumEntry | null {
  if (!standing) return null;
  const name = standing.teamNameZh || standing.teamName || standing.teamCode || "待补";
  return { flagCode: standing.teamCode ?? null, lines: [name] };
}

function sideToPodiumEntry(
  side: BracketMatch["sides"][number] | undefined,
  isXT: boolean,
): PodiumEntry | null {
  if (!side || side.players.length === 0) return null;
  const flagCode = dedupeCountries(side.players)[0] ?? null;
  if (isXT) {
    return { flagCode, lines: [flagCode ?? "待补"] };
  }
  const lines = side.players.slice(0, 2).map((player) => compactPlayerName(player));
  return { flagCode, lines: lines.length > 0 ? lines : ["待补"] };
}

function deriveBracketPodium(
  rounds: EventDetail["bracket"],
  isXT: boolean,
): PodiumDisplay | null {
  const finalRound = rounds.find((round) => round.code === "Final");
  const finalMatch = finalRound?.matches[0];
  if (!finalMatch) return null;

  const finalWinner = finalMatch.sides.find((side) => side.isWinner);
  const finalLoser = finalMatch.sides.find((side) => !side.isWinner);
  const champion = sideToPodiumEntry(finalWinner, isXT);
  const runnerUp = sideToPodiumEntry(finalLoser, isXT);

  let thirdPlace: PodiumEntry | null = null;
  let thirdPlaceSecond: PodiumEntry | null = null;

  const bronzeRound = rounds.find((round) => round.code === "Bronze");
  const bronzeMatch = bronzeRound?.matches[0];
  if (bronzeMatch && bronzeMatch.sides.some((side) => side.isWinner)) {
    const bronzeWinner = bronzeMatch.sides.find((side) => side.isWinner);
    thirdPlace = sideToPodiumEntry(bronzeWinner, isXT);
  } else {
    const semiRound = rounds.find((round) => round.code === "SemiFinal");
    const losers = (semiRound?.matches ?? [])
      .map((match) => match.sides.find((side) => !side.isWinner))
      .filter((side): side is BracketMatch["sides"][number] => Boolean(side));
    thirdPlace = sideToPodiumEntry(losers[0], isXT);
    thirdPlaceSecond = sideToPodiumEntry(losers[1], isXT);
  }

  if (!champion && !runnerUp && !thirdPlace) return null;
  return { champion, runnerUp, thirdPlace, thirdPlaceSecond };
}

function PodiumEntryDisplay({
  entry,
  showCrown,
  compact,
}: {
  entry: PodiumEntry | null;
  showCrown?: boolean;
  compact?: boolean;
}) {
  const flagSize = compact
    ? "h-8 w-8 sm:h-9 sm:w-9"
    : "h-11 w-11 sm:h-14 sm:w-14";
  const flagScale = compact ? "scale-[1.1] sm:scale-[1.3]" : "scale-[1.6] sm:scale-[2.2]";
  const nameWidth = compact
    ? "max-w-[58px] sm:max-w-[72px] text-[0.66rem] sm:text-[0.72rem]"
    : "max-w-[76px] sm:max-w-[100px] text-[0.72rem] sm:text-[0.82rem]";
  const lines = entry?.lines && entry.lines.length > 0 ? entry.lines : ["待补"];

  return (
    <div className="flex flex-col items-center">
      <div className="relative mb-1.5">
        <div
          className={cn(
            "flex items-center justify-center rounded-full bg-white shadow-sm ring-1 ring-[#e8edf8]",
            flagSize,
          )}
        >
          <Flag code={entry?.flagCode ?? null} className={flagScale} />
        </div>
        {showCrown && (
          <Crown
            size={compact ? 14 : 18}
            className="absolute -right-1 -top-2 fill-yellow-400 text-yellow-600 drop-shadow-sm rotate-[12deg]"
          />
        )}
      </div>
      <div className={cn("text-center font-bold text-slate-700", nameWidth)}>
        {lines.map((line, index) => (
          <p key={index} className="truncate leading-tight">
            {line}
          </p>
        ))}
      </div>
    </div>
  );
}

function PodiumSlot({
  rank,
  entry,
  entrySecond,
  baseHeight,
  colorScheme,
}: {
  rank: 1 | 2 | 3;
  entry: PodiumEntry | null;
  entrySecond?: PodiumEntry | null;
  baseHeight: string;
  colorScheme: {
    bg: string;
    border: string;
    text: string;
    trophy: string;
  };
}) {
  const isChampion = rank === 1;
  const tied = Boolean(entrySecond);

  return (
    <div className="flex flex-1 flex-col items-center">
      <div className="mb-2.5 flex w-full items-end justify-center gap-1 sm:gap-2">
        {tied ? (
          <>
            <PodiumEntryDisplay entry={entry} compact />
            <PodiumEntryDisplay entry={entrySecond ?? null} compact />
          </>
        ) : (
          <PodiumEntryDisplay entry={entry} showCrown={isChampion} />
        )}
      </div>

      <div
        className={cn(
          "relative flex w-full flex-col items-center justify-center rounded-t-xl border-x border-t transition-all duration-500",
          colorScheme.bg,
          colorScheme.border,
          baseHeight,
        )}
      >
        <Trophy size={isChampion ? 20 : 16} className={cn("mb-0.5", colorScheme.trophy)} />
        <span
          className={cn(
            "font-numeric text-lg font-black leading-none sm:text-xl",
            colorScheme.text,
          )}
        >
          {rank}
        </span>
      </div>
    </div>
  );
}

function Podium({ podium }: { podium: PodiumDisplay }) {
  return (
    <div className="flex items-end justify-center gap-2 px-1 py-4 sm:gap-4 sm:px-4">
      <PodiumSlot
        rank={3}
        entry={podium.thirdPlace}
        entrySecond={podium.thirdPlaceSecond ?? null}
        baseHeight="h-12 sm:h-14"
        colorScheme={{
          bg: "bg-[#fdf8f4]",
          border: "border-orange-100",
          text: "text-orange-700",
          trophy: "text-orange-400",
        }}
      />
      <PodiumSlot
        rank={1}
        entry={podium.champion}
        baseHeight="h-20 sm:h-24"
        colorScheme={{
          bg: "bg-[#fffdf2]",
          border: "border-yellow-200",
          text: "text-yellow-700",
          trophy: "text-yellow-500",
        }}
      />
      <PodiumSlot
        rank={2}
        entry={podium.runnerUp}
        baseHeight="h-16 sm:h-18"
        colorScheme={{
          bg: "bg-[#f8fafc]",
          border: "border-slate-200",
          text: "text-slate-700",
          trophy: "text-slate-400",
        }}
      />
    </div>
  );
}

function teamPodiumDisplay(podium: {
  champion: StageStanding | null;
  runnerUp: StageStanding | null;
  thirdPlace: StageStanding | null;
  thirdPlaceSecond?: StageStanding | null;
}): PodiumDisplay {
  return {
    champion: standingToPodiumEntry(podium.champion),
    runnerUp: standingToPodiumEntry(podium.runnerUp),
    thirdPlace: standingToPodiumEntry(podium.thirdPlace),
    thirdPlaceSecond: standingToPodiumEntry(podium.thirdPlaceSecond ?? null),
  };
}

function isTeamTieCompleted(tie: TeamTie | null | undefined) {
  if (!tie?.winnerCode) return false;
  return tie.scoreA >= 3 || tie.scoreB >= 3;
}

function hasCompletedBracketFinal(rounds: EventDetail["bracket"]) {
  const finalRound = rounds.find((round) => round.code === "Final" || round.code === "F");
  if (!finalRound || finalRound.matches.length === 0) return true;
  return finalRound.matches.some((match) => Boolean(match.matchScore?.trim()));
}

function TeamTieCard({
  tie,
  title,
  eventReturnHref,
  eventId,
  subEventCode,
  showTeamLinks = true,
}: {
  tie: TeamTie;
  title?: string;
  eventReturnHref: string;
  eventId: string;
  subEventCode: string;
  showTeamLinks?: boolean;
}) {
  const titleText = title || tie.roundZh || tie.round || "循环赛";
  const winnerA = tie.winnerCode === tie.teamA.code;
  const winnerB = tie.winnerCode === tie.teamB.code;
  return (
    <div className="rounded-[1.35rem] bg-white px-4 py-3.5 ring-1 ring-[#e8edf8]">
      <div className="flex items-center justify-between gap-2">
        <span className="shrink-0 text-[0.85rem] font-bold text-slate-500">{titleText}</span>
        <div className="flex items-center gap-1.5 min-w-0">
          {showTeamLinks ? (
            <Link href={route(buildTeamRosterHref(eventId, subEventCode, tie.teamA.code, eventReturnHref))} className="inline-flex items-center gap-1 shrink-0">
              <Flag code={tie.teamA.code} className="shrink-0 scale-[1.05]" />
              <span className={cn("text-[0.95rem] font-black leading-none", winnerA ? "text-slate-950" : "text-slate-500")}>
                {tie.teamA.code}
              </span>
            </Link>
          ) : (
            <>
              <Flag code={tie.teamA.code} className="shrink-0 scale-[1.05]" />
              <span className={cn("text-[0.95rem] font-black leading-none", winnerA ? "text-slate-950" : "text-slate-500")}>
                {tie.teamA.code}
              </span>
            </>
          )}
          <span className={cn("font-numeric ml-0.5 text-[1.25rem] font-black leading-none tabular-nums", winnerA ? "text-[#2d6cf6]" : "text-slate-400")}>
            {tie.scoreA}
          </span>
          <span className="text-[0.95rem] font-black leading-none text-slate-300">-</span>
          <span className={cn("font-numeric text-[1.25rem] font-black leading-none tabular-nums", winnerB ? "text-[#2d6cf6]" : "text-slate-400")}>
            {tie.scoreB}
          </span>
          {showTeamLinks ? (
            <Link href={route(buildTeamRosterHref(eventId, subEventCode, tie.teamB.code, eventReturnHref))} className="inline-flex items-center gap-1 shrink-0">
              <span className={cn("ml-0.5 text-[0.95rem] font-black leading-none", winnerB ? "text-slate-950" : "text-slate-500")}>
                {tie.teamB.code}
              </span>
              <Flag code={tie.teamB.code} className="shrink-0 scale-[1.05]" />
            </Link>
          ) : (
            <>
              <span className={cn("ml-0.5 text-[0.95rem] font-black leading-none", winnerB ? "text-slate-950" : "text-slate-500")}>
                {tie.teamB.code}
              </span>
              <Flag code={tie.teamB.code} className="shrink-0 scale-[1.05]" />
            </>
          )}
        </div>
      </div>
      <div className="mt-2 divide-y divide-slate-100">
        {tie.rubbers.map((rubber, index) => (
          <Link
            key={rubber.matchId}
            href={route(withFromQuery(`/matches/${rubber.matchId}`, eventReturnHref))}
            className="flex items-start justify-between gap-3 py-2 transition"
          >
            <div className="flex min-w-0 flex-1 items-start gap-2">
              <span className="shrink-0 text-[0.88rem] font-black leading-snug text-[#2d6cf6]">第{index + 1}盘</span>
              <span className="min-w-0 flex-1 text-[0.88rem] font-medium leading-snug text-slate-600">{compactRubberPlayersLabel(rubber)}</span>
            </div>
            <span className="font-numeric shrink-0 text-[0.95rem] font-black leading-snug tabular-nums text-[#2d6cf6]">{rubber.matchScore ?? "-"}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function FinalStandingsView({ standings }: { standings: StageStanding[] }) {
  if (standings.length === 0) return null;

  return (
    <div className="rounded-[1.6rem] bg-white p-4 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
      <h3 className="text-[1.25rem] font-black text-slate-950">最终排名</h3>
      <div className="mt-4 space-y-3">
        {standings.map((standing) => (
          <div key={standing.teamCode} className="flex items-center gap-3 rounded-[1rem] bg-[#f6f8fd] px-3 py-3">
            <div className="grid h-9 w-9 place-items-center rounded-full bg-[#2d6cf6] text-[1rem] font-black text-white">
              {standing.rank}
            </div>
            <Flag code={standing.teamCode} className="scale-[1.35]" />
            <p className="text-[1.02rem] font-black text-slate-900">{standing.teamNameZh || standing.teamName}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatQualificationMark(mark: string | null | undefined, rank?: number | null): string {
  if ((rank ?? 0) === 0) return "-";
  if (!mark) return "-";
  const map: Record<string, string> = {
    "Q-MD": "晋级",
    "Q-PR": "预选赛",
    "NQ": "淘汰",
  };
  return map[mark] ?? mark;
}

function GroupStandingsTable({
  standings,
  eventId,
  subEventCode,
  eventReturnHref,
}: {
  standings: StageStanding[];
  eventId: string;
  subEventCode: string;
  eventReturnHref: string;
}) {
  if (standings.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-[1.2rem] bg-white ring-1 ring-[#e8edf8]">
      <div className="grid grid-cols-[2.5rem_minmax(0,1fr)_2.2rem_2.2rem_2.2rem_3rem_4rem] gap-2 border-b border-slate-100 px-3 py-2 text-[0.68rem] font-bold uppercase tracking-[0.06em] text-slate-400">
        <span>排名</span>
        <span>队伍</span>
        <span className="text-center">赛</span>
        <span className="text-center">胜</span>
        <span className="text-center">负</span>
        <span className="text-center">积分</span>
        <span className="text-center">晋级状态</span>
      </div>
      <div>
        {standings.map((standing) => (
          <Link
            key={standing.teamCode}
            href={route(buildTeamRosterHref(eventId, subEventCode, standing.teamCode, eventReturnHref))}
            className="grid grid-cols-[2.5rem_minmax(0,1fr)_2.2rem_2.2rem_2.2rem_3rem_4rem] items-center gap-2 px-3 py-3 text-[0.82rem] font-bold text-slate-700 not-last:border-b not-last:border-slate-100 transition hover:bg-[#f7faff]"
          >
            <span className="text-[#2d6cf6]">{standing.rank}</span>
            <span className="flex min-w-0 items-center gap-2">
              <Flag code={standing.teamCode} className="shrink-0" />
              <span className="truncate">{standing.teamNameZh || standing.teamName}</span>
            </span>
            <span className="text-center">{standing.matches ?? 0}</span>
            <span className="text-center">{standing.wins ?? 0}</span>
            <span className="text-center">{standing.losses ?? 0}</span>
            <span className="text-center">{standing.tiePoints ?? 0}</span>
            <span className="text-center text-[0.78rem]">
              {formatQualificationMark(standing.qualificationMark, standing.rank)}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function RoundRobinView({
  view,
  defaultCollapsed = false,
  eventReturnHref,
  eventId,
  subEventCode,
}: {
  view: EventRoundRobinView;
  defaultCollapsed?: boolean;
  eventReturnHref: string;
  eventId: string;
  subEventCode: string;
}) {
  const [collapsedStages, setCollapsedStages] = React.useState<Set<string>>(
    defaultCollapsed ? new Set(view.stages.map((stage) => stage.code)) : new Set(),
  );
  const [collapsedGroups, setCollapsedGroups] = React.useState<Set<string>>(new Set());

  React.useEffect(() => {
    setCollapsedStages(defaultCollapsed ? new Set(view.stages.map((stage) => stage.code)) : new Set());
  }, [defaultCollapsed, view.stages]);

  const toggleStage = React.useCallback((key: string) => {
    setCollapsedStages((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const toggleGroup = React.useCallback((key: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  return (
    <div className="pb-10 pt-5">
      {(view.podium.champion || view.podium.runnerUp || view.podium.thirdPlace) && (
        <section>
          <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">领奖台</h2>
          <Podium podium={teamPodiumDisplay(view.podium)} />
        </section>
      )}

      {view.finalStandings.length > 0 ? (
        <div className="mt-6">
          <FinalStandingsView standings={view.finalStandings} />
        </div>
      ) : null}

      <div className="mt-6 space-y-6">
        {view.stages.map((stage) => {
          const isStageCollapsed = collapsedStages.has(stage.code);
          return (
            <section key={stage.code}>
              <button
                type="button"
                onClick={() => toggleStage(stage.code)}
                className="mb-3 flex w-full items-center justify-between gap-3 px-1.5"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <h2 className="text-[1.25rem] font-black text-slate-950">{stage.nameZh || stage.name}</h2>
                  <span className="text-[0.92rem] font-semibold text-slate-500">
                    {stage.format === "group_round_robin" ? "分组循环赛" : "循环赛"}
                  </span>
                </div>
                <span className="shrink-0 flex items-center gap-1 text-[0.86rem] font-bold text-slate-500">
                  {isStageCollapsed ? "展开" : "收起"}
                  {isStageCollapsed ? <ChevronDown size={16} strokeWidth={2.5} /> : <ChevronUp size={16} strokeWidth={2.5} />}
                </span>
              </button>
              {!isStageCollapsed ? (
                stage.groups ? (
                  <div className="space-y-4">
                    {stage.groups.map((group) => {
                      const groupKey = `${stage.code}:${group.code}`;
                      const isCollapsed = collapsedGroups.has(groupKey);
                      return (
                        <div key={group.code} className="rounded-[1.6rem] bg-white p-4 ring-1 ring-[#e8edf8] shadow-sm">
                          <button
                            type="button"
                            onClick={() => toggleGroup(groupKey)}
                            className="flex w-full justify-between items-center"
                          >
                            <h3 className="shrink-0 text-base font-black text-slate-900 whitespace-nowrap">{group.nameZh || group.code}</h3>
                            <div className="flex min-w-0 flex-1 flex-wrap pt-2 items-center justify-center gap-1 text-[0.72rem] font-bold text-slate-600">
                              {group.teams.map((team) => (
                                <span key={team} className="inline-flex items-center gap-0.5 rounded-sm bg-[#f8fafc] px-1 py-2 whitespace-nowrap leading-none">
                                  <Flag code={team} />
                                  <span>{team}</span>
                                </span>
                              ))}
                            </div>
                            <span className="shrink-0 flex items-center gap-0.5 text-[0.8rem] font-medium text-slate-400">
                              {isCollapsed ? "展开" : "收起"}
                              {isCollapsed ? <ChevronDown size={14} strokeWidth={2.5} /> : <ChevronUp size={14} strokeWidth={2.5} />}
                            </span>
                          </button>
                          {!isCollapsed && (
                            <div className="mt-4 space-y-3">
                              <GroupStandingsTable
                                standings={group.standings ?? []}
                                eventId={eventId}
                                subEventCode={subEventCode}
                                eventReturnHref={eventReturnHref}
                              />
                              {group.ties.map((tie, index) => (
                                <TeamTieCard
                                  key={tie.tieId}
                                  tie={tie}
                                  title={`第${index + 1}场`}
                                  eventReturnHref={eventReturnHref}
                                  eventId={eventId}
                                  subEventCode={subEventCode}
                                />
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="space-y-3">
                    {(stage.ties ?? []).map((tie, index) => (
                      <TeamTieCard
                        key={tie.tieId}
                        tie={tie}
                        title={`第${index + 1}场`}
                        eventReturnHref={eventReturnHref}
                        eventId={eventId}
                        subEventCode={subEventCode}
                      />
                    ))}
                  </div>
                )
              ) : null}
            </section>
          );
        })}
      </div>

    </div>
  );
}

function ChampionsListView({ subEvent }: { subEvent: EventSubEventView | undefined }) {
  if (!subEvent || subEvent.disabled || !supportsChampionRosterTab(subEvent.code)) {
    return (
      <div className="pt-5">
        <div className="rounded-[1.7rem] bg-white/82 p-8 text-center text-slate-500 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          当前项目无可展示的冠军成员
        </div>
      </div>
    );
  }

  const champion = subEvent.champion;
  const championNames = normalizeChampionNames(champion);
  const countries = champion
    ? dedupeCountries(champion.players).length > 0
      ? dedupeCountries(champion.players)
      : champion.championCountryCode
        ? [champion.championCountryCode]
        : []
    : [];

  return (
    <div className="pb-10 pt-4">
      <section>
        <h2 className="mb-3 text-[1.2rem] font-black text-slate-900">{subEventLabel(subEvent)}</h2>
        <div className="rounded-[1.6rem] bg-white p-4 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          <div className="flex items-center gap-2">
            <Crown size={18} className="text-[#d4a017]" />
            <span className="text-[0.92rem] font-bold text-slate-500">冠军球队</span>
          </div>
          {champion && champion.players.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-[0.88rem] font-bold text-slate-500">成员名单</p>
              <div className="flex flex-wrap gap-2">
                {champion.players.map((player) => (
                  <Link
                    key={player.playerId}
                    href={route(`/players/${player.slug}`)}
                    className="inline-flex items-center gap-2 rounded-full bg-[#f6f8fd] px-3 py-1.5 transition hover:bg-[#eef4ff]"
                  >
                    <span className="text-base font-bold text-slate-700">{displayPlayerName(player)}</span>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function EventDetailSkeleton() {
  return (
    <div className="mx-auto min-h-screen max-w-lg bg-[#f8fafc]">
      <div className="animate-pulse">
        {/* Header Skeleton */}
        <section className="relative overflow-hidden bg-[#f0f4ff] px-4 pb-4 pt-4">
          <div className="relative z-10">
            <div className="flex items-start justify-between gap-2">
              <div className="mt-0.5 h-8 w-8 rounded-full bg-slate-200/60" />
              <div className="min-w-0 flex-1 px-4 pt-1.5 flex flex-col items-center">
                <div className="h-6 w-3/4 rounded bg-slate-200/60" />
                <div className="mt-2 h-4 w-1/2 rounded bg-slate-200/60" />
              </div>
              <div className="mt-0.5 h-8 w-8 rounded-full bg-slate-200/60" />
            </div>

            <div className="mt-7 flex gap-1.5 overflow-hidden rounded-full bg-white/80 px-1 py-[3px]">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-[28px] w-20 rounded-full bg-slate-100/80" />
              ))}
            </div>
          </div>
        </section>

        {/* Content Skeleton */}
        <div className="relative z-10 -mt-3 rounded-t-[1.5rem] bg-white px-5 pt-3 pb-4 shadow-[0_-12px_40px_rgba(0,0,0,0.04)] ring-1 ring-black/[0.02]">
          <div className="flex justify-around border-b border-slate-100 px-1">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex h-14 items-center gap-2 px-4">
                <div className="h-4 w-12 rounded bg-slate-100" />
              </div>
            ))}
          </div>

          <div className="mt-6 space-y-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <div className="h-3 w-16 rounded bg-slate-50" />
                  <div className="h-5 w-12 rounded-full bg-slate-50" />
                </div>
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="h-6 w-6 rounded-full bg-slate-100" />
                    <div className="h-4 flex-1 rounded bg-slate-100" />
                    <div className="h-6 w-8 rounded bg-slate-100" />
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="h-6 w-6 rounded-full bg-slate-100" />
                    <div className="h-4 flex-1 rounded bg-slate-100" />
                    <div className="h-6 w-8 rounded bg-slate-100" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function EventDetailContent() {
  const params = useParams<{ eventId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlSubEvent = searchParams.get("sub_event");
  const urlView = normalizeViewMode(searchParams.get("view"));
  const urlDate = searchParams.get("date");
  const from = searchParams.get("from");
  const [data, setData] = React.useState<EventDetail | null>(null);
  const [selectedSubEvent, setSelectedSubEvent] = React.useState<string | null>(urlSubEvent);
  const [viewMode, setViewMode] = React.useState<ViewMode>(urlView ?? "session");
  const [selectedDate, setSelectedDate] = React.useState<string | null>(urlDate);
  const [loading, setLoading] = React.useState(true);
  const initialUrlSubEventRef = React.useRef(urlSubEvent);
  const shouldSyncUrlRef = React.useRef(Boolean(urlSubEvent || urlView || urlDate));
  const handleBack = React.useCallback(() => {
    if (from) {
      router.push(from as Route);
      return;
    }
    if (window.history.length > 1) {
      router.back();
      return;
    }
    router.push("/events");
  }, [router, from]);

  React.useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetch(`/api/v1/events/${params.eventId}`);
        const json = (await res.json()) as EventDetailResponse;
        if (json.code === 0) {
          setData(json.data);
          setSelectedSubEvent((current) => current ?? initialUrlSubEventRef.current ?? json.data.selectedSubEvent);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }

    if (params.eventId) load();
  }, [params.eventId]);

  const useNewLiveTabs =
    data?.event.lifecycleStatus === "in_progress" &&
    ((data?.sessionSchedule.length ?? 0) > 0 || (data?.scheduleDays.length ?? 0) > 0);

  React.useEffect(() => {
    if (!data) return;

    setViewMode((current) => {
      if (useNewLiveTabs) {
        return current === "session" || current === "draw" || current === "schedule" ? current : "session";
      }
      return current === "schedule" || current === "draw" || current === "champions" ? current : "schedule";
    });
  }, [data, useNewLiveTabs]);

  const currentSubEvent = selectedSubEvent ?? data?.selectedSubEvent ?? null;
  const effectiveDate = viewMode === "schedule" ? selectedDate : null;

  React.useEffect(() => {
    if (!data || !currentSubEvent) return;
    if (!shouldSyncUrlRef.current) return;

    const nextHref = buildEventDetailHref(params.eventId, {
      subEvent: currentSubEvent,
      view: viewMode,
      date: effectiveDate,
      from: from,
    });
    const currentHref = searchParams.toString() ? `/events/${params.eventId}?${searchParams.toString()}` : `/events/${params.eventId}`;

    if (nextHref !== currentHref) {
      router.replace(route(nextHref), { scroll: false });
    }
  }, [currentSubEvent, data, effectiveDate, from, params.eventId, router, searchParams, viewMode]);

  const handleSelectSubEvent = React.useCallback((value: string | null) => {
    if (!value) return;
    shouldSyncUrlRef.current = true;
    if (data && viewMode === "schedule" && useNewLiveTabs) {
      setSelectedDate(
        resolveScheduleDateForSubEvent({
          days: data.scheduleDays,
          subEventCode: value,
          eventTimeZone: data.event.timeZone,
          preferredDate: selectedDate,
        }),
      );
    }
    setSelectedSubEvent(value);
  }, [data, selectedDate, useNewLiveTabs, viewMode]);

  const handleChangeViewMode = React.useCallback((value: ViewMode) => {
    shouldSyncUrlRef.current = true;
    if (value === "schedule" && data && currentSubEvent && useNewLiveTabs) {
      setSelectedDate((current) =>
        resolveScheduleDateForSubEvent({
          days: data.scheduleDays,
          subEventCode: currentSubEvent,
          eventTimeZone: data.event.timeZone,
          preferredDate: current,
        }),
      );
    }
    setViewMode(value);
  }, [currentSubEvent, data, useNewLiveTabs]);

  const handleSelectDate = React.useCallback((value: string | null) => {
    shouldSyncUrlRef.current = true;
    setSelectedDate(value);
  }, []);

  if (loading || !data) {
    return <EventDetailSkeleton />;
  }

  const resolvedSubEvent = currentSubEvent ?? data.selectedSubEvent;
  const subEventViews = data.subEvents.map((subEvent) => {
    const detail = data.subEventDetails.find((item) => item.code === subEvent.code);
    return {
      ...subEvent,
      champion: detail?.champion ?? subEvent.champion,
      bracket: detail?.bracket ?? [],
      roundRobinView: detail?.roundRobinView ?? null,
      teamKnockoutView: detail?.teamKnockoutView ?? null,
      presentationMode: detail?.presentationMode ?? data.presentationMode,
    };
  });
  const currentDetail = subEventViews.find((detail) => detail.code === resolvedSubEvent);
  const currentBracket = currentDetail?.bracket ?? [];
  const currentChampion = currentDetail?.champion ?? null;
  const currentRoundRobinView = currentDetail?.roundRobinView ?? data.roundRobinView ?? null;
  const currentTeamKnockoutView = currentDetail?.teamKnockoutView ?? data.teamKnockoutView ?? null;
  const currentPresentationMode = currentDetail?.presentationMode ?? data.presentationMode;
  const currentSubEventMeta = subEventViews.find((subEvent) => subEvent.code === resolvedSubEvent);
  const isXT = currentSubEventMeta ? isXTSubEvent(currentSubEventMeta.code, currentSubEventMeta.nameZh || "") : false;
  const showChampionsTab = currentSubEventMeta ? !currentSubEventMeta.disabled && supportsChampionRosterTab(currentSubEventMeta.code) : false;
  const hasKnockoutCompanion = currentBracket.length > 0 || (currentTeamKnockoutView?.rounds.length ?? 0) > 0;
  const shouldShowRoundRobin = currentRoundRobinView != null;
  const shouldShowTeamKnockout = currentTeamKnockoutView != null && (currentTeamKnockoutView.rounds.length > 0 || currentTeamKnockoutView.bronzeTie != null);
  const shouldShowBracket = currentBracket.length > 0;

  const isEventFinished = (() => {
    if (!data.event.endDate) return false;
    const now = new Date();
    const today =
      now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") + "-" + String(now.getDate()).padStart(2, "0");
    return data.event.endDate <= today;
  })();

  const eventReturnHref = buildEventDetailHref(params.eventId, {
    subEvent: resolvedSubEvent,
    view: viewMode,
    date: effectiveDate,
    from: from,
  });

  return (
    <main className="mx-auto min-h-screen max-w-lg bg-[#f8fafc]">
      <div className="sticky top-0 z-50 shadow-[0_4px_20px_rgba(0,0,0,0.08)]">
        <EventHeader
          data={data}
          subEvents={data.subEvents}
          currentSubEvent={resolvedSubEvent}
          onSelect={handleSelectSubEvent}
          onBack={handleBack}
        />
      </div>

      <div className="relative z-10 -mt-3 rounded-t-[1.5rem] bg-white px-5 pt-3 shadow-[0_-12px_40px_rgba(0,0,0,0.04)] ring-1 ring-black/[0.02] pb-4">
        {isEventFinished && (
          <ChampionBanner champion={currentChampion} subEvent={currentSubEventMeta} rounds={currentBracket} />
        )}
        <div className="mt-2">
          {useNewLiveTabs ? (
            <>
              <LiveViewTabs mode={viewMode} onChange={handleChangeViewMode} />
              {viewMode === "session" ? (
                <SessionScheduleView
                  sessions={data.sessionSchedule}
                  lifecycleStatus={data.event.lifecycleStatus}
                  eventTimeZone={data.event.timeZone}
                />
              ) : viewMode === "schedule" ? (
                <ScheduleByDateView
                  days={data.scheduleDays}
                  selectedSubEvent={resolvedSubEvent}
                  lifecycleStatus={data.event.lifecycleStatus}
                  eventTimeZone={data.event.timeZone}
                  selectedDate={selectedDate}
                  onSelectDate={handleSelectDate}
                  eventReturnHref={eventReturnHref}
                />
              ) : (
                <div className="space-y-6">
                  {shouldShowTeamKnockout ? (
                    <TeamKnockoutDrawView
                      view={currentTeamKnockoutView}
                      eventId={params.eventId}
                      subEventCode={resolvedSubEvent}
                      eventReturnHref={eventReturnHref}
                    />
                  ) : shouldShowBracket || currentPresentationMode === "knockout" ? (
                    <DrawView
                      rounds={currentBracket}
                      selectedSubEvent={resolvedSubEvent}
                      champion={currentChampion}
                      isXT={isXT}
                      teamKnockoutView={currentTeamKnockoutView}
                      eventReturnHref={eventReturnHref}
                      eventId={params.eventId}
                    />
                  ) : null}

                  {shouldShowRoundRobin ? (
                    <RoundRobinView
                      view={currentRoundRobinView}
                      defaultCollapsed={hasKnockoutCompanion}
                      eventReturnHref={eventReturnHref}
                      eventId={params.eventId}
                      subEventCode={resolvedSubEvent}
                    />
                  ) : null}
                </div>
              )}
            </>
          ) : currentPresentationMode === "staged_round_robin" && currentRoundRobinView ? (
            <RoundRobinView
              view={currentRoundRobinView}
              eventReturnHref={eventReturnHref}
              eventId={params.eventId}
              subEventCode={resolvedSubEvent}
            />
          ) : currentPresentationMode === "team_knockout_with_bronze" && currentTeamKnockoutView ? (
            <>
              <LegacyViewTabs mode={viewMode} onChange={handleChangeViewMode} showChampionsTab={showChampionsTab} />
              {viewMode === "schedule" ? (
                <TeamKnockoutScheduleView
                  view={currentTeamKnockoutView}
                  eventReturnHref={eventReturnHref}
                  eventId={params.eventId}
                  subEventCode={resolvedSubEvent}
                />
              ) : viewMode === "draw" ? (
                <TeamKnockoutDrawView
                  view={currentTeamKnockoutView}
                  eventId={params.eventId}
                  subEventCode={resolvedSubEvent}
                  eventReturnHref={eventReturnHref}
                />
              ) : (
                <ChampionsListView subEvent={currentSubEventMeta} />
              )}
            </>
          ) : (
            <>
              <LegacyViewTabs mode={viewMode} onChange={handleChangeViewMode} showChampionsTab={showChampionsTab} />
              {viewMode === "schedule" ? (
                <ScheduleView rounds={currentBracket} isXT={isXT} eventReturnHref={eventReturnHref} />
              ) : viewMode === "draw" ? (
                <DrawView
                  rounds={currentBracket}
                  selectedSubEvent={resolvedSubEvent}
                  champion={currentChampion}
                  isXT={isXT}
                  teamKnockoutView={currentTeamKnockoutView}
                  eventReturnHref={eventReturnHref}
                  eventId={params.eventId}
                />
              ) : (
                <ChampionsListView subEvent={currentSubEventMeta} />
              )}
            </>
          )}
        </div>
      </div>
    </main>
  );
}

export default function EventDetailPage() {
  return (
    <Suspense fallback={<EventDetailSkeleton />}>
      <EventDetailContent />
    </Suspense>
  );
}
