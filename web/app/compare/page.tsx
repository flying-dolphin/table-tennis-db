"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { ChevronLeft, ArrowRightLeft, Trophy, Zap, Globe, Home } from "lucide-react";
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
            !isEqual && (isHigherA === higherIsBetter ? "text-brand-deep scale-105" : "text-text-secondary opacity-60")
          )}>
            {format(valA)}
          </div>
          <div className="w-[1px] h-4 bg-border-subtle mx-4" />
          <div className={cn(
            "flex-1 text-center text-body-lg font-bold tabular-nums",
            !isEqual && (isHigherB === higherIsBetter ? "text-brand-deep scale-105" : "text-text-secondary opacity-60")
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
        <Link href="/rankings" className="text-body text-brand-deep font-medium">更换</Link>
      </div>

      <div className="px-4 py-6">
        {/* Player Cards */}
        <div className="flex items-center gap-3 mb-8">
          <Link href={`/players/${pA.slug}`} className="flex-1 bg-white rounded-lg p-4 flex flex-col items-center shadow-sm border border-white">
            <PlayerAvatar player={pA} size="lg" />
            <h2 className="mt-3 text-body font-bold text-text-primary text-center leading-tight">
              {pA.nameZh || pA.name}
            </h2>
            <span className="mt-1 text-micro font-medium text-text-tertiary bg-page-background px-2 py-0.5 rounded-full uppercase tracking-wider">
              {pA.countryCode}
            </span>
          </Link>
          
          <div className="shrink-0 bg-brand-deep text-white w-10 h-10 rounded-full flex items-center justify-center shadow-lg z-10">
            <ArrowRightLeft size={18} />
          </div>

          <Link href={`/players/${pB.slug}`} className="flex-1 bg-white rounded-lg p-4 flex flex-col items-center shadow-sm border border-white">
            <PlayerAvatar player={pB} size="lg" />
            <h2 className="mt-3 text-body font-bold text-text-primary text-center leading-tight">
              {pB.nameZh || pB.name}
            </h2>
            <span className="mt-1 text-micro font-medium text-text-tertiary bg-page-background px-2 py-0.5 rounded-full uppercase tracking-wider">
              {pB.countryCode}
            </span>
          </Link>
        </div>

        {/* Head to Head Summary */}
        <div className="bg-white rounded-lg p-5 shadow-sm border border-white mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Zap size={18} className="text-brand-deep" />
            <h3 className="text-body font-bold text-text-primary">历史交手</h3>
          </div>
          
          <div className="flex items-center justify-between mb-2">
            <div className="flex flex-col items-center flex-1">
              <span className="text-data-hero font-black text-brand-deep leading-none tabular-nums">{data.headToHeadSummary.playerA.wins}</span>
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
              className="h-full bg-brand-deep" 
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
            <Globe size={18} className="text-brand-deep" />
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
            label="三大赛冠军" 
            valA={pA.stats?.threeTitles ?? 0} 
            valB={pB.stats?.threeTitles ?? 0} 
          />
          <MetricRow 
            label="七大赛冠军" 
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
          </div>
          
          <div className="flex flex-col">
            {data.headToHeadMatches.length === 0 ? (
              <div className="py-10 text-center text-text-tertiary text-body">暂无交手记录</div>
            ) : (
              data.headToHeadMatches.map((match) => {
                const isWinnerA = match.winnerId === pA.playerId;
                return (
                  <div key={match.matchId} className="flex items-center px-3 py-3 border-b border-border-subtle last:border-0">
                    <div className="flex-1 overflow-hidden">
                      <div className="text-micro text-text-tertiary mb-0.5 truncate uppercase tracking-wider">
                        {match.eventYear} {match.eventNameZh || match.eventName}
                      </div>
                      <div className="text-body font-bold text-text-primary">
                        {match.roundZh || match.round}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        "w-6 h-6 rounded flex items-center justify-center text-micro font-bold transition-all tabular-nums",
                        isWinnerA ? "bg-brand-deep text-white" : "bg-page-background text-text-tertiary"
                      )}>
                        {isWinnerA ? "胜" : "负"}
                      </div>
                      <div className="text-body-lg font-black tabular-nums min-w-[36px] text-center">
                        {match.matchScore}
                      </div>
                      <div className={cn(
                        "w-6 h-6 rounded flex items-center justify-center text-micro font-bold transition-all tabular-nums",
                        !isWinnerA ? "bg-brand-deep text-white" : "bg-page-background text-text-tertiary"
                      )}>
                        {!isWinnerA ? "胜" : "负"}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
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
