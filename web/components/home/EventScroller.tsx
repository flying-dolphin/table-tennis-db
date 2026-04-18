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
        days: [{ num: 30, out: true }, { num: 31, out: true }, { num: 1 }, { num: 2 }, { num: 3 }, { num: 4 }, { num: 5 }],
        eventLayers: [[{ name: "2026澳门单打世界杯", startCol: 3, span: 5, color: "bg-[#A7D9D2] text-[#2C5F58]" }]]
      },
      {
        days: [{ num: 6 }, { num: 7 }, { num: 8 }, { num: 9 }, { num: 10 }, { num: 11 }, { num: 12 }],
        eventLayers: [
          [{ name: "WTT常规挑战赛太原", startCol: 3, span: 5, color: "bg-[#ADE8F4] text-[#0077B6]" }],
          [{ name: "支线赛", startCol: 3, span: 4, color: "bg-[#FDE2B4] text-[#D48F37]" }]
        ]
      },
      {
        days: [{ num: 13 }, { num: 14 }, { num: 15 }, { num: 16 }, { num: 17 }, { num: 18 }, { num: 19 }],
        eventLayers: [
          [{ name: "哈维若夫站", startCol: 1, span: 5, color: "bg-[#FDE2B4] text-[#D48F37]" }, { name: "支线", startCol: 6, span: 2, color: "bg-[#FDE2B4] text-[#D48F37]" }]
        ]
      },
      {
        days: [{ num: 20 }, { num: 21 }, { num: 22 }, { num: 23 }, { num: 24 }, { num: 25 }, { num: 26 }],
        eventLayers: [[{ name: "塞内茨站", startCol: 1, span: 3, color: "bg-[#FDE2B4] text-[#D48F37]" }]]
      },
      {
        days: [{ num: 27 }, { num: 28 }, { num: 29 }, { num: 30 }, { num: 1, out: true }, { num: 2, out: true }, { num: 3, out: true }],
        eventLayers: [[{ name: "伦敦团体锦标赛", startCol: 2, span: 6, color: "bg-brand-soft text-white" }]]
      }
    ]
  },
  {
    id: 5, name: "May", nameZh: "5月",
    weeks: [
      {
        days: [{ num: 27, out: true }, { num: 28, out: true }, { num: 29, out: true }, { num: 30, out: true }, { num: 1 }, { num: 2 }, { num: 3 }],
        eventLayers: [[{ name: "沙特大满贯赛", startCol: 5, span: 3, color: "bg-[#1A232C] text-[#D4AF37]" }]]
      },
      {
        days: [{ num: 4 }, { num: 5 }, { num: 6 }, { num: 7 }, { num: 8 }, { num: 9 }, { num: 10 }],
        eventLayers: [[{ name: "WTT沙特大满贯赛", startCol: 1, span: 7, color: "bg-[#1A232C] text-[#D4AF37]" }]]
      },
      {
        days: [{ num: 11 }, { num: 12 }, { num: 13 }, { num: 14 }, { num: 15 }, { num: 16 }, { num: 17 }],
        eventLayers: []
      },
      {
        days: [{ num: 18 }, { num: 19 }, { num: 20 }, { num: 21 }, { num: 22 }, { num: 23 }, { num: 24 }],
        eventLayers: [[{ name: "WTT常规挑战赛曼谷", startCol: 3, span: 5, color: "bg-[#ADE8F4] text-[#0077B6]" }]]
      },
      {
        days: [{ num: 25 }, { num: 26 }, { num: 27 }, { num: 28 }, { num: 29 }, { num: 30 }, { num: 31 }],
        eventLayers: [[{ name: "WTT曼谷", startCol: 1, span: 3, color: "bg-[#ADE8F4] text-[#0077B6]" }]]
      }
    ]
  }
];

