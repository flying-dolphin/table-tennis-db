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
  Search,
  Trophy,
  ChevronLeft,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  PlayCircle,
} from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import "@/public/images/flags_local.css";

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
  };
  subEvents: Array<{
    code: string;
    nameZh: string | null;
    disabled: boolean;
    hasDraw: boolean;
    drawMatches: number;
    importedMatches: number;
  }>;
  selectedSubEvent: string;
  subEventDetails: Array<{
    code: string;
    champion: EventChampion | null;
    bracket: Array<{ code: string; label: string; order: number; matches: BracketMatch[] }>;
    roundRobinView: EventRoundRobinView | null;
    presentationMode: "knockout" | "staged_round_robin";
  }>;
  champion: EventChampion | null;
  bracket: Array<{ code: string; label: string; order: number; matches: BracketMatch[] }>;
  roundRobinView: EventRoundRobinView | null;
  presentationMode: "knockout" | "staged_round_robin";
};

type EventDetailResponse = {
  code: number;
  data: EventDetail;
};

type ViewMode = "schedule" | "draw";

function displayName(name: string, nameZh: string | null) {
  return nameZh?.trim() || name;
}

function displayDateRange(startDate: string | null, endDate: string | null) {
  if (!startDate && !endDate) return "时间待补";
  if (startDate && startDate === endDate) return startDate;
  return [startDate, endDate].filter(Boolean).join(" 至 ");
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

function subEventLabel(subEvent: { code: string; nameZh: string | null } | undefined) {
  return subEvent?.nameZh || subEvent?.code || "项目待补";
}

function isDoublesSubEvent(code: string, label: string) {
  const text = `${code} ${label}`.toUpperCase();
  return code === "WD" || code === "MD" || code === "XD" || code === "XT" || text.includes("双打") || text.includes("MIXED");
}

function isXTSubEvent(code: string, label: string) {
  return code === "XT";
}

function isTeamSubEvent(code: string, label: string) {
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

function Flag({ code, className }: { code: string | null; className?: string }) {
  if (!code) return <span className={cn("inline-block h-3.5 w-5 rounded-sm bg-slate-200", className)} />;

  return <span className={cn("fg rounded-[2px] shadow-sm", `fg-${code}`, className)} aria-hidden="true" />;
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
              {subEvent.nameZh || subEvent.code}
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
    <div className="relative pt-1">
      <div className="relative overflow-hidden rounded-[1.5rem] bg-[linear-gradient(90deg,#dfeafe_0%,#d9e7ff_55%,#d5e1ff_100%)] pl-[104px] pr-3 shadow-[0_14px_28px_rgba(144,166,201,0.16)] py-1 sm:pl-[120px]">
        <div className="absolute inset-y-0 left-0 w-32 bg-[radial-gradient(circle_at_18%_50%,rgba(255,255,255,0.95),transparent_60%)]" />
        <div className="absolute -left-6 bottom-0 h-20 w-20 rounded-full bg-[radial-gradient(circle,rgba(255,255,255,0.85),transparent_72%)]" />
        <div className="absolute right-0 top-0 h-full w-36 bg-[radial-gradient(circle_at_85%_20%,rgba(255,255,255,0.38),transparent_58%)]" />
        <div className="relative flex min-h-[64px] sm:min-h-[72px] items-center gap-3">
          {champion?.players[0] && !isDoubles && !isTeam && !isXT ? (
            <PlayerAvatar
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
        className="pointer-events-none absolute bottom-0 left-2 z-10 h-auto w-[100px] drop-shadow-[0_6px_10px_rgba(144,166,201,0.25)] sm:left-3 sm:w-[116px]"
        priority
      />
    </div>
  );
}

function ViewTabs({ mode, onChange }: { mode: ViewMode; onChange: (mode: ViewMode) => void }) {
  return (
    <div className="flex justify-between border-b border-slate-200/80 px-8">
      <button
        type="button"
        onClick={() => onChange("schedule")}
        className={cn(
          "relative flex h-14 items-center justify-center gap-2 px-4 text-[1.06rem] font-bold transition-colors",
          mode === "schedule" ? "text-[#2d6cf6]" : "text-slate-400 hover:text-slate-700",
        )}
      >
        <List size={16} />
        赛程列表
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
          "relative flex h-14 items-center justify-center gap-2 px-4 text-[1.06rem] font-bold transition-colors",
          mode === "draw" ? "text-[#2d6cf6]" : "text-slate-400 hover:text-slate-700",
        )}
      >
        <FolderTree size={20} />
        完整赛事图
        <span
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute inset-x-4 bottom-0 h-[3px] rounded-full transition-all",
            mode === "draw" ? "bg-[#2d6cf6]" : "bg-transparent",
          )}
        />
      </button>
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

function DrawMatchCard({ match, isChampionPath, isXT }: { match: BracketMatch; isChampionPath: boolean; isXT?: boolean }) {
  const [sideA, sideB] = [...match.sides].sort((left, right) => left.sideNo - right.sideNo);
  const sides = [sideA, sideB].filter(Boolean);

  return (
    <Link
      href={route(`/matches/${match.matchId}`)}
      className={cn(
        "relative block w-[176px] rounded-[1.1rem] border bg-white px-3 py-3 shadow-[0_10px_22px_rgba(180,189,203,0.14)] transition hover:-translate-y-0.5",
        isChampionPath ? "border-[#3f79f3] shadow-[0_10px_26px_rgba(63,121,243,0.18)]" : "border-[#d8e1ef]",
      )}
    >
      {isChampionPath ? <span className="absolute -right-2 top-9 h-5 w-5 rounded-full bg-[#3f79f3] ring-4 ring-white" /> : null}
      <div className="space-y-2.5">
        {sides.map((side) => (
          <div key={side.sideNo} className="grid grid-cols-[16px_1fr_auto] items-center gap-2">
            <Flag code={dedupeCountries(side.players)[0] ?? null} className="scale-[1.05] origin-left" />
            <p className={cn("truncate text-[0.95rem] font-bold", side.isWinner ? "text-slate-950" : "text-slate-600")}>
              {sideName(side, isXT)}
            </p>
            <span className={cn("font-numeric text-[1.9rem] font-black leading-none tabular-nums", side.isWinner ? "text-[#2d6cf6]" : "text-slate-300")}>
              {match.matchScore?.split("-")[side.sideNo - 1] ?? "-"}
            </span>
          </div>
        ))}
      </div>
    </Link>
  );
}

function DrawView({
  rounds,
  selectedSubEvent,
  champion,
  isXT,
}: {
  rounds: EventDetail["bracket"];
  selectedSubEvent: string;
  champion: EventChampion | null;
  isXT?: boolean;
}) {
  const [search, setSearch] = React.useState("");
  const highlightedNames = normalizeChampionNames(champion).map((name) => truncateChineseName(name, 4));

  const filteredRounds = React.useMemo(() => {
    if (!search.trim()) return rounds;
    const keyword = search.trim().toLowerCase();
    return rounds
      .map((round) => ({
        ...round,
        matches: round.matches.filter((match) =>
          match.sides.some((side) => side.players.some((player) => displayPlayerName(player).toLowerCase().includes(keyword))),
        ),
      }))
      .filter((round) => round.matches.length > 0);
  }, [rounds, search]);

  if (rounds.length === 0) {
    return (
      <div className="pt-5">
        <div className="rounded-[1.7rem] bg-white/82 p-8 text-center text-slate-500 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
          这项签表还没收录
        </div>
      </div>
    );
  }

  return (
    <div className="pb-10 pt-5">
      <div className="rounded-[1.8rem] bg-white/86 p-4 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <label className="flex min-h-14 flex-1 items-center gap-3 rounded-[1.15rem] bg-[#f3f6fb] px-4 text-slate-500">
            <Search size={21} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索选手（如：孙颖莎）"
              className="w-full bg-transparent text-[1.05rem] outline-none placeholder:text-slate-400"
            />
          </label>
          <div className="inline-flex min-h-14 items-center gap-2 rounded-[1.15rem] bg-[#f3f6ff] px-4 text-[1.02rem] font-bold text-[#3873f5]">
            <Trophy size={18} />
            当前项目 {selectedSubEvent}
          </div>
        </div>

        <div className="mt-4 rounded-[1.2rem] bg-[#f7f9fd] px-3 py-3">
          <div className="grid min-w-[720px] grid-cols-[repeat(var(--round-count),minmax(140px,1fr))] gap-4" style={{ ["--round-count" as string]: String(filteredRounds.length) }}>
            {filteredRounds.map((round) => (
              <div key={round.code} className="text-center">
                <p className="text-[1.1rem] font-black text-slate-900">{round.label}</p>
                <p className="mt-1 text-sm text-slate-400">{round.matches.length} 场</p>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-5 overflow-x-auto pb-2">
          <div className="flex min-w-max items-start gap-8 pr-4">
            {filteredRounds.map((round, roundIndex) => (
              <div key={round.code} className="relative flex w-[176px] shrink-0 flex-col justify-center" style={{ minHeight: `${Math.max(round.matches.length, 1) * 132}px` }}>
                <div className="space-y-5">
                  {round.matches.map((match) => {
                    const isChampionPath = highlightedNames.length > 0 && match.sides.some((side) => side.isWinner && highlightedNames.every((name) => sideName(side, isXT).includes(name)));
                    return <DrawMatchCard key={match.matchId} match={match} isChampionPath={isChampionPath} isXT={isXT} />;
                  })}
                </div>
                {roundIndex < filteredRounds.length - 1 ? (
                  <div className="pointer-events-none absolute -right-5 top-1/2 h-px w-5 bg-[#8cb0ff]" />
                ) : null}
              </div>
            ))}

            {highlightedNames.length > 0 ? (
              <div className="flex shrink-0 flex-col items-center justify-center self-center rounded-[1.3rem] border border-[#efcf8a] bg-[linear-gradient(180deg,#fff9e8_0%,#fffdf8_100%)] px-5 py-6 shadow-[0_12px_28px_rgba(218,187,112,0.16)]">
                <Crown size={24} className="text-[#d6a129]" />
                <div className="mt-3 flex items-center gap-2">
                  <Flag code={champion?.championCountryCode ?? dedupeCountries(champion?.players ?? [])[0] ?? null} className="scale-[1.25]" />
                  <p className="text-[1.35rem] font-black text-slate-950">{highlightedNames.join(" / ")}</p>
                </div>
                <p className="mt-2 text-[1rem] font-medium text-slate-500">冠军</p>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function PodiumCard({
  title,
  standing,
}: {
  title: string;
  standing: StageStanding | null;
}) {
  return (
    <div className="rounded-[1.4rem] bg-white p-4 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
      <p className="text-[0.92rem] font-bold text-slate-500">{title}</p>
      <div className="mt-3 flex items-center gap-3">
        <Flag code={standing?.teamCode ?? null} className="scale-[1.35]" />
        <p className="text-[1.2rem] font-black text-slate-950">{standing?.teamNameZh || standing?.teamName || "待补"}</p>
      </div>
    </div>
  );
}

function TeamTieCard({ tie }: { tie: TeamTie }) {
  return (
    <div className="rounded-[1.4rem] bg-white p-4 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
      <div className="flex items-center justify-between gap-3 text-[0.92rem] font-bold text-slate-500">
        <span>{tie.roundZh || tie.round || "循环赛"}</span>
        <span>团体赛</span>
      </div>
      <div className="mt-4 grid grid-cols-[1fr_auto] gap-3">
        <div className="space-y-3">
          {[
            { team: tie.teamA, score: tie.scoreA, winner: tie.winnerCode === tie.teamA.code },
            { team: tie.teamB, score: tie.scoreB, winner: tie.winnerCode === tie.teamB.code },
          ].map((item) => (
            <div key={item.team.code} className="flex items-center gap-3 rounded-[1rem] bg-[#f6f8fd] px-3 py-3">
              <Flag code={item.team.code} className="scale-[1.35] origin-left shrink-0" />
              <p className={cn("text-[1.05rem] font-black", item.winner ? "text-slate-950" : "text-slate-600")}>
                {item.team.nameZh || item.team.name}
              </p>
            </div>
          ))}
        </div>
        <div className="flex min-w-[62px] flex-col items-end justify-center gap-4 font-numeric text-[2rem] font-black leading-none tabular-nums">
          <span className={tie.winnerCode === tie.teamA.code ? "text-[#2d6cf6]" : "text-slate-400"}>{tie.scoreA}</span>
          <span className={tie.winnerCode === tie.teamB.code ? "text-[#2d6cf6]" : "text-slate-400"}>{tie.scoreB}</span>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {tie.rubbers.map((rubber, index) => (
          <Link
            key={rubber.matchId}
            href={route(`/matches/${rubber.matchId}`)}
            className="rounded-full bg-[#eef4ff] px-3 py-1.5 text-[0.92rem] font-bold text-[#2d6cf6] transition hover:bg-[#dfeaff]"
          >
            第{index + 1}盘 {rubber.matchScore ?? "比分待补"}
          </Link>
        ))}
      </div>
    </div>
  );
}

function FinalStandingsView({ standings }: { standings: StageStanding[] }) {
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

function RoundRobinView({ view }: { view: EventRoundRobinView }) {
  return (
    <div className="pb-10 pt-5">
      <section>
        <h2 className="mb-3 text-[1.2rem] font-black text-slate-950">领奖台</h2>
        <div className="grid gap-3">
          <PodiumCard title="冠军" standing={view.podium.champion} />
          <PodiumCard title="亚军" standing={view.podium.runnerUp} />
          <PodiumCard title="季军" standing={view.podium.thirdPlace} />
        </div>
      </section>

      <div className="mt-6 space-y-6">
        {view.stages.map((stage) => (
          <section key={stage.code}>
            <div className="mb-3 flex items-center justify-between px-1">
              <h2 className="text-[1.3rem] font-black text-slate-950">{stage.nameZh || stage.name}</h2>
              <span className="text-[0.92rem] font-medium text-slate-500">
                {stage.format === "group_round_robin" ? "分组循环赛" : "循环赛"}
              </span>
            </div>
            {stage.groups ? (
              <div className="space-y-4">
                {stage.groups.map((group) => (
                  <div key={group.code} className="rounded-[1.6rem] bg-[#f7f9fd] p-4 ring-1 ring-[#e8eef9]">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <h3 className="text-[1.08rem] font-black text-slate-900">{group.nameZh || group.code}</h3>
                      <div className="flex flex-wrap justify-end gap-2 text-[0.88rem] font-bold text-slate-500">
                        {group.teams.map((team) => (
                          <span key={team} className="inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-1">
                            <Flag code={team} />
                            {team}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="space-y-3">
                      {group.ties.map((tie) => (
                        <TeamTieCard key={tie.tieId} tie={tie} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {(stage.ties ?? []).map((tie) => (
                  <TeamTieCard key={tie.tieId} tie={tie} />
                ))}
              </div>
            )}
          </section>
        ))}
      </div>

      <div className="mt-6">
        <FinalStandingsView standings={view.finalStandings} />
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
  const [viewMode, setViewMode] = React.useState<ViewMode>("schedule");
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

  if (loading || !data) {
    return (
      <main className="mx-auto min-h-screen max-w-lg overflow-hidden pb-20">
        <div className="flex justify-center py-20 text-body text-text-tertiary">加载中...</div>
      </main>
    );
  }

  const currentSubEvent = selectedSubEvent ?? data.selectedSubEvent;
  const currentDetail = data.subEventDetails.find((detail) => detail.code === currentSubEvent);
  const currentBracket = currentDetail?.bracket ?? [];
  const currentChampion = currentDetail?.champion ?? null;
  const currentRoundRobinView = currentDetail?.roundRobinView ?? data.roundRobinView ?? null;
  const currentPresentationMode = currentDetail?.presentationMode ?? data.presentationMode;
  const currentSubEventMeta = data.subEvents.find((subEvent) => subEvent.code === currentSubEvent);
  const isXT = currentSubEventMeta ? isXTSubEvent(currentSubEventMeta.code, currentSubEventMeta.nameZh || "") : false;

  return (
    <main className="mx-auto min-h-screen max-w-lg bg-[#f8fafc] pb-24">
      <EventHeader
        data={data}
        subEvents={data.subEvents}
        currentSubEvent={currentSubEvent}
        onSelect={setSelectedSubEvent}
        onBack={handleBack}
      />

      <div className="relative z-10 -mt-3 rounded-sm bg-white px-5 pt-3 shadow-[0_-12px_40px_rgba(0,0,0,0.04)] ring-1 ring-black/[0.02]">
        <ChampionBanner champion={currentChampion} subEvent={currentSubEventMeta} rounds={currentBracket} />
        <div className="mt-2">
          {currentPresentationMode === "staged_round_robin" && currentRoundRobinView ? (
            <RoundRobinView view={currentRoundRobinView} />
          ) : (
            <>
              <ViewTabs mode={viewMode} onChange={setViewMode} />
              {viewMode === "schedule" ? (
                <ScheduleView rounds={currentBracket} isXT={isXT} />
              ) : (
                <DrawView rounds={currentBracket} selectedSubEvent={currentSubEvent} champion={currentChampion} isXT={isXT} />
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
