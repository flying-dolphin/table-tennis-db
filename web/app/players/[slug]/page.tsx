"use client";

import React, { useDeferredValue, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowUpRight, ChevronRight, ChevronDown, List, Search, X, UsersRound } from "lucide-react";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import { PlayerBackButton } from "@/components/player/PlayerBackButton";
import "@/public/images/flags_local.css";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type EventRecord = {
  eventId: number;
  eventName: string | null;
  eventNameZh: string | null;
  date: string | null;
  eventCategorySortOrder: number | null;
  subEventTypeCode: string | null;
  subEventNameZh: string | null;
  result: string | null;
  isChampion: boolean;
};

type Player = {
  playerId: number;
  slug: string;
  name: string;
  nameZh: string | null;
  country: string | null;
  countryCode: string | null;
  gender: string | null;
  birthYear: number | null;
  age: number | null;
  styleZh: string | null;
  rank: number | null;
  rankChange: number | null;
  points: number | null;
  careerBestRank: number | null;
  yearEvents: number | null;
  yearMatches: number | null;
  yearWins: number | null;
  avatarFile: string | null;
  avatarUrl: string | null;
};

type PlayerStats = {
  eventsTotal: number;
  sevenEvents: number;
  sevenFinals: number;
  winRate: number | null;
  foreignWinRate: number | null;
  domesticWinRate: number | null;
  allThreeTitles: number;
  singleThreeTitles: number;
  allSevenTitles: number;
  singleSevenTitles: number;
};

type RecentMatch = {
  matchId: number;
  eventName: string | null;
  eventNameZh: string | null;
  date: string | null;
  opponentName: string | null;
  opponentCountry: string | null;
  matchScore: string | null;
  didWin: boolean;
};

type TopOpponent = {
  playerId: number | null;
  slug: string | null;
  name: string;
  nameZh: string | null;
  countryCode: string | null;
  matches: number;
  winRate: number | null;
  latestDate: string | null;
};

type PlayerDetail = {
  player: Player;
  stats: PlayerStats;
  recentMatches: RecentMatch[];
  events: EventRecord[];
};

type OpponentSortField = "matches" | "winRate";

type OpponentSortOrder = "asc" | "desc";

