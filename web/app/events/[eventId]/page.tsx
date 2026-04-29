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
    startLocalTime: string | null;
    endLocalTime: string | null;
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

function formatBeijingTimeLabel(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

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
  startLocalTime: string | null,
  endLocalTime: string | null,
  eventTimeZone: string | null,
) {
  if (!eventTimeZone || !startLocalTime) return null;
  const startDate = zonedLocalDateTimeToDate(localDate, startLocalTime, eventTimeZone);
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
  if (!endLocalTime) return `北京时间 ${startLabel}`;

  const endDate = zonedLocalDateTimeToDate(localDate, endLocalTime, eventTimeZone);
  if (!endDate) return `北京时间 ${startLabel}`;
  return `北京时间 ${startLabel} - ${formatDateTime(endDate)}`;
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

function isMixedTeamSubEvent(code: string) {
  return code === "WT" || code === "XT";
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
  if (normalized === "cancelled") {
    return { label: "已取消", className: "bg-slate-100 text-slate-500 ring-slate-200" };
  }
  if (normalized === "walkover") {
    return { label: "退赛", className: "bg-amber-50 text-amber-700 ring-amber-100" };
  }
  return { label: "未开始", className: "bg-blue-50 text-[#2d6cf6] ring-blue-100" };
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

function MatchListCard({ match, matchIndex, isXT }: { match: BracketMatch; matchIndex: number; isXT?: boolean }) {
  const [sideA, sideB] = [...match.sides].sort((left, right) => left.sideNo - right.sideNo);
  const sides = [sideA, sideB].filter(Boolean);

  return (
    <Link
      href={route(`/matches/${match.matchId}`)}
      className="block rounded-2xl bg-white px-4 py-3.5 ring-1 ring-slate-100 shadow-sm transition active:scale-[0.99]"
    >
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-[0.82rem] font-medium text-slate-400">已结束</span>
      </div>

      <div className="flex gap-3">
        <div className="flex-1 min-w-0 space-y-2.5">
          {sides.map((side, i) => {
            const score = match.matchScore?.split("-")[side.sideNo - 1] ?? "-";
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
                <span className={cn("font-numeric text-[1.5rem] font-black leading-none tabular-nums ml-1 shrink-0", side.isWinner ? "text-[#2d6cf6]" : "text-slate-300")}>
                  {score}
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
                session.startLocalTime,
                session.endLocalTime,
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
                  {session.startLocalTime || "待定"} - {session.endLocalTime || "待定"}
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
}: {
  match: EventScheduleMatch;
  showBeijingTime: boolean;
}) {
  const [sideA, sideB] = [...match.sides].sort((left, right) => left.sideNo - right.sideNo);
  const meta = scheduleStatusMeta(match.status);
  const scoreParts = match.matchScore?.split("-") ?? [];
  const sideRows = [sideA, sideB].filter(Boolean);
  const beijingTimeLabel = showBeijingTime ? formatBeijingTimeLabel(match.scheduledUtcAt) : null;

  return (
    <Link href={route(`/schedule-matches/${match.scheduleMatchId}`)} className="block rounded-[1.2rem] bg-white px-3.5 py-3 ring-1 ring-[#e8edf8] shadow-sm transition active:scale-[0.99]">
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
        {match.rawScheduleStatus ? (
          <span className="shrink-0 text-[0.72rem] font-bold text-slate-300">{match.rawScheduleStatus}</span>
        ) : null}
      </div>

      <div className="mt-3 space-y-2.5">
        {sideRows.map((side) => {
          const score = scoreParts[side.sideNo - 1] ?? null;
          const label = scheduleSideLabel(side);
          return (
            <div key={side.sideNo} className="flex items-center gap-2">
              <Flag code={side.teamCode || side.players[0]?.countryCode || null} className="shrink-0 scale-[1.18] origin-left" />
              <div className="min-w-0 flex-1">
                <p className={cn("truncate text-[1rem] font-black leading-tight", side.isWinner ? "text-slate-950" : "text-slate-700")}>
                  {label}
                </p>
                {side.seed ? <p className="mt-0.5 text-[0.7rem] font-bold text-slate-400">Seed {side.seed}</p> : null}
              </div>
              {score ? (
                <span className={cn("font-numeric text-[1.35rem] font-black tabular-nums", side.isWinner ? "text-[#2d6cf6]" : "text-slate-300")}>
                  {score}
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
}: {
  days: EventDetail["scheduleDays"];
  selectedSubEvent: string;
  lifecycleStatus: string | null;
}) {
  const filteredDays = days
    .map((day) => ({
      ...day,
      matches: day.matches.filter((match) => match.subEventTypeCode === selectedSubEvent),
    }))
    .filter((day) => day.matches.length > 0);

  const [selectedDate, setSelectedDate] = React.useState<string | null>(filteredDays[0]?.localDate ?? null);

  React.useEffect(() => {
    if (filteredDays.length === 0) {
      setSelectedDate(null);
      return;
    }

    if (!selectedDate || !filteredDays.some((day) => day.localDate === selectedDate)) {
      setSelectedDate(filteredDays[0].localDate);
    }
  }, [filteredDays, selectedDate]);

  if (filteredDays.length === 0) {
    return (
      <div className="pt-5">
        <div className="rounded-[1.7rem] bg-white/82 p-8 text-center text-slate-500 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          这项逐场赛程还没发布
        </div>
      </div>
    );
  }

  const activeDay = filteredDays.find((day) => day.localDate === selectedDate) ?? filteredDays[0];
  const showBeijingTime = lifecycleStatus === "in_progress";

  return (
    <div className="pb-10 pt-4">
      <div className="space-y-4">
        <div className="sticky top-0 z-10 -mx-2 overflow-x-auto px-2 pb-2 pt-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <div className="flex min-w-max gap-2">
            {filteredDays.map((day) => {
              const isActive = day.localDate === activeDay.localDate;
              return (
                <button
                  key={day.localDate}
                  type="button"
                  onClick={() => setSelectedDate(day.localDate)}
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
              <ScheduleMatchCard key={match.scheduleMatchId} match={match} showBeijingTime={showBeijingTime} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function ScheduleView({ rounds, isXT }: { rounds: EventDetail["bracket"]; isXT?: boolean }) {
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
                      <MatchListCard key={match.matchId} match={match} matchIndex={index + 1} isXT={isXT} />
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

function TeamTieSummaryCard({ tie, tieIndex }: { tie: TeamTie; tieIndex?: number }) {
  const winnerA = tie.winnerCode === tie.teamA.code;
  const winnerB = tie.winnerCode === tie.teamB.code;
  return (
    <div className="rounded-[1.35rem] bg-white px-4 py-3.5 ring-1 ring-[#e8edf8]">
      <div className="flex items-center justify-between gap-2">
        <span className="shrink-0 text-[0.85rem] font-bold text-slate-500">
          {tieIndex !== undefined ? `第 ${tieIndex} 场` : "已结束"}
        </span>
        <div className="flex items-center gap-1.5 min-w-0">
          <Flag code={tie.teamA.code} className="shrink-0 scale-[1.05]" />
          <span className={cn("text-[0.95rem] font-black leading-none", winnerA ? "text-slate-950" : "text-slate-500")}>
            {tie.teamA.code}
          </span>
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
          <span className={cn("ml-0.5 text-[0.95rem] font-black leading-none", winnerB ? "text-slate-950" : "text-slate-500")}>
            {tie.teamB.code}
          </span>
          <Flag code={tie.teamB.code} className="shrink-0 scale-[1.05]" />
        </div>
      </div>
      <div className="mt-2 divide-y divide-slate-100">
        {tie.rubbers.map((rubber, index) => (
          <Link
            key={rubber.matchId}
            href={route(`/matches/${rubber.matchId}`)}
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

function TeamKnockoutScheduleView({ view }: { view: EventTeamKnockoutView }) {
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
                    <TeamTieSummaryCard key={tie.tieId} tie={tie} tieIndex={index + 1} />
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
}: {
  match: BracketMatch;
  isChampionPath: boolean;
  isXT?: boolean;
  matchNumber?: number;
}) {
  const [sideA, sideB] = [...match.sides].sort((a, b) => a.sideNo - b.sideNo);
  const sides = [sideA, sideB].filter(Boolean);

  return (
    <div className="relative">
      {matchNumber !== undefined && (
        <span className="absolute right-full top-1/2 mr-1 w-3.5 -translate-y-1/2 text-right text-[0.6rem] font-bold text-[#9bb3e0]">
          {matchNumber}
        </span>
      )}
      <Link
        href={route(`/matches/${match.matchId}`)}
        className={cn(
          "block rounded-[0.6rem] border bg-white px-1.5 py-1 shadow-sm transition active:scale-[0.99]",
          isChampionPath ? "border-[#3a74f2] shadow-[0_2px_8px_rgba(58,116,242,0.14)]" : "border-[#dce7f5]",
        )}
      >
        <div className="space-y-1">
          {sides.map((side) => {
            const score = match.matchScore?.split("-")[side.sideNo - 1] ?? "-";
            const flag = dedupeCountries(side.players)[0] ?? null;
            return (
              <div key={side.sideNo} className="flex items-center gap-1">
                <Flag code={flag} className="shrink-0 scale-[0.85] origin-left" />
                <p className={cn("min-w-0 flex-1 truncate text-[0.7rem] font-bold leading-tight", side.isWinner ? "text-slate-900" : "text-slate-400")}>
                  {sideName(side, isXT)}
                </p>
                <span className={cn("font-numeric shrink-0 text-[1rem] font-black leading-none tabular-nums", side.isWinner ? "text-[#2d6cf6]" : "text-slate-300")}>
                  {score}
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
}: {
  rounds: EventDetail["bracket"];
  selectedSubEvent: string;
  champion: EventChampion | null;
  isXT?: boolean;
  teamKnockoutView?: EventTeamKnockoutView | null;
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

  return (
    <div className="pb-10 pt-5">
      {!teamKnockoutView && bracketPodium && (
        <section className="mb-6">
          <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">领奖台</h2>
          <Podium podium={bracketPodium} />
        </section>
      )}

      {teamKnockoutView && (
        <section className="mb-6 space-y-6">
          <div>
            <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">领奖台</h2>
            <Podium podium={teamPodiumDisplay(teamKnockoutView.podium)} />
          </div>

          {teamKnockoutView.finalTie && (
            <section>
              <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">决赛</h2>
              <TeamTieCard tie={teamKnockoutView.finalTie} title="冠军战" />
            </section>
          )}

          {teamKnockoutView.bronzeTie && (
            <section>
              <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">铜牌赛</h2>
              <TeamTieCard tie={teamKnockoutView.bronzeTie} title="铜牌战" />
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

function TeamTieNodeCard({ tie, title }: { tie: TeamTie; title?: string }) {
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
            <Flag code={item.team.code} className="shrink-0 scale-[1.0]" />
            <span className={cn("flex-1 text-[0.88rem] font-black leading-none", item.isWinner ? "text-slate-950" : "text-slate-500")}>
              {item.team.code}
            </span>
            <span className={cn("font-numeric shrink-0 text-[1.12rem] font-black leading-none tabular-nums", item.isWinner ? "text-[#2d6cf6]" : "text-slate-300")}>
              {item.score}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DrawTeamTieCard({ tie }: { tie: TeamTie }) {
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
            <Flag code={item.team.code} className="shrink-0 scale-[0.85] origin-left" />
            <span className={cn("min-w-0 flex-1 truncate text-[0.7rem] font-bold leading-tight", item.isWinner ? "text-slate-900" : "text-slate-400")}>
              {item.team.code}
            </span>
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

function TeamKnockoutDrawView({ view }: { view: EventTeamKnockoutView }) {
  const mainRounds = React.useMemo(
    () => {
      const filtered = view.rounds
        .filter((round) => round.code !== "Bronze" && round.ties.length > 0)
        .slice()
        .sort((a, b) => a.order - b.order);
      return orderTeamRoundsByFeeders(filtered);
    },
    [view.rounds],
  );
  const bronzeTie = view.bronzeTie ?? view.rounds.find((round) => round.code === "Bronze")?.ties[0] ?? null;

  if (mainRounds.length === 0 && !bronzeTie) {
    return (
      <div className="pt-5">
        <div className="rounded-[1.7rem] bg-white/82 p-8 text-center text-slate-500 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          这项赛事图还没收录
        </div>
      </div>
    );
  }

  const firstRoundCount = mainRounds[0]?.ties.length ?? 1;
  const slotH0 = Math.max(TEAM_DRAW_CARD_H + 12, 72);
  const totalH = firstRoundCount * slotH0;

  const getCardInfo = (rIdx: number, mIdx: number) => {
    const count = mainRounds[rIdx]?.ties.length ?? 1;
    const slotH = totalH / count;
    return {
      top: mIdx * slotH + (slotH - TEAM_DRAW_CARD_H) / 2,
      centerY: mIdx * slotH + slotH / 2,
      left: rIdx * (TEAM_DRAW_CARD_W + TEAM_DRAW_COL_GAP),
    };
  };

  const totalW = mainRounds.length * (TEAM_DRAW_CARD_W + TEAM_DRAW_COL_GAP);

  return (
    <div className="pb-10 pt-5">
      <section className="mb-6">
        <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">领奖台</h2>
        <Podium podium={teamPodiumDisplay(view.podium)} />
      </section>

      {mainRounds.length > 0 && (
        <div className="overflow-x-auto pb-2">
          <div className="mb-3 flex" style={{ minWidth: totalW }}>
            {mainRounds.map((round) => (
              <div
                key={round.code}
                className="shrink-0 text-center"
                style={{ width: TEAM_DRAW_CARD_W, marginRight: TEAM_DRAW_COL_GAP }}
              >
                <p className="text-[0.78rem] font-black text-slate-900">{round.label}</p>
                <p className="mt-0.5 text-[0.65rem] font-medium text-slate-400">{round.ties.length} 场</p>
              </div>
            ))}
          </div>

          <div className="relative" style={{ height: totalH, minWidth: totalW }}>
            <svg
              className="pointer-events-none absolute inset-0 overflow-visible"
              style={{ width: totalW, height: totalH }}
            >
              {mainRounds.map((_, rIdx) => {
                if (rIdx >= mainRounds.length - 1) return null;
                const currentRound = mainRounds[rIdx];
                const nextRound = mainRounds[rIdx + 1];
                return nextRound.ties.map((nt, nMIdx) => {
                  const f1Idx = nMIdx * 2;
                  const f2Idx = nMIdx * 2 + 1;
                  if (f2Idx >= currentRound.ties.length) return null;
                  const f1Tie = currentRound.ties[f1Idx];
                  const f2Tie = currentRound.ties[f2Idx];
                  const teams = new Set([nt.teamA.code, nt.teamB.code]);
                  if (
                    !f1Tie.winnerCode ||
                    !f2Tie.winnerCode ||
                    !teams.has(f1Tie.winnerCode) ||
                    !teams.has(f2Tie.winnerCode)
                  ) {
                    return null;
                  }
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

            {mainRounds.map((round, rIdx) =>
              round.ties.map((tie, mIdx) => {
                const { top, left } = getCardInfo(rIdx, mIdx);
                return (
                  <div
                    key={tie.tieId}
                    className="absolute"
                    style={{ top, left, width: TEAM_DRAW_CARD_W }}
                  >
                    <DrawTeamTieCard tie={tie} />
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
          <TeamTieNodeCard tie={bronzeTie} />
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

function TeamTieCard({ tie, title }: { tie: TeamTie; title?: string }) {
  const titleText = title || tie.roundZh || tie.round || "循环赛";
  const winnerA = tie.winnerCode === tie.teamA.code;
  const winnerB = tie.winnerCode === tie.teamB.code;
  return (
    <div className="rounded-[1.35rem] bg-white px-4 py-3.5 ring-1 ring-[#e8edf8]">
      <div className="flex items-center justify-between gap-2">
        <span className="shrink-0 text-[0.85rem] font-bold text-slate-500">{titleText}</span>
        <div className="flex items-center gap-1.5 min-w-0">
          <Flag code={tie.teamA.code} className="shrink-0 scale-[1.05]" />
          <span className={cn("text-[0.95rem] font-black leading-none", winnerA ? "text-slate-950" : "text-slate-500")}>
            {tie.teamA.code}
          </span>
          <span className={cn("font-numeric ml-0.5 text-[1.25rem] font-black leading-none tabular-nums", winnerA ? "text-[#2d6cf6]" : "text-slate-400")}>
            {tie.scoreA}
          </span>
          <span className="text-[0.95rem] font-black leading-none text-slate-300">-</span>
          <span className={cn("font-numeric text-[1.25rem] font-black leading-none tabular-nums", winnerB ? "text-[#2d6cf6]" : "text-slate-400")}>
            {tie.scoreB}
          </span>
          <span className={cn("ml-0.5 text-[0.95rem] font-black leading-none", winnerB ? "text-slate-950" : "text-slate-500")}>
            {tie.teamB.code}
          </span>
          <Flag code={tie.teamB.code} className="shrink-0 scale-[1.05]" />
        </div>
      </div>
      <div className="mt-2 divide-y divide-slate-100">
        {tie.rubbers.map((rubber, index) => (
          <Link
            key={rubber.matchId}
            href={route(`/matches/${rubber.matchId}`)}
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

function GroupStandingsTable({ standings }: { standings: StageStanding[] }) {
  if (standings.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-[1.2rem] bg-white ring-1 ring-[#e8edf8]">
      <div className="grid grid-cols-[2.5rem_minmax(0,1fr)_2.2rem_2.2rem_2.2rem_3rem_3.5rem] gap-2 border-b border-slate-100 px-3 py-2 text-[0.68rem] font-bold uppercase tracking-[0.06em] text-slate-400">
        <span>排名</span>
        <span>队伍</span>
        <span className="text-center">赛</span>
        <span className="text-center">胜</span>
        <span className="text-center">负</span>
        <span className="text-center">积分</span>
        <span className="text-center">局分</span>
      </div>
      <div>
        {standings.map((standing) => (
          <div
            key={standing.teamCode}
            className="grid grid-cols-[2.5rem_minmax(0,1fr)_2.2rem_2.2rem_2.2rem_3rem_3.5rem] items-center gap-2 px-3 py-3 text-[0.82rem] font-bold text-slate-700 not-last:border-b not-last:border-slate-100"
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
            <span className="text-center">
              {standing.scoreFor ?? 0}-{standing.scoreAgainst ?? 0}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RoundRobinView({ view, defaultCollapsed = false }: { view: EventRoundRobinView; defaultCollapsed?: boolean }) {
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
                              <GroupStandingsTable standings={group.standings ?? []} />
                              {group.ties.map((tie, index) => (
                                <TeamTieCard key={tie.tieId} tie={tie} title={`第${index + 1}场`} />
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
                      <TeamTieCard key={tie.tieId} tie={tie} title={`第${index + 1}场`} />
                    ))}
                  </div>
                )
              ) : null}
            </section>
          );
        })}
      </div>

      {view.finalStandings.length > 0 ? (
        <div className="mt-6">
          <FinalStandingsView standings={view.finalStandings} />
        </div>
      ) : null}
    </div>
  );
}

function ChampionsListView({ subEvents }: { subEvents: EventSubEventView[] }) {
  const subEventsWithChampions = subEvents.filter((se) => !se.disabled && isMixedTeamSubEvent(se.code));

  if (subEventsWithChampions.length === 0) {
    return (
      <div className="pt-5">
        <div className="rounded-[1.7rem] bg-white/82 p-8 text-center text-slate-500 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          本赛事无{getSubEventShortName("WT") || "WT"}/{getSubEventShortName("XD") || "XD"}项目
        </div>
      </div>
    );
  }

  return (
    <div className="pb-10 pt-4">
      <div className="space-y-6">
        {subEventsWithChampions.map((se) => {
          const champion = se.champion;
          const championNames = normalizeChampionNames(champion);
          const countries = champion
            ? dedupeCountries(champion.players).length > 0
              ? dedupeCountries(champion.players)
              : champion.championCountryCode
                ? [champion.championCountryCode]
                : []
            : [];

          return (
            <section key={se.code}>
              <h2 className="mb-3 text-[1.2rem] font-black text-slate-900">{subEventLabel(se)}</h2>
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
          );
        })}
      </div>
    </div>
  );
}

function EventDetailContent() {
  const params = useParams<{ eventId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlSubEvent = searchParams.get("sub_event");
  const [data, setData] = React.useState<EventDetail | null>(null);
  const [selectedSubEvent, setSelectedSubEvent] = React.useState<string | null>(urlSubEvent);
  const [viewMode, setViewMode] = React.useState<ViewMode>("session");
  const [loading, setLoading] = React.useState(true);
  const handleBack = React.useCallback(() => {
    if (window.history.length > 1) {
      router.back();
      return;
    }
    router.push("/events");
  }, [router]);

  React.useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const query = urlSubEvent ? `?sub_event=${encodeURIComponent(urlSubEvent)}` : "";
        const res = await fetch(`/api/v1/events/${params.eventId}${query}`);
        const json = (await res.json()) as EventDetailResponse;
        if (json.code === 0) {
          setData(json.data);
          setSelectedSubEvent((current) => current ?? urlSubEvent ?? json.data.selectedSubEvent);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }

    if (params.eventId) load();
  }, [params.eventId, urlSubEvent]);

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

  if (loading || !data) {
    return (
      <main className="mx-auto min-h-screen max-w-lg overflow-hidden pb-20">
        <div className="flex justify-center py-20 text-body text-text-tertiary">加载中...</div>
      </main>
    );
  }

  const currentSubEvent = selectedSubEvent ?? data.selectedSubEvent;
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
  const currentDetail = subEventViews.find((detail) => detail.code === currentSubEvent);
  const currentBracket = currentDetail?.bracket ?? [];
  const currentChampion = currentDetail?.champion ?? null;
  const currentRoundRobinView = currentDetail?.roundRobinView ?? data.roundRobinView ?? null;
  const currentTeamKnockoutView = currentDetail?.teamKnockoutView ?? data.teamKnockoutView ?? null;
  const currentPresentationMode = currentDetail?.presentationMode ?? data.presentationMode;
  const currentSubEventMeta = subEventViews.find((subEvent) => subEvent.code === currentSubEvent);
  const isXT = currentSubEventMeta ? isXTSubEvent(currentSubEventMeta.code, currentSubEventMeta.nameZh || "") : false;
  const showChampionsTab = currentSubEventMeta ? !currentSubEventMeta.disabled && isMixedTeamSubEvent(currentSubEventMeta.code) : false;
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

  return (
    <main className="mx-auto min-h-screen max-w-lg bg-[#f8fafc]">
      <div className="sticky top-0 z-50 shadow-[0_4px_20px_rgba(0,0,0,0.08)]">
        <EventHeader
          data={data}
          subEvents={data.subEvents}
          currentSubEvent={currentSubEvent}
          onSelect={setSelectedSubEvent}
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
              <LiveViewTabs mode={viewMode} onChange={setViewMode} />
              {viewMode === "session" ? (
                <SessionScheduleView
                  sessions={data.sessionSchedule}
                  lifecycleStatus={data.event.lifecycleStatus}
                  eventTimeZone={data.event.timeZone}
                />
              ) : viewMode === "schedule" ? (
                <ScheduleByDateView
                  days={data.scheduleDays}
                  selectedSubEvent={currentSubEvent}
                  lifecycleStatus={data.event.lifecycleStatus}
                />
              ) : (
                <div className="space-y-6">
                  {shouldShowRoundRobin ? (
                    <RoundRobinView view={currentRoundRobinView} defaultCollapsed={hasKnockoutCompanion} />
                  ) : null}

                  {shouldShowTeamKnockout ? (
                    <TeamKnockoutDrawView view={currentTeamKnockoutView} />
                  ) : shouldShowBracket || currentPresentationMode === "knockout" ? (
                    <DrawView
                      rounds={currentBracket}
                      selectedSubEvent={currentSubEvent}
                      champion={currentChampion}
                      isXT={isXT}
                      teamKnockoutView={currentTeamKnockoutView}
                    />
                  ) : null}
                </div>
              )}
            </>
          ) : currentPresentationMode === "staged_round_robin" && currentRoundRobinView ? (
            <RoundRobinView view={currentRoundRobinView} />
          ) : currentPresentationMode === "team_knockout_with_bronze" && currentTeamKnockoutView ? (
            <>
              <LegacyViewTabs mode={viewMode} onChange={setViewMode} showChampionsTab={showChampionsTab} />
              {viewMode === "schedule" ? (
                <TeamKnockoutScheduleView view={currentTeamKnockoutView} />
              ) : viewMode === "draw" ? (
                <TeamKnockoutDrawView view={currentTeamKnockoutView} />
              ) : (
                <ChampionsListView subEvents={subEventViews} />
              )}
            </>
          ) : (
            <>
              <LegacyViewTabs mode={viewMode} onChange={setViewMode} showChampionsTab={showChampionsTab} />
              {viewMode === "schedule" ? (
                <ScheduleView rounds={currentBracket} isXT={isXT} />
              ) : viewMode === "draw" ? (
                <DrawView
                  rounds={currentBracket}
                  selectedSubEvent={currentSubEvent}
                  champion={currentChampion}
                  isXT={isXT}
                  teamKnockoutView={currentTeamKnockoutView}
                />
              ) : (
                <ChampionsListView subEvents={subEventViews} />
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
    <Suspense fallback={<div className="min-h-screen bg-page-background py-20 text-center text-text-tertiary">页面加载中...</div>}>
      <EventDetailContent />
    </Suspense>
  );
}
