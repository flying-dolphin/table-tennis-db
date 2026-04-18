"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type CalendarEvent = {
  calendarId: number;
  year: number;
  name: string;
  nameZh: string | null;
  dateRange: string | null;
  dateRangeZh: string | null;
  location: string | null;
  locationZh: string | null;
  status: string | null;
  eventId: number | null;
  categoryCode: string | null;
  categoryNameZh: string | null;
  sortOrder: number | null;
};

type CalendarResponse = {
  code: number;
  message: string;
  data: {
    year: number;
    availableYears: number[];
    events: CalendarEvent[];
  };
};

type DayCell = { num: number; out?: boolean };
type EventChip = { name: string; startCol: number; span: number; color: string };
type WeekRow = { days: DayCell[]; eventLayers: EventChip[][] };
type MonthCard = {
  id: string;
  year: number;
  month: number;
  name: string;
  nameZh: string;
  weeks: WeekRow[];
  eventCount: number;
};

const MONTH_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_ZH = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];
const MONTH_INDEX_MAP: Record<string, number> = {
  Jan: 1,
  Feb: 2,
  Mar: 3,
  Apr: 4,
  May: 5,
  Jun: 6,
  Jul: 7,
  Aug: 8,
  Sep: 9,
  Oct: 10,
  Nov: 11,
  Dec: 12,
};

const EVENT_COLORS = [
  "bg-[#A7D9D2] text-[#2C5F58]",
  "bg-[#ADE8F4] text-[#0077B6]",
  "bg-[#FDE2B4] text-[#D48F37]",
  "bg-[#FCD5CE] text-[#9A3412]",
  "bg-[#D9EAD3] text-[#3F6212]",
  "bg-[#E9D5FF] text-[#6B21A8]",
];

type EventRange = {
  event: CalendarEvent;
  startMonth: number;
  startDay: number;
  endMonth: number;
  endDay: number;
};

