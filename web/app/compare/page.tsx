"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import type { Route } from "next";
import { ChevronLeft, ArrowRightLeft, Trophy, Zap, Globe, Search, X, ChevronRight } from "lucide-react";
import Link from "next/link";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type PlayerStats = {
  totalMatches: number;
  totalWins: number;
  winRate: number;
  headToHeadCount: number;
  foreignMatches: number;
  foreignWins: number;
  foreignWinRate: number;
  domesticMatches: number;
  domesticWins: number;
  domesticWinRate: number;
  eventsTotal: number;
  threeTitles: number;
  sevenTitles: number;
  sevenFinals: number;
};

type ComparePlayer = {
  playerId: number;
  slug: string;
  name: string;
  nameZh: string | null;
  country: string | null;
  countryCode: string;
  avatarFile: string | null;
  avatarUrl: string | null;
  stats: PlayerStats | null;
};

type CompareMatch = {
  matchId: number;
  eventId: number | null;
  eventName: string | null;
  eventNameZh: string | null;
  eventYear: number | null;
  round: string | null;
  roundZh: string | null;
  matchScore: string | null;
  winnerId: number | null;
  startDate: string | null;
};

type SearchPlayer = {
  playerId: number;
  slug: string;
  name: string;
  nameZh: string | null;
  country: string | null;
  countryCode: string;
  avatarFile: string | null;
  avatarUrl: string | null;
  rank: number | null;
  points: number | null;
};

type SearchPlayersResponse = {
  code: number;
  message: string;
  data: {
    items: SearchPlayer[];
    query: string;
  };
};

type CompareResponse = {
  code: number;
  message: string;
  data: {
    players: ComparePlayer[];
    headToHeadSummary: {
      totalMatches: number;
      playerA: { wins: number; winRate: number };
      playerB: { wins: number; winRate: number };
    };
    headToHeadMatches: CompareMatch[];
  };
};

function CompareContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const playerASlug = searchParams.get("player_a");
  const playerBSlug = searchParams.get("player_b");

  const [data, setData] = useState<CompareResponse["data"] | null>(null);
  const [loading, setLoading] = useState(true);
  const [replaceTarget, setReplaceTarget] = useState<"A" | "B" | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchPlayer[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  function route(path: string) {
    return path as Route;
  }

  useEffect(() => {
    if (!playerASlug || !playerBSlug) return;

    async function load() {
      setLoading(true);
      try {
        const res = await fetch(`/api/v1/compare?player_a=${playerASlug}&player_b=${playerBSlug}`);
        const json = (await res.json()) as CompareResponse;
        if (json.code === 0) {
          setData(json.data);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [playerASlug, playerBSlug]);

  useEffect(() => {
    if (!replaceTarget) return;

    async function loadSearchResults() {
      setSearchLoading(true);
      try {
        const params = new URLSearchParams();
        params.set("limit", "12");
        if (searchQuery.trim()) {
          params.set("q", searchQuery.trim());
        }
        const excludeSlug = replaceTarget === "A" ? playerBSlug : playerASlug;
        if (excludeSlug) {
          params.set("exclude_slug", excludeSlug);
        }

        const res = await fetch(`/api/v1/players/search?${params.toString()}`);
        const json = (await res.json()) as SearchPlayersResponse;
        if (json.code === 0) {
          setSearchResults(json.data.items);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setSearchLoading(false);
      }
    }

    loadSearchResults();
  }, [replaceTarget, searchQuery, playerASlug, playerBSlug]);

  if (!playerASlug || !playerBSlug) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-4 text-center">
        <h1 className="text-xl font-bold mb-4">请选择两名球员进行对比</h1>
        <Link href="/rankings" className="bg-brand-deep text-white px-6 py-2 rounded-full font-bold">
          前往排名页
        </Link>
      </div>
    );
  }

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-text-tertiary">加载中...</div>;
  }

  if (!data) {
    return <div className="min-h-screen flex items-center justify-center">未找到相关数据</div>;
  }

  const [pA, pB] = data.players;

  const openReplaceModal = (target: "A" | "B") => {
    setReplaceTarget(target);
    setSearchQuery("");
    setSearchResults([]);
  };

  const closeReplaceModal = () => {
    setReplaceTarget(null);
    setSearchQuery("");
    setSearchResults([]);
  };

  const handleReplacePlayer = (player: SearchPlayer) => {
    const params = new URLSearchParams(searchParams.toString());
    if (replaceTarget === "A") {
      params.set("player_a", player.slug);
    }
    if (replaceTarget === "B") {
      params.set("player_b", player.slug);
    }
    closeReplaceModal();
    router.push(route(`/compare?${params.toString()}`));
  };

  const MetricRow = ({ label, valA, valB, higherIsBetter = true, isPercentage = false }: any) => {
    const isHigherA = valA > valB;
    const isHigherB = valB > valA;
    const isEqual = valA === valB;

    const format = (v: any) => (isPercentage ? `${v}%` : v);

    return (
      <div className="flex flex-col py-3 border-b border-border-subtle last:border-0">
        <div className="text-micro text-text-tertiary text-center mb-1 font-medium uppercase tracking-widest">{label}</div>
        <div className="flex items-center justify-between px-2">
          <div className={cn(
            "flex-1 text-center text-body-lg font-bold tabular-nums",
            !isEqual && (isHigherA === higherIsBetter ? "text-brand-strong scale-105" : "text-text-secondary opacity-60")
          )}>
            {format(valA)}
          </div>
          <div className="w-[1px] h-4 bg-border-subtle mx-4" />
          <div className={cn(
            "flex-1 text-center text-body-lg font-bold tabular-nums",
            !isEqual && (isHigherB === higherIsBetter ? "text-brand-strong scale-105" : "text-text-secondary opacity-60")
          )}>
            {format(valB)}
          </div>
        </div>
      </div>
    );
  };

  return (
    <main className="min-h-screen pb-20 bg-page-background">
      {/* Header */}
      <div className="bg-white/80 backdrop-blur-md sticky top-0 z-30 border-b border-border-subtle px-4 py-3 flex items-center justify-between">
        <button onClick={() => router.back()} className="p-1 -ml-1 text-text-secondary">
          <ChevronLeft size={24} />
        </button>
        <h1 className="text-heading-2 font-bold text-text-primary">球员对比</h1>
        <div className="w-8" />
      </div>

      <div className="px-4 py-6">
        {/* Player Cards */}
        <div className="flex items-center gap-3 mb-8">
          <button
            type="button"
            onClick={() => openReplaceModal("A")}
            className="flex-1 bg-white rounded-lg p-4 flex flex-col items-center shadow-sm border border-white transition-colors hover:bg-brand-mist/20"
          >
            <PlayerAvatar player={pA} size="lg" />
            <h2 className="mt-3 text-body font-bold text-text-primary text-center leading-tight">
              {pA.nameZh || pA.name}
            </h2>
            <span className="mt-1 text-micro font-medium text-text-tertiary bg-page-background px-2 py-0.5 rounded-full uppercase tracking-wider">
              {pA.countryCode}
            </span>
            <span className="mt-3 text-micro font-semibold text-brand-strong">点击更换球员</span>
          </button>

          <div className="shrink-0 bg-brand-strong text-white w-10 h-10 rounded-full flex items-center justify-center shadow-lg z-10">
            <ArrowRightLeft size={18} />
          </div>

          <button
            type="button"
            onClick={() => openReplaceModal("B")}
            className="flex-1 bg-white rounded-lg p-4 flex flex-col items-center shadow-sm border border-white transition-colors hover:bg-brand-mist/20"
          >
            <PlayerAvatar player={pB} size="lg" />
            <h2 className="mt-3 text-body font-bold text-text-primary text-center leading-tight">
              {pB.nameZh || pB.name}
            </h2>
            <span className="mt-1 text-micro font-medium text-text-tertiary bg-page-background px-2 py-0.5 rounded-full uppercase tracking-wider">
              {pB.countryCode}
            </span>
            <span className="mt-3 text-micro font-semibold text-brand-strong">点击更换球员</span>
          </button>
        </div>

        {/* Head to Head Summary */}
        <div className="bg-white rounded-lg p-5 shadow-sm border border-white mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Zap size={18} className="text-brand-strong" />
            <h3 className="text-body font-bold text-text-primary">历史交手</h3>
          </div>

          <div className="flex items-center justify-between mb-2">
            <div className="flex flex-col items-center flex-1">
              <span className="text-data-hero font-black text-brand-strong leading-none tabular-nums">{data.headToHeadSummary.playerA.wins}</span>
              <span className="text-caption text-text-tertiary mt-1">胜</span>
            </div>
            <div className="px-4 text-micro font-bold text-text-tertiary bg-page-background rounded-full py-1 uppercase tracking-widest">
              共 {data.headToHeadSummary.totalMatches} 场
            </div>
            <div className="flex flex-col items-center flex-1">
              <span className="text-data-hero font-black text-text-secondary leading-none tabular-nums">{data.headToHeadSummary.playerB.wins}</span>
              <span className="text-caption text-text-tertiary mt-1">胜</span>
            </div>
          </div>

          <div className="w-full h-2 bg-page-background rounded-full overflow-hidden flex">
            <div
              className="h-full bg-brand-strong"
              style={{ width: `${data.headToHeadSummary.playerA.winRate}%` }}
            />
            <div
              className="h-full bg-text-tertiary/30"
              style={{ width: `${data.headToHeadSummary.playerB.winRate}%` }}
            />
          </div>
        </div>

        {/* Stats Metrics */}
        <div className="bg-white rounded-lg p-2 shadow-sm border border-white mb-6">
          <div className="px-3 pt-3 pb-1 flex items-center gap-2">
            <Globe size={18} className="text-brand-strong" />
            <h3 className="text-body font-bold text-text-primary">核心指标</h3>
          </div>

          <MetricRow
            label="总胜率"
            valA={pA.stats?.winRate ?? 0}
            valB={pB.stats?.winRate ?? 0}
            isPercentage={true}
          />
          <MetricRow
            label="外战胜率"
            valA={pA.stats?.foreignWinRate ?? 0}
            valB={pB.stats?.foreignWinRate ?? 0}
            isPercentage={true}
          />
          <MetricRow
            label="内战胜率"
            valA={pA.stats?.domesticWinRate ?? 0}
            valB={pB.stats?.domesticWinRate ?? 0}
            isPercentage={true}
          />
          <MetricRow
            label="三大赛单项冠军"
            valA={pA.stats?.threeTitles ?? 0}
            valB={pB.stats?.threeTitles ?? 0}
          />
          <MetricRow
            label="七大赛单项冠军"
            valA={pA.stats?.sevenTitles ?? 0}
            valB={pB.stats?.sevenTitles ?? 0}
          />
          <MetricRow
            label="七大赛决赛"
            valA={pA.stats?.sevenFinals ?? 0}
            valB={pB.stats?.sevenFinals ?? 0}
          />
          <MetricRow
            label="参与赛事"
            valA={pA.stats?.eventsTotal ?? 0}
            valB={pB.stats?.eventsTotal ?? 0}
          />
        </div>

        {/* H2H Match List */}
        <div className="bg-white rounded-lg p-2 shadow-sm border border-white">
          <div className="px-3 pt-3 pb-3 flex items-center gap-2">
            <Trophy size={18} className="text-brand-deep" />
            <h3 className="text-body font-bold text-text-primary">交手记录</h3>
            <span className="text-micro font-medium text-text-tertiary">仅女单</span>
          </div>

          <div className="flex flex-col">
            {data.headToHeadMatches.length === 0 ? (
              <div className="py-10 text-center text-text-tertiary text-body">暂无交手记录</div>
            ) : (
              data.headToHeadMatches.map((match) => {
                const isWinnerA = match.winnerId === pA.playerId;
                return (
                  <Link
                    key={match.matchId}
                    href={route(`/matches/${match.matchId}`)}
                    className="flex items-center px-3 py-3 border-b border-border-subtle last:border-0 transition-colors hover:bg-page-background"
                  >
                    <div className="flex-1 overflow-hidden">
                      <div className="text-micro text-text-tertiary mb-0.5 truncate uppercase tracking-wider">
                        {match.eventNameZh || match.eventName}
                      </div>
                      <div className="text-body text-text-primary">
                        {match.roundZh || match.round}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        "w-6 h-6 rounded flex items-center justify-center text-micro font-bold transition-all tabular-nums",
                        isWinnerA ? "bg-brand-strong text-white" : "bg-page-background text-text-tertiary"
                      )}>
                        {isWinnerA ? "胜" : "负"}
                      </div>
                      <div className="text-body-lg font-black tabular-nums min-w-[36px] text-center">
                        {match.matchScore}
                      </div>
                      <div className={cn(
                        "w-6 h-6 rounded flex items-center justify-center text-micro font-bold transition-all tabular-nums",
                        !isWinnerA ? "bg-brand-strong text-white" : "bg-page-background text-text-tertiary"
                      )}>
                        {!isWinnerA ? "胜" : "负"}
                      </div>
                      <ChevronRight size={16} className="text-text-tertiary" />
                    </div>
                  </Link>
                );
              })
            )}
          </div>
        </div>
      </div>

      {replaceTarget && (
        <div className="fixed inset-0 z-[70] bg-[rgb(var(--overlay-dark))/0.35] backdrop-blur-sm flex items-center justify-center px-4">
          <div className="w-full max-w-[420px] rounded-lg bg-white border border-border-subtle shadow-xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-4 border-b border-border-subtle">
              <div>
                <h3 className="text-heading-2 font-bold text-text-primary">
                  更换{replaceTarget === "A" ? pA.nameZh || pA.name : pB.nameZh || pB.name}
                </h3>
                <p className="mt-1 text-micro text-text-tertiary">搜索并替换当前对比球员</p>
              </div>
              <button
                type="button"
                onClick={closeReplaceModal}
                className="w-8 h-8 rounded-full flex items-center justify-center text-text-tertiary hover:bg-page-background"
                aria-label="关闭"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-4 border-b border-border-subtle">
              <label className="flex items-center gap-3 bg-page-background rounded-lg px-4 h-12 border border-border-subtle">
                <Search size={18} className="text-text-tertiary" />
                <input
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="搜索球员姓名"
                  className="flex-1 bg-transparent outline-none text-body text-text-primary placeholder:text-text-tertiary"
                />
              </label>
            </div>

            <div className="max-h-[420px] overflow-y-auto">
              {searchLoading ? (
                <div className="py-12 text-center text-text-tertiary">搜索中...</div>
              ) : searchResults.length === 0 ? (
                <div className="py-12 text-center text-text-tertiary">未找到匹配球员</div>
              ) : (
                searchResults.map((player) => (
                  <button
                    key={player.playerId}
                    type="button"
                    onClick={() => handleReplacePlayer(player)}
                    className="w-full flex items-center gap-3 px-4 py-3 border-b border-border-subtle last:border-0 text-left transition-colors hover:bg-page-background"
                  >
                    <PlayerAvatar player={player} size="sm" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-body font-bold text-text-primary">
                          {player.nameZh || player.name}
                        </span>
                        {player.rank != null ? (
                          <span className="shrink-0 text-micro font-semibold text-brand-deep bg-brand-mist/40 px-2 py-0.5 rounded-full">
                            #{player.rank}
                          </span>
                        ) : null}
                      </div>
                      <div className="mt-1 text-micro text-text-tertiary">
                        {player.countryCode || "国家待补"}
                      </div>
                    </div>
                    <ChevronRight size={16} className="shrink-0 text-text-tertiary" />
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-text-tertiary">页面加载中...</div>}>
      <CompareContent />
    </Suspense>
  );
}
