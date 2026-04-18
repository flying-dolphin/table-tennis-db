"use client";

import { ChevronRight } from "lucide-react";
import Image from "next/image";
import { MOCK_RANKINGS } from "@/lib/mock";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export default function RankingTable() {
  return (
    <section className="mt-8 mb-12">
      <div className="px-6 flex justify-between items-end mb-4 pr-8">
        <h2 className="text-[22px] font-black text-text-primary tracking-tight">世界排名 <span className="text-brand-deep/80 font-bold ml-1 text-lg">Top 5</span></h2>
        <button className="flex items-center text-[12px] font-bold text-text-tertiary hover:text-brand-deep transition-all">
          查看全部 <ChevronRight size={14} className="ml-0.5" />
        </button>
      </div>

      <div className="px-6 space-y-3 pb-32">
        {MOCK_RANKINGS.map((player, idx) => {
          const changeValue = [0, 1, -1, 0, 2][idx]; // Mock trends
          return (
            <div 
              key={player.rank}
              className="flex items-center bg-gradient-to-br from-white/80 to-white/40 backdrop-blur-2xl p-3.5 rounded-[24px] shadow-[0_20px_50px_-10px_rgba(40,65,105,0.12),inset_0_1px_4px_rgba(255,255,255,1)] border-[1.5px] border-white hover:bg-gradient-to-br hover:from-white hover:to-white/60 hover:shadow-[0_30px_60px_-15px_rgba(40,65,105,0.15)] transition-all duration-300 relative overflow-hidden group"
            >
              {/* Rank Number */}
              <div className="w-10 shrink-0 text-center">
                <span className="text-[22px] font-black text-text-tertiary italic pr-1">{player.rank}</span>
              </div>

              {/* Avatar (Initials gradient instead of broken image) */}
              <div className="w-11 h-11 rounded-full bg-gradient-to-br from-brand-primary to-brand-deep flex items-center justify-center shrink-0 shadow-inner">
                <span className="text-white font-bold text-sm tracking-widest leading-none drop-shadow-sm">
                  {player.name_zh.slice(0, 1)}
                </span>
              </div>

              {/* Player Info (Single Line) */}
              <div className="ml-4 flex-1 flex items-center gap-2.5 overflow-hidden">
                <h3 className="text-[15px] font-bold text-text-primary leading-tight truncate">
                  {player.name_zh}
                </h3>
                <span className="shrink-0 text-[10px] font-bold text-brand-deep/80 bg-brand-soft/30 border border-brand-soft/20 px-1.5 py-0.5 rounded uppercase tracking-wider">
                  {player.country}
                </span>
                {changeValue !== 0 ? (
                  <span className={cn(
                    "shrink-0 text-[10px] font-bold flex items-center",
                    changeValue > 0 ? "text-[#34C759]" : "text-[#FF3B30]"
                  )}>
                    {changeValue > 0 ? "↑" : "↓"}{Math.abs(changeValue)}
                  </span>
                ) : (
                  <span className="shrink-0 text-[10px] font-medium text-text-tertiary">-</span>
                )}
              </div>

              {/* Points */}
              <div className="text-right shrink-0 pr-2 flex items-baseline gap-1">
                <span className="text-lg font-black text-text-primary tracking-tight">
                  {player.points.toLocaleString()}
                </span>
                <span className="text-[11px] font-bold text-text-tertiary">
                  分
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
