"use client";

import React from "react";
import Link from "next/link";
import type { Route } from "next";
import { CalendarDays, Search, Trophy, X } from "lucide-react";
import { IconFlag, IconOlympics } from "@tabler/icons-react";
import { Outfit } from "next/font/google";

const letterIcon = Outfit({
  subsets: ["latin"],
  weight: "800",
});

function route(path: string) {
  return path as Route;
}

type EventListItem = {
  eventId: number;
  year: number;
  name: string;
  nameZh: string | null;
  eventTypeName: string | null;
  eventKind: string | null;
  eventKindZh: string | null;
  categoryCode: string | null;
  categoryNameZh: string | null;
  ageGroup: string | null;
  eventSeries: string | null;
  totalMatches: number | null;
  startDate: string | null;
  endDate: string | null;
  location: string | null;
  drawMatches: number;
  importedMatches: number;
};

type EventsResponse = {
  code: number;
  data: {
    year: number | null;
    minYear: number;
    availableYears: number[];
    events: EventListItem[];
    total: number;
    hasMore: boolean;
  };
};

function displayEventName(event: Pick<EventListItem, "name" | "nameZh">) {
  return event.nameZh?.trim() || event.name;
}

function displayDateRange(startDate: string | null, endDate: string | null) {
  if (!startDate && !endDate) return "时间待补";
  if (startDate && startDate === endDate) return startDate;
  return [startDate, endDate].filter(Boolean).join(" - ");
}

function compactCategory(event: EventListItem) {
  return event.categoryNameZh || event.eventKindZh || event.eventKind || event.eventTypeName || "赛事";
}

const PAGE_SIZE = 20;
type AgeGroupFilter = "senior" | "non_senior" | "all";
const EVENTS_PAGE_CACHE_KEY = "events-page-cache";
const EVENTS_PAGE_CACHE_LIMIT = 100;

const AGE_GROUP_OPTIONS: Array<{ value: AgeGroupFilter; label: string }> = [
  { value: "senior", label: "成年组" },
  { value: "non_senior", label: "非成年组" },
  { value: "all", label: "全部年龄" },
];

function normalizeSeries(series: string | null) {
  const value = (series ?? "").trim().toUpperCase();
  if (value === "WTT") return "WTT";
  if (value === "ITTF") return "ITTF";
  if (value.startsWith("OLYMPIC")) return "OLYMPIC";
  return "OTHER";
}

function EventSeriesIcon({ series }: { series: string | null }) {
  const key = normalizeSeries(series);
  if (key === "WTT") {
    return (
      <span className={`${letterIcon.className} text-[16px] leading-none tracking-tighter`}>
        W
      </span>
    );
  }
  if (key === "ITTF") {
    return <Trophy size={20} strokeWidth={3} />;
  }
  if (key === "OLYMPIC") {
    return <IconOlympics size={28} stroke={2.2} />;
  }
  return <IconFlag size={20} stroke={3} />;
}

