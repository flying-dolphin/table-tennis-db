"use client";

import React, { Suspense, useCallback } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight, Zap } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import { Flag } from "@/components/Flag";
import { getVisibleSideAvatarPlayers } from "@/lib/match-side-avatars";
import { formatSubEventLabel } from "@/lib/sub-event-label";

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

type MatchPlayer = MatchSide["players"][number];

type MatchDetail = {
  kind?: "match";
  match: {
    matchId: number | string;
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

type TieSide = {
  sideNo: number;
  isWinner: boolean;
  teamCode: string | null;
  seed: number | null;
  qualifier: boolean | null;
  placeholderText: string | null;
  players: MatchPlayer[];
};

type TieRubber = {
  externalMatchCode: string | null;
  matchScore: string | null;
  games: Array<{ player: number; opponent: number }>;
  winnerSide: string | null;
  sides: Array<{
    sideNo: number;
    teamCode: string | null;
    players: MatchPlayer[];
  }>;
};

type TieDetail = {
  kind: "tie";
  match: {
    scheduleMatchId: number | string;
    eventId: number;
    eventName: string | null;
    eventNameZh: string | null;
    eventYear: number | null;
    subEventTypeCode: string;
    subEventNameZh: string | null;
    roundLabel: string;
    scheduledLocalAt: string | null;
    tableNo: string | null;
    matchScore: string | null;
    winnerSide: string | null;
    startDate: string | null;
    endDate: string | null;
  };
  sides: TieSide[];
  rubbers: TieRubber[];
};

type MatchDetailResponse = {
  code: number;
  data: MatchDetail | TieDetail;
};

type CompareData = {
  players: Array<{
    playerId: number;
    name: string;
    nameZh: string | null;
    stats: { matches: number; wins: number; losses: number; winRate: number } | null;
  }>;
  headToHeadSummary: {
    totalMatches: number;
    playerA: { wins: number; winRate: number };
    playerB: { wins: number; winRate: number };
  };
  headToHeadMatches: Array<{
    matchId: number;
    eventName: string | null;
    eventNameZh: string | null;
    round: string | null;
    roundZh: string | null;
    matchScore: string | null;
    winnerId: number | null;
  }>;
};

type CompareResponse = {
  code: number;
  data: CompareData;
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

function displayDateTime(value: string | null) {
  if (!value) return "时间待补";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function sideTitle(side: { players: MatchPlayer[] }) {
  const maxChars = side.players.length > 1 ? 8 : 14;
  return side.players.map((p) => limitName(displayPlayerName(p), maxChars)).join(" / ");
}

function sideCountries(side: { players: MatchPlayer[]; teamCode?: string | null }) {
  return Array.from(new Set(side.players.map((player) => player.countryCode).filter(Boolean))).join(" / ");
}

function scoreLabel(games: Array<{ player: number; opponent: number }>) {
  if (games.length === 0) return "局分待补";
  return games.map((game) => `${game.player}-${game.opponent}`).join(", ");
}

function isStandardTeamCode(teamCode: string | null | undefined) {
  return typeof teamCode === "string" && /^[A-Z]{3}$/.test(teamCode);
}

function isSinglesSubEvent(subEventTypeCode: string) {
  return subEventTypeCode === "MS" || subEventTypeCode === "WS" || subEventTypeCode === "JBS" || subEventTypeCode === "JGS";
}

function scorePartsFromMatchScore(matchScore: string | null) {
  const rawScore = matchScore || "";
  const isWO = rawScore.toUpperCase().includes("WO");
  const cleanScore = rawScore.replace(/\s*\(?WO\)?/i, "").trim();
  const scoreParts = cleanScore.split("-").map((score) => score.trim());
  return {
    isWO,
    left: scoreParts[0] || (isWO ? "0" : "-"),
    right: scoreParts[1] || (isWO ? "0" : "-"),
  };
}

function GameScoreTable({
  games,
  sideA,
  sideB,
  matchScore,
  attached = false,
}: {
  games: Array<{ player: number; opponent: number }>;
  sideA: MatchSide | undefined;
  sideB: MatchSide | undefined;
  matchScore: string | null;
  attached?: boolean;
}) {
  const total = scorePartsFromMatchScore(matchScore);
  const rows: Array<{ side: MatchSide | undefined; isA: boolean; total: string }> = [
    { side: sideA, isA: true, total: total.left },
    { side: sideB, isA: false, total: total.right },
  ];

  return (
    <div
      className={cn(
        "overflow-hidden bg-white",
        attached ? "" : "rounded-lg border border-border-subtle shadow-sm",
      )}
    >
      {games.length === 0 ? (
        <div className="px-4 py-8 text-center">
          <p className="text-body font-bold text-text-secondary">局分还没补齐</p>
        </div>
      ) : (
        <table className="w-full table-fixed border-collapse">
          <thead>
            <tr className="border-b border-border-subtle text-caption font-bold text-text-tertiary">
              <th className="w-[36%] px-4 py-4 text-left font-bold">球员</th>
              {games.map((_, index) => (
                <th key={index} className="px-1 py-4 text-center font-bold">
                  {index + 1}
                </th>
              ))}
              <th className="w-[15%] whitespace-nowrap px-1 py-4 text-center font-bold">总分</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className={cn(rowIndex === 0 ? "border-b border-border-subtle" : "")}>
                <td className="px-4 py-4 text-left">
                  <p className="line-clamp-1 text-body font-bold text-text-primary" title={row.side ? sideTitle(row.side) : ""}>
                    {row.side ? sideTitle(row.side) : "待定"}
                  </p>
                  <p className="mt-0.5 text-micro font-bold uppercase tracking-wider text-text-tertiary">
                    {row.side ? sideCountries(row.side) || "—" : "TBD"}
                  </p>
                </td>
                {games.map((game, index) => {
                  const own = row.isA ? game.player : game.opponent;
                  // 高亮顶部选手（sideA）赢下的每一局，与设计稿保持一致。
                  const highlight = row.isA && game.player > game.opponent;
                  return (
                    <td
                      key={index}
                      className={cn(
                        "px-1 py-4 text-center font-numeric text-body-lg font-black tabular-nums",
                        highlight ? "text-brand-strong" : "text-text-primary",
                      )}
                    >
                      {own}
                    </td>
                  );
                })}
                <td className="whitespace-nowrap px-1 py-4 text-center font-numeric text-body-lg font-black tabular-nums text-text-primary">
                  {row.total}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function HeroBackBar({ title, meta, onBack }: { title: string; meta: string; onBack: () => void }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <button
        type="button"
        onClick={onBack}
        className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center text-slate-900 transition-colors"
      >
        <ChevronLeft size={26} strokeWidth={2} />
      </button>
      <div className="min-w-0 flex-1 text-center pt-1">
        <h1 className="line-clamp-2 text-[1.12rem] font-black leading-snug text-slate-950">{title}</h1>
        <p className="mt-1.5 line-clamp-1 text-[0.78rem] font-bold text-[#6f83aa]">{meta}</p>
      </div>
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center" />
    </div>
  );
}

function HeroStatusPill({ label }: { label: string }) {
  return (
    <div className="flex justify-center">
      <span className="rounded-full bg-white/10 px-4 py-1 text-[0.78rem] font-bold text-white/85 ring-1 ring-inset ring-white/20">
        {label}
      </span>
    </div>
  );
}

function HeroWinBadge() {
  return (
    <span className="absolute -bottom-3 left-1/2 z-20 -translate-x-1/2 rounded-full bg-brand-strong h-6 w-6 text-[0.72rem] grid place-items-center leading-none text-white ring-1 ring-[#243456]">
      胜
    </span>
  );
}

function SideAvatarStack({
  players,
  sideNo,
  variant = "card",
}: {
  players: MatchPlayer[];
  sideNo: number;
  variant?: "hero" | "card";
}) {
  const visiblePlayers = getVisibleSideAvatarPlayers(players);

  if (visiblePlayers.length === 0) {
    return variant === "hero" ? (
      <div className="grid h-[4.5rem] w-[4.5rem] place-items-center rounded-full bg-[#f3f6fb] ring-1 ring-white/90 shadow-lg" />
    ) : (
      <div className="h-12 w-12 shrink-0 rounded-full bg-surface-tinted" />
    );
  }

  if (variant === "hero") {
    const isPair = visiblePlayers.length > 1;
    return (
      <div className={cn("flex h-[4.5rem] items-center justify-center", isPair ? "w-[6.2rem] gap-1" : "w-[4.5rem]")}>
        {visiblePlayers.map((player, index) => (
          <PlayerAvatar
            key={`${player.playerId ?? "player"}-${index}-${player.avatarFile ?? "no-avatar"}`}
            player={{ ...player, playerId: player.playerId ?? `hero-${sideNo}-${index}` }}
            size="lg"
            className={cn(
              "bg-[#f3f6fb] ring-1 ring-white/90 shadow-lg",
              isPair ? "!h-[3.75rem] !w-[3.75rem]" : "!h-full !w-full",
            )}
          />
        ))}
      </div>
    );
  }

  const isPair = visiblePlayers.length > 1;
  return (
    <div className={cn("flex shrink-0 items-center", isPair ? "w-[5.25rem]" : "w-12")}>
      {visiblePlayers.map((player, index) => (
        <PlayerAvatar
          key={`${player.playerId ?? "player"}-${index}-${player.avatarFile ?? "no-avatar"}`}
          player={{ ...player, playerId: player.playerId ?? `side-${sideNo}-${index}` }}
          size="md"
          className={cn(isPair ? "!h-11 !w-11 ring-2 ring-white" : "", index > 0 ? "-ml-2.5" : "")}
        />
      ))}
    </div>
  );
}

function HeroScore({ left, right, isWO }: { left: string; right: string; isWO: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center pt-3">
      <div className="flex items-center gap-2 font-numeric font-black leading-none text-white tabular-nums">
        <span className="text-[2.7rem]">{left}</span>
        <span className="text-[1.6rem] text-white/55">-</span>
        <span className="text-[2.7rem]">{right}</span>
      </div>
      <span className="mt-3 h-2.5 w-2.5 rounded-full bg-white/25" />
      {isWO ? <span className="mt-1 text-[0.68rem] font-black text-amber-300">弃权</span> : null}
    </div>
  );
}

function HeroShell({ children, attached = false }: { children: React.ReactNode; attached?: boolean }) {
  return (
    <div
      className={cn(
        "relative overflow-hidden",
        attached ? "" : "mt-4 rounded-[1.6rem] shadow-[0_20px_40px_rgba(27,42,74,0.32)]",
      )}
    >
      <div className="absolute inset-0 bg-gradient-to-br from-[#1c2c4d] via-[#26365b] to-[#3b2c49]" />
      <div className="absolute inset-0 bg-[url('/images/header_bg.jpeg')] bg-cover bg-center opacity-[0.12] mix-blend-luminosity" />
      <div className={cn("relative px-4 pt-5", attached ? "pb-12" : "pb-5")}>{children}</div>
    </div>
  );
}

function MatchScoreHero({
  sideA,
  sideB,
  matchScore,
  winnerSide,
  hasResult,
  attached = false,
}: {
  sideA: MatchSide | undefined;
  sideB: MatchSide | undefined;
  matchScore: string | null;
  winnerSide: string | null;
  hasResult: boolean;
  attached?: boolean;
}) {
  const score = scorePartsFromMatchScore(matchScore);

  const renderSide = (side: MatchSide | undefined, index: number, winner: boolean) => {
    const countryCode = side?.players[0]?.countryCode ?? null;
    return (
      <div className="flex min-w-0 flex-col items-center text-center">
        <div className="relative">
          <SideAvatarStack players={side?.players ?? []} sideNo={side?.sideNo ?? index} variant="hero" />
          {winner ? <HeroWinBadge /> : null}
        </div>
        <p className={cn("mt-4 line-clamp-2 text-[0.95rem] font-bold leading-tight", winner ? "text-white" : "text-white/85")}>
          {side ? sideTitle(side) : "待定"}
        </p>
        <p className="mt-1 flex items-center justify-center gap-1.5 text-[0.7rem] font-bold uppercase tracking-wider text-white/45">
          {isStandardTeamCode(countryCode) ? (
            <Flag code={countryCode} className="shrink-0 rounded-[2px] text-[1.05rem]" />
          ) : null}
          <span className="line-clamp-1">{side ? sideCountries(side) || "—" : "TBD"}</span>
        </p>
      </div>
    );
  };

  return (
    <HeroShell attached={attached}>
      <HeroStatusPill label={hasResult ? "已结束" : "未开始"} />
      <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-2">
        {renderSide(sideA, 0, winnerSide === "A")}
        <HeroScore left={score.left} right={score.right} isWO={score.isWO} />
        {renderSide(sideB, 1, winnerSide === "B")}
      </div>
    </HeroShell>
  );
}

function TieScoreHero({
  title,
  meta,
  sideA,
  sideB,
  matchScore,
  hasResult,
  onBack,
}: {
  title: string;
  meta: string;
  sideA: TieSide | undefined;
  sideB: TieSide | undefined;
  matchScore: string | null;
  hasResult: boolean;
  onBack: () => void;
}) {
  const score = scorePartsFromMatchScore(matchScore);

  const renderSide = (side: TieSide | undefined, winner: boolean) => {
    const teamCode = side?.teamCode || side?.players[0]?.countryCode || null;
    return (
      <div className="flex min-w-0 flex-col items-center text-center">
        <div className="relative">
          <div className="grid h-[3.25rem] w-[4.5rem] place-items-center overflow-hidden">
            {isStandardTeamCode(teamCode) ? <Flag code={teamCode} className="!h-full !w-full rounded-none leading-none [background-size:cover]" /> : null}
          </div>
          {winner ? <HeroWinBadge /> : null}
        </div>
        <p className={cn("mt-4 line-clamp-1 text-[1.05rem] font-black uppercase tracking-wider", winner ? "text-white" : "text-white/85")}>
          {teamCode || "TBD"}
        </p>
        <p className="mt-1 line-clamp-1 text-[0.7rem] font-bold text-white/45">
          {side ? side.players.map(displayPlayerName).join(" / ") || "阵容待补" : "阵容待补"}
        </p>
      </div>
    );
  };

  return (
    <section className="px-4 pb-4 pt-4">
      <HeroBackBar title={title} meta={meta} onBack={onBack} />
      <HeroShell>
        <HeroStatusPill label={hasResult ? "已结束" : "未开始"} />
        <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-start gap-2">
          {renderSide(sideA, sideA?.isWinner ?? false)}
          <HeroScore left={score.left} right={score.right} isWO={score.isWO} />
          {renderSide(sideB, sideB?.isWinner ?? false)}
        </div>
      </HeroShell>
    </section>
  );
}

function SideCard({ side, hasResult }: { side: MatchSide; hasResult: boolean }) {
  return (
    <section
      className={cn(
        "rounded-lg border p-4 shadow-sm overflow-hidden",
        hasResult && side.isWinner ? "border-brand-deep bg-brand-mist" : "border-white/60 bg-white/75",
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <SideAvatarStack players={side.players} sideNo={side.sideNo} />
          <div className="min-w-0 flex-1">
            <h2 className="line-clamp-1 text-heading-2 font-black text-text-primary" title={sideTitle(side)}>
              {sideTitle(side)}
            </h2>
            <p className="mt-0.5 line-clamp-1 text-caption font-bold uppercase tracking-wider text-text-tertiary">
              {sideCountries(side) || "国家待补"}
            </p>
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

function TieSideCard({ side, hasResult }: { side: TieSide; hasResult: boolean }) {
  const firstPlayer = side.players[0];
  const teamCode = side.teamCode || firstPlayer?.countryCode || null;

  return (
    <section
      className={cn(
        "rounded-lg border p-4 shadow-sm overflow-hidden",
        hasResult && side.isWinner ? "border-brand-deep bg-brand-mist" : "border-white/60 bg-white/75",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="flex w-8 shrink-0 justify-start">
            {isStandardTeamCode(teamCode) ? <Flag code={teamCode} className="scale-[1.25]" /> : null}
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="line-clamp-1 text-heading-2 font-black uppercase tracking-wider text-text-primary">
              {sideCountries(side) || side.teamCode || "国家待补"}
            </h2>
            {side.players.length > 0 ? (
              <p className="mt-0.5 line-clamp-1 text-caption font-bold text-text-tertiary">
                {side.players.map(displayPlayerName).join(" / ")}
              </p>
            ) : null}
          </div>
        </div>
        {hasResult ? (
          <span
            className={cn(
              "grid h-9 w-9 shrink-0 place-items-center rounded-full text-caption font-black",
              side.isWinner ? "bg-brand-deep text-white" : "bg-surface-secondary text-text-tertiary",
            )}
          >
            {side.isWinner ? "胜" : "负"}
          </span>
        ) : null}
      </div>
    </section>
  );
}

function TieRubberCard({ rubber, index }: { rubber: TieRubber; index: number }) {
  const [sideA, sideB] = [...rubber.sides].sort((left, right) => left.sideNo - right.sideNo);
  const scoreParts = rubber.matchScore?.split("-") ?? [];

  return (
    <section className="rounded-lg border border-white/60 bg-white/75 p-4 shadow-sm overflow-hidden">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-heading-2 font-black text-text-primary">第 {index + 1} 盘</h3>
        <span className="font-numeric text-[1.2rem] font-black text-text-primary tabular-nums">{rubber.matchScore || "-"}</span>
      </div>

      <div className="space-y-3">
        {[sideA, sideB].filter(Boolean).map((side) => {
          const score = scoreParts[side.sideNo - 1] ?? "-";
          const isWinner = rubber.winnerSide === (side.sideNo === 1 ? "A" : "B");
          const teamCode = side.teamCode || side.players[0]?.countryCode || null;
          return (
            <div key={side.sideNo} className="rounded-md bg-surface-secondary/70 px-3 py-3">
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className={cn("line-clamp-1 text-body font-black", isWinner ? "text-text-primary" : "text-text-secondary")} title={sideTitle(side)}>
                    {sideTitle(side) || "阵容待补"}
                  </p>
                  <div className="mt-0.5 flex items-center gap-1.5 line-clamp-1 text-micro font-bold uppercase tracking-wider text-text-tertiary">
                    {isStandardTeamCode(teamCode) ? <Flag code={teamCode} /> : null}
                    <span>{sideCountries(side) || side.teamCode || "国家待补"}</span>
                  </div>
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

function SinglesComparePanel({ playerA, playerB }: { playerA: MatchPlayer; playerB: MatchPlayer }) {
  const [data, setData] = React.useState<CompareData | null>(null);

  React.useEffect(() => {
    let alive = true;
    async function load() {
      if (!playerA.slug || !playerB.slug) return;
      try {
        const params = new URLSearchParams({ player_a: playerA.slug, player_b: playerB.slug });
        const res = await fetch(`/api/v1/compare?${params.toString()}`);
        const json = (await res.json()) as CompareResponse;
        if (alive && json.code === 0) setData(json.data);
      } catch (err) {
        console.error(err);
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, [playerA.slug, playerB.slug]);

  if (!playerA.slug || !playerB.slug || !data) return null;

  const [pA, pB] = data.players;
  const latest = data.headToHeadMatches[0] ?? null;
  const summary = data.headToHeadSummary;
  const nameA = pA?.nameZh || pA?.name || displayPlayerName(playerA);
  const nameB = pB?.nameZh || pB?.name || displayPlayerName(playerB);
  // 胜场多的一方使用主色，少的一方使用半透明主色。
  const aLeads = summary.playerA.wins >= summary.playerB.wins;
  const bLeads = summary.playerB.wins >= summary.playerA.wins;

  return (
    <section className="px-4 pt-4">
      <div className="rounded-md border border-border-subtle bg-white p-5 shadow-sm">
        {/* 标题区 */}
        <div className="mb-5 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Zap size={18} className="text-brand-strong" />
            <h2 className="text-body font-bold text-text-primary">历史交手</h2>
          </div>
          {summary.totalMatches >= 2 ? (
            <Link
              href={route(`/compare?player_a=${playerA.slug}&player_b=${playerB.slug}`)}
              className="flex items-center gap-0.5 text-caption font-bold text-brand-strong"
            >
              更多
              <ChevronRight size={14} />
            </Link>
          ) : null}
        </div>

        {/* 胜场对比 + 胜率数字条 */}
        <div className="mb-2 flex items-end justify-between gap-3">
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="line-clamp-1 text-caption font-bold text-text-secondary">{nameA}</span>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className={cn("font-numeric text-data-hero font-black leading-none tabular-nums", aLeads ? "text-brand-strong" : "text-text-secondary")}>{summary.playerA.wins}</span>
              <span className="text-micro font-bold text-text-tertiary">胜 · {summary.playerA.winRate}%</span>
            </div>
          </div>
          <span className="mb-1 shrink-0 rounded-full bg-page-background px-3 py-1 text-micro font-bold uppercase tracking-widest text-text-tertiary">
            共 {summary.totalMatches} 场
          </span>
          <div className="flex min-w-0 flex-1 flex-col items-end">
            <span className="line-clamp-1 text-right text-caption font-bold text-text-secondary">{nameB}</span>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="text-micro font-bold text-text-tertiary">{summary.playerB.winRate}% · 胜</span>
              <span className={cn("font-numeric text-data-hero font-black leading-none tabular-nums", bLeads ? "text-brand-strong" : "text-text-secondary")}>{summary.playerB.wins}</span>
            </div>
          </div>
        </div>
        <div className="flex h-2 w-full overflow-hidden rounded-full bg-page-background">
          <div className={cn("h-full", aLeads ? "bg-brand-strong" : "bg-brand-strong/50")} style={{ width: `${summary.playerA.winRate}%` }} />
          <div className={cn("h-full", bLeads ? "bg-brand-strong" : "bg-brand-strong/50")} style={{ width: `${summary.playerB.winRate}%` }} />
        </div>

        {/* 最近一次交手 */}
        {latest ? (
          <Link
            href={route(`/matches/${latest.matchId}`)}
            className="mt-2 flex items-center justify-between gap-3 py-2 transition-colors hover:bg-brand-mist/30"
          >
            <div className="min-w-0">
              <p className="line-clamp-1 text-sm font-bold uppercase tracking-wider text-text-tertiary">
                {latest.eventNameZh || latest.eventName || "赛事待补"}
              </p>
              <p className="mt-0.5 line-clamp-1 text-xs font-bold text-text-primary">{latest.roundZh || latest.round || "轮次待补"}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="font-numeric text-body-lg font-black text-text-primary tabular-nums">{latest.matchScore || "-"}</span>
              <ChevronRight size={16} className="text-text-tertiary" />
            </div>
          </Link>
        ) : (
          <p className="mt-5 rounded-md bg-surface-secondary px-3 py-3 text-center text-caption font-bold text-text-tertiary">暂无历史交手记录</p>
        )}
      </div>
    </section>
  );
}

function MatchContent() {
  const params = useParams<{ matchId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromHref = searchParams.get("from");
  const [data, setData] = React.useState<MatchDetail | TieDetail | null>(null);
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
      <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-page-background pb-28">
        <div className="flex justify-center py-20 text-body text-text-tertiary">加载中...</div>
      </main>
    );
  }

  if (data.kind === "tie") {
    const [sideA, sideB] = [...data.sides].sort((left, right) => left.sideNo - right.sideNo);
    const hasResult = data.match.winnerSide !== null;

    return (
      <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-page-background pb-28">
        <TieScoreHero
          title={displayName(data.match.eventName, data.match.eventNameZh)}
          meta={`${displayDateTime(data.match.scheduledLocalAt)} · ${data.match.tableNo || "场地待补"} | ${formatSubEventLabel(data.match.subEventTypeCode, data.match.subEventNameZh)} · ${data.match.roundLabel}`}
          sideA={sideA}
          sideB={sideB}
          matchScore={data.match.matchScore}
          hasResult={hasResult}
          onBack={handleBack}
        />

        <section className="grid gap-3 px-5 pt-4">
          {sideA ? <TieSideCard side={sideA} hasResult={hasResult} /> : null}
          {sideB ? <TieSideCard side={sideB} hasResult={hasResult} /> : null}
        </section>

        {data.rubbers.length > 0 ? (
          <section className="px-5 pt-5">
            <div className="mb-3">
              <h2 className="text-heading-2 font-black text-text-primary">逐盘详情</h2>
            </div>
            <div className="space-y-3">
              {data.rubbers.map((rubber, index) => (
                <TieRubberCard key={rubber.externalMatchCode ?? `${index}`} rubber={rubber} index={index} />
              ))}
            </div>
          </section>
        ) : null}
      </main>
    );
  }

  const [sideA, sideB] = [...data.sides].sort((left, right) => left.sideNo - right.sideNo);
  const hasResult = data.match.winnerSide !== null;
  const showCompare =
    isSinglesSubEvent(data.match.subEventTypeCode) &&
    sideA?.players.length === 1 &&
    sideB?.players.length === 1 &&
    Boolean(sideA.players[0]?.slug && sideB.players[0]?.slug);

  return (
    <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-page-background pb-10">
      <div className="px-4 pt-4">
        <HeroBackBar
          title={displayName(data.match.eventName, data.match.eventNameZh)}
          meta={`${displayDate(data.match.startDate)} · ${formatSubEventLabel(data.match.subEventTypeCode, data.match.subEventNameZh)} · ${data.match.roundLabel}`}
          onBack={handleBack}
        />
      </div>

      {/* 局分卡片上悬浮、略微压住 hero 底部 */}
      <section className="pt-1">
        <div className="overflow-hidden rounded-t-sm shadow-[0_16px_36px_rgba(27,42,74,0.26)]">
          <MatchScoreHero
            sideA={sideA}
            sideB={sideB}
            matchScore={data.match.matchScore}
            winnerSide={data.match.winnerSide}
            hasResult={hasResult}
            attached
          />
        </div>
      </section>
      <section className="px-4">
        <div className="relative z-10 -mt-8 overflow-hidden rounded-md border border-border-subtle bg-white shadow-[0_12px_30px_rgba(84,112,156,0.20)]">
          <GameScoreTable
            games={data.match.games}
            sideA={sideA}
            sideB={sideB}
            matchScore={data.match.matchScore}
            attached
          />
        </div>
        </section>

      {showCompare ? <SinglesComparePanel playerA={sideA.players[0]} playerB={sideB.players[0]} /> : null}
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
