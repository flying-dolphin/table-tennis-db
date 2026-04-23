"use client";

import React from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowLeft, CalendarDays, ChevronRight, Search, Trophy } from "lucide-react";

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

export default function EventsPage() {
  const [selectedYear, setSelectedYear] = React.useState<string>("all");
  const [keyword, setKeyword] = React.useState("");
  const [debouncedKeyword, setDebouncedKeyword] = React.useState("");
  const [meta, setMeta] = React.useState<Omit<EventsResponse["data"], "events" | "total" | "hasMore"> | null>(null);
  const [events, setEvents] = React.useState<EventListItem[]>([]);
  const [hasMore, setHasMore] = React.useState(false);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const listScrollRef = React.useRef<HTMLDivElement>(null);
  const loadMoreRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedKeyword(keyword.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [keyword]);

  const loadEvents = React.useCallback(async (offset: number, isInitial = false) => {
    if (isInitial) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }
    try {
      const params = new URLSearchParams();
      params.set("year", selectedYear);
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
  }, [selectedYear, debouncedKeyword]);

  React.useEffect(() => {
    if (listScrollRef.current) {
      listScrollRef.current.scrollTop = 0;
    }
    setHasMore(false);
    void loadEvents(0, true);
  }, [loadEvents]);

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

  const subtitle = selectedYear === "all" ? "所有参与积分的赛事" : `${selectedYear} 年赛事`;
  const years = meta?.availableYears ?? [];
  const hasQuery = debouncedKeyword.length > 0;

  return (
    <main
      className="mx-auto flex max-w-lg flex-col overflow-hidden bg-gray-50/30"
      style={{ height: "calc(100dvh - (4rem + env(safe-area-inset-bottom)))" }}
    >
      <section className="relative overflow-hidden px-5 pb-7 pt-5 text-white">
        <div className="absolute inset-0 [background:linear-gradient(45deg,#242536_0%,#45465a_54%,#666477_100%)]" />
        <div className="absolute inset-0 opacity-55 [background:radial-gradient(circle_at_86%_8%,#7b7789_0%,transparent_56%),radial-gradient(circle_at_12%_88%,#252638_0%,transparent_62%)]" />
        <div className="relative z-10">
          <div className="mb-2">
            <Link
              href="/"
              className="mb-4 inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-[12px] font-bold text-white/85 backdrop-blur-sm transition-colors hover:bg-white/15"
            >
              <ArrowLeft size={14} strokeWidth={2} />
              返回
            </Link>
            <div className="min-w-0">
              <p className="text-caption font-bold uppercase tracking-widest text-white/68">EVENTS</p>
              <h1 className="mt-1 text-display font-black leading-none tracking-tight">赛事</h1>
              <p className="mt-2.5 text-caption font-bold leading-relaxed text-white/72">
                {subtitle} · {total} 场
              </p>
            </div>
          </div>
        </div>
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 bottom-0 h-10 [background:linear-gradient(180deg,rgba(255,255,255,0)_0%,rgba(26,30,42,0.5)_100%)]"
        />
      </section>

      <div className="-mt-6 flex min-h-0 flex-1 flex-col overflow-hidden rounded-t-[22px] bg-white/96">
        <div className="z-20 border-b border-black/[0.06] bg-white/90 px-5 py-3.5 backdrop-blur-md">
          <div className="flex items-center gap-2.5">
            <div className="relative w-[130px] shrink-0">
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
            <div className="relative min-w-0 flex-1">
              <Search
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary"
              />
              <input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="搜索赛事名称"
                className="min-h-9 w-full rounded-[10px] border border-black/[0.08] bg-white pl-8 pr-3 text-body text-text-primary shadow-[0_1px_2px_rgba(16,24,40,0.04)] outline-none transition-colors placeholder:text-text-tertiary focus:border-brand-deep/50"
              />
            </div>
          </div>
        </div>

        <div ref={listScrollRef} className="min-h-0 flex-1 overflow-y-auto px-5 pb-28">
          {loading ? (
            <div className="flex justify-center py-20 text-body text-text-tertiary">加载中...</div>
          ) : events.length === 0 ? (
            <div className="rounded-lg border border-black/[0.06] bg-white/80 p-6 text-center shadow-sm">
              <p className="text-body font-bold text-text-secondary">
                {hasQuery ? "没有匹配的赛事" : selectedYear === "all" ? "暂无赛事数据" : "这一年还没翻到赛事"}
              </p>
            </div>
          ) : (
            <div className="space-y-2.5 pt-2">
              {events.map((event) => (
                <Link
                  key={event.eventId}
                  href={route(`/events/${event.eventId}`)}
                  className="group block rounded-[12px] border border-black/[0.06] bg-white px-3.5 py-3.5 transition-colors hover:bg-black/[0.02]"
                >
                  <div className="flex items-start gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-[10px] bg-brand-mist text-brand-strong">
                      <Trophy size={18} />
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
                      <h2 className="line-clamp-2 text-body-lg font-black leading-snug text-text-primary transition-colors group-hover:text-brand-strong">
                        {displayEventName(event)}
                      </h2>
                      <p className="mt-1 text-caption font-semibold text-text-tertiary">
                        {displayDateRange(event.startDate, event.endDate)}
                        {event.location ? ` · ${event.location}` : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <strong className="text-body-lg font-black tabular-nums text-text-primary">
                        {event.importedMatches || event.totalMatches || 0}
                      </strong>
                      <span className="text-micro font-bold text-text-tertiary">场</span>
                      <ChevronRight
                        size={16}
                        className="mt-1 text-text-tertiary transition-colors group-hover:text-brand-strong"
                      />
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