export default function EventsPage() {
  const [selectedYear, setSelectedYear] = React.useState<string>("all");
  const [selectedAgeGroup, setSelectedAgeGroup] = React.useState<AgeGroupFilter>("senior");
  const [keyword, setKeyword] = React.useState("");
  const [debouncedKeyword, setDebouncedKeyword] = React.useState("");
  const [meta, setMeta] = React.useState<Omit<EventsResponse["data"], "events" | "total" | "hasMore"> | null>(null);
  const [events, setEvents] = React.useState<EventListItem[]>([]);
  const [hasMore, setHasMore] = React.useState(false);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [restored, setRestored] = React.useState(false);
  const listScrollRef = React.useRef<HTMLDivElement>(null);
  const loadMoreRef = React.useRef<HTMLDivElement>(null);
  const restoredFromCacheRef = React.useRef(false);

  const persistCache = React.useCallback(() => {
    try {
      window.sessionStorage.setItem(
        EVENTS_PAGE_CACHE_KEY,
        JSON.stringify({
          selectedYear,
          selectedAgeGroup,
          keyword,
          debouncedKeyword,
          meta,
          events: events.slice(0, EVENTS_PAGE_CACHE_LIMIT),
          hasMore,
          total,
          scrollTop: listScrollRef.current?.scrollTop ?? 0,
        }),
      );
    } catch (err) {
      console.error(err);
    }
  }, [debouncedKeyword, events, hasMore, keyword, meta, selectedAgeGroup, selectedYear, total]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedKeyword(keyword.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [keyword]);

  React.useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem(EVENTS_PAGE_CACHE_KEY);
      if (!raw) {
        setRestored(true);
        return;
      }

      const cache = JSON.parse(raw) as {
        selectedYear?: string;
        selectedAgeGroup?: AgeGroupFilter;
        keyword?: string;
        debouncedKeyword?: string;
        meta?: Omit<EventsResponse["data"], "events" | "total" | "hasMore"> | null;
        events?: EventListItem[];
        hasMore?: boolean;
        total?: number;
        scrollTop?: number;
      };

      setSelectedYear(cache.selectedYear ?? "all");
      setSelectedAgeGroup(cache.selectedAgeGroup ?? "senior");
      setKeyword(cache.keyword ?? "");
      setDebouncedKeyword(cache.debouncedKeyword ?? "");
      setMeta(cache.meta ?? null);
      setEvents(cache.events ?? []);
      setHasMore(cache.hasMore ?? false);
      setTotal(cache.total ?? 0);
      setLoading(false);
      restoredFromCacheRef.current = Array.isArray(cache.events);

      window.requestAnimationFrame(() => {
        if (listScrollRef.current && typeof cache.scrollTop === "number") {
          listScrollRef.current.scrollTop = cache.scrollTop;
        }
      });
    } catch (err) {
      console.error(err);
    } finally {
      setRestored(true);
    }
  }, []);

  React.useEffect(() => {
    if (!restored) return;
    persistCache();
  }, [persistCache, restored]);

  const loadEvents = React.useCallback(async (offset: number, isInitial = false) => {
    if (isInitial) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }
    try {
      const params = new URLSearchParams();
      params.set("year", selectedYear);
      params.set("age_group", selectedAgeGroup);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(offset));
      if (debouncedKeyword) {
        params.set("q", debouncedKeyword);
      }
      const res = await fetch(`/api/v1/events?${params.toString()}`);
      const json = (await res.json()) as EventsResponse;
      if (json.code === 0) {
        const { events: pageEvents, hasMore: more, total: nextTotal, ...nextMeta } = json.data;
        setMeta(nextMeta);
        if (isInitial) {
          setEvents(pageEvents);
        } else {
          setEvents((prev) => [...prev, ...pageEvents]);
        }
        setHasMore(more);
        setTotal(nextTotal);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [selectedYear, selectedAgeGroup, debouncedKeyword]);

  React.useEffect(() => {
    if (!restored) return;

    if (restoredFromCacheRef.current) {
      restoredFromCacheRef.current = false;
      return;
    }

    if (listScrollRef.current) {
      listScrollRef.current.scrollTop = 0;
    }
    setHasMore(false);
    void loadEvents(0, true);
  }, [loadEvents, restored]);

  React.useEffect(() => {
    if (!hasMore || loading || loadingMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          void loadEvents(events.length);
        }
      },
      { root: listScrollRef.current, threshold: 0.1 },
    );
    if (loadMoreRef.current) {
      observer.observe(loadMoreRef.current);
    }
    return () => observer.disconnect();
  }, [events.length, hasMore, loadEvents, loading, loadingMore]);

  const ageGroupLabel = AGE_GROUP_OPTIONS.find((item) => item.value === selectedAgeGroup)?.label ?? "成年组";
  const subtitle = selectedYear === "all" ? `${ageGroupLabel}赛事` : `${selectedYear} 年${ageGroupLabel}赛事`;
  const years = meta?.availableYears ?? [];
  const hasQuery = debouncedKeyword.length > 0;

  return (
    <main
      className="mx-auto flex max-w-lg flex-col overflow-hidden bg-gray-50/30"
      style={{ height: "calc(100dvh - (4rem + env(safe-area-inset-bottom)))" }}
    >
      <section className="relative overflow-hidden bg-[radial-gradient(circle_at_right,#d7e6ff_0%,rgba(215,230,255,0.18)_48%,transparent_72%)] px-4 pb-3 pt-4">
        <div className="relative z-10 flex items-end gap-x-4 mb-8 mt-2">
          <h1 className="text-3xl font-bold leading-tight text-slate-950">赛事</h1>
          <p className="text-[0.9rem] font-medium text-slate-500">
            {subtitle} · {total} 场
          </p>
        </div>
      </section>

      <div className="-mt-6 flex min-h-0 flex-1 flex-col overflow-hidden rounded-t-[22px] bg-white/96">
        <div className="z-20 border-b border-black/[0.06] bg-white/90 px-5 py-3.5 backdrop-blur-md">
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2.5">
              <div className="relative flex-1">
                <CalendarDays
                  size={15}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary"
                />
                <select
                  value={selectedYear}
                  onChange={(event) => setSelectedYear(event.target.value)}
                  className="min-h-9 w-full appearance-none rounded-[10px] border border-black/[0.08] bg-white pl-8 pr-8 text-body font-semibold text-text-primary shadow-[0_1px_2px_rgba(16,24,40,0.04)] outline-none transition-colors focus:border-brand-deep/50"
                >
                  <option value="all">全部年份</option>
                  {years.map((year) => (
                    <option key={year} value={String(year)}>
                      {year}
                    </option>
                  ))}
                </select>
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-micro text-text-tertiary">
                  ▼
                </span>
              </div>
              <div className="relative flex-1">
                <select
                  value={selectedAgeGroup}
                  onChange={(event) => setSelectedAgeGroup(event.target.value as AgeGroupFilter)}
                  className="min-h-9 w-full appearance-none rounded-[10px] border border-black/[0.08] bg-white px-3 pr-8 text-body font-semibold text-text-primary shadow-[0_1px_2px_rgba(16,24,40,0.04)] outline-none transition-colors focus:border-brand-deep/50"
                >
                  {AGE_GROUP_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-micro text-text-tertiary">
                  ▼
                </span>
              </div>
            </div>
            <div className="relative w-full">
              <Search
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary"
              />
              <input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="搜索赛事名称"
                className="min-h-9 w-full rounded-[10px] border border-black/[0.08] bg-white pl-8 pr-8 text-body text-text-primary shadow-[0_1px_2px_rgba(16,24,40,0.04)] outline-none transition-colors placeholder:text-text-tertiary focus:border-brand-deep/50"
              />
              {keyword && (
                <button
                  type="button"
                  onClick={() => setKeyword("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 flex h-5 w-5 items-center justify-center rounded-full text-text-tertiary transition-colors hover:bg-black/[0.06] hover:text-text-secondary"
                >
                  <X size={14} />
                </button>
              )}
            </div>
          </div>
        </div>

        <div
          ref={listScrollRef}
          onScroll={() => {
            if (restored) {
              persistCache();
            }
          }}
          className="min-h-0 flex-1 overflow-y-auto px-5 pb-28"
        >
          {loading ? (
            <div className="flex justify-center py-20 text-body text-text-tertiary">加载中...</div>
          ) : events.length === 0 ? (
            <div className="rounded-lg border border-black/[0.06] bg-white/80 p-6 text-center shadow-sm">
              <p className="text-body font-bold text-text-secondary">
                {hasQuery ? "没有匹配的赛事" : selectedYear === "all" ? "暂无赛事数据" : "这一年还没翻到赛事"}
              </p>
            </div>
          ) : (
            <div>
              {events.map((event) => (
                <Link
                  key={event.eventId}
                  href={route(`/events/${event.eventId}`)}
                  onClick={() => {
                    persistCache();
                  }}
                  className="group flex items-center border-b border-black/[0.06] py-3.5 transition-colors last:border-0 hover:bg-black/[0.02]"
                >
                  <div className="mr-3 grid h-10 w-10 shrink-0 place-items-center rounded-[10px] bg-brand-mist text-brand-strong">
                    <EventSeriesIcon series={event.eventSeries} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                      <span className="rounded-full bg-black/[0.06] px-2 py-0.5 text-micro font-bold text-text-primary">
                        {event.year}
                      </span>
                      <span className="rounded-full bg-brand-soft/60 px-2 py-0.5 text-micro font-bold text-text-primary">
                        {compactCategory(event)}
                      </span>
                      {event.drawMatches > 0 ? (
                        <span className="rounded-full bg-state-success/12 px-2 py-0.5 text-micro font-bold text-state-success-text">
                          有正赛图
                        </span>
                      ) : (
                        <span className="rounded-full bg-surface-tinted px-2 py-0.5 text-micro font-bold text-text-tertiary">
                          比赛记录
                        </span>
                      )}
                    </div>
                    <h2 className="line-clamp-2 text-body-lg font-bold leading-tight text-text-primary transition-colors group-hover:text-brand-strong">
                      {displayEventName(event)}
                    </h2>
                    <p className="mt-1 text-caption font-semibold text-text-tertiary">
                      {displayDateRange(event.startDate, event.endDate)}
                      {event.location ? ` · ${event.location}` : ""}
                    </p>
                  </div>
                  <div className="ml-2 min-w-[58px] shrink-0 text-right">
                    <div className="flex flex-col items-end">
                      <span className="text-body-lg font-bold tabular-nums text-text-primary">
                        {event.importedMatches || event.totalMatches || 0}
                      </span>
                      <span className="text-micro text-text-tertiary">场</span>
                    </div>
                  </div>
                </Link>
              ))}
              <div ref={loadMoreRef} className="py-4 text-center">
                {loadingMore ? (
                  <span className="text-body text-text-tertiary">加载中...</span>
                ) : !hasMore ? (
                  <span className="text-body text-text-tertiary">已加载全部</span>
                ) : null}
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