type OpponentResponse = {
  items: TopOpponent[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
  sortBy: OpponentSortField;
  sortOrder: OpponentSortOrder;
  query: string;
};

type EventTierFilter = "all" | "three" | "seven";

type EventSubTypeFilter = "all" | "WS" | "WD" | "XD" | "team";

const subEventNames: Record<string, string> = {
  WS: '女子单打',
  MS: '男子单打',
  WD: '女子双打',
  MD: '男子双打',
  XD: '混合双打',
  XT: '混合团队',
  WT: '女子团体',
  MT: '男子团体',
};

function route(path: string) {
  return path as Route;
}

function displayPlayerName(player: Pick<Player, 'name' | 'nameZh'>) {
  return player.nameZh?.trim() || player.name;
}

function displayEventName(event: Pick<EventRecord, 'eventName' | 'eventNameZh'> | Pick<RecentMatch, 'eventName' | 'eventNameZh'>) {
  return event.eventNameZh?.trim() || event.eventName || '未命名赛事';
}

function displayDate(value: string | null) {
  if (!value) return '时间待补';
  if (/^\d{4}$/.test(value)) return `${value} 年`;

  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

function formatNumber(value: number | null | undefined) {
  if (value == null) return '-';
  return new Intl.NumberFormat('zh-CN').format(value);
}

function formatPercent(value: number | null | undefined) {
  if (value == null) return '-';
  return `${Number(value).toFixed(Number.isInteger(value) ? 0 : 1)}%`;
}

function displayBio(player: Player) {
  const parts: string[] = [];
  if (player.birthYear) {
    parts.push(`${player.birthYear}年出生${player.age ? ` (${player.age}岁)` : ''}`);
  } else if (player.age) {
    parts.push(`${player.age} 岁`);
  }
  return parts.join(' ') || '-';
}

function rankChangeLabel(value: number | null) {
  if (value == null || value === 0) return '排名保持';
  return value > 0 ? `上升 ${value}` : `下降 ${Math.abs(value)}`;
}

function subEventLabel(event: EventRecord) {
  return event.subEventNameZh || subEventNames[event.subEventTypeCode ?? ''] || event.subEventTypeCode || '项目待补';
}

function matchesEventTier(event: EventRecord, filter: EventTierFilter) {
  if (filter === "all") return true;
  const sortOrder = event.eventCategorySortOrder;
  if (sortOrder == null) return false;
  if (filter === "three") return sortOrder >= 1 && sortOrder <= 5;
  return sortOrder >= 1 && sortOrder <= 9;
}

function matchesSubEventFilter(event: EventRecord, filter: EventSubTypeFilter) {
  if (filter === "all") return true;
  if (filter === "team") {
    return event.subEventTypeCode === "WT" || event.subEventTypeCode === "XT";
  }
  return event.subEventTypeCode === filter;
}

function genderLabel(value: string | null) {
  if (!value) return '待补';
  if (value.toLowerCase() === 'female') return '女';
  if (value.toLowerCase() === 'male') return '男';
  return value;
}

function SectionHeader({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3 px-1">
      <div>
        <h2 className="text-heading-2 font-black tracking-tight text-text-primary">{title}</h2>
        {hint ? <p className="mt-0.5 text-caption font-medium text-text-tertiary">{hint}</p> : null}
      </div>
    </div>
  );
}

type RecordsTab = "events" | "opponents";

function RecordsTabs({ activeTab, onChange }: { activeTab: RecordsTab; onChange: (tab: RecordsTab) => void }) {
  return (
    <div className="flex justify-between border-b border-border-subtle px-8">
      <button
        type="button"
        onClick={() => onChange("events")}
        className={cn(
          "relative flex h-12 items-center justify-center gap-2 px-4 text-body font-bold transition-colors",
          activeTab === "events" ? "text-brand-strong" : "text-text-tertiary hover:text-text-secondary",
        )}
      >
        <List size={16} />
        比赛记录
        <span
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute inset-x-4 bottom-0 h-[3px] rounded-full transition-all",
            activeTab === "events" ? "bg-brand-strong" : "bg-transparent",
          )}
        />
      </button>
      <button
        type="button"
        onClick={() => onChange("opponents")}
        className={cn(
          "relative flex h-12 items-center justify-center gap-2 px-4 text-body font-bold transition-colors",
          activeTab === "opponents" ? "text-brand-strong" : "text-text-tertiary hover:text-text-secondary",
        )}
      >
        <UsersRound size={18} />
        对手
        <span
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute inset-x-4 bottom-0 h-[3px] rounded-full transition-all",
            activeTab === "opponents" ? "bg-brand-strong" : "bg-transparent",
          )}
        />
      </button>
    </div>
  );
}

function EmptyState({ title, action = '想要' }: { title: string; action?: string }) {
  return (
    <div className="rounded-lg border border-white/60 bg-white/55 p-5 text-center shadow-sm">
      <p className="text-body font-bold text-text-secondary">{title}</p>
      <Link
        href={route('/search')}
        className="mt-3 inline-flex items-center rounded-full border border-border-subtle bg-white/75 px-4 py-2 text-caption font-bold text-brand-strong shadow-sm transition-colors hover:bg-white"
      >
        {action}
        <ArrowUpRight size={13} className="ml-1" strokeWidth={2} />
      </Link>
    </div>
  );
}

