"use client";

import React, { Suspense, useCallback } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight, Goal } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { Flag } from "@/components/Flag";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import { formatSubEventLabel } from "@/lib/sub-event-label";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function route(path: string) {
  return path as Route;
}

type ScheduleMatchSidePlayer = {
  playerId: number | null;
  slug: string | null;
  name: string;
  nameZh: string | null;
  countryCode: string | null;
  avatarFile: string | null;
};

type ScheduleMatchSide = {
  sideNo: number;
  isWinner: boolean;
  teamCode: string | null;
  seed: number | null;
  qualifier: boolean | null;
  placeholderText: string | null;
  players: ScheduleMatchSidePlayer[];
};

type ScheduleMatchRubber = {
  externalMatchCode: string | null;
  matchScore: string | null;
  games: Array<{ player: number; opponent: number }>;
  winnerSide: string | null;
  sides: Array<{
    sideNo: number;
    teamCode: string | null;
    players: ScheduleMatchSidePlayer[];
  }>;
};

type ScheduleMatchDetail = {
  match: {
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
    roundLabel: string;
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
    startDate: string | null;
    endDate: string | null;
    externalMatchCode: string | null;
  };
  sides: ScheduleMatchSide[];
  rubbers: ScheduleMatchRubber[];
};

type ScheduleMatchDetailResponse = {
  code: number;
  data: ScheduleMatchDetail;
};

function displayName(name: string | null, nameZh: string | null) {
  return nameZh?.trim() || name || "未命名赛事";
}

function displayPlayerName(player: ScheduleMatchSidePlayer) {
  return player.nameZh?.trim() || player.name;
}

function limitName(name: string, maxChars: number = 18) {
  const chars = Array.from(name);
  if (chars.length <= maxChars) return name;
  return `${chars.slice(0, maxChars).join("")}...`;
}

