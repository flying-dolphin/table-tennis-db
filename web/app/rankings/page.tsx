"use client";

import React, { useState, useEffect } from "react";
import { Check, ChevronLeft, GitCompareArrows, X } from "lucide-react";
import Link from "next/link";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type RankingPlayer = {
  playerId: number;
  rank: number;
  points: number;
  rankChange: number;
  slug: string;
  name: string;
  nameZh: string | null;
  country: string | null;
  countryCode: string;
  avatarFile: string | null;
  winRate: number;
  headToHeadCount: number;
};

type RankingsResponse = {
  code: number;
  message: string;
  data: {
    category: string;
    sortBy: string;
    snapshot: {
      rankingWeek: string;
      rankingDate: string;
    } | null;
    players: RankingPlayer[];
    hasMore: boolean;
    total: number;
  };
};

export default function RankingsPage() {
  const [players, setPlayers] = useState<RankingPlayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [sortBy, setSortBy] = useState("points");
  const [compareMode, setCompareMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const loadMoreRef = React.useRef<HTMLDivElement>(null);

  const loadPlayers = async (offset: number, isInitial = false) => {
    if (isInitial) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }
    try {
      const res = await fetch(`/api/v1/rankings?sort_by=${sortBy}&limit=20&offset=${offset}`);
      const json = (await res.json()) as RankingsResponse;
      if (json.code === 0) {
        if (isInitial) {
          setPlayers(json.data.players);
        } else {
          setPlayers((prev) => [...prev, ...json.data.players]);
        }
        setHasMore(json.data.hasMore);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    loadPlayers(0, true);
  }, [sortBy]);

  useEffect(() => {
    if (!hasMore || loadingMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          loadPlayers(players.length);
        }
      },
      { threshold: 0.1 }
    );
    if (loadMoreRef.current) {
      observer.observe(loadMoreRef.current);
    }
    return () => observer.disconnect();
  }, [hasMore, loadingMore, players.length]);

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((i) => i !== id);
      }
      if (prev.length >= 2) {
        return [prev[1], id];
      }
      return [...prev, id];
    });
  };

  const toggleCompareMode = () => {
    setCompareMode((prev) => {
      if (prev) {
        setSelectedIds([]);
      }
      return !prev;
    });
  };

  const selectedPlayers = players.filter((p) => selectedIds.includes(p.playerId));

  return (
    <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-gray-50/30 pb-32">
      {/* Header */}
      <section className="relative overflow-hidden px-5 pb-5 pt-5 text-white shadow-lg">
        <div className="absolute inset-0 [background:linear-gradient(165deg,#2e2e42_0%,#565568_50%,#767484_100%)]" />
        <div className="absolute inset-0 opacity-50 [background:radial-gradient(circle_at_85%_10%,#4e4868_0%,transparent_60%),radial-gradient(circle_at_15%_90%,#888796_0%,transparent_60%)]" />
        <div className="relative z-10">
          <div className="mb-5 flex items-start gap-3">
            <Link
              href="/"
              aria-label="返回首页"
              className="-ml-2 grid h-11 w-11 shrink-0 place-items-center rounded-full text-white/85 transition-colors hover:bg-white/10 hover:text-white"
            >
              <ChevronLeft size={24} />
            </Link>
            <div className="min-w-0 flex-1 pt-1">
              <h1 className="text-display-sm font-black leading-none tracking-tight">世界排名</h1>
              <p className="mt-2 text-caption font-bold leading-relaxed text-white/55">
                按积分、胜率和交手热度浏览球员，选两位就能开比。
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 overflow-x-auto no-scrollbar pb-1">
            {[
              { id: "points", label: "积分" },
              { id: "win_rate", label: "胜率" },
              { id: "head_to_head_count", label: "交手次数" },
            ].map((item) => (
              <button
                key={item.id}
                onClick={() => setSortBy(item.id)}
                className={cn(
                  "min-h-11 shrink-0 rounded-full border px-4 text-body font-bold transition-all active:scale-95",
                  sortBy === item.id
                    ? "border-white bg-white text-text-primary shadow-sm"
                    : "border-white/15 bg-white/10 text-white/78 backdrop-blur-md hover:bg-white/16 hover:text-white"
                )}
              >
                {item.label}
              </button>
            ))}
            <button
              type="button"
              onClick={toggleCompareMode}
              aria-pressed={compareMode}
              className={cn(
                "ml-auto inline-flex min-h-11 shrink-0 items-center gap-2 rounded-full border px-3.5 text-body font-bold transition-all active:scale-95",
                compareMode
                  ? "border-brand-deep bg-brand-deep text-white shadow-sm"
                  : "border-white/25 bg-white/12 text-white backdrop-blur-md hover:bg-white/18"
              )}
            >
              {compareMode ? <X size={18} /> : <GitCompareArrows size={18} />}
              <span>{compareMode ? "退出选择" : "选择对比"}</span>
            </button>
          </div>
        </div>
      </section>

      {/* List */}
      <div className="px-4 mt-4">
        {loading ? (
          <div className="flex justify-center py-20 text-text-tertiary text-body">加载中...</div>
        ) : (
          <div className="bg-white/60 backdrop-blur-md rounded-lg overflow-hidden border border-white/50 shadow-sm">
            {players.map((player) => (
              <div
                key={player.playerId}
                className={cn(
                  "flex items-center py-3 px-3 transition-colors border-b border-white/40 last:border-0",
                  selectedIds.includes(player.playerId) ? "bg-brand-mist/30" : "hover:bg-white/40"
                )}
              >
                {compareMode && (
                  <label className="mr-2 flex min-h-11 min-w-11 cursor-pointer items-center justify-center rounded-full transition-colors hover:bg-brand-mist/70">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(player.playerId)}
                      onChange={() => toggleSelect(player.playerId)}
                      aria-label={`选择 ${player.nameZh || player.name} 进行对比`}
                      className="peer sr-only"
                    />
                    <span
                      className={cn(
                        "grid h-7 w-7 place-items-center rounded-full border-2 transition-all",
                        selectedIds.includes(player.playerId)
                          ? "border-brand-deep bg-brand-deep text-white shadow-sm"
                          : "border-border-strong bg-white/80 text-transparent shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] peer-focus-visible:border-brand-deep peer-focus-visible:ring-2 peer-focus-visible:ring-brand-deep peer-focus-visible:ring-offset-2"
                      )}
                    >
                      <Check size={15} strokeWidth={3} />
                    </span>
                  </label>
                )}
                
                <div className="w-8 shrink-0 text-center mr-1">
                  <span className={cn(
                    "text-body-lg font-bold tabular-nums",
                    player.rank <= 3 ? "text-brand-strong" : "text-text-tertiary"
                  )}>
                    {player.rank}
                  </span>
                </div>

                <Link href={`/players/${player.slug}`} className="flex flex-1 items-center overflow-hidden">
                  <PlayerAvatar player={player} size="sm" />
                  <div className="ml-3 flex-1 overflow-hidden">
                    <div className="flex items-center gap-1.5">
                      <h3 className="text-body-lg font-bold text-text-primary leading-tight truncate">
                        {player.nameZh || player.name}
                      </h3>
                      <span className="shrink-0 text-micro font-medium text-text-tertiary bg-white/50 border border-white/50 px-1 py-0.5 rounded uppercase">
                        {player.countryCode}
                      </span>
                    </div>
                  </div>
                </Link>

                <div className="text-right shrink-0 min-w-[70px]">
                  <div className="flex flex-col items-end">
                    <span className="text-body-lg font-bold text-text-primary tabular-nums">
                      {sortBy === "win_rate" 
                        ? `${(player.winRate * 100).toFixed(1)}%` 
                        : sortBy === "head_to_head_count"
                        ? player.headToHeadCount
                        : player.points.toLocaleString()}
                    </span>
                    <span className="text-micro text-text-tertiary">
                      {sortBy === "win_rate" ? "胜率" : sortBy === "head_to_head_count" ? "场次" : "积分"}
                    </span>
                  </div>
                </div>
              </div>
            ))}
            <div ref={loadMoreRef} className="py-4 text-center">
              {loadingMore && (
                <span className="text-body text-text-tertiary">加载中...</span>
              )}
              {!loadingMore && !hasMore && players.length > 0 && (
                <span className="text-body text-text-tertiary">已加载全部</span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Compare Action Bar */}
      {compareMode && selectedIds.length > 0 && (
        <div className="fixed bottom-[84px] inset-x-0 z-40 px-4 animate-in fade-in slide-in-from-bottom-4 duration-300">
          <div className="bg-brand-deep/95 backdrop-blur-md text-white rounded-lg py-2.5 px-4 shadow-[0_8px_32px_rgba(30,42,61,0.24)] flex items-center justify-between border border-white/20">
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="flex -space-x-2 shrink-0">
                {selectedPlayers.map((p) => (
                  <PlayerAvatar key={p.playerId} player={p} size="sm" className="ring-2 ring-brand-deep" />
                ))}
              </div>
              <div className="flex flex-col overflow-hidden">
                <span className="text-body font-bold truncate leading-tight">
                  {selectedIds.length === 1 ? "再选一人对比" : `${selectedPlayers[0].nameZh || selectedPlayers[0].name} vs ${selectedPlayers[1].nameZh || selectedPlayers[1].name}`}
                </span>
                <span className="text-micro text-white/60 font-medium tracking-tight">
                  {selectedIds.length === 1 ? "对比需要两名球员" : "已准备好对比数据"}
                </span>
              </div>
            </div>
            
            {selectedIds.length === 2 ? (
              <Link 
                href={`/compare?player_a=${selectedPlayers[0].slug}&player_b=${selectedPlayers[1].slug}`}
                className="bg-white text-brand-deep px-5 py-2 rounded-full text-body font-bold hover:bg-brand-mist active:scale-95 transition-all shrink-0 shadow-sm"
              >
                开始对比
              </Link>
            ) : (
              <div className="w-8 h-8 rounded-full border-2 border-dashed border-white/30 flex items-center justify-center shrink-0">
                <span className="text-micro font-bold text-white/40">2</span>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
