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
  startDate: string | null;
  endDate: string | null;
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
type WeekRow = { days: DayCell[]; eventLayers: EventChip[][]; hiddenEventCount: number };
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

const EVENT_COLOR_TOKENS = {
  grandSmashRed: "bg-[rgb(var(--event-grand-smash-bg))] text-[rgb(var(--event-grand-smash-text))]",
  championsPurple: "bg-[rgb(var(--event-champions-bg))] text-[rgb(var(--event-champions-text))]",
  contenderBlue: "bg-[rgb(var(--event-contender-bg))] text-[rgb(var(--event-contender-text))]",
  feederOchre: "bg-[rgb(var(--event-feeder-bg))] text-[rgb(var(--event-feeder-text))]",
  finalsOrangeRed: "bg-[rgb(var(--event-finals-bg))] text-[rgb(var(--event-finals-text))]",
  worldCupCyan: "bg-[rgb(var(--event-world-cup-bg))] text-[rgb(var(--event-world-cup-text))]",
  olympicWttcRed: "bg-[rgb(var(--event-olympic-bg))] text-[rgb(var(--event-olympic-text))]",
  fallbackOther: "bg-[rgb(var(--event-fallback-bg))] text-[rgb(var(--event-fallback-text))]",
} as const;

const EVENT_CATEGORY_COLOR_MAP: Record<string, string> = {
  WTT_GRAND_SMASH: EVENT_COLOR_TOKENS.grandSmashRed,
  WTT_CHAMPIONS: EVENT_COLOR_TOKENS.championsPurple,
  WTT_STAR_CONTENDER: EVENT_COLOR_TOKENS.contenderBlue,
  WTT_CONTENDER: EVENT_COLOR_TOKENS.contenderBlue,
  WTT_FEEDER: EVENT_COLOR_TOKENS.feederOchre,
  WTT_FINALS: EVENT_COLOR_TOKENS.finalsOrangeRed,
  ITTF_WORLD_CUP: EVENT_COLOR_TOKENS.worldCupCyan,
  ITTF_MIXED_TEAM_WORLD_CUP: EVENT_COLOR_TOKENS.worldCupCyan,
  ITTF_WTTC: EVENT_COLOR_TOKENS.olympicWttcRed,
  ITTF_WORLD_TEAM_CHAMPS: EVENT_COLOR_TOKENS.olympicWttcRed,
  OLYMPIC_GAMES: EVENT_COLOR_TOKENS.olympicWttcRed,
};

function resolveEventChipColor(event: CalendarEvent): string {
  const code = (event.categoryCode ?? "").trim().toUpperCase();
  if (code && EVENT_CATEGORY_COLOR_MAP[code]) {
    return EVENT_CATEGORY_COLOR_MAP[code];
  }
  return EVENT_COLOR_TOKENS.fallbackOther;
}

type EventRange = {
  event: CalendarEvent;
  startYear: number;
  startMonth: number;
  startDay: number;
  endYear: number;
  endMonth: number;
  endDay: number;
};