export default function EventScroller() {
  const [activeMonthId, setActiveMonthId] = useState(4);
  const [expandedMonthId, setExpandedMonthId] = useState<number | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting && entry.intersectionRatio > 0.6) {
            const id = Number((entry.target as HTMLElement).dataset.monthId);
            if (id) setActiveMonthId(id);
          }
        });
      },
      { root: container, threshold: [0.6, 0.7, 0.8, 0.9, 1.0] }
    );

    const items = container.querySelectorAll('.month-card-wrapper');
    items.forEach(el => observer.observe(el));

    return () => observer.disconnect();
  }, []);

  const renderCardContent = (month: any, isModal: boolean = false) => (
    <>
      <div className={cn("flex items-center justify-between bg-[#1A232C] text-white", isModal ? "px-6 py-5" : "px-4 py-3")}>
        <div className="text-left">
          <h2 className={cn("font-semibold tracking-wide leading-none", isModal ? "text-[14px]" : "text-[12px]")}>2026赛事日历</h2>
        </div>
        <div className="text-right">
          <p className={cn("font-bold tracking-wide", isModal ? "text-[14px]" : "text-[12px]")}>{month.name} <span className="opacity-70 font-normal">| {month.nameZh}</span></p>
        </div>
      </div>
      <div className={cn("grid grid-cols-7 text-center border-b border-white/40", isModal ? "pt-3 pb-2.5 bg-white/20" : "pt-2 pb-1.5 bg-white/10")}>
        {['一', '二', '三', '四', '五', '六', '日'].map(d => (
          <span key={d} className={cn("font-medium text-text-tertiary", isModal ? "text-[11px]" : "text-[9px]")}>{d}</span>
        ))}
      </div>
      <div className={cn("flex flex-col bg-transparent", isModal ? "p-2.5 gap-1" : "p-1.5 gap-0.5")}>
        {month.weeks.map((row: any, i: number) => (
          <div key={i} className={cn("relative border-b border-border-subtle/20 last:border-0 rounded-md", isModal ? "pt-6 pb-1.5 min-h-[64px]" : "pt-4 pb-1 min-h-[46px]")}>
            <div className="grid grid-cols-7 absolute top-1 inset-x-0 px-1">
              {row.days.map((d: any, j: number) => (
                <div key={j} className={cn(
                  "text-center font-semibold",
                  isModal ? "text-[12px]" : "text-[10px]",
                  d.out ? "text-border-strong opacity-40" : "text-text-primary",
                  d.num === 1 && d.out === false && month.id === 4 ? cn("text-brand-deep bg-brand-soft/50 rounded-full flex items-center justify-center mx-auto", isModal ? "w-6 h-6 -mt-0.5" : "w-5 h-5 -mt-0.5") : ""
                )}>
                  {d.num}
                </div>
              ))}
            </div>
            <div className="relative z-10 px-0.5">
              {row.eventLayers.map((layer: any, lIdx: number) => (
                <div key={lIdx} className={cn("grid grid-cols-7 relative", isModal ? "gap-x-1 mb-1" : "gap-x-1 mb-0.5")}>
                  {layer.map((ev: any, eIdx: number) => (
                    <div
                      key={eIdx}
                      style={{ gridColumnStart: ev.startCol, gridColumnEnd: `span ${ev.span}` }}
                      className={cn(
                        "font-medium truncate flex items-center shadow-sm",
                        isModal ? "rounded-[6px] px-1.5 py-1 text-[9px]" : "rounded-[4px] px-1 py-0.5 text-[8px]",
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
    </>
  );

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 bg-page-background/60 backdrop-blur-md transition-all duration-300 flex items-center justify-center px-6",
          expandedMonthId ? "opacity-100 pointer-events-auto z-40" : "opacity-0 pointer-events-none -z-10"
        )}
      >
        {expandedMonthId && (
          <div
            className="w-full max-w-[420px] shadow-xl shadow-slate-200/50 border border-white/50 backdrop-blur-md rounded-[40px] overflow-hidden bg-white/60 animate-in zoom-in-95 duration-300 transform-gpu cursor-pointer"
            onClick={() => setExpandedMonthId(null)}
          >
            {renderCardContent(MONTH_DATA.find(m => m.id === expandedMonthId), true)}
          </div>
        )}
      </div>

      <section className="mt-4 mb-4 relative z-10 w-full">
        <div
          ref={scrollContainerRef}
          className="flex overflow-x-auto gap-4 py-4 px-6 snap-x snap-mandatory shrink-0 items-center [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
        >
          {MONTH_DATA.map((month) => {
            const isActive = month.id === activeMonthId;

            return (
              <div
                key={month.id}
                data-month-id={month.id}
                onClick={() => {
                  // Direct expansion when clicked to ensure responsiveness
                  setExpandedMonthId(month.id);

                  // Also sync the scroller just in case
                  const el = scrollContainerRef.current?.querySelector(`[data-month-id="${month.id}"]`);
                  el?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
                }}
                className={cn(
                  "month-card-wrapper snap-center shrink-0 w-[78vw] max-w-[280px] transition-all duration-500 ease-[cubic-bezier(0.23,1,0.32,1)] cursor-pointer transform origin-center",
                  isActive ? "scale-100 opacity-100" : "scale-[0.88] opacity-60"
                )}
              >
                <div className={cn(
                  "bg-white/60 backdrop-blur-md rounded-[32px] border border-white/50 overflow-hidden pb-0.5 transition-shadow duration-500",
                  isActive ? "shadow-lg shadow-slate-300/40" : "shadow-sm"
                )}>
                  {renderCardContent(month, false)}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </>
  );
}
