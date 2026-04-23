"use client";

import React, { Suspense } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useParams } from "next/navigation";
import { ArrowLeft, CalendarDays, ChevronRight, Goal, Trophy } from "lucide-react";
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

type MatchSide = {
  sideNo: number;
  isWinner: boolean;
  players: Array<{
    playerId: number | null;
    slug: string | null;
    name: string;
    nameZh: string | null;
    countryCode: string | null;
    avatarFile: string | null;
  }>;
};

type MatchDetail = {
  match: {
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
    roundLabel: string;
    matchScore: string | null;
    games: Array<{ player: number; opponent: number }>;
    winnerSide: string | null;
    winnerName: string | null;
    startDate: string | null;
    endDate: string | null;
  };
  sides: MatchSide[];
};

type MatchDetailResponse = {
  code: number;
  data: MatchDetail;
};

function displayName(name: string | null, nameZh: string | null) {
  return nameZh?.trim() || name || "未命名赛事";
}

function displayPlayerName(player: MatchSide["players"][number]) {
  return player.nameZh?.trim() || player.name;
}

function displayDate(value: string | null) {
  return value || "日期待补";
}

function sideTitle(side: MatchSide) {
  return side.players.map(displayPlayerName).join(" / ");
}

function sideCountries(side: MatchSide) {
  return Array.from(new Set(side.players.map((player) => player.countryCode).filter(Boolean))).join(" / ");
}

function SideCard({ side }: { side: MatchSide }) {
  const firstPlayer = side.players[0];

  return (
    <section
      className={cn(
        "rounded-lg border p-4 shadow-sm",
        side.isWinner ? "border-brand-deep bg-brand-mist" : "border-white/60 bg-white/75",
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {firstPlayer ? (
            <PlayerAvatar player={{ ...firstPlayer, playerId: firstPlayer.playerId ?? `side-${side.sideNo}` }} size="md" />
          ) : (
            <div className="h-12 w-12 rounded-full bg-surface-tinted" />
          )}
          <div className="min-w-0">
            <h2 className="truncate text-heading-2 font-black text-text-primary">{sideTitle(side)}</h2>
            <p className="mt-0.5 text-caption font-bold uppercase tracking-wider text-text-tertiary">
              {sideCountries(side) || "国家待补"}
            </p>
          </div>
        </div>
        <span
          className={cn(
            "grid h-9 min-w-9 place-items-center rounded-full text-caption font-black",
            side.isWinner ? "bg-brand-deep text-white" : "bg-surface-secondary text-text-tertiary",
          )}
        >
          {side.isWinner ? "胜" : "负"}
        </span>
      </div>

      <div className="grid gap-2">
        {side.players.map((player, index) => {
          const content = (
            <div className="flex min-h-11 items-center justify-between gap-3 rounded-md bg-white/70 px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-body font-bold text-text-primary">{displayPlayerName(player)}</p>
                <p className="text-micro font-bold uppercase tracking-wider text-text-tertiary">
                  {player.countryCode || "国家待补"}
                </p>
              </div>
              {player.slug ? <ChevronRight size={15} className="text-text-tertiary" /> : null}
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

function MatchContent() {
  const params = useParams<{ matchId: string }>();
  const [data, setData] = React.useState<MatchDetail | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetch(`/api/v1/matches/${params.matchId}`);
        const json = (await res.json()) as MatchDetailResponse;
        if (json.code === 0) {
          setData(json.data);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }

    if (params.matchId) load();
  }, [params.matchId]);

  if (loading || !data) {
    return (
      <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-gray-50/30 pb-28">
        <div className="flex justify-center py-20 text-body text-text-tertiary">加载中...</div>
      </main>
    );
  }

  const [sideA, sideB] = [...data.sides].sort((left, right) => left.sideNo - right.sideNo);

  return (
    <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-gray-50/30 pb-28">
      <section className="relative overflow-hidden px-5 pb-6 pt-5 text-white shadow-lg">
        <div className="absolute inset-0 [background:linear-gradient(45deg,#222b34_0%,#4b6479_54%,#83acd2_100%)]" />
        <div className="absolute inset-0 opacity-50 [background:radial-gradient(circle_at_88%_10%,#dceaf8_0%,transparent_42%),radial-gradient(circle_at_8%_88%,#1e2a3d_0%,transparent_58%)]" />
        <div className="relative z-10">
          <Link
            href={route(`/events/${data.match.eventId}?sub_event=${data.match.subEventTypeCode}`)}
            className="mb-5 inline-flex min-h-11 items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3 text-caption font-bold text-white/85 backdrop-blur-sm transition-colors hover:bg-white/15"
          >
            <ArrowLeft size={14} />
            返回赛事
          </Link>
          <p className="text-caption font-bold uppercase tracking-widest text-white/66">
            {data.match.subEventNameZh || data.match.subEventTypeCode}
          </p>
          <h1 className="mt-2 line-clamp-2 text-display font-black leading-tight">
            {displayName(data.match.eventName, data.match.eventNameZh)}
          </h1>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-white/15 bg-white/10 p-3 backdrop-blur-md">
              <div className="mb-1 flex items-center gap-1.5 text-white/66">
                <CalendarDays size={14} />
                <span className="text-micro font-bold uppercase tracking-widest">日期</span>
              </div>
              <p className="text-body font-black">{displayDate(data.match.startDate)}</p>
            </div>
            <div className="rounded-lg border border-white/15 bg-white/10 p-3 backdrop-blur-md">
              <div className="mb-1 flex items-center gap-1.5 text-white/66">
                <Trophy size={14} />
                <span className="text-micro font-bold uppercase tracking-widest">轮次</span>
              </div>
              <p className="text-body font-black">{data.match.roundLabel}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="px-5 pt-4">
        <div className="rounded-lg border border-white/60 bg-white/80 p-5 text-center shadow-sm backdrop-blur-md">
          <div className="mb-2 flex items-center justify-center gap-2 text-brand-strong">
            <Goal size={18} />
            <span className="text-caption font-black uppercase tracking-widest">Match Score</span>
          </div>
          <p className="font-numeric text-[46px] font-black leading-none text-text-primary tabular-nums">
            {data.match.matchScore || "-"}
          </p>
          <p className="mt-2 text-caption font-semibold text-text-tertiary">
            获胜方：{data.match.winnerName || "待补"}
          </p>
        </div>
      </section>

      <section className="grid gap-3 px-5 pt-4">
        {sideA ? <SideCard side={sideA} /> : null}
        {sideB ? <SideCard side={sideB} /> : null}
      </section>

      <section className="px-5 pt-5">
        <div className="rounded-lg border border-white/60 bg-white/70 p-4 shadow-sm backdrop-blur-md">
          <h2 className="mb-3 text-heading-2 font-black text-text-primary">局分</h2>
          {data.match.games.length === 0 ? (
            <div className="rounded-lg bg-surface-secondary p-4 text-center">
              <p className="text-body font-bold text-text-secondary">局分还没补齐</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {data.match.games.map((game, index) => (
                <div key={index} className="rounded-md bg-surface-secondary p-3 text-center">
                  <p className="text-micro font-black uppercase tracking-widest text-text-tertiary">第 {index + 1} 局</p>
                  <p className="mt-1 font-numeric text-heading-1 font-black text-text-primary tabular-nums">
                    {game.player} - {game.opponent}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

export default function MatchPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-page-background py-20 text-center text-text-tertiary">页面加载中...</div>}>
      <MatchContent />
    </Suspense>
  );
}
