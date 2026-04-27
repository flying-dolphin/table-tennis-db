"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { animated, useSpring } from "@react-spring/web";
import { useDrag } from "@use-gesture/react";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export type CalendarEvent = {
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
  const rows = 6;
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
    .sort((a, b) => a.year * 12 + a.month - (b.year * 12 + b.month));
}

function renderMonthCardContent(month: MonthCard, isModal: boolean) {
  return (
    <>
      <div className={cn("flex items-center justify-between bg-[rgb(var(--hero-anchor))] text-white", isModal ? "px-5 py-4" : "px-3 py-1.5")}>
        <div className="text-left">
          <h2 className={cn("font-semibold tracking-wide leading-none", isModal ? "text-body" : "text-micro")}>
            {month.year}赛事日历
          </h2>
        </div>
        <div className="text-right">
          <p className={cn("font-bold tracking-wide", isModal ? "text-body" : "text-micro")}>
            {month.name} <span className="opacity-70 font-normal">| {month.nameZh}</span>
          </p>
        </div>
      </div>
      <div className={cn("grid grid-cols-7 text-center border-b border-white/40", isModal ? "px-5 pt-3 pb-2.5 bg-white/20" : "px-3 pt-1 pb-0.5 bg-white/10")}>
        {["一", "二", "三", "四", "五", "六", "日"].map((d) => (
          <span key={d} className={cn("font-medium text-text-tertiary", isModal ? "text-caption" : "text-micro")}>
            {d}
          </span>
        ))}
      </div>
      <div className={cn("flex flex-col bg-transparent", isModal ? "py-2.5 gap-1" : "h-[220px] py-0.5 gap-0")}>
        {month.weeks.map((row, i) => (
          <div key={i} className={cn("relative border-b border-border-subtle/20 last:border-0", isModal ? "px-5 py-2 pb-1.5 min-h-[64px]" : "px-3 py-0.5 h-[36px]")}>
            <div className={cn("grid grid-cols-7", isModal ? "" : "leading-none")}>
              {row.days.map((d, j) => (
                <div
                  key={j}
                  className={cn(
                    "text-center font-semibold",
                    isModal ? "text-body" : "text-[8px]",
                    d.out ? "text-border-strong" : "text-text-primary",
                  )}
                >
                  {d.num}
                </div>
              ))}
            </div>
            <div>
              {row.eventLayers.map((layer, lIdx) => (
                <div key={lIdx} className={cn("grid grid-cols-7 relative", isModal ? "gap-x-1 mb-1" : "gap-x-0.5 mb-0")}>
                  {layer.map((ev, eIdx) => (
                    <div
                      key={eIdx}
                      style={{ gridColumnStart: ev.startCol, gridColumnEnd: `span ${ev.span}` }}
                      className={cn(
                        "font-medium flex items-center shadow-sm overflow-hidden",
                        isModal
                          ? "rounded-[6px] px-1.5 py-1 text-[10px] leading-tight whitespace-normal break-words min-h-[24px]"
                          : "rounded-[3px] px-0.5 py-0 text-[6px] leading-[10px] whitespace-nowrap text-ellipsis min-h-[10px]",
                        ev.color,
                      )}
                      title={ev.name}
                    >
                      {ev.span > 1 && ev.name}
                    </div>
                  ))}
                </div>
              ))}
              {row.hiddenEventCount > 0 && (
                <div className={cn("text-right font-medium text-text-tertiary", isModal ? "text-micro pr-1" : "text-[7px] pr-0.5 leading-none")}>
                  +{row.hiddenEventCount}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

type CarouselTrackProps = {
  monthData: MonthCard[];
  initialIndex: number;
  carouselWidth: number;
  onCardClick: (monthId: string) => void;
};

// Inner carousel — only mounted once monthData, initialIndex, and carouselWidth
// are all known. useSpring is therefore initialized with the correct target
// trackX from the very first render, so the first paint is already on the
// current month and never flashes through January.
const CarouselTrack = React.memo(function CarouselTrack({ monthData, initialIndex, carouselWidth, onCardClick }: CarouselTrackProps) {
  const cardGap = 16;
  const cardWidth = Math.min(carouselWidth * 0.72, 240);
  const slideStep = cardWidth + cardGap;
  const baseTrackX = carouselWidth / 2 - cardWidth / 2;

  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const activeIndexRef = useRef(initialIndex);
  // isDragging is intentionally a ref (not state). The snap effect below
  // depends on activeIndex / layout only — if isDragging were state and lived
  // in that effect's deps, every drag-end (and every stray setIsDragging(false)
  // fired from a tap-after-incomplete-gesture) would re-run the snap and could
  // animate the carousel back to whatever activeIndex currently holds, even
  // when the user has already settled visually somewhere else.
  const isDraggingRef = useRef(false);
  const wheelLockRef = useRef(false);
  const dragStartTrackXRef = useRef(0);
  const hasDraggedRef = useRef(false);
  const suppressClickRef = useRef(false);

  const [{ trackX }, trackApi] = useSpring(() => ({
    trackX: baseTrackX - initialIndex * slideStep,
    config: { tension: 260, friction: 32 },
  }));

  const clampIndex = useCallback(
    (index: number) => {
      const max = Math.max(0, monthData.length - 1);
      return Math.min(Math.max(index, 0), max);
    },
    [monthData.length],
  );

  // Smooth animate on activeIndex change; also re-sync on layout (baseTrackX /
  // slideStep) changes from resize. Skip during drag — drag handler writes
  // trackX directly.
  useEffect(() => {
    if (isDraggingRef.current) return;
    trackApi.start({ trackX: baseTrackX - activeIndex * slideStep });
  }, [activeIndex, baseTrackX, slideStep, trackApi]);

  const setActiveIndexSafe = useCallback(
    (index: number) => {
      const nextIndex = clampIndex(index);
      if (nextIndex === activeIndexRef.current) return;
      activeIndexRef.current = nextIndex;
      setActiveIndex(nextIndex);
    },
    [clampIndex],
  );

  const handleWheel = useCallback(
    (event: React.WheelEvent<HTMLDivElement>) => {
      const absX = Math.abs(event.deltaX);
      const absY = Math.abs(event.deltaY);
      if (absX < 8 || absX <= absY) return;
      event.preventDefault();
      if (wheelLockRef.current) return;
      wheelLockRef.current = true;
      setActiveIndexSafe(activeIndexRef.current + (event.deltaX > 0 ? 1 : -1));
      window.setTimeout(() => {
        wheelLockRef.current = false;
      }, 520);
    },
    [setActiveIndexSafe],
  );

  const bindDrag = useDrag(
    ({ first, last, movement: [mx], velocity: [vx], direction: [dx] }) => {
      if (slideStep <= 0 || monthData.length <= 1) return;
      const maxIndex = monthData.length - 1;
      const minTrackX = baseTrackX - maxIndex * slideStep;
      const maxTrackX = baseTrackX;

      if (first) {
        hasDraggedRef.current = false;
        // Re-derive activeIndex from the actual trackX before each new gesture.
        // Defends against any case where a previous gesture ended without
        // updating activeIndex (e.g. a drag whose `last` event was swallowed):
        // without this, the next tap's `setIsDragging(false)` could fire the
        // snap effect with a stale activeIndex and animate back to the
        // initial month behind the modal.
        const currentTrackX = trackX.get();
        const recoveredIndex = clampIndex(Math.round((baseTrackX - currentTrackX) / slideStep));
        if (recoveredIndex !== activeIndexRef.current) {
          activeIndexRef.current = recoveredIndex;
          setActiveIndex(recoveredIndex);
        }
        dragStartTrackXRef.current = baseTrackX - activeIndexRef.current * slideStep;
      }

      const isIntentionalDrag = Math.abs(mx) > 12;
      const dragDistance = mx * 1.12;
      let nextTrackX = dragStartTrackXRef.current + dragDistance;
      if (nextTrackX > maxTrackX) {
        nextTrackX = maxTrackX + (nextTrackX - maxTrackX) * 0.28;
      } else if (nextTrackX < minTrackX) {
        nextTrackX = minTrackX + (nextTrackX - minTrackX) * 0.28;
      }

      if (!last) {
        if (isIntentionalDrag) {
          hasDraggedRef.current = true;
          suppressClickRef.current = true;
          isDraggingRef.current = true;
          trackApi.start({ trackX: nextTrackX, immediate: true });
        }
        return;
      }

      isDraggingRef.current = false;
      if (!hasDraggedRef.current) return; // real tap — let onClick handle it

      const dir = dx === 0 ? (mx < 0 ? -1 : 1) : dx;
      const projected = nextTrackX + vx * 220 * dir;
      const targetIndex = clampIndex(Math.round((baseTrackX - projected) / slideStep));
      setActiveIndexSafe(targetIndex);
      hasDraggedRef.current = false;
      window.setTimeout(() => {
        suppressClickRef.current = false;
      }, 80);
    },
    {
      axis: "x",
      threshold: 2,
      triggerAllEvents: true,
      preventScroll: true,
      pointer: { touch: true },
    },
  );

  const handleCardClick = useCallback(
    (monthId: string) => {
      if (suppressClickRef.current) return;
      onCardClick(monthId);
    },
    [onCardClick],
  );

  return (
    <div
      onWheel={handleWheel}
      className="overflow-hidden py-3 touch-pan-y select-none"
      {...bindDrag()}
    >
      <animated.div
        className="flex gap-4"
        style={{
          transform: trackX.to((value) => `translateX(${value}px)`),
          willChange: "transform",
        }}
      >
        {monthData.map((month, index) => {
          const isActive = index === activeIndex;
          const t = trackX.to((value) => {
            if (slideStep <= 0) return index === activeIndex ? 1 : 0;
            const center = (baseTrackX - value) / slideStep;
            return Math.max(0, 1 - Math.abs(index - center));
          });

          return (
            <button
              key={month.id}
              data-month-id={month.id}
              data-month-index={index}
              type="button"
              onClick={() => handleCardClick(month.id)}
              className="month-card-wrapper shrink-0 w-[72vw] max-w-[240px] cursor-pointer outline-none [-webkit-tap-highlight-color:transparent] text-left"
            >
              <animated.div
                style={{
                  transform: t.to((value) => `scale(${0.83 + value * 0.22}) translateZ(0)`),
                  opacity: t.to((value) => 0.42 + value * 0.58),
                }}
                className={cn(
                  "bg-white/60 backdrop-blur-md rounded-lg border border-white/50 overflow-hidden pb-0.5 [backface-visibility:hidden] origin-center",
                  isActive
                    ? "shadow-[0_8px_18px_-12px_rgba(30,42,61,0.18)]"
                    : "shadow-none",
                )}
              >
                {renderMonthCardContent(month, false)}
              </animated.div>
            </button>
          );
        })}
      </animated.div>
    </div>
  );
});

export type EventScrollerProps = {
  initialEvents: CalendarEvent[];
};

export default function EventScroller({ initialEvents }: EventScrollerProps) {
  const [expandedMonthId, setExpandedMonthId] = useState<string | null>(null);
  const [carouselWidth, setCarouselWidth] = useState(0);
  const sizerRef = useRef<HTMLDivElement>(null);
  const monthData = useMemo(() => buildMonthCards(initialEvents), [initialEvents]);
  const initialIndex = useMemo(() => {
    const now = new Date();
    const currentMonthId = `${now.getFullYear()}-${now.getMonth() + 1}`;
    const found = monthData.findIndex((month) => month.id === currentMonthId);
    return found >= 0 ? found : 0;
  }, [monthData]);

  useEffect(() => {
    const el = sizerRef.current;
    if (!el) return;
    const update = () => setCarouselWidth(el.clientWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const closeExpandedMonth = useCallback(() => setExpandedMonthId(null), []);

  const expandedMonth = useMemo(
    () => monthData.find((item) => item.id === expandedMonthId) ?? null,
    [expandedMonthId, monthData],
  );

  const canShowCarousel = monthData.length > 0 && carouselWidth > 0;

  return (
    <>
      <section className="relative z-10 w-full">
        <div ref={sizerRef} className="w-full">
          {monthData.length === 0 && (
            <div className="w-[78vw] max-w-[280px] rounded-lg bg-white/70 border border-white/60 p-4 text-body text-text-tertiary">
              暂无赛事日程
            </div>
          )}

          {canShowCarousel && (
            <CarouselTrack
              monthData={monthData}
              initialIndex={initialIndex}
              carouselWidth={carouselWidth}
              onCardClick={setExpandedMonthId}
            />
          )}
        </div>
      </section>

      {expandedMonth && (
        <div
          className="fixed inset-0 z-[60] bg-[rgb(var(--overlay-dark))/0.4] backdrop-blur-xl transition-all duration-300 flex items-center justify-center px-5 opacity-100 pointer-events-auto transform-gpu"
          style={{ WebkitBackdropFilter: "blur(24px)" }}
          onClick={(event) => {
            event.stopPropagation();
            closeExpandedMonth();
          }}
          onPointerDown={(event) => event.stopPropagation()}
          onPointerUp={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            className="w-full max-w-[420px] shadow-[0_25px_60px_rgba(0,0,0,0.3)] border border-white/60 backdrop-blur-2xl rounded-lg overflow-hidden bg-white/80 animate-in zoom-in-95 duration-300 transform-gpu cursor-pointer text-left"
            style={{ WebkitBackdropFilter: "blur(40px)" }}
            onClick={(event) => {
              event.stopPropagation();
              closeExpandedMonth();
            }}
          >
            {renderMonthCardContent(expandedMonth, true)}
          </button>
        </div>
      )}
    </>
  );
}
