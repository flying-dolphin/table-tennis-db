"use client";

import React, { useState, useRef, useEffect } from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Reusable mock data structure representing a month
const MONTH_DATA = [
  {
    id: 4, name: "April", nameZh: "4月",
    weeks: [
      {
        days: [ { num: 30, out: true }, { num: 31, out: true }, { num: 1 }, { num: 2 }, { num: 3 }, { num: 4 }, { num: 5 } ],
        eventLayers: [ [ { name: "2026澳门单打世界杯", startCol: 3, span: 5, color: "bg-[#A7D9D2] text-[#2C5F58]" } ] ]
      },
      {
        days: [ { num: 6 }, { num: 7 }, { num: 8 }, { num: 9 }, { num: 10 }, { num: 11 }, { num: 12 } ],
        eventLayers: [
          [ { name: "WTT常规挑战赛太原", startCol: 3, span: 5, color: "bg-[#ADE8F4] text-[#0077B6]" } ],
          [ { name: "支线赛", startCol: 3, span: 4, color: "bg-[#FDE2B4] text-[#D48F37]" } ]
        ]
      },
      {
        days: [ { num: 13 }, { num: 14 }, { num: 15 }, { num: 16 }, { num: 17 }, { num: 18 }, { num: 19 } ],
        eventLayers: [
          [ { name: "哈维若夫站", startCol: 1, span: 5, color: "bg-[#FDE2B4] text-[#D48F37]" }, { name: "支线", startCol: 6, span: 2, color: "bg-[#FDE2B4] text-[#D48F37]" } ]
        ]
      },
      {
        days: [ { num: 20 }, { num: 21 }, { num: 22 }, { num: 23 }, { num: 24 }, { num: 25 }, { num: 26 } ],
        eventLayers: [ [ { name: "塞内茨站", startCol: 1, span: 3, color: "bg-[#FDE2B4] text-[#D48F37]" } ] ]
      },
      {
        days: [ { num: 27 }, { num: 28 }, { num: 29 }, { num: 30 }, { num: 1, out: true }, { num: 2, out: true }, { num: 3, out: true } ],
        eventLayers: [ [ { name: "伦敦团体锦标赛", startCol: 2, span: 6, color: "bg-brand-soft text-white" } ] ]
      }
    ]
  },
  {
    id: 5, name: "May", nameZh: "5月",
    weeks: [
      {
        days: [ { num: 27, out:true }, { num: 28, out:true }, { num: 29, out:true }, { num: 30, out:true }, { num: 1 }, { num: 2 }, { num: 3 } ],
        eventLayers: [ [ { name: "沙特大满贯赛", startCol: 5, span: 3, color: "bg-[#1A232C] text-[#D4AF37]" } ] ]
      },
      {
        days: [ { num: 4 }, { num: 5 }, { num: 6 }, { num: 7 }, { num: 8 }, { num: 9 }, { num: 10 } ],
        eventLayers: [ [ { name: "WTT沙特大满贯赛", startCol: 1, span: 7, color: "bg-[#1A232C] text-[#D4AF37]" } ] ]
      },
      {
        days: [ { num: 11 }, { num: 12 }, { num: 13 }, { num: 14 }, { num: 15 }, { num: 16 }, { num: 17 } ],
        eventLayers: []
      },
      {
        days: [ { num: 18 }, { num: 19 }, { num: 20 }, { num: 21 }, { num: 22 }, { num: 23 }, { num: 24 } ],
        eventLayers: [ [ { name: "WTT常规挑战赛曼谷", startCol: 3, span: 5, color: "bg-[#ADE8F4] text-[#0077B6]" } ] ]
      },
      {
        days: [ { num: 25 }, { num: 26 }, { num: 27 }, { num: 28 }, { num: 29 }, { num: 30 }, { num: 31 } ],
        eventLayers: [ [ { name: "WTT曼谷", startCol: 1, span: 3, color: "bg-[#ADE8F4] text-[#0077B6]" } ] ]
      }
    ]
  }
];

export default function EventScroller() {
  const [activeMonthId, setActiveMonthId] = useState(4);

  return (
    <section className="mt-6 relative z-10">
      <div className="flex overflow-x-auto gap-4 px-6 pb-6 pt-2 snap-x snap-mandatory scrollbar-hide shrink-0 items-center">
        {MONTH_DATA.map((month) => {
          const isActive = month.id === activeMonthId;
          return (
            <div
              key={month.id}
              onClick={() => setActiveMonthId(month.id)}
              className={cn(
                "snap-center shrink-0 w-[85vw] max-w-[320px] transition-all duration-500 ease-out cursor-pointer transform origin-center",
                isActive ? "scale-100 opacity-100 shadow-[0_12px_40px_rgba(0,0,0,0.08)]" : "scale-[0.88] opacity-60 shadow-sm"
              )}
            >
              <div className="bg-white rounded-[24px] overflow-hidden border border-border-subtle/50 pointer-events-none">
                {/* Header */}
                <div className={cn("px-4 py-3 flex items-center justify-between transition-colors duration-500", isActive ? "bg-[#1A232C] text-white" : "bg-surface-secondary text-text-primary")}>
                  <div className="text-left">
                    <h2 className="text-[12px] font-bold tracking-widest leading-none">2026赛事日历</h2>
                  </div>
                  <div className="text-right">
                     <p className="text-[12px] font-black tracking-widest">{month.name} <span className="opacity-70 font-normal">| {month.nameZh}</span></p>
                  </div>
                </div>
                
                {/* Days of week */}
                <div className="grid grid-cols-7 text-center pt-2 pb-1.5 bg-surface-primary border-b border-border-subtle">
                  {['一', '二', '三', '四', '五', '六', '日'].map(d => (
                    <span key={d} className="text-[9px] font-bold text-text-tertiary">{d}</span>
                  ))}
                </div>

                {/* Grid Body */}
                <div className="p-1.5 flex flex-col gap-0.5 bg-white">
                  {month.weeks.map((row, i) => (
                    <div key={i} className="relative pt-4 pb-1 min-h-[46px] border-b border-border-subtle/20 last:border-0 rounded-md">
                      {/* Day Numbers Layer */}
                      <div className="grid grid-cols-7 absolute top-0.5 inset-x-0 px-0.5">
                          {row.days.map((d, j) => (
                            <div key={j} className={cn(
                              "text-center text-[10px] font-black", 
                              d.out ? "text-border-strong opacity-40" : "text-text-primary"
                            )}>
                              {d.num}
                            </div>
                          ))}
                      </div>
                      
                      {/* Events Layer */}
                      <div className="relative z-10 px-0.5">
                        {row.eventLayers.map((layer, lIdx) => (
                          <div key={lIdx} className="grid grid-cols-7 gap-x-1 mb-0.5 relative">
                            {layer.map((ev, eIdx) => (
                              <div 
                                key={eIdx}
                                style={{ gridColumnStart: ev.startCol, gridColumnEnd: `span ${ev.span}` }}
                                className={cn(
                                  "rounded-[4px] px-1 py-0.5 text-[8px] font-bold truncate flex items-center shadow-[0_1px_2px_rgba(0,0,0,0.03)]", 
                                  ev.color
                                )}
                              >
                                {ev.name}
                              </div>
                            ))}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
