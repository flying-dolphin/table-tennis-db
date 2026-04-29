"use client";

import React from "react";
import Link from "next/link";
import type { Route } from "next";
import { useRouter, useSearchParams } from "next/navigation";
import { CalendarDays, Search, Trophy, Medal, X } from "lucide-react";
import { Outfit } from "next/font/google";
import {
  ensureEventsHistoryKey,
  readEventsSnapshot,
  writeEventsHistoryKey,
  writeEventsSnapshot,
} from "@/lib/events-history-cache";

import Image from "next/image";

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
  presentationMode: "knockout" | "staged_round_robin" | null;
  hasPresentation: boolean;
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

function presentationBadge(event: EventListItem) {
  if (event.presentationMode === "staged_round_robin") {
    return {
      label: "赛事流程",
      className: "rounded-full bg-state-success/12 px-2 py-0.5 text-micro font-bold text-state-success-text",
    };
  }
  if (event.drawMatches > 0) {
    return {
      label: "有正赛图",
      className: "rounded-full bg-state-success/12 px-2 py-0.5 text-micro font-bold text-state-success-text",
    };
  }
  return {
    label: "比赛记录",
    className: "rounded-full bg-surface-tinted px-2 py-0.5 text-micro font-bold text-text-tertiary",
  };
}

const PAGE_SIZE = 20;
type AgeGroupFilter = "senior" | "non_senior" | "all";
const EVENTS_PAGE_CACHE_LIMIT = 100;

const AGE_GROUP_OPTIONS: Array<{ value: AgeGroupFilter; label: string }> = [
  { value: "senior", label: "成年组" },
  { value: "non_senior", label: "非成年组" },
  { value: "all", label: "全部年龄" },
];

type EventsQueryState = {
  selectedYear: string;
  selectedAgeGroup: AgeGroupFilter;
  keyword: string;
};

type SearchParamReader = {
  get(name: string): string | null;
};

type EventsPageSnapshot = EventsQueryState & {
  debouncedKeyword: string;
  meta: Omit<EventsResponse["data"], "events" | "total" | "hasMore"> | null;
  events: EventListItem[];
  hasMore: boolean;
  total: number;
  scrollTop: number;
};

function normalizeAgeGroup(value: string | null): AgeGroupFilter {
  if (value === "senior" || value === "non_senior" || value === "all") {
    return value;
  }
  return "senior";
}

function readQueryState(searchParams: SearchParamReader): EventsQueryState {
  return {
    selectedYear: searchParams.get("year") || "all",
    selectedAgeGroup: normalizeAgeGroup(searchParams.get("age_group")),
    keyword: (searchParams.get("q") || "").trim(),
  };
}

function buildQueryString(query: EventsQueryState) {
  const params = new URLSearchParams();
  if (query.selectedYear !== "all") {
    params.set("year", query.selectedYear);
  }
  if (query.selectedAgeGroup !== "senior") {
    params.set("age_group", query.selectedAgeGroup);
  }
  const trimmedKeyword = query.keyword.trim();
  if (trimmedKeyword) {
    params.set("q", trimmedKeyword);
  }
  return params.toString();
}

function buildQuerySignature(query: Pick<EventsQueryState, "selectedYear" | "selectedAgeGroup"> & { debouncedKeyword: string }) {
  return JSON.stringify({
    year: query.selectedYear,
    ageGroup: query.selectedAgeGroup,
    keyword: query.debouncedKeyword,
  });
}

import { EventCategoryIcon, getEventCategory } from "@/components/events/EventCategoryIcon";

function EventsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialQueryRef = React.useRef<EventsQueryState>(readQueryState(searchParams));
  const [selectedYear, setSelectedYear] = React.useState<string>(initialQueryRef.current.selectedYear);
  const [selectedAgeGroup, setSelectedAgeGroup] = React.useState<AgeGroupFilter>(initialQueryRef.current.selectedAgeGroup);
  const [keyword, setKeyword] = React.useState(initialQueryRef.current.keyword);
  const [debouncedKeyword, setDebouncedKeyword] = React.useState(initialQueryRef.current.keyword.trim());
  const [meta, setMeta] = React.useState<Omit<EventsResponse["data"], "events" | "total" | "hasMore"> | null>(null);
  const [events, setEvents] = React.useState<EventListItem[]>([]);
  const [hasMore, setHasMore] = React.useState(false);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [ready, setReady] = React.useState(false);
  const listScrollRef = React.useRef<HTMLDivElement>(null);
  const loadMoreRef = React.useRef<HTMLDivElement>(null);
  const historyKeyRef = React.useRef<string | null>(null);
  const restoredFromSnapshotRef = React.useRef(false);
  const loadedQuerySignatureRef = React.useRef<string | null>(null);

  const persistSnapshot = React.useCallback(() => {
    const currentSignature = buildQuerySignature({
      selectedYear,
      selectedAgeGroup,
      debouncedKeyword,
    });

    if (loadedQuerySignatureRef.current !== currentSignature) {
      return;
    }

    const historyKey = historyKeyRef.current ?? ensureEventsHistoryKey();
    if (!historyKey) {
      return;
    }

    historyKeyRef.current = historyKey;
    writeEventsSnapshot<EventsPageSnapshot>(historyKey, {
      selectedYear,
      selectedAgeGroup,
      keyword,
      debouncedKeyword,
      meta,
      events: events.slice(0, EVENTS_PAGE_CACHE_LIMIT),
      hasMore,
      total,
      scrollTop: listScrollRef.current?.scrollTop ?? 0,
    });
  }, [debouncedKeyword, events, hasMore, keyword, meta, selectedAgeGroup, selectedYear, total]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedKeyword(keyword.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [keyword]);

  React.useEffect(() => {
    const historyKey = ensureEventsHistoryKey();
    historyKeyRef.current = historyKey;

    if (!historyKey) {
      setReady(true);
      return;
    }

    const snapshot = readEventsSnapshot<EventsPageSnapshot>(historyKey);
    const queryState = initialQueryRef.current;
    const expectedSignature = buildQuerySignature({
      selectedYear: queryState.selectedYear,
      selectedAgeGroup: queryState.selectedAgeGroup,
      debouncedKeyword: queryState.keyword.trim(),
    });

    if (
      snapshot &&
      buildQuerySignature({
        selectedYear: snapshot.selectedYear,
        selectedAgeGroup: snapshot.selectedAgeGroup,
        debouncedKeyword: snapshot.debouncedKeyword,
      }) === expectedSignature
    ) {
      setSelectedYear(snapshot.selectedYear);
      setSelectedAgeGroup(snapshot.selectedAgeGroup);
      setKeyword(snapshot.keyword);
      setDebouncedKeyword(snapshot.debouncedKeyword);
      setMeta(snapshot.meta);
      setEvents(snapshot.events);
      setHasMore(snapshot.hasMore);
      setTotal(snapshot.total);
      setLoading(false);
      loadedQuerySignatureRef.current = expectedSignature;
      restoredFromSnapshotRef.current = true;

      window.requestAnimationFrame(() => {
        if (listScrollRef.current) {
          listScrollRef.current.scrollTop = snapshot.scrollTop;
        }
      });
    }
    setReady(true);
  }, []);

  React.useEffect(() => {
    if (!ready) return;

    const nextQuery = buildQueryString({
      selectedYear,
      selectedAgeGroup,
      keyword,
    });
    const currentQuery = searchParams.toString();

    if (nextQuery === currentQuery) {
      return;
    }

    const nextHref = nextQuery ? `/events?${nextQuery}` : "/events";
    router.replace(route(nextHref), { scroll: false });
  }, [keyword, ready, router, searchParams, selectedAgeGroup, selectedYear]);

  React.useEffect(() => {
    if (!ready || !historyKeyRef.current) return;
    writeEventsHistoryKey(historyKeyRef.current);
  }, [ready, searchParams]);

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
        loadedQuerySignatureRef.current = buildQuerySignature({
          selectedYear,
          selectedAgeGroup,
          debouncedKeyword,
        });
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [selectedYear, selectedAgeGroup, debouncedKeyword]);

  React.useEffect(() => {
    if (!ready) return;

    if (restoredFromSnapshotRef.current) {
      restoredFromSnapshotRef.current = false;
      return;
    }

    if (listScrollRef.current) {
      listScrollRef.current.scrollTop = 0;
    }
    setHasMore(false);
    void loadEvents(0, true);
  }, [loadEvents, ready]);

  React.useEffect(() => {
    if (!ready || loading || loadingMore) return;
    persistSnapshot();
  }, [loading, loadingMore, persistSnapshot, ready]);

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
      <section className="relative overflow-hidden bg-[#f0f4ff] px-4 pb-3 pt-4">
        <div
          className="absolute inset-0 z-0 pointer-events-none"
          style={{
            backgroundImage: "url('/images/header_bg.jpeg')",
            backgroundSize: "cover",
            backgroundPosition: "center right",
            opacity: 0.7,
          }}
        />
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
            if (ready) {
              persistSnapshot();
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
               {events.map((event) => {
                 const category = getEventCategory(event);

                return (
                  <Link
                    key={event.eventId}
                    href={route(`/events/${event.eventId}`)}
                    onClick={() => {
                      persistSnapshot();
                    }}
                    className="group flex items-center border-b border-black/[0.06] py-3.5 transition-colors last:border-0 hover:bg-black/[0.02]"
                  >
                    <EventCategoryIcon category={category} className="mr-3 h-10 w-10 rounded-[10px]" />
                    <div className="min-w-0 flex-1">
                      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                        <span className="rounded-full bg-black/[0.06] px-2 py-0.5 text-micro font-bold text-text-primary">
                          {event.year}
                        </span>
                        <span className="rounded-full bg-brand-soft/60 px-2 py-0.5 text-micro font-bold text-text-primary">
                          {compactCategory(event)}
                        </span>
                        {/* <span className={badge.className}>{badge.label}</span> */}
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
                );
              })}
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

export default function EventsPage() {
  return (
    <React.Suspense fallback={<main className="min-h-screen bg-gray-50/30" />}>
      <EventsPageContent />
    </React.Suspense>
  );
}
