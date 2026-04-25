"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import { Flag } from "@/components/Flag";
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
  avatarFile: string | null;
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
        const response = await fetch("/api/v1/home/rankings?limit=10", { cache: "no-store" });
        const payload = (await response.json()) as RankingsResponse;
        if (!canceled && payload.code === 0) {
          setPlayers(payload.data.players);
        }
      } catch (error) {
        if (!canceled) {
          console.error("Failed to load ranking data:", error);
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
    <section className="px-5">
      <div className="bg-white/60 backdrop-blur-md rounded-lg p-4 shadow-[0_1px_0_rgba(255,255,255,0.5)] border border-white/50 relative overflow-hidden">
        <div className="flex justify-between items-end mb-2.5 px-2 relative z-10">
          <h2 className="text-heading-2 font-bold text-text-secondary tracking-tight">
            世界排名 <span className="text-brand-deep/80 font-medium ml-1 text-body">Top 10</span>
          </h2>
          <a
            href="/rankings"
            className="flex items-center text-caption font-medium text-text-tertiary hover:text-brand-deep transition-all pb-1"
          >
            更多
            <ChevronRight size={14} className="ml-0.5 relative top-px" strokeWidth={1.5} />
          </a>
        </div>

        <div className="flex flex-col w-full relative z-10">
          {loading && (
            <div className="p-4 text-body text-text-tertiary bg-white/60 rounded-md border border-white/60">
              加载中...
            </div>
          )}

          {!loading && players.length === 0 && (
            <div className="p-4 text-body text-text-tertiary bg-white/60 rounded-md border border-white/60">
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
                    className="flex items-center bg-white/80 px-2 py-2 border border-white shadow-sm rounded-lg relative overflow-hidden mb-2 transition-colors hover:bg-white"
                  >
                    <div className="w-9 shrink-0 text-center mr-1">
                      <span className="text-heading-1 font-bold text-brand-strong pr-1 leading-none tabular-nums">{player.rank}</span>
                    </div>

                    <PlayerAvatar player={player} size="md" />

                    <div className="ml-3 flex-1 overflow-hidden">
                      <div className="flex items-center gap-1.5">
                        <h3 className="text-body-lg font-bold text-text-primary leading-tight truncate">
                          {displayName(player)}
                        </h3>
                      <div className="flex items-center gap-1.5 shrink-0">
                          <Flag code={player.countryCode} className="scale-110 origin-center" />
                          <span className="text-micro font-bold text-text-tertiary uppercase tracking-wider">
                            {player.countryCode}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="w-[72px] text-right shrink-0 pr-1 flex flex-col items-end leading-none">
                      <div className="flex items-baseline gap-1">
                        <span className="text-body-lg font-semibold text-text-primary tracking-tight tabular-nums">
                          {player.points.toLocaleString()}
                        </span>
                        <span className="text-micro font-medium text-text-tertiary">分</span>
                      </div>
                      {changeValue !== 0 && (
                        <span
                          className={cn(
                            "mt-1 text-micro font-semibold tabular-nums",
                            changeValue > 0 ? "text-state-success" : "text-state-danger",
                          )}
                        >
                          {changeValue > 0 ? "↑" : "↓"}
                          {Math.abs(changeValue)}
                        </span>
                      )}
                    </div>
                  </Link>
                );
              }

              return (
                <Link
                  key={player.playerId}
                  href={`/players/${player.slug}`}
                  className="flex items-center py-2.5 px-1 hover:bg-white/30 transition-colors rounded-sm"
                >
                  <div className="w-8 shrink-0 text-center mr-1">
                    <span className="text-body-lg font-medium text-text-tertiary pr-0.5 tabular-nums">{player.rank}</span>
                  </div>

                  <PlayerAvatar player={player} size="sm" />

                  <div className="ml-3 flex-1 overflow-hidden">
                    <div className="flex items-center gap-1.5">
                      <h3 className="text-body-lg font-bold text-text-primary leading-tight truncate">
                        {displayName(player)}
                      </h3>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <Flag code={player.countryCode} className="scale-100 origin-center" />
                        <span className="text-micro font-bold text-text-tertiary uppercase tracking-wider">
                          {player.countryCode}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="w-[72px] text-right shrink-0 pr-1 flex flex-col items-end leading-none">
                    <div className="flex items-baseline gap-0.5">
                      <span className="text-body font-semibold text-text-secondary tracking-tight tabular-nums">
                        {player.points.toLocaleString()}
                      </span>
                      <span className="text-micro font-medium text-text-tertiary">分</span>
                    </div>
                    {changeValue !== 0 && (
                      <span
                        className={cn(
                          "mt-1 text-micro font-semibold tabular-nums",
                          changeValue > 0 ? "text-state-success" : "text-state-danger",
                        )}
                      >
                        {changeValue > 0 ? "↑" : "↓"}
                        {Math.abs(changeValue)}
                      </span>
                    )}
                  </div>
                </Link>
              );
            })}
        </div>
      </div>
    </section>
  );
}