function displayDate(value: string | null) {
  if (!value) return "日期待补";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

function displayDateTime(value: string | null) {
  if (!value) return "时间待补";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function sideTitle(side: ScheduleMatchSide | ScheduleMatchRubber["sides"][number]) {
  if (side.players.length === 0) return "阵容待补";
  const maxChars = side.players.length > 1 ? 8 : 14;
  return side.players.map((p) => limitName(displayPlayerName(p), maxChars)).join(" / ");
}

function sideCountries(side: ScheduleMatchSide | ScheduleMatchRubber["sides"][number]) {
  return Array.from(new Set(side.players.map((player) => player.countryCode).filter(Boolean))).join(" / ");
}

function scoreLabel(games: Array<{ player: number; opponent: number }>) {
  if (games.length === 0) return "局分待补";
  return games.map((game) => `${game.player}-${game.opponent}`).join(", ");
}

function isTeamSubEvent(subEventTypeCode: string) {
  return subEventTypeCode === "MT" || subEventTypeCode === "WT" || subEventTypeCode === "XT";
}

function SideCard({ side, teamEvent, hasResult }: { side: ScheduleMatchSide; teamEvent: boolean; hasResult: boolean }) {
  const firstPlayer = side.players[0];

  return (
    <section
      className={cn(
        "rounded-lg border p-4 shadow-sm overflow-hidden",
        hasResult && side.isWinner ? "border-brand-deep bg-brand-mist" : "border-white/60 bg-white/75",
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          {teamEvent ? (
            <div className="flex w-6 shrink-0 justify-start">
              <Flag code={side.teamCode || firstPlayer?.countryCode || null} className="scale-[1.2]" />
            </div>
          ) : firstPlayer ? (
            <div className="shrink-0">
              <PlayerAvatar player={{ ...firstPlayer, playerId: firstPlayer.playerId ?? `side-${side.sideNo}` }} size="md" />
            </div>
          ) : (
            <div className="h-12 w-12 shrink-0 rounded-full bg-surface-tinted" />
          )}
          <div className="min-w-0 flex-1">
            {teamEvent ? (
              <h2 className="line-clamp-1 text-heading-2 font-black uppercase tracking-wider text-text-primary" title={sideCountries(side) || side.teamCode || "国家待补"}>
                {sideCountries(side) || side.teamCode || "国家待补"}
              </h2>
            ) : (
              <>
                <h2 className="line-clamp-1 text-heading-2 font-black text-text-primary" title={sideTitle(side)}>
                  {sideTitle(side)}
                </h2>
                <p className="mt-0.5 line-clamp-1 text-caption font-bold uppercase tracking-wider text-text-tertiary">
                  {sideCountries(side) || side.teamCode || "国家待补"}
                </p>
              </>
            )}
          </div>
        </div>
        {hasResult && (
          <span
            className={cn(
              "grid h-9 w-9 shrink-0 place-items-center rounded-full text-caption font-black",
              side.isWinner ? "bg-brand-deep text-white" : "bg-surface-secondary text-text-tertiary",
            )}
          >
            {side.isWinner ? "胜" : "负"}
          </span>
        )}
      </div>

      <div className="grid gap-2">
        {side.players.map((player, index) => {
          const content = (
            <div className="flex min-h-11 items-center justify-between gap-3 rounded-md bg-white/70 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="line-clamp-1 text-body font-bold text-text-primary">
                  {limitName(displayPlayerName(player), 15)}
                </p>
                <p className="line-clamp-1 text-micro font-bold uppercase tracking-wider text-text-tertiary">
                  {player.countryCode || side.teamCode || "国家待补"}
                </p>
              </div>
              {player.slug ? <ChevronRight size={15} className="shrink-0 text-text-tertiary" /> : null}
            </div>
          );

          if (!player.slug) {
            return <article key={`${side.sideNo}-${index}`}>{content}</article>;
          }

          return (
            <Link key={player.slug} href={route(`/players/${player.slug}`)}>
              {content}
            </Link>
          );
        })}
      </div>
    </section>
  );
}

function RubberCard({
  rubber,
  index,
  teamEvent,
}: {
  rubber: ScheduleMatchRubber;
  index: number;
  teamEvent: boolean;
}) {
  const [sideA, sideB] = [...rubber.sides].sort((left, right) => left.sideNo - right.sideNo);
  const scoreParts = rubber.matchScore?.split("-") ?? [];

  return (
    <section className="rounded-lg border border-white/60 bg-white/75 p-4 shadow-sm overflow-hidden">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-heading-2 font-black text-text-primary">{teamEvent ? `第 ${index + 1} 盘` : `第 ${index + 1} 场`}</h3>
        <span className="font-numeric text-[1.2rem] font-black text-text-primary tabular-nums">{rubber.matchScore || "-"}</span>
      </div>

      <div className="space-y-3">
        {[sideA, sideB].filter(Boolean).map((side) => {
          const score = scoreParts[side.sideNo - 1] ?? "-";
          const isWinner = rubber.winnerSide === (side.sideNo === 1 ? "A" : "B");
          return (
            <div key={side.sideNo} className="rounded-md bg-surface-secondary/70 px-3 py-3">
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className={cn("line-clamp-1 text-body font-black", isWinner ? "text-text-primary" : "text-text-secondary")} title={sideTitle(side)}>
                    {sideTitle(side)}
                  </p>
                  <p className="mt-0.5 line-clamp-1 text-micro font-bold uppercase tracking-wider text-text-tertiary">
                    {sideCountries(side) || side.teamCode || "国家待补"}
                  </p>
                </div>
                <span className={cn("font-numeric text-[1.15rem] font-black tabular-nums", isWinner ? "text-brand-deep" : "text-text-tertiary")}>{score}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-3 rounded-md bg-white/70 px-3 py-2 text-[0.9rem] font-medium text-text-secondary">
        局分：{scoreLabel(rubber.games)}
      </div>
    </section>
  );
}

function ScheduleMatchContent() {
  const params = useParams<{ scheduleMatchId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromHref = searchParams.get("from");
  const [data, setData] = React.useState<ScheduleMatchDetail | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetch(`/api/v1/schedule-matches/${params.scheduleMatchId}`);
        const json = (await res.json()) as ScheduleMatchDetailResponse;
        if (json.code === 0) {
          setData(json.data);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }

    if (params.scheduleMatchId) load();
  }, [params.scheduleMatchId]);

  const handleBack = useCallback(() => {
    if (fromHref) {
      router.replace(route(fromHref));
      return;
    }
    if (window.history.length > 1) {
      router.back();
      return;
    }
    if (!data) {
      router.push(route("/events"));
      return;
    }
    router.push(route(`/events/${data.match.eventId}?sub_event=${data.match.subEventTypeCode}`));
  }, [data, fromHref, router]);

  if (loading || !data) {
    return (
      <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-gray-50/30 pb-28">
        <div className="flex justify-center py-20 text-body text-text-tertiary">加载中...</div>
      </main>
    );
  }

  const [sideA, sideB] = [...data.sides].sort((left, right) => left.sideNo - right.sideNo);
  const teamEvent = isTeamSubEvent(data.match.subEventTypeCode);

  const rawScore = data.match.matchScore || "";
  const isWO = rawScore.toUpperCase().includes("WO");
  const cleanScore = rawScore.replace(/\s*\(?WO\)?/i, "").trim();
  const scoreParts = cleanScore.split("-").map((s) => s.trim());
  const sA = scoreParts[0] || (isWO ? "0" : "-");
  const sB = scoreParts[1] || (isWO ? "0" : "-");

  const winnerName =
    data.match.winnerSide === "A"
      ? sideA
        ? sideTitle(sideA)
        : null
      : data.match.winnerSide === "B"
        ? sideB
          ? sideTitle(sideB)
          : null
        : null;

  return (
    <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-gray-50/30 pb-28">
      <section className="relative overflow-hidden bg-[#f0f4ff] px-4 pb-4 pt-4">
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
              onClick={handleBack}
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center text-slate-900 transition-colors"
            >
              <ChevronLeft size={26} strokeWidth={2} />
            </button>

            <div className="min-w-0 flex-1 text-center pt-1.5">
              <h1 className="line-clamp-2 text-[1.2rem] font-bold leading-snug text-slate-950">
                {displayName(data.match.eventName, data.match.eventNameZh)}
              </h1>
            </div>

            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center" />
          </div>
        </div>
      </section>

      <section className="px-5 pt-4">
        <div className="rounded-lg border border-white/60 bg-white/80 p-5 text-center shadow-sm backdrop-blur-md overflow-hidden">
          <div className="mb-4 flex items-center justify-center gap-2 text-brand-strong">
            <Goal size={18} />
            <span className="text-caption font-black uppercase tracking-widest">Match Score</span>
          </div>

          <div className="flex items-center justify-center gap-8">
            <div className="flex flex-col items-center gap-2">
              <Flag code={sideA?.teamCode || sideA?.players[0]?.countryCode || null} className="scale-[1.8]" />
              <span className="text-micro font-black uppercase tracking-widest text-text-tertiary">
                {sideA?.teamCode || sideA?.players[0]?.countryCode || "TBD"}
              </span>
            </div>

            <div className="flex items-start justify-center gap-4 font-numeric text-[46px] font-black leading-none text-text-primary tabular-nums">
              <div className="flex flex-col items-center">
                <span>{sA}</span>
                {isWO && sA === "0" && (
                  <span className="mt-1.5 text-[12px] font-bold text-text-tertiary">弃权</span>
                )}
              </div>
              <span className="pt-1.5 text-text-tertiary/30">-</span>
              <div className="flex flex-col items-center">
                <span>{sB}</span>
                {isWO && sB === "0" && (
                  <span className="mt-1.5 text-[12px] font-bold text-text-tertiary">弃权</span>
                )}
              </div>
            </div>

            <div className="flex flex-col items-center gap-2">
              <Flag code={sideB?.teamCode || sideB?.players[0]?.countryCode || null} className="scale-[1.8]" />
              <span className="text-micro font-black uppercase tracking-widest text-text-tertiary">
                {sideB?.teamCode || sideB?.players[0]?.countryCode || "TBD"}
              </span>
            </div>
          </div>

          <p className="mt-4 text-[0.82rem] font-medium text-text-tertiary">
            {displayDateTime(data.match.scheduledLocalAt)} · {data.match.tableNo || "场地待补"} | {formatSubEventLabel(data.match.subEventTypeCode, data.match.subEventNameZh)} · {data.match.roundLabel}
          </p>
        </div>
      </section>

      {data.rubbers.length > 0 ? (
        <section className="px-5 pt-5">
          <div className="mb-3">
            <h2 className="text-heading-2 font-black text-text-primary">逐盘详情</h2>
          </div>
          <div className="space-y-3">
            {data.rubbers.map((rubber, index) => (
              <RubberCard key={rubber.externalMatchCode ?? `${index}`} rubber={rubber} index={index} teamEvent={teamEvent} />
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}

export default function ScheduleMatchPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-page-background py-20 text-center text-text-tertiary">页面加载中...</div>}>
      <ScheduleMatchContent />
    </Suspense>
  );
}