function parseDateString(value: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

function parseDateRange(event: CalendarEvent): EventRange | null {
  const startDate = parseDateString(event.startDate);
  const endDate = parseDateString(event.endDate);
  if (startDate && endDate) {
    return {
      event,
      startYear: startDate.getFullYear(),
      startMonth: startDate.getMonth() + 1,
      startDay: startDate.getDate(),
      endYear: endDate.getFullYear(),
      endMonth: endDate.getMonth() + 1,
      endDay: endDate.getDate(),
    };
  }

  const zh = event.dateRangeZh ?? "";
  const zhMatch = zh.match(/(\d{2})-(\d{1,2})至(\d{2})-(\d{1,2})/);
  if (zhMatch) {
    return {
      event,
      startYear: event.year,
      startMonth: Number(zhMatch[1]),
      startDay: Number(zhMatch[2]),
      endYear: event.year,
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
      startYear: event.year,
      startMonth: MONTH_INDEX_MAP[enRange[2]],
      startDay: Number(enRange[1]),
      endYear: event.year,
      endMonth: MONTH_INDEX_MAP[enRange[4]],
      endDay: Number(enRange[3]),
    };
  }
  const enCompact = en.match(/(\d{1,2})-(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/);
  if (enCompact) {
    const month = MONTH_INDEX_MAP[enCompact[3]];
    return {
      event,
      startYear: event.year,
      startMonth: month,
      startDay: Number(enCompact[1]),
      endYear: event.year,
      endMonth: month,
      endDay: Number(enCompact[2]),
    };
  }
  if (enSingle) {
    const month = MONTH_INDEX_MAP[enSingle[1]];
    return {
      event,
      startYear: event.year,
      startMonth: month,
      startDay: 1,
      endYear: event.year,
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
    ranges.push({ start: weekStart, end: weekEnd });
  }
  return { firstOffset, rows, ranges };
}

function buildMonthWeeks(year: number, month: number, events: EventRange[]): WeekRow[] {
  const dim = daysInMonth(year, month);
  const prevMonth = month === 1 ? 12 : month - 1;
  const prevYear = month === 1 ? year - 1 : year;
  const prevDim = daysInMonth(prevYear, prevMonth);
  const nextMonth = month === 12 ? 1 : month + 1;
  const nextYear = month === 12 ? year + 1 : year;

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
      const currentMonthKey = year * 12 + month;
      const eventStartKey = ev.startYear * 12 + ev.startMonth;
      const eventEndKey = ev.endYear * 12 + ev.endMonth;
      const spansCurrentMonth = eventStartKey <= currentMonthKey && eventEndKey >= currentMonthKey;
      if (!spansCurrentMonth) continue;

      let eventStart = 1;
      let eventEnd = dim;
      const startsInPrevMonth = ev.startYear === prevYear && ev.startMonth === prevMonth;
      const endsInNextMonth = ev.endYear === nextYear && ev.endMonth === nextMonth;
      if (ev.startYear === year && ev.startMonth === month) eventStart = ev.startDay;
      if (startsInPrevMonth) eventStart = ev.startDay - prevDim;
      if (ev.endYear === year && ev.endMonth === month) eventEnd = ev.endDay;
      if (endsInNextMonth) eventEnd = dim + ev.endDay;

      const start = Math.max(range.start, eventStart);
      const end = Math.min(range.end, eventEnd);
      if (start > end) continue;

      const weekStart = row * 7 - firstOffset + 1;
      const startCol = start - weekStart + 1;
      const span = end - start + 1;
      chips.push({
        name: (ev.event.nameZh ?? ev.event.name).trim(),
        startCol,
        span,
        color: resolveEventChipColor(ev.event),
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

    const visibleLayers = layers.slice(0, 2);
    const hiddenEventCount = layers.slice(2).reduce((count, layer) => count + layer.length, 0);
    weeks.push({ days, eventLayers: visibleLayers, hiddenEventCount });
  }

  return weeks;
}

function buildMonthCards(events: CalendarEvent[]) {
  const parsed = events.map(parseDateRange).filter((item): item is EventRange => Boolean(item));
  const monthMap = new Map<string, { year: number; month: number; events: EventRange[] }>();

  for (const item of parsed) {
    const minMonthKey = item.event.year * 12 + 1;
    const maxMonthKey = item.event.year * 12 + 12;
    const startKey = Math.max(minMonthKey, item.startYear * 12 + item.startMonth);
    const endKey = Math.min(maxMonthKey, item.endYear * 12 + item.endMonth);

    for (let monthKey = startKey; monthKey <= endKey; monthKey += 1) {
      const month = monthKey - item.event.year * 12;
      const key = `${item.event.year}-${month}`;
      if (!monthMap.has(key)) {
        monthMap.set(key, {
          year: item.event.year,
          month,
          events: [],
        });
      }
      monthMap.get(key)!.events.push(item);
    }
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
      } catch (error) {
        if (!canceled) {
          console.error("Failed to load calendar events:", error);
          setMonthData([]);
        }
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
      <div className={cn("flex items-center justify-between bg-[rgb(var(--hero-anchor))] text-white", isModal ? "px-6 py-5" : "px-4 py-1.5")}>
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
      <div className={cn("grid grid-cols-7 text-center border-b border-white/40", isModal ? "pt-3 pb-2.5 bg-white/20" : "pt-1 pb-0.5 bg-white/10")}>
        {["一", "二", "三", "四", "五", "六", "日"].map((d) => (
          <span key={d} className={cn("font-medium text-text-tertiary", isModal ? "text-[11px]" : "text-[9px]")}>
            {d}
          </span>
        ))}
      </div>
      <div className={cn("flex flex-col bg-transparent", isModal ? "p-2.5 gap-1" : "p-1 gap-0.5")}>
        {month.weeks.map((row, i) => (
          <div key={i} className={cn("relative border-b border-border-subtle/20 last:border-0 rounded-md", isModal ? "p-2 pb-1.5 min-h-[64px]" : "p-1 pb-0.5 min-h-[36px]")}>
            <div className="grid grid-cols-7 px-1">
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
            <div className="px-0.5">
              {row.eventLayers.map((layer, lIdx) => (
                <div key={lIdx} className={cn("grid grid-cols-7 relative", isModal ? "gap-x-1 mb-1" : "gap-x-1 mb-0.5")}>
                  {layer.map((ev, eIdx) => (
                    <div
                      key={eIdx}
                      style={{ gridColumnStart: ev.startCol, gridColumnEnd: `span ${ev.span}` }}
                      className={cn(
                        "font-medium flex items-center shadow-sm overflow-hidden",
                        isModal
                          ? "rounded-[6px] px-1.5 py-1 text-[9px] leading-tight whitespace-normal break-words min-h-[24px]"
                          : "rounded-[4px] px-1 py-0.5 text-[8px] whitespace-nowrap text-ellipsis",
                        ev.color,
                      )}
                      title={ev.name}
                    >
                      {ev.name}
                    </div>
                  ))}
                </div>
              ))}
              {row.hiddenEventCount > 0 && (
                <div className={cn("text-right font-medium text-text-tertiary", isModal ? "text-[10px] pr-1" : "text-[9px] pr-0.5")}>
                  +{row.hiddenEventCount}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  );

  return (
    <>
      {expandedMonth && (
        <div
          className="fixed inset-0 z-60 bg-[rgb(var(--overlay-dark))/0.4] backdrop-blur-xl transition-all duration-300 flex items-center justify-center px-6 opacity-100 pointer-events-auto transform-gpu"
          style={{ WebkitBackdropFilter: "blur(24px)" }}
          onClick={() => setExpandedMonthId(null)}
        >
          <button
            type="button"
            className="w-full max-w-[420px] shadow-[0_25px_60px_rgba(0,0,0,0.3)] border border-white/60 backdrop-blur-2xl rounded-[40px] overflow-hidden bg-white/80 animate-in zoom-in-95 duration-300 transform-gpu cursor-pointer text-left"
            style={{ WebkitBackdropFilter: "blur(40px)" }}
            onClick={() => setExpandedMonthId(null)}
          >
            {renderCardContent(expandedMonth, true)}
          </button>
        </div>
      )}

      <section className="mt-0 mb-0 relative z-10 w-full">
        <div
          ref={scrollContainerRef}
          className="flex overflow-x-auto gap-4 py-1.5 px-6 snap-x snap-mandatory shrink-0 items-center [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
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
                    "outline-none select-none [-webkit-tap-highlight-color:transparent] transform-gpu",
                    isActive ? "scale-100 opacity-100" : "scale-[0.88] opacity-60",
                  )}
                >
                  <div
                    className={cn(
                      "bg-white/60 backdrop-blur-md rounded-[32px] border border-white/50 overflow-hidden pb-0.5 transition-shadow duration-500 transform-gpu [backface-visibility:hidden]",
                      isActive ? "shadow-[0_10px_25px_-5px_rgba(107,151,203,0.3)]" : "shadow-sm",
                    )}
                  >
                    {renderCardContent(month, false)}
                  </div>
                </button>
              );
            })}
        </div>
      </section>
    </>
  );
}