function PlayerHero({ player }: { player: Player }) {
  return (
    <section className="relative overflow-hidden px-5 pb-10 pt-5 text-white shadow-lg">
      <div className="absolute inset-0 [background:linear-gradient(45deg,#242536_0%,#45465a_54%,#666477_100%)]" />
      <div className="absolute inset-0 opacity-55 [background:radial-gradient(circle_at_86%_8%,#7b7789_0%,transparent_56%),radial-gradient(circle_at_12%_88%,#252638_0%,transparent_62%)]" />
      <div className="relative z-10">
        <PlayerBackButton />

        <div className="flex items-end gap-5">
          <PlayerAvatar
            player={{
              playerId: player.playerId,
              name: player.name,
              nameZh: player.nameZh,
              avatarFile: player.avatarFile,
            }}
            size="lg"
            className="h-28 w-28 border-white/70 ring-4 ring-white/15"
          />

          <div className="min-w-0 flex-1 pb-1">
            <div className="flex flex-col gap-1">
              <div className="flex items-end gap-3">
                <h1 className="truncate text-display font-black leading-none tracking-tight">
                  {displayPlayerName(player)}
                </h1>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <p className="truncate text-caption font-bold text-white/68 tracking-wider uppercase italic">
                  {player.name}
                </p>
                {player.countryCode && (
                  <div className="flex items-center gap-1.5 rounded bg-white/10 px-1.5 py-0.5 backdrop-blur-md">
                    <div className={`fg fg-${player.countryCode} scale-100 origin-center`} />
                    <span className="text-micro font-bold text-white/80">{player.country || player.countryCode}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="mt-3.5 flex flex-wrap items-center gap-1.5">
              <span className="rounded-full bg-white/12 px-2.5 py-0.5 text-micro font-bold text-white/90 backdrop-blur-sm">
                {player.gender === 'Female' ? '女' : player.gender === 'Male' ? '男' : '待补'}
              </span>
              <span className="rounded-full bg-white/12 px-2.5 py-0.5 text-micro font-bold text-white/90 backdrop-blur-sm">
                {displayBio(player)}
              </span>
              {player.styleZh && (
                <span className="rounded-full bg-white/12 px-2.5 py-0.5 text-micro font-bold text-white/90 backdrop-blur-sm">
                  {player.styleZh}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function PlayerRankCard({ player }: { player: Player }) {
  const rankChange = player.rankChange ?? 0;

  return (
    <section className="px-5 -mt-6 relative z-20">
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl border border-white/60 bg-white/70 p-4 shadow-sm backdrop-blur-md">
          <p className="flex items-center gap-1.5 text-micro font-black text-text-tertiary uppercase tracking-widest">
            当前排名
            <span className={cn(
              "text-[10px] tabular-nums font-black",
              rankChange > 0 ? "text-state-success" : rankChange < 0 ? "text-state-danger" : "text-text-tertiary/40"
            )}>
              {rankChange > 0 ? '↑' : rankChange < 0 ? '↓' : '•'} {rankChange !== 0 ? Math.abs(rankChange) : ''}
            </span>
          </p>
          <div className="mt-1.5 flex items-baseline gap-1.5 font-black">
            <span className="text-display-sm text-text-primary leading-none tabular-nums">{player.rank ?? '-'}</span>
            {player.careerBestRank && (
              <span className="text-micro text-text-tertiary font-bold bg-brand-soft/20 border-1 px-2 py-0.5 rounded-sm">
                最高 {player.careerBestRank}
              </span>
            )}
          </div>
        </div>
        <div className="rounded-2xl border border-white/60 bg-white/70 p-4 shadow-sm backdrop-blur-md">
          <p className="text-micro font-black text-text-tertiary uppercase tracking-widest">当前积分</p>
          <strong className="mt-1.5 block text-display-sm text-text-primary leading-none tabular-nums">{formatNumber(player.points)}</strong>
        </div>
      </div>
    </section>
  );
}

function StatSectionTitle({ label }: { label: string }) {
  return (
    <div className="mb-4 flex items-center gap-2.5">
      <span className="whitespace-nowrap text-[10px] font-semibold uppercase tracking-[1.5px] text-text-tertiary">{label}</span>
      <div className="h-px flex-1 bg-gradient-to-r from-border-subtle to-transparent" />
    </div>
  );
}

function PlayerStatsBento({ player, stats }: { player: Player; stats: PlayerStats }) {
  const yearWinRate = player.yearMatches ? (player.yearWins ?? 0) / player.yearMatches * 100 : null;
  const sevenFinalsRate = stats.sevenEvents ? (stats.sevenFinals / stats.sevenEvents) * 100 : null;

  const cardClass = "rounded-2xl border border-border-subtle bg-white p-4 shadow-sm";

  return (
    <section className="px-5 pt-5">
      <SectionHeader title="职业数据" />

      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-[2fr_3fr] gap-3">
          {/* 赛事 */}
          <div className={cardClass}>
            <StatSectionTitle label="赛事" />
            <div className="flex flex-col gap-4">
              <div className="flex items-end gap-x-6">
                <div>
                  <p className="font-numeric text-[32px] font-bold text-gold leading-none tabular-nums">{stats.eventsTotal}</p>
                  <p className="mt-1.5 text-[10px] font-semibold uppercase tracking-widest text-text-tertiary">总数</p>
                </div>
                <div className="">
                  <p className="font-numeric text-[22px] font-bold leading-none tabular-nums">{player.yearEvents ?? 0}</p>
                  <p className="mt-1.5 text-[10px] font-semibold uppercase tracking-widest text-text-tertiary">今年</p>
                </div>
              </div>
              <div className='flex items-end gap-x-1'>
                <div>
                  <p className="font-numeric text-[22px] font-bold leading-none text-text-primary tabular-nums">{stats.sevenEvents}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-text-tertiary">七大赛</p>
                  </div>
                </div>
                {sevenFinalsRate != null && (
                  <span className="rounded bg-[rgba(197,160,89,0.12)] px-1.5 py-0.5 text-[10px] font-semibold leading-none text-gold tabular-nums">
                    决赛率 {formatPercent(sevenFinalsRate)}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* 胜率 */}
          <div className={cardClass}>
            <StatSectionTitle label="胜率" />
            <div className="flex flex-col gap-4">
              <div className="text-center">
                <p className="font-numeric text-[32px] font-bold leading-none text-text-primary tabular-nums">{formatPercent(stats.winRate)}</p>
                <p className="mt-2 text-[10px] font-semibold uppercase tracking-[1.5px] text-text-tertiary">总胜率</p>
              </div>
              <div className="grid grid-cols-3 border-border-subtle pt-4 text-center">
                <div className="border-r border-border-subtle px-1.5">
                  <p className="font-numeric text-[12px] font-bold leading-none text-gold text-brand-strong tabular-nums">{formatPercent(stats.foreignWinRate)}</p>
                  <p className="mt-1.5 text-[10px] font-semibold text-text-tertiary">外战</p>
                </div>
                <div className="px-1.5 border-r border-border-subtle">
                  <p className="font-numeric text-[12px] font-bold leading-none text-text-primary tabular-nums">{formatPercent(stats.domesticWinRate)}</p>
                  <p className="mt-1.5 text-[10px] font-semibold text-text-tertiary">内战</p>
                </div>
                <div className="px-1.5">
                  <p className="font-numeric text-[12px] font-bold leading-none tabular-nums">{formatPercent(yearWinRate)}</p>
                  <p className="mt-1.5 text-[10px] font-semibold text-text-tertiary">今年</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 冠军 */}
        <div className={cardClass}>
          <StatSectionTitle label="冠军" />
          <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-4">
            <div>
              <p className="mb-3 text-center text-[10px] font-semibold uppercase tracking-[1.5px] text-text-tertiary">三大赛</p>
              <div className="grid grid-cols-2 gap-3 text-center">
                <div>
                  <p className="font-numeric text-[28px] font-bold leading-none text-gold tabular-nums">{stats.allThreeTitles}</p>
                  <p className="mt-1.5 text-[10px] font-semibold text-text-tertiary">总数</p>
                </div>
                <div>
                  <p className="font-numeric text-[28px] font-bold leading-none tabular-nums">{stats.singleThreeTitles}</p>
                  <p className="mt-1.5 text-[10px] font-semibold ">单打</p>
                </div>
              </div>
            </div>
            <div className="h-16 w-px bg-border-subtle" />
            <div>
              <p className="mb-3 text-center text-[10px] font-semibold uppercase tracking-[1.5px] text-text-tertiary">七大赛</p>
              <div className="grid grid-cols-2 gap-3 text-center">
                <div>
                  <p className="font-numeric text-[28px] font-bold leading-none text-gold tabular-nums">{stats.allSevenTitles}</p>
                  <p className="mt-1.5 text-[10px] font-semibold text-text-tertiary">总数</p>
                </div>
                <div>
                  <p className="font-numeric text-[28px] font-bold leading-none tabular-nums">{stats.singleSevenTitles}</p>
                  <p className="mt-1.5 text-[10px] font-semibold">单打</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function RecentMatches({ matches }: { matches: RecentMatch[] }) {
  return (
    <section className="px-5 pt-6">
      <SectionHeader title="最近比赛" />
      {matches.length === 0 ? (
        <EmptyState title="最近比赛暂无数据" />
      ) : (
        <div className="space-y-2.5">
          {matches.map((match) => (
            <Link
              key={match.matchId}
              href={route(`/matches/${match.matchId}`)}
              className="flex items-center gap-3 rounded-lg border border-white/70 bg-white/70 p-3 shadow-sm backdrop-blur-md transition-colors hover:bg-white"
            >
              <div
                className={`grid h-12 w-12 shrink-0 place-items-center rounded-full text-body font-black tabular-nums ${match.didWin ? 'bg-state-success/12 text-state-success' : 'bg-state-danger/12 text-state-danger'
                  }`}
              >
                {match.didWin ? '胜' : '负'}
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="truncate text-body font-black text-text-primary">{displayEventName(match)}</h3>
                <p className="mt-1 truncate text-caption font-semibold text-text-tertiary">
                  {displayDate(match.date)} · vs {match.opponentName || '对手待补'}
                  {match.opponentCountry ? ` (${match.opponentCountry})` : ''}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-body font-black text-text-secondary tabular-nums">{match.matchScore || '-'}</p>
                <ChevronRight size={16} className="ml-auto mt-1 text-text-tertiary" strokeWidth={2} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

function PlayerEventRecords({ events }: { events: EventRecord[] }) {
  const [championsOnly, setChampionsOnly] = useState(false);
  const [eventTierFilter, setEventTierFilter] = useState<EventTierFilter>("all");
  const [subEventFilter, setSubEventFilter] = useState<EventSubTypeFilter>("all");
  const [expanded, setExpanded] = useState(false);

  const filteredEvents = events.filter((event) => {
    if (championsOnly && !event.isChampion) return false;
    if (!matchesEventTier(event, eventTierFilter)) return false;
    if (!matchesSubEventFilter(event, subEventFilter)) return false;
    return true;
  });

  React.useEffect(() => {
    setExpanded(false);
  }, [championsOnly, eventTierFilter, subEventFilter]);

  const displayEvents = expanded ? filteredEvents : filteredEvents.slice(0, 10);
  const hasMore = filteredEvents.length > 10;
  const filterButtonClass =
    "rounded-full border px-3 py-1.5 text-[11px] font-bold transition-colors";
  const activeFilterButtonClass = "border-brand-strong bg-brand-strong text-white";
  const inactiveFilterButtonClass = "border-border-subtle bg-white text-text-secondary hover:border-brand-strong/35 hover:text-brand-strong";

  if (events.length === 0) {
    return <EmptyState title="赛事记录暂无数据" />;
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="mb-2 flex flex-col gap-3 border-b border-black/[0.05] px-2 pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setChampionsOnly((current) => !current)}
            className={cn(
              filterButtonClass,
              championsOnly ? activeFilterButtonClass : inactiveFilterButtonClass,
            )}
          >
            只看冠军
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {[
            { value: "all", label: "全部" },
            { value: "three", label: "三大赛" },
            { value: "seven", label: "七大赛" },
          ].map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setEventTierFilter(option.value as EventTierFilter)}
              className={cn(
                filterButtonClass,
                eventTierFilter === option.value ? activeFilterButtonClass : inactiveFilterButtonClass,
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {[
            { value: "all", label: "全部项目" },
            { value: "WS", label: "WS" },
            { value: "WD", label: "WD" },
            { value: "XD", label: "XD" },
            { value: "team", label: "团体" },
          ].map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setSubEventFilter(option.value as EventSubTypeFilter)}
              className={cn(
                filterButtonClass,
                subEventFilter === option.value ? activeFilterButtonClass : inactiveFilterButtonClass,
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {filteredEvents.length === 0 ? (
        <div className="px-2 py-6 text-center text-caption font-medium text-text-tertiary">
          当前筛选下暂无比赛记录
        </div>
      ) : null}

      {displayEvents.map((event, idx) => (
        <Link
          key={`${event.eventId}:${event.subEventTypeCode ?? "unknown"}`}
          href={route(`/events/${event.eventId}`)}
          className={cn(
            "grid grid-cols-[1fr_auto] gap-3 px-2 py-3 transition-colors hover:bg-white/40 group",
            idx !== displayEvents.length - 1 && "border-b border-black/[0.04]"
          )}
        >
          <div className="min-w-0">
            <h3 className="truncate text-body font-bold text-text-primary group-hover:text-brand-strong transition-colors">{displayEventName(event)}</h3>
            <p className="mt-0.5 text-caption font-medium text-text-tertiary">
              {displayDate(event.date)} · {subEventLabel(event)}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-brand-soft/50 px-2.5 py-0.5 text-micro font-bold text-brand-strong uppercase tracking-wider">
              {event.result || '成绩待补'}
            </span>
            <ChevronRight size={14} className="text-text-tertiary/50 group-hover:text-brand-strong transition-colors" />
          </div>
        </Link>
      ))}
      {hasMore && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="mt-2 w-full flex items-center justify-center gap-1.5 py-2.5 text-caption font-bold text-brand-strong hover:text-brand-deep transition-colors border-t border-black/[0.04]"
        >
          <ChevronDown size={14} />
          展开全部
          <span className="text-text-tertiary font-medium">({filteredEvents.length})</span>
        </button>
      )}
      {expanded && filteredEvents.length > 0 && (
        <button
          onClick={() => setExpanded(false)}
          className="mt-2 w-full flex items-center justify-center gap-1.5 py-2.5 text-caption font-bold text-text-tertiary hover:text-brand-strong transition-colors border-t border-black/[0.04]"
        >
          <ChevronDown size={14} className="rotate-180" />
          收起
        </button>
      )}
    </div>
  );
}

function PlayerTopOpponents({ slug, active }: { slug: string; active: boolean }) {
  const [keyword, setKeyword] = useState("");
  const deferredKeyword = useDeferredValue(keyword);
  const [sortBy, setSortBy] = useState<OpponentSortField>("matches");
  const [sortOrder, setSortOrder] = useState<OpponentSortOrder>("desc");
  const [opponents, setOpponents] = useState<TopOpponent[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [initialLoading, setInitialLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadMoreRef = React.useRef<HTMLDivElement | null>(null);
  const requestKeyRef = React.useRef("");

  const loadOpponents = React.useCallback(
    async (mode: "reset" | "append", offset: number) => {
      if (!slug || !active) return;
      const params = new URLSearchParams({
        limit: "10",
        offset: offset.toString(),
        q: deferredKeyword.trim(),
        sortBy,
        sortOrder,
      });

      const requestKey = `${slug}|${deferredKeyword.trim()}|${sortBy}|${sortOrder}|${offset}`;
      requestKeyRef.current = requestKey;

      setError(null);
      if (mode === "reset") setInitialLoading(true);
      else setLoadingMore(true);

      try {
        const res = await fetch(`/api/v1/players/${slug}/opponents?${params.toString()}`);
        const json = await res.json();

        if (requestKeyRef.current !== requestKey) return;
        if (json.code !== 0) {
          setError("对手数据加载失败");
          return;
        }

        const data = json.data as OpponentResponse;
        setOpponents((current) => (mode === "append" ? [...current, ...data.items] : data.items));
        setHasMore(data.hasMore);
      } catch (err) {
        console.error(err);
        if (requestKeyRef.current === requestKey) {
          setError("对手数据加载失败");
        }
      } finally {
        if (requestKeyRef.current === requestKey) {
          if (mode === "reset") setInitialLoading(false);
          else setLoadingMore(false);
        }
      }
    },
    [active, deferredKeyword, slug, sortBy, sortOrder],
  );

  React.useEffect(() => {
    if (!active || !slug) return;
    setOpponents([]);
    setHasMore(true);
    void loadOpponents("reset", 0);
  }, [active, deferredKeyword, loadOpponents, slug, sortBy, sortOrder]);

  React.useEffect(() => {
    if (!active || !hasMore || initialLoading || loadingMore) return;

    const node = loadMoreRef.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          void loadOpponents("append", opponents.length);
        }
      },
      { rootMargin: "240px 0px" },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [active, hasMore, initialLoading, loadOpponents, loadingMore, opponents.length]);

  const toggleSort = React.useCallback((field: OpponentSortField) => {
    setSortBy((currentField) => {
      if (currentField === field) {
        setSortOrder((currentOrder) => (currentOrder === "desc" ? "asc" : "desc"));
        return currentField;
      }

      setSortOrder("desc");
      return field;
    });
  }, []);

  const sortLabel = React.useCallback(
    (field: OpponentSortField, label: string) => (
      <button
        type="button"
        onClick={() => toggleSort(field)}
        className={cn(
          "flex items-center justify-center gap-1 text-[0.78rem] font-bold transition-colors",
          sortBy === field ? "text-[#2d6cf6]" : "text-slate-400 hover:text-slate-700",
        )}
      >
        {label}
        <ChevronDown
          size={12}
          className={cn(
            "transition-transform",
            sortBy === field && sortOrder === "asc" ? "rotate-180" : "",
          )}
        />
      </button>
    ),
    [sortBy, sortOrder, toggleSort],
  );

  return (
    <div className="flex flex-col">
      <div className="border-b border-slate-200/80 pb-3">
        <div className="relative">
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索对手姓名"
            className="h-11 w-full rounded-full border border-slate-200 bg-white pl-10 pr-11 text-[0.95rem] font-medium text-slate-900 outline-none transition focus:border-[#2d6cf6]"
          />
          {keyword ? (
            <button
              type="button"
              onClick={() => setKeyword("")}
              className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full bg-slate-100 text-slate-500 transition hover:bg-slate-200"
              aria-label="清空搜索"
            >
              <X size={14} />
            </button>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_4.25rem_4.25rem] items-center gap-3 border-b border-slate-200/80 px-1 py-3">
        <p className="text-[0.76rem] font-black uppercase tracking-[0.18em] text-slate-400">对手</p>
        {sortLabel("matches", "交手次数")}
        {sortLabel("winRate", "胜率")}
      </div>

      {initialLoading ? (
        <div className="py-10 text-center text-caption font-medium text-text-tertiary">加载中...</div>
      ) : error ? (
        <div className="py-10 text-center text-caption font-medium text-state-danger">{error}</div>
      ) : opponents.length === 0 ? (
        <div className="py-10 text-center text-caption font-medium text-text-tertiary">
          {deferredKeyword.trim() ? "没有找到匹配的对手" : "对手交手数据暂无记录"}
        </div>
      ) : (
        <>
          <div className="flex flex-col">
            {opponents.map((opponent, index) => {
              const rank = index + 1;
              const content = (
                <div
                  className={cn(
                    "grid grid-cols-[minmax(0,1fr)_4.25rem_4.25rem_auto] items-center gap-3 px-1 py-3 transition-colors group",
                    "hover:bg-[#f6f8fd]",
                    index !== opponents.length - 1 && "border-b border-slate-100",
                  )}
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="w-6 shrink-0 text-[0.82rem] font-bold text-[#9bb3e0]">{rank}</span>
                      {opponent.countryCode ? (
                        <span className={`fg fg-${opponent.countryCode} shrink-0 scale-[1.05]`} />
                      ) : null}
                      <div className="min-w-0">
                        <h3 className="truncate text-[0.98rem] font-bold leading-tight text-slate-900 group-hover:text-[#2d6cf6]">
                          {opponent.nameZh?.trim() || opponent.name}
                        </h3>
                        <p className="mt-1 truncate text-[0.8rem] font-medium text-slate-400">
                          {opponent.name}
                          {opponent.latestDate ? ` · 最近 ${displayDate(opponent.latestDate)}` : ""}
                        </p>
                      </div>
                    </div>
                  </div>
                  <strong className="text-center font-numeric text-[1.2rem] font-black leading-none text-slate-900 tabular-nums">
                    {opponent.matches}
                  </strong>
                  <strong className="text-center font-numeric text-[1.2rem] font-black leading-none text-[#2d6cf6] tabular-nums">
                    {formatPercent(opponent.winRate)}
                  </strong>
                  <ChevronRight size={15} className="text-slate-300 group-hover:text-[#2d6cf6]" />
                </div>
              );

              if (!opponent.slug) {
                return <article key={`${opponent.playerId ?? "unknown"}-${opponent.name}`}>{content}</article>;
              }

              return (
                <Link key={opponent.slug} href={route(`/players/${opponent.slug}`)} className="block">
                  {content}
                </Link>
              );
            })}
          </div>

          <div ref={loadMoreRef} className="py-4 text-center text-[0.82rem] font-medium text-slate-400">
            {loadingMore ? "加载更多对手..." : hasMore ? "继续下滑查看更多" : "已显示全部对手"}
          </div>
        </>
      )}
    </div>
  );
}

export default function PlayerDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const [slug, setSlug] = React.useState<string | null>(null);
  const [detail, setDetail] = React.useState<PlayerDetail | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [recordsTab, setRecordsTab] = React.useState<RecordsTab>("events");

  React.useEffect(() => {
    params.then(({ slug }) => setSlug(slug));
  }, [params]);

  React.useEffect(() => {
    if (!slug) return;
    async function load() {
      try {
        const res = await fetch(`/api/v1/players/${slug}`);
        const json = await res.json();
        if (json.code === 0) {
          setDetail(json.data);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [slug]);

  if (loading || !detail) {
    return (
      <main className="mx-auto min-h-screen max-w-lg overflow-hidden pb-12 bg-gray-50/30">
        <div className="flex items-center justify-center py-20">
          <span className="text-body text-text-tertiary">加载中...</span>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-lg overflow-hidden pb-12 bg-gray-50/30">
      <PlayerHero player={detail.player} />
      <PlayerRankCard player={detail.player} />
      <PlayerStatsBento player={detail.player} stats={detail.stats} />
      <section className="px-5 pt-6 pb-2">
        <div className="relative overflow-hidden rounded-sm bg-white px-4 pt-2 shadow-[0_-12px_40px_rgba(0,0,0,0.04)] ring-1 ring-black/[0.02]">
          <RecordsTabs activeTab={recordsTab} onChange={setRecordsTab} />
          <div className="mt-3">
            {recordsTab === "events" ? (
              <PlayerEventRecords events={detail.events} />
            ) : (
              <PlayerTopOpponents slug={detail.player.slug} active={recordsTab === "opponents"} />
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
