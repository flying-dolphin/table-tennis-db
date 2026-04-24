"use client";

import React, { useState, useEffect } from "react";
import { ArrowLeft, Check, GitCompareArrows, X } from "lucide-react";
import Link from "next/link";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const getRankClass = (rank: number) => {
  if (rank === 1) return "rank-badge rank-1";
  if (rank === 2) return "rank-badge rank-2";
  if (rank === 3) return "rank-badge rank-3";
  return "rank-badge rank-default";
};

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

type SortField = "points" | "win_rate";

const SORT_OPTIONS: { id: SortField; label: string }[] = [
  { id: "points", label: "积分" },
  { id: "win_rate", label: "胜率" },
];

export default function RankingsPage() {
  const [players, setPlayers] = useState<RankingPlayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [rankingDate, setRankingDate] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortField>("points");
  const [compareMode, setCompareMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const listScrollRef = React.useRef<HTMLDivElement>(null);
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
        setRankingDate(json.data.snapshot?.rankingDate ?? null);
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
      { root: listScrollRef.current, threshold: 0.1 }
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
  const subtitle = (() => {
    if (!rankingDate) return "更新于2026年4月14日";
    const match = rankingDate.trim().match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/);
    if (!match) return `更新于${rankingDate}`;
    return `更新于${match[1]}年${Number(match[2])}月${Number(match[3])}日`;
  })();

  return (
    <main
      className="mx-auto flex max-w-lg flex-col overflow-hidden bg-gray-50/30"
      style={{ height: "calc(100dvh - (4rem + env(safe-area-inset-bottom)))" }}
    >
      <section className="relative overflow-hidden bg-[radial-gradient(circle_at_right,#d7e6ff_0%,rgba(215,230,255,0.18)_48%,transparent_72%)] px-4 pb-3 pt-4">
        <div className="relative z-10 flex items-end gap-x-4 mb-8 mt-2">
          <h1 className="text-3xl font-bold leading-tight text-slate-950">世界排名</h1>
          <p className="text-[0.9rem] font-medium text-slate-500">
            {subtitle}
          </p>
        </div>
      </section>

      <div className="-mt-6 flex min-h-0 flex-1 flex-col overflow-hidden rounded-t-[22px] bg-white/96">
        {/* Controls */}
        <div className="z-20 border-b border-black/[0.06] bg-white/90 px-5 py-3.5 backdrop-blur-md">
          <div className="flex items-center justify-between gap-3">
            <div className="flex shrink-0 items-center rounded-[12px] bg-black/[0.06] p-1">
              {SORT_OPTIONS.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setSortBy(item.id)}
                  className={cn(
                    "min-h-9 rounded-[8px] px-5 text-body font-bold transition-all active:scale-95",
                    sortBy === item.id
                      ? "bg-white text-text-primary shadow-[0_2px_8px_rgba(17,24,39,0.12)]"
                      : "text-text-secondary hover:text-text-primary"
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={toggleCompareMode}
              aria-pressed={compareMode}
              className={cn(
                "inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-full border px-3.5 text-[13px] font-bold transition-all active:scale-95",
                compareMode
                  ? "border-brand-deep bg-brand-deep text-white shadow-sm"
                  : "border-brand-deep/40 bg-white text-brand-deep hover:bg-brand-mist/30"
              )}
            >
              {compareMode ? <X size={16} /> : <span>⇄</span>}
              <span>{compareMode ? "退出选择" : "选择对比"}</span>
            </button>
          </div>
        </div>

        {/* List */}
        <div ref={listScrollRef} className="min-h-0 flex-1 overflow-y-auto px-5 pb-28">
          {loading ? (
            <div className="flex justify-center py-20 text-text-tertiary text-body">加载中...</div>
          ) : (
            <div>
              {players.map((player) => (
                <div
                  key={player.playerId}
                  className={cn(
                    "flex items-center border-b border-black/[0.06] px-0 py-3.5 transition-colors last:border-0",
                    selectedIds.includes(player.playerId) ? "bg-brand-mist/15" : "hover:bg-black/[0.02]"
                  )}
                >
                  {compareMode && (
                    <label className="mr-2 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors hover:bg-brand-mist/70">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(player.playerId)}
                        onChange={() => toggleSelect(player.playerId)}
                        aria-label={`选择 ${player.nameZh || player.name} 进行对比`}
                        className="peer sr-only"
                      />
                      <span
                        className={cn(
                          "grid h-6 w-6 place-items-center rounded-full border-2 transition-all",
                          selectedIds.includes(player.playerId)
                            ? "border-brand-deep bg-brand-deep text-white shadow-sm"
                            : "border-border-strong bg-white/80 text-transparent shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] peer-focus-visible:border-brand-deep peer-focus-visible:ring-2 peer-focus-visible:ring-brand-deep peer-focus-visible:ring-offset-2"
                        )}
                      >
                        <Check size={13} strokeWidth={3} />
                      </span>
                    </label>
                  )}

                  <div className="mr-2 w-9 shrink-0 text-center">
                    <span className={getRankClass(player.rank)}>
                      {player.rank}
                    </span>
                  </div>

                  {compareMode ? (
                    <button
                      type="button"
                      onClick={() => toggleSelect(player.playerId)}
                      className="flex flex-1 items-center overflow-hidden"
                    >
                      <PlayerAvatar player={player} size="sm" />
                      <div className="ml-3 flex-1 overflow-hidden">
                        <div className="flex items-center gap-1.5">
                          <h3 className="text-body-lg font-bold text-text-primary leading-tight truncate">
                            {player.nameZh || player.name}
                          </h3>
                          {player.countryCode && (
                            <div className={`fg fg-${player.countryCode} shrink-0 scale-90 origin-center`} />
                          )}
                          <span className="shrink-0 text-micro font-medium text-text-tertiary bg-white/50 border border-white/50 px-1 py-0.5 rounded uppercase">
                            {player.countryCode}
                          </span>
                          {player.rankChange !== 0 && (
                            <span
                              className={cn(
                                "text-micro font-semibold tabular-nums",
                                player.rankChange > 0 ? "text-state-success" : "text-state-danger"
                              )}
                            >
                              {player.rankChange > 0 ? "↑" : "↓"}
                              {Math.abs(player.rankChange)}
                            </span>
                          )}
                        </div>
                      </div>
                    </button>
                  ) : (
                    <Link href={`/players/${player.slug}`} className="flex flex-1 items-center overflow-hidden">
                      <PlayerAvatar player={player} size="sm" />
                      <div className="ml-3 flex-1 overflow-hidden">
                        <div className="flex items-center gap-1.5">
                          <h3 className="text-body-lg font-bold text-text-primary leading-tight truncate">
                            {player.nameZh || player.name}
                          </h3>
                          {player.countryCode && (
                            <div className={`fg fg-${player.countryCode} shrink-0 scale-90 origin-center`} />
                          )}
                          <span className="shrink-0 text-micro font-medium text-text-tertiary bg-white/50 border border-white/50 px-1 py-0.5 rounded uppercase">
                            {player.countryCode}
                          </span>
                          {player.rankChange !== 0 && (
                            <span
                              className={cn(
                                "text-micro font-semibold tabular-nums",
                                player.rankChange > 0 ? "text-state-success" : "text-state-danger"
                              )}
                            >
                              {player.rankChange > 0 ? "↑" : "↓"}
                              {Math.abs(player.rankChange)}
                            </span>
                          )}
                        </div>
                      </div>
                    </Link>
                  )}

                  <div className="min-w-[58px] shrink-0 text-right">
                    <div className="flex flex-col items-end">
                      <span className="text-body-lg font-bold text-text-primary tabular-nums">
                        {sortBy === "win_rate"
                          ? `${(player.winRate).toFixed(2)}%`
                          : player.points.toLocaleString()}
                      </span>
                      <span className="text-micro text-text-tertiary">
                        {sortBy === "win_rate" ? "胜率" : "积分"}
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
