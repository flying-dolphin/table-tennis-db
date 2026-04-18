import { ChevronRight, Crown } from "lucide-react";
import Image from "next/image";
import { MOCK_RANKINGS } from "@/lib/mock";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Generate 20 items from mock
const EXTENDED_RANKINGS = Array.from({ length: 4 }).flatMap(() => MOCK_RANKINGS).map((player, idx) => ({
  ...player,
  rank: idx + 1
}));

export default function RankingTable() {
  return (
    <section className="mt-8 mb-6 px-6">
      <div className="bg-white/60 backdrop-blur-md rounded-[40px] p-6 shadow-xl shadow-slate-200/50 border border-white/50 relative overflow-hidden">

        {/* Header */}
        <div className="flex justify-between items-end mb-6 px-1 relative z-10">
          <h2 className="text-[20px] font-bold text-slate-700 tracking-tight">世界排名 <span className="text-brand-deep/80 font-medium ml-1 text-[14px]">Top 20</span></h2>
          <button className="flex items-center text-[12px] font-medium text-text-tertiary hover:text-brand-deep transition-all pb-1">
            更多<ChevronRight size={14} className="ml-0.5 relative top-px" strokeWidth={1.5} />
          </button>
        </div>

        {/* List Directly on Tray */}
        <div className="flex flex-col w-full relative z-10">
          {EXTENDED_RANKINGS.map((player, idx) => {
            const isTop1 = idx === 0;
            const changeValue = idx < 5 ? [0, 1, -1, 0, 2][idx] : 0; // Mock trends

            if (isTop1) {
              return (
                <div key={player.rank} className="flex items-center bg-white/80 p-4 border border-white shadow-sm rounded-[28px] relative overflow-hidden cursor-pointer mb-3 transition-colors hover:bg-white">
                  {/* Rank Number */}
                  <div className="w-10 shrink-0 text-center mr-2">
                    <span className="text-[26px] font-bold text-blue-600 pr-1 leading-none">{player.rank}</span>
                  </div>

                  {/* Avatar */}
                  <div className="w-12 h-12 rounded-full bg-gradient-to-br from-brand-primary to-brand-deep flex items-center justify-center shrink-0 shadow-sm border border-white relative z-10">
                    <span className="text-white font-medium text-lg tracking-widest leading-none drop-shadow-sm">
                      {player.name_zh.slice(0, 1)}
                    </span>
                  </div>

                  {/* Player Info */}
                  <div className="ml-3 flex-1 flex flex-col justify-center overflow-hidden">
                    <div className="flex items-center gap-2">
                      <h3 className="text-[16px] font-bold text-slate-800 leading-tight truncate">
                        {player.name_zh}
                      </h3>
                      <span className="shrink-0 text-[10px] font-medium text-slate-500 bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded uppercase tracking-wider">
                        {player.country}
                      </span>
                    </div>
                  </div>

                  {/* Points (Single Line) */}
                  <div className="text-right shrink-0 pr-1 flex items-baseline gap-1">
                    <span className="text-[18px] font-semibold text-slate-800 tracking-tight">
                      {player.points.toLocaleString()}
                    </span>
                    <span className="text-[10px] font-medium text-slate-400">
                      分
                    </span>
                  </div>
                </div>
              );
            }

            return (
              <div key={player.rank} className="flex items-center p-3.5 border-b border-white/40 last:border-0 hover:bg-white/30 transition-colors cursor-pointer rounded-xl">
                <div className="w-10 shrink-0 text-center mr-2">
                  <span className="text-[18px] font-medium text-slate-400 pr-1">{player.rank}</span>
                </div>

                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#8CA8C7] to-[#607D9E] flex items-center justify-center shrink-0 shadow-inner border border-white">
                  <span className="text-white/90 font-medium text-xs tracking-widest leading-none drop-shadow-sm">
                    {player.name_zh.slice(0, 1)}
                  </span>
                </div>

                <div className="ml-3 flex-1 flex items-center gap-2 overflow-hidden">
                  <h3 className="text-[15px] font-semibold text-slate-700 leading-tight truncate">
                    {player.name_zh}
                  </h3>
                  <span className="shrink-0 text-[9px] font-medium text-slate-400 bg-white/50 border border-white/50 px-1.5 py-0.5 rounded uppercase tracking-wider">
                    {player.country}
                  </span>
                  {changeValue !== 0 && (
                    <span className={cn(
                      "shrink-0 text-[10px] font-medium flex items-center",
                      changeValue > 0 ? "text-[#34C759]" : "text-[#FF3B30]"
                    )}>
                      {changeValue > 0 ? "↑" : "↓"}{Math.abs(changeValue)}
                    </span>
                  )}
                </div>

                <div className="text-right shrink-0 pr-2 flex items-baseline gap-1">
                  <span className="text-[16px] font-semibold text-slate-500 tracking-tight">
                    {player.points.toLocaleString()}
                  </span>
                  <span className="text-[9px] font-medium text-slate-400">
                    分
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