function parseDateRange(event: CalendarEvent): EventRange | null {
  const zh = event.dateRangeZh ?? "";
  const zhMatch = zh.match(/(\d{2})-(\d{1,2})至(\d{2})-(\d{1,2})/);
  if (zhMatch) {
    return {
      event,
      startMonth: Number(zhMatch[1]),
      startDay: Number(zhMatch[2]),
      endMonth: Number(zhMatch[3]),
      endDay: Number(zhMatch[4]),
    };
  }

  const en = event.dateRange ?? "";
  const enSingle = en.match(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/);
  const enRange = en.match(/(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*-\s*(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/);
  if (enRange) {
    return {
      event,
      startMonth: MONTH_INDEX_MAP[enRange[2]],
      startDay: Number(enRange[1]),
      endMonth: MONTH_INDEX_MAP[enRange[4]],
      endDay: Number(enRange[3]),
    };
  }
  const enCompact = en.match(/(\d{1,2})-(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/);
  if (enCompact) {
    const month = MONTH_INDEX_MAP[enCompact[3]];
    return {
      event,
      startMonth: month,
      startDay: Number(enCompact[1]),
      endMonth: month,
      endDay: Number(enCompact[2]),
    };
  }
  if (enSingle) {
    const month = MONTH_INDEX_MAP[enSingle[1]];
    return {
      event,
      startMonth: month,
      startDay: 1,
      endMonth: month,
      endDay: 1,
    };
  }
  return null;
}

function daysInMonth(year: number, month: number) {
  return new Date(year, month, 0).getDate();
}

function mondayFirstWeekday(year: number, month: number) {
  const jsDay = new Date(year, month - 1, 1).getDay(); // 0=Sun
  return jsDay === 0 ? 6 : jsDay - 1; // 0=Mon
}

function weekRanges(month: number, year: number) {
  const dim = daysInMonth(year, month);
  const firstOffset = mondayFirstWeekday(year, month);
  const rows = Math.ceil((firstOffset + dim) / 7);
  const ranges: Array<{ start: number; end: number }> = [];
  for (let r = 0; r < rows; r += 1) {
    const weekStart = r * 7 - firstOffset + 1;
    const weekEnd = weekStart + 6;
    ranges.push({ start: Math.max(1, weekStart), end: Math.min(dim, weekEnd) });
  }
  return { firstOffset, rows, ranges };
}

function buildMonthWeeks(year: number, month: number, events: EventRange[]): WeekRow[] {
  const dim = daysInMonth(year, month);
  const prevMonth = month === 1 ? 12 : month - 1;
  const prevYear = month === 1 ? year - 1 : year;
  const prevDim = daysInMonth(prevYear, prevMonth);

  const { firstOffset, rows, ranges } = weekRanges(month, year);
  const weeks: WeekRow[] = [];

  for (let row = 0; row < rows; row += 1) {
    const days: DayCell[] = [];
    for (let col = 0; col < 7; col += 1) {
      const absolute = row * 7 + col;
      const day = absolute - firstOffset + 1;
      if (day < 1) {
        days.push({ num: prevDim + day, out: true });
      } else if (day > dim) {
        days.push({ num: day - dim, out: true });
      } else {
        days.push({ num: day });
      }
    }

    const range = ranges[row];
    const chips: EventChip[] = [];
    for (const ev of events) {
      const spansCurrentMonth = ev.startMonth <= month && ev.endMonth >= month;
      if (!spansCurrentMonth) continue;

      let eventStart = 1;
      let eventEnd = dim;
      if (ev.startMonth === month) eventStart = ev.startDay;
      if (ev.endMonth === month) eventEnd = ev.endDay;

      const start = Math.max(range.start, eventStart);
      const end = Math.min(range.end, eventEnd);
      if (start > end) continue;

      const weekStart = row * 7 - firstOffset + 1;
      const startCol = start - weekStart + 1;
      const span = end - start + 1;
      const colorIndex = ev.event.sortOrder != null ? ev.event.sortOrder % EVENT_COLORS.length : 0;
      chips.push({
        name: (ev.event.nameZh ?? ev.event.name).trim(),
        startCol,
        span,
        color: EVENT_COLORS[colorIndex],
      });
    }

    chips.sort((a, b) => a.startCol - b.startCol || b.span - a.span);
    const layers: EventChip[][] = [];
    for (const chip of chips) {
      let placed = false;
      for (const layer of layers) {
        const overlap = layer.some((existing) => {
          const a1 = existing.startCol;
          const a2 = existing.startCol + existing.span - 1;
          const b1 = chip.startCol;
          const b2 = chip.startCol + chip.span - 1;
          return !(a2 < b1 || b2 < a1);
        });
        if (!overlap) {
          layer.push(chip);
          placed = true;
          break;
        }
      }
      if (!placed) layers.push([chip]);
    }

    weeks.push({ days, eventLayers: layers.slice(0, 2) });
  }

  return weeks;
}

function buildMonthCards(events: CalendarEvent[]) {
  const parsed = events.map(parseDateRange).filter((item): item is EventRange => Boolean(item));
  const monthMap = new Map<string, { year: number; month: number; events: EventRange[] }>();

  for (const item of parsed) {
    const key = `${item.event.year}-${item.startMonth}`;
    if (!monthMap.has(key)) {
      monthMap.set(key, {
        year: item.event.year,
        month: item.startMonth,
        events: [],
      });
    }
    monthMap.get(key)!.events.push(item);
  }

  return Array.from(monthMap.entries())
    .map(([key, value]) => ({
      id: key,
      year: value.year,
      month: value.month,
      name: MONTH_EN[value.month - 1] ?? `${value.month}`,
      nameZh: MONTH_ZH[value.month - 1] ?? `${value.month}月`,
      weeks: buildMonthWeeks(value.year, value.month, value.events),
      eventCount: value.events.length,
    }))
    .sort((a, b) => a.month - b.month);
}

export default function EventScroller() {
  const [activeMonthId, setActiveMonthId] = useState<string>("");
  const [expandedMonthId, setExpandedMonthId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [monthData, setMonthData] = useState<MonthCard[]>([]);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let canceled = false;
    async function loadCalendar() {
      try {
        const response = await fetch("/api/v1/home/calendar", { cache: "no-store" });
        const payload = (await response.json()) as CalendarResponse;
        if (canceled || payload.code !== 0) return;
        const months = buildMonthCards(payload.data.events);
        setMonthData(months);
        if (months[0]) setActiveMonthId(months[0].id);
      } finally {
        if (!canceled) setLoading(false);
      }
    }
    loadCalendar();
    return () => {
      canceled = true;
    };
  }, []);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && entry.intersectionRatio > 0.6) {
            const id = (entry.target as HTMLElement).dataset.monthId;
            if (id) setActiveMonthId(id);
          }
        });
      },
      { root: container, threshold: [0.6, 0.7, 0.8, 0.9, 1.0] },
    );

    const items = container.querySelectorAll(".month-card-wrapper");
    items.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, [monthData.length]);

  const expandedMonth = useMemo(
    () => monthData.find((item) => item.id === expandedMonthId) ?? null,
    [expandedMonthId, monthData],
  );

  const renderCardContent = (month: MonthCard, isModal = false) => (
    <>
      <div className={cn("flex items-center justify-between bg-[#1A232C] text-white", isModal ? "px-6 py-5" : "px-4 py-3")}>
        <div className="text-left">
          <h2 className={cn("font-semibold tracking-wide leading-none", isModal ? "text-[14px]" : "text-[12px]")}>
            {month.year}赛事日历
          </h2>
        </div>
        <div className="text-right">
          <p className={cn("font-bold tracking-wide", isModal ? "text-[14px]" : "text-[12px]")}>
            {month.name} <span className="opacity-70 font-normal">| {month.nameZh}</span>
          </p>
        </div>
      </div>
      <div className={cn("grid grid-cols-7 text-center border-b border-white/40", isModal ? "pt-3 pb-2.5 bg-white/20" : "pt-2 pb-1.5 bg-white/10")}>
        {["一", "二", "三", "四", "五", "六", "日"].map((d) => (
          <span key={d} className={cn("font-medium text-text-tertiary", isModal ? "text-[11px]" : "text-[9px]")}>
            {d}
          </span>
        ))}
      </div>
      <div className={cn("flex flex-col bg-transparent", isModal ? "p-2.5 gap-1" : "p-1.5 gap-0.5")}>
        {month.weeks.map((row, i) => (
          <div key={i} className={cn("relative border-b border-border-subtle/20 last:border-0 rounded-md", isModal ? "pt-6 pb-1.5 min-h-[64px]" : "pt-4 pb-1 min-h-[46px]")}>
            <div className="grid grid-cols-7 absolute top-1 inset-x-0 px-1">
              {row.days.map((d, j) => (
                <div
                  key={j}
                  className={cn(
                    "text-center font-semibold",
                    isModal ? "text-[12px]" : "text-[10px]",
                    d.out ? "text-border-strong opacity-40" : "text-text-primary",
                  )}
                >
                  {d.num}
                </div>
              ))}
            </div>
            <div className="relative z-10 px-0.5">
              {row.eventLayers.map((layer, lIdx) => (
                <div key={lIdx} className={cn("grid grid-cols-7 relative", isModal ? "gap-x-1 mb-1" : "gap-x-1 mb-0.5")}>
                  {layer.map((ev, eIdx) => (
                    <div
                      key={eIdx}
                      style={{ gridColumnStart: ev.startCol, gridColumnEnd: `span ${ev.span}` }}
                      className={cn(
                        "font-medium truncate flex items-center shadow-sm",
                        isModal ? "rounded-[6px] px-1.5 py-1 text-[9px]" : "rounded-[4px] px-1 py-0.5 text-[8px]",
                        ev.color,
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
          expandedMonth ? "opacity-100 pointer-events-auto z-60" : "opacity-0 pointer-events-none -z-10",
        )}
        onClick={() => setExpandedMonthId(null)}
      >
        {expandedMonth && (
          <button
            type="button"
            className="w-full max-w-[420px] shadow-xl shadow-slate-200/50 border border-white/50 backdrop-blur-md rounded-[40px] overflow-hidden bg-white/60 animate-in zoom-in-95 duration-300 transform-gpu cursor-pointer text-left"
            onClick={() => setExpandedMonthId(null)}
          >
            {renderCardContent(expandedMonth, true)}
          </button>
        )}
      </div>

      <section className="mt-4 mb-4 relative z-10 w-full">
        <div
          ref={scrollContainerRef}
          className="flex overflow-x-auto gap-4 py-4 px-6 snap-x snap-mandatory shrink-0 items-center [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
        >
          {loading && (
            <div className="w-[78vw] max-w-[280px] rounded-[32px] bg-white/70 border border-white/60 p-4 text-[13px] text-text-tertiary">
              日程加载中...
            </div>
          )}

          {!loading && monthData.length === 0 && (
            <div className="w-[78vw] max-w-[280px] rounded-[32px] bg-white/70 border border-white/60 p-4 text-[13px] text-text-tertiary">
              暂无赛事日程
            </div>
          )}

          {!loading &&
            monthData.map((month) => {
              const isActive = month.id === activeMonthId;

              return (
                <button
                  key={month.id}
                  data-month-id={month.id}
                  type="button"
                  onClick={() => {
                    setExpandedMonthId(month.id);
                    const el = scrollContainerRef.current?.querySelector(`[data-month-id="${month.id}"]`);
                    el?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
                  }}
                  className={cn(
                    "month-card-wrapper snap-center shrink-0 w-[78vw] max-w-[280px] transition-all duration-500 ease-[cubic-bezier(0.23,1,0.32,1)] cursor-pointer transform origin-center",
                    isActive ? "scale-100 opacity-100" : "scale-[0.88] opacity-60",
                  )}
                >
                  <div
                    className={cn(
                      "bg-white/60 backdrop-blur-md rounded-[32px] border border-white/50 overflow-hidden pb-0.5 transition-shadow duration-500",
                      isActive ? "shadow-lg shadow-slate-300/40" : "shadow-sm",
                    )}
                  >
                    {renderCardContent(month, false)}
                    <div className="px-3 pb-2 text-[10px] text-text-tertiary text-left">重点赛事 {month.eventCount} 项</div>
                  </div>
                </button>
              );
            })}
        </div>
      </section>
    </>
  );
}

