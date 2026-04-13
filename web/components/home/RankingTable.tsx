"use client";

import React from "react";
import Image from "next/image";
import { MOCK_RANKINGS } from "@/lib/mock";

export default function RankingTable() {
  return (
    <section className="mt-8 mb-12">
      <div className="px-8 flex justify-between items-end mb-6">
        <h2 className="text-xl font-bold">ITTF TOP 5</h2>
        <button className="text-sm font-medium text-dark/40 hover:text-dark transition-colors">
          Show Weekly Change
        </button>
      </div>

      <div className="px-8 space-y-4">
        {MOCK_RANKINGS.map((player) => (
          <div 
            key={player.rank}
            className="flex items-center bg-white p-4 rounded-[32px] shadow-sm border border-dark/5 hover:border-mint/30 transition-all duration-300 group"
          >
            {/* Rank Pill */}
            <div className="w-12 h-12 rounded-2xl bg-soft flex items-center justify-center font-bold text-dark group-hover:bg-dark group-hover:text-white transition-colors">
              #{player.rank}
            </div>

            {/* Avatar & Name */}
            <div className="ml-4 flex-1 flex items-center gap-4">
              <div className="relative w-12 h-12 rounded-full overflow-hidden bg-soft grayscale group-hover:grayscale-0 transition-all">
                <Image
                  src={player.avatar}
                  alt={player.name}
                  fill
                  className="object-cover"
                />
              </div>
              <div>
                <h3 className="text-base font-bold text-dark leading-tight">
                  {player.name_zh}
                </h3>
                <p className="text-xs font-medium text-dark/30 uppercase tracking-wider">
                  {player.name}
                </p>
              </div>
            </div>

            {/* Points & Country */}
            <div className="text-right">
              <p className="text-sm font-bold text-dark">
                {player.points.toLocaleString()} <span className="text-[10px] text-dark/30">pts</span>
              </p>
              <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-soft">
                <span className="text-[10px] font-bold text-dark/60">{player.country}</span>
              </div>
            </div>
          </div>
        ))}
        
        <button className="w-full py-6 rounded-[32px] border-2 border-dashed border-dark/10 text-dark/30 font-bold hover:border-dark/20 hover:text-dark/40 transition-all">
          View Top 100 Ranking
        </button>
      </div>
    </section>
  );
}
