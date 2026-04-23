"use client";

import React, { Suspense } from "react";
import Image from "next/image";
import Link from "next/link";
import type { Route } from "next";
import { useParams, useSearchParams } from "next/navigation";
import {
  Crown,
  List,
  FolderTree,
  Search,
  Spline,
  Trophy,
  ChevronLeft
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
  }>;
  champion: EventChampion | null;
  bracket: Array<{ code: string; label: string; order: number; matches: BracketMatch[] }>;
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

function sideName(side: BracketMatch["sides"][number]) {
  return side.players.map(displayPlayerName).join(" / ");
}

function sideCountry(side: BracketMatch["sides"][number]) {
  return dedupeCountries(side.players).join(" / ");
}

function subEventLabel(subEvent: { code: string; nameZh: string | null } | undefined) {
  return subEvent?.nameZh || subEvent?.code || "项目待补";
}

function isDoublesSubEvent(code: string, label: string) {
  const text = `${code} ${label}`.toUpperCase();
  return code === "WD" || code === "MD" || code === "XD" || text.includes("双打") || text.includes("MIXED");
}

function isTeamSubEvent(code: string, label: string) {
  const text = `${code} ${label}`.toUpperCase();
  return text.includes("TEAM") || text.includes("团体");
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
  return games.map((game) => `${game.player}-${game.opponent}`).join("、");
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
}: {
  data: EventDetail;
  subEvents: EventDetail["subEvents"];
  currentSubEvent: string;
  onSelect: (code: string) => void;
}) {
  return (
    <section className="relative overflow-hidden bg-[radial-gradient(circle_at_right,#d7e6ff_0%,rgba(215,230,255,0.18)_48%,transparent_72%)] px-4 pb-3 pt-4">
      <div className="relative z-10">
        <div className="flex items-center justify-between gap-3">
          <Link
            href="/events"
            className="grid h-9 w-9 place-items-center rounded-full text-slate-900 transition-colors hover:bg-black/5"
          >
            <ChevronLeft size={24} />
          </Link>
          <div className="min-w-0 flex-1 text-center">
            <h1 className="line-clamp-1 text-[1.25rem] font-bold leading-tight text-slate-950">
              {displayName(data.event.name, data.event.nameZh)}
            </h1>
          </div>
          <div className="h-9 w-9" />
        </div>

        <div className="mt-1 flex items-center justify-center gap-2 text-[0.9rem] font-medium text-slate-500">
          <span>{displayDateRange(data.event.startDate, data.event.endDate)}</span>
        </div>

        <div className="relative z-10 mt-1 border-b border-slate-200/80">
          <SubEventTabs subEvents={subEvents} currentSubEvent={currentSubEvent} onSelect={onSelect} />
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
    <div className="-mb-px px-1">
      <div className="flex gap-1 overflow-x-auto no-scrollbar">
        {subEvents.map((subEvent) => {
          const active = currentSubEvent === subEvent.code;
          return (
            <button
              key={subEvent.code}
              type="button"
              disabled={subEvent.disabled}
              onClick={() => onSelect(subEvent.code)}
              className={cn(
                "relative flex h-12 shrink-0 items-center whitespace-nowrap px-4 text-[1rem] font-semibold transition-colors disabled:opacity-30",
                active
                  ? "text-[#2d6cf6]"
                  : "text-slate-400 hover:text-slate-700",
              )}
            >
              {subEvent.nameZh || subEvent.code}
              <span
                aria-hidden="true"
                className={cn(
                  "pointer-events-none absolute inset-x-4 bottom-0 h-[3px] rounded-full transition-all",
                  active ? "bg-[#2d6cf6]" : "bg-transparent",
                )}
              />
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
  const championPath = findChampionMatch(rounds, championNames);
  const headline = isTeam
    ? countries[0] || champion?.championCountryCode || championNames[0] || "冠军待补"
    : championNames.join(" / ") || "冠军待补";
  const subtitle = `${label}冠军`;

  return (
    <div className="pt-2">
      <div className="relative overflow-hidden rounded-[1.7rem] bg-[linear-gradient(90deg,#dfeafe_0%,#d9e7ff_55%,#d5e1ff_100%)] px-3 py-3 shadow-[0_14px_28px_rgba(144,166,201,0.16)] ring-1 ring-white/80">
        <div className="absolute inset-y-0 left-0 w-32 bg-[radial-gradient(circle_at_18%_50%,rgba(255,255,255,0.95),transparent_60%)]" />
        <div className="absolute -left-6 bottom-0 h-20 w-20 rounded-full bg-[radial-gradient(circle,rgba(255,255,255,0.85),transparent_72%)]" />
        <div className="absolute right-0 top-0 h-full w-36 bg-[radial-gradient(circle_at_85%_20%,rgba(255,255,255,0.38),transparent_58%)]" />
        <div className="relative grid grid-cols-[84px_minmax(0,1fr)] items-center gap-2 sm:grid-cols-[96px_86px_minmax(0,1fr)] sm:gap-3">
          <div className="relative flex h-full items-end justify-center">
            <Image src="/images/cup.png" alt="冠军奖杯" width={96} height={112} className="h-auto w-[74px] sm:w-[84px]" priority />
          </div>

          <div className="relative hidden h-full items-center justify-center sm:flex">
            {champion?.players[0] && !isDoubles && !isTeam ? (
              <div className="rounded-full bg-white/45 p-1 shadow-[0_8px_20px_rgba(136,154,180,0.12)]">
                <PlayerAvatar player={champion.players[0]} size="lg" className="h-[72px] w-[72px] ring-4 ring-white/75" />
              </div>
            ) : null}
          </div>

          <div className="relative min-w-0 pr-1">
            {!isDoubles && !isTeam ? (
              <Image
                src="/images/wheatear_left.png"
                alt=""
                width={28}
                height={72}
                className="absolute -left-3 top-0 hidden h-auto w-[18px] opacity-85 sm:block"
              />
            ) : null}
            {!isDoubles && !isTeam ? (
              <Image
                src="/images/wheatear_right.png"
                alt=""
                width={28}
                height={72}
                className="absolute right-3 top-0 hidden h-auto w-[18px] opacity-85 sm:block"
              />
            ) : null}

            <div className="rounded-[1.35rem] bg-white/22 px-3 py-3 backdrop-blur-[4px]">
              <div className="flex items-center gap-1.5 text-[#466cb9]">
                <Crown size={15} className="shrink-0 text-[#cc9a2c]" />
                <p className="truncate text-[0.95rem] font-bold tracking-[0.01em]">{subtitle}</p>
              </div>

              <div className="mt-2 flex items-center gap-2">
                {isTeam && countries[0] ? <Flag code={countries[0]} className="shrink-0 scale-[1.25] origin-left" /> : null}
                <p className="truncate text-[1.9rem] font-black leading-none text-slate-950 sm:text-[2.1rem]">{headline}</p>
                {!isTeam && countries[0] ? <Flag code={countries[0]} className="mb-0.5 shrink-0 scale-[1.15]" /> : null}
              </div>

              {championPath?.finalMatch ? (
                <p className="mt-2 truncate text-[0.85rem] font-medium text-slate-600">
                  决赛 {championPath.finalMatch.matchScore || "比分待补"}
                  {championPath.winningSide ? ` · 对阵 ${sideName(championPath.winningSide)}` : ""}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ViewTabs({ mode, onChange }: { mode: ViewMode; onChange: (mode: ViewMode) => void }) {
  return (
    <div className="pt-6">
      <div className="grid grid-cols-2 gap-3 rounded-[1.65rem] bg-white/80 p-2 shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80 backdrop-blur">
        <button
          type="button"
          onClick={() => onChange("schedule")}
          className={cn(
            "flex min-h-14 items-center justify-center gap-2 rounded-[1.15rem] text-[1.06rem] font-black transition",
            mode === "schedule" ? "bg-[#4a86f7] text-white shadow-[0_8px_22px_rgba(74,134,247,0.28)]" : "text-slate-500 hover:bg-slate-50",
          )}
        >
          <List size={20} />
          赛程列表
        </button>
        <button
          type="button"
          onClick={() => onChange("draw")}
          className={cn(
            "flex min-h-14 items-center justify-center gap-2 rounded-[1.15rem] text-[1.06rem] font-black transition",
            mode === "draw" ? "bg-[#4a86f7] text-white shadow-[0_8px_22px_rgba(74,134,247,0.28)]" : "text-slate-500 hover:bg-slate-50",
          )}
        >
          <FolderTree size={20} />
          完整赛事图
        </button>
      </div>
    </div>
  );
}

function MatchListCard({ match, matchIndex }: { match: BracketMatch; matchIndex: number }) {
  const [sideA, sideB] = [...match.sides].sort((left, right) => left.sideNo - right.sideNo);

  return (
    <Link
      href={route(`/matches/${match.matchId}`)}
      className="block rounded-[1.7rem] bg-white px-4 py-4 shadow-[0_14px_30px_rgba(174,184,199,0.16)] ring-1 ring-white/80 transition hover:-translate-y-0.5 hover:shadow-[0_18px_40px_rgba(164,177,196,0.22)]"
    >
      <div className="mb-3 flex items-center justify-between gap-3 text-slate-500">
        <span className="text-[1.02rem] font-medium">已结束</span>
        <span className="text-sm font-semibold text-[#4a86f7]">赛事回放</span>
      </div>

      <div className="grid grid-cols-[26px_1fr_auto] gap-3">
        <div className="pt-4 text-center text-[1.8rem] font-black leading-none text-[#8aa5de]">{matchIndex}</div>

        <div className="space-y-2">
          {[sideA, sideB].filter(Boolean).map((side) => (
            <div
              key={side.sideNo}
              className={cn(
                "flex min-h-14 items-center gap-3 rounded-[1rem] px-3 py-2.5",
                side.isWinner ? "bg-[#f5f8ff]" : "bg-white",
              )}
            >
              <Flag code={dedupeCountries(side.players)[0] ?? null} className="scale-[1.55] origin-left shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[1.08rem] font-black text-slate-900">{sideName(side)}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="grid min-w-[118px] grid-cols-[auto_16px_minmax(0,1fr)] items-center gap-3 rounded-[1.15rem] bg-[#f6f8fd] px-3 py-3">
          <div className="space-y-2 text-right font-numeric text-[2rem] font-black leading-none tabular-nums text-slate-400">
            {[sideA, sideB].filter(Boolean).map((side) => (
              <p key={side.sideNo} className={side.isWinner ? "text-[#2d6cf6]" : "text-slate-400"}>
                {match.matchScore?.split("-")[side.sideNo - 1] ?? "-"}
              </p>
            ))}
          </div>
          <div className="space-y-4 pt-1.5">
            {[sideA, sideB].filter(Boolean).map((side) => (
              <span
                key={side.sideNo}
                className={cn(
                  "block h-4 w-4 rounded-full",
                  side.isWinner ? "bg-[#2d6cf6] shadow-[0_0_0_3px_rgba(45,108,246,0.14)]" : "bg-slate-200",
                )}
              />
            ))}
          </div>
          <div>
            <p className="text-[1.05rem] font-medium text-slate-500">局分</p>
            <p className="mt-2 text-[1rem] leading-8 text-slate-600">{sideGamesLabel(match.games)}</p>
          </div>
        </div>
      </div>
    </Link>
  );
}

function ScheduleView({ rounds }: { rounds: EventDetail["bracket"] }) {
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
    <div className="pb-10 pt-5">
      <div className="space-y-6">
        {rounds.map((round) => (
          <section key={round.code}>
            <div className="mb-3 flex items-center justify-between px-1">
              <h2 className="text-[2rem] font-black leading-none text-slate-950">{round.label}</h2>
              <span className="text-[1.02rem] font-medium text-slate-500">已完成</span>
            </div>
            <div className="space-y-4">
              {round.matches.map((match, index) => (
                <MatchListCard key={match.matchId} match={match} matchIndex={index + 1} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function DrawMatchCard({ match, isChampionPath }: { match: BracketMatch; isChampionPath: boolean }) {
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
              {sideName(side)}
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
}: {
  rounds: EventDetail["bracket"];
  selectedSubEvent: string;
  champion: EventChampion | null;
}) {
  const [search, setSearch] = React.useState("");
  const highlightedNames = normalizeChampionNames(champion);

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
                    const isChampionPath = highlightedNames.length > 0 && match.sides.some((side) => side.isWinner && highlightedNames.every((name) => sideName(side).includes(name)));
                    return <DrawMatchCard key={match.matchId} match={match} isChampionPath={isChampionPath} />;
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

function EventDetailContent() {
  const params = useParams<{ eventId: string }>();
  const searchParams = useSearchParams();
  const urlSubEvent = searchParams.get("sub_event");
  const [data, setData] = React.useState<EventDetail | null>(null);
  const [selectedSubEvent, setSelectedSubEvent] = React.useState<string | null>(urlSubEvent);
  const [viewMode, setViewMode] = React.useState<ViewMode>("schedule");
  const [loading, setLoading] = React.useState(true);

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
  const currentSubEventMeta = data.subEvents.find((subEvent) => subEvent.code === currentSubEvent);

  return (
    <main className="mx-auto min-h-screen max-w-lg bg-[#f8fafc] pb-24">
      <EventHeader
        data={data}
        subEvents={data.subEvents}
        currentSubEvent={currentSubEvent}
        onSelect={setSelectedSubEvent}
      />

      <div className="relative z-10 -mt-3 rounded-t-[2.5rem] bg-white px-5 pt-3 shadow-[0_-12px_40px_rgba(0,0,0,0.04)] ring-1 ring-black/[0.02]">
        <ChampionBanner champion={currentChampion} subEvent={currentSubEventMeta} rounds={currentBracket} />
        <ViewTabs mode={viewMode} onChange={setViewMode} />
        <div className="mt-2">
          {viewMode === "schedule" ? (
            <ScheduleView rounds={currentBracket} />
          ) : (
            <DrawView rounds={currentBracket} selectedSubEvent={currentSubEvent} champion={currentChampion} />
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
