"use client";

import React, { Suspense, useCallback } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, CalendarDays, ChevronLeft, ChevronRight, Goal, Trophy } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import { formatSubEventLabel } from "@/lib/sub-event-label";
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

function limitName(name: string, maxChars: number = 18) {
  const chars = Array.from(name);
  if (chars.length <= maxChars) return name;
  return `${chars.slice(0, maxChars).join("")}...`;
}

function displayDate(value: string | null) {
  return value || "日期待补";
}

function sideTitle(side: MatchSide) {
  // 更加激进的限制：双打每个名字 8 字符，单打 14 字符
  const maxChars = side.players.length > 1 ? 8 : 14;
  return side.players.map((p) => limitName(displayPlayerName(p), maxChars)).join(" / ");
}

function sideCountries(side: MatchSide) {
  return Array.from(new Set(side.players.map((player) => player.countryCode).filter(Boolean))).join(" / ");
}

function SideCard({ side }: { side: MatchSide }) {
  const firstPlayer = side.players[0];

  return (
    <section
      className={cn(
        "rounded-lg border p-4 shadow-sm overflow-hidden",
        side.isWinner ? "border-brand-deep bg-brand-mist" : "border-white/60 bg-white/75",
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          {firstPlayer ? (
            <div className="shrink-0">
              <PlayerAvatar player={{ ...firstPlayer, playerId: firstPlayer.playerId ?? `side-${side.sideNo}` }} size="md" />
            </div>
          ) : (
            <div className="h-12 w-12 shrink-0 rounded-full bg-surface-tinted" />
          )}
          <div className="min-w-0 flex-1">
            <h2 className="line-clamp-1 text-heading-2 font-black text-text-primary" title={sideTitle(side)}>
              {sideTitle(side)}
            </h2>
            <p className="mt-0.5 line-clamp-1 text-caption font-bold uppercase tracking-wider text-text-tertiary">
              {sideCountries(side) || "国家待补"}
            </p>
          </div>
        </div>
        <span
          className={cn(
            "grid h-9 w-9 shrink-0 place-items-center rounded-full text-caption font-black",
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
              <div className="min-w-0 flex-1">
                <p className="line-clamp-1 text-body font-bold text-text-primary">
                  {limitName(displayPlayerName(player), 15)}
                </p>
                <p className="line-clamp-1 text-micro font-bold uppercase tracking-wider text-text-tertiary">
                  {player.countryCode || "国家待补"}
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

function MatchContent() {
  const params = useParams<{ matchId: string }>();
  const router = useRouter();
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

  const handleBack = useCallback(() => {
    if (window.history.length > 1) {
      router.back();
      return;
    }
    if (!data) {
      router.push(route("/events"));
      return;
    }
    router.push(route(`/events/${data.match.eventId}?sub_event=${data.match.subEventTypeCode}`));
  }, [data, router]);

  if (loading || !data) {
    return (
      <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-gray-50/30 pb-28">
        <div className="flex justify-center py-20 text-body text-text-tertiary">加载中...</div>
      </main>
    );
  }

  const [sideA, sideB] = [...data.sides].sort((left, right) => left.sideNo - right.sideNo);

  const winnerName = (() => {
    const score = data.match.matchScore;
    if (!score) return null;
    const parts = score.split("-").map(Number);
    if (parts.length !== 2 || !Number.isFinite(parts[0]) || !Number.isFinite(parts[1])) return null;
    const winnerSide = parts[0] > parts[1] ? sideA : sideB;
    if (!winnerSide) return null;
    // 获胜方名字也进行激进截断
    const maxChars = winnerSide.players.length > 1 ? 8 : 14;
    return winnerSide.players.map((p) => limitName(displayPlayerName(p), maxChars)).join(" / ");
  })();

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
              <div className="mt-2 flex items-center justify-center gap-3">
                <span className="text-[0.88rem] font-medium text-[#7d8fae]">{displayDate(data.match.startDate)}</span>
                <span className="text-[0.88rem] text-[#c5cddc]">·</span>
                <span className="text-[0.88rem] font-medium text-[#7d8fae]">{data.match.roundLabel}</span>
              </div>
            </div>

            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center" />
          </div>
        </div>
      </section>

      <section className="px-5 pt-4">
        <div className="rounded-lg border border-white/60 bg-white/80 p-5 text-center shadow-sm backdrop-blur-md overflow-hidden">
          <div className="mb-2 flex items-center justify-center gap-2 text-brand-strong">
            <Goal size={18} />
            <span className="text-caption font-black uppercase tracking-widest">Match Score</span>
          </div>
          <p className="font-numeric text-[46px] font-black leading-none text-text-primary tabular-nums">
            {data.match.matchScore || "-"}
          </p>
          <div className="mt-2 flex justify-center w-full overflow-hidden">
            <p className="max-w-full line-clamp-1 px-2 text-caption font-semibold text-text-tertiary" title={winnerName || ""}>
              获胜方：{winnerName || "待补"}
            </p>
          </div>
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
