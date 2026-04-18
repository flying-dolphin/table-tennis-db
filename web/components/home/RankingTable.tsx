"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type HomeRankingPlayer = {
  rank: number;
  points: number;
  rankChange: number;
  playerId: number;
  slug: string;
  name: string;
  nameZh: string | null;
  country: string | null;
  countryCode: string;
};

type RankingsResponse = {
  code: number;
  message: string;
  data: {
    category: string;
    snapshot: {
      snapshotId: number;
      rankingWeek: string;
      rankingDate: string;
    } | null;
    players: HomeRankingPlayer[];
  };
};

function displayName(player: HomeRankingPlayer) {
  return player.nameZh?.trim() || player.name;
}

export default function RankingTable() {
  const [players, setPlayers] = useState<HomeRankingPlayer[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let canceled = false;
    async function load() {
      try {
        const response = await fetch("/api/v1/home/rankings?limit=20", { cache: "no-store" });
        const payload = (await response.json()) as RankingsResponse;
        if (!canceled && payload.code === 0) {
          setPlayers(payload.data.players);
        }
      } catch {
        if (!canceled) {
          setPlayers([]);
        }
      } finally {
        if (!canceled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      canceled = true;
    };
  }, []);

  return (
    <section className="mt-2 mb-4 px-4">
      <div className="bg-white/60 backdrop-blur-md rounded-[32px] p-4 shadow-xl shadow-slate-200/50 border border-white/50 relative overflow-hidden">
        <div className="flex justify-between items-end mb-2.5 px-1 relative z-10">
          <h2 className="text-[18px] font-bold text-slate-700 tracking-tight">
            世界排名 <span className="text-brand-deep/80 font-medium ml-1 text-[14px]">Top 20</span>
          </h2>
          <a
            href="/rankings"
            className="flex items-center text-[12px] font-medium text-text-tertiary hover:text-brand-deep transition-all pb-1"
          >
            更多
            <ChevronRight size={14} className="ml-0.5 relative top-px" strokeWidth={1.5} />
          </a>
        </div>

        <div className="flex flex-col w-full relative z-10">
          {loading && (
            <div className="p-4 text-[13px] text-text-tertiary bg-white/60 rounded-2xl border border-white/60">
              加载中...
            </div>
          )}

          {!loading && players.length === 0 && (
            <div className="p-4 text-[13px] text-text-tertiary bg-white/60 rounded-2xl border border-white/60">
              暂无数据
            </div>
          )}

          {!loading &&
            players.map((player, idx) => {
              const isTop1 = idx === 0;
              const changeValue = player.rankChange ?? 0;

              if (isTop1) {
                return (
                  <Link
                    key={player.playerId}
                    href={`/players/${player.slug}`}
                    className="flex items-center bg-white/80 p-2 border border-white shadow-sm rounded-[24px] relative overflow-hidden mb-1.5 transition-colors hover:bg-white"
                  >
                    <div className="w-10 shrink-0 text-center mr-1">
                      <span className="text-[22px] font-bold text-blue-600 pr-1 leading-none">{player.rank}</span>
                    </div>

                    <div className="w-12 h-12 rounded-full bg-gradient-to-br from-brand-primary to-brand-deep flex items-center justify-center shrink-0 shadow-sm border border-white relative z-10">
                      <span className="text-white font-medium text-lg tracking-widest leading-none drop-shadow-sm">
                        {displayName(player).slice(0, 1)}
                      </span>
                    </div>

                    <div className="ml-2.5 flex-1 flex flex-col justify-center overflow-hidden">
                      <div className="flex items-center gap-1.5">
                        <h3 className="text-[15px] font-bold text-slate-800 leading-tight truncate">
                          {displayName(player)}
                        </h3>
                        <span className="shrink-0 text-[10px] font-medium text-slate-500 bg-slate-100 border border-slate-200 px-1 py-0.5 rounded uppercase tracking-wider">
                          {player.countryCode}
                        </span>
                      </div>
                    </div>

                    <div className="text-right shrink-0 pr-1 flex items-baseline gap-1">
                      <span className="text-[16px] font-semibold text-slate-800 tracking-tight">
                        {player.points.toLocaleString()}
                      </span>
                      <span className="text-[10px] font-medium text-slate-400">分</span>
                    </div>
                  </Link>
                );
              }

              return (
                <Link
                  key={player.playerId}
                  href={`/players/${player.slug}`}
                  className="flex items-center py-2 px-1 border-b border-white/40 last:border-0 hover:bg-white/30 transition-colors rounded-xl"
                >
                  <div className="w-9 shrink-0 text-center mr-1">
                    <span className="text-[16px] font-medium text-slate-400 pr-0.5">{player.rank}</span>
                  </div>

                  <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#8CA8C7] to-[#607D9E] flex items-center justify-center shrink-0 shadow-inner border border-white">
                    <span className="text-white/90 font-medium text-xs tracking-widest leading-none drop-shadow-sm">
                      {displayName(player).slice(0, 1)}
                    </span>
                  </div>

                  <div className="ml-2.5 flex-1 flex items-center gap-1.5 overflow-hidden">
                    <h3 className="text-[14px] font-semibold text-slate-700 leading-tight truncate">
                      {displayName(player)}
                    </h3>
                    <span className="shrink-0 text-[9px] font-medium text-slate-400 bg-white/50 border border-white/50 px-1 py-0.5 rounded uppercase tracking-wider">
                      {player.countryCode}
                    </span>
                    {changeValue !== 0 && (
                      <span
                        className={cn(
                          "shrink-0 text-[10px] font-medium flex items-center",
                          changeValue > 0 ? "text-[#34C759]" : "text-[#FF3B30]",
                        )}
                      >
                        {changeValue > 0 ? "↑" : "↓"}
                        {Math.abs(changeValue)}
                      </span>
                    )}
                  </div>

                  <div className="text-right shrink-0 pr-1 flex items-baseline gap-0.5">
                    <span className="text-[14px] font-semibold text-slate-500 tracking-tight">
                      {player.points.toLocaleString()}
                    </span>
                    <span className="text-[9px] font-medium text-slate-400">分</span>
                  </div>
                </Link>
              );
            })}
        </div>
      </div>
    </section>
  );
}
