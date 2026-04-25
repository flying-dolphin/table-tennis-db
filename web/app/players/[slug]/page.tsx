"use client";

import React, { useDeferredValue, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowUpRight, ChevronRight, ChevronDown, List, Search, Trophy, X, UsersRound } from "lucide-react";
import { Flag } from "@/components/Flag";
import { PlayerBackButton } from "@/components/player/PlayerBackButton";
import { formatSubEventLabel, getSubEventShortName } from "@/lib/sub-event-label";
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
  subEvents: Array<{
    subEventTypeCode: string | null;
    subEventNameZh: string | null;
    result: string | null;
    isChampion: boolean;
  }>;
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

function route(path: string) {
  return path as Route;
}

function displayPlayerName(player: Pick<Player, 'name' | 'nameZh'>) {
  return player.nameZh?.trim() || player.name;
}

function displayEventName(event: Pick<EventRecord, 'eventName' | 'eventNameZh'>) {
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
    parts.push(`${player.birthYear}年出生`);
  } else if (player.age) {
    parts.push(`${player.age} 岁`);
  }
  return parts.join(' ') || '-';
}

function rankChangeLabel(value: number | null) {
  if (value == null || value === 0) return '排名保持';
  return value > 0 ? `上升 ${value}` : `下降 ${Math.abs(value)}`;
}

function matchesSubEventCode(code: string | null, filter: EventSubTypeFilter) {
  if (filter === "team") {
    return code === "WT" || code === "XT";
  }
  return code === filter;
}

function getMatchingSubEvents(event: EventRecord, filter: EventSubTypeFilter) {
  if (filter === "all") return event.subEvents;
  return event.subEvents.filter((subEvent) => matchesSubEventCode(subEvent.subEventTypeCode, filter));
}

function getDisplaySubEvent(event: EventRecord, filter: EventSubTypeFilter) {
  const matched = getMatchingSubEvents(event, filter);
  if (matched.length > 0) return matched[0];
  return event.subEvents[0] ?? null;
}

function getDisplaySubEventLabel(event: EventRecord, filter: EventSubTypeFilter) {
  if (filter !== "all") {
    const displaySubEvent = getDisplaySubEvent(event, filter);
    return displaySubEvent
      ? formatSubEventLabel(displaySubEvent.subEventTypeCode, displaySubEvent.subEventNameZh)
      : "项目待补";
  }

  const labels = event.subEvents
    .map((subEvent) => formatSubEventLabel(subEvent.subEventTypeCode, subEvent.subEventNameZh))
    .filter((label, index, all) => label && all.indexOf(label) === index);
  return labels.join(" / ") || "项目待补";
}

function getDisplayResult(event: EventRecord, filter: EventSubTypeFilter) {
  return getDisplaySubEvent(event, filter)?.result ?? "成绩待补";
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
  return event.subEvents.some((subEvent) => matchesSubEventCode(subEvent.subEventTypeCode, filter));
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

function MetricBar({ label, value }: { label: string; value: number | null }) {
  const width = Math.max(0, Math.min(100, value ?? 0));

  return (
    <div className="grid grid-cols-[5rem_minmax(0,1fr)_3.25rem] items-center gap-3">
      <span className="text-[0.82rem] font-semibold text-[#44527c]">{label}</span>
      <div className="h-2 rounded-full bg-[#e8edf8]">
        <div
          className="h-full rounded-full bg-[linear-gradient(90deg,#162a67_0%,#29479c_100%)]"
          style={{ width: `${width}%` }}
        />
      </div>
      <span className="text-right font-numeric text-[0.88rem] font-black text-[#162a67] tabular-nums">
        {formatPercent(value)}
      </span>
    </div>
  );
}

function HeroBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-white/12 bg-white/10 px-2.5 py-1 text-[0.7rem] font-bold text-white/88 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-sm">
      {children}
    </span>
  );
}

type RecordsTab = "events" | "opponents";

function RecordsTabs({ activeTab, onChange }: { activeTab: RecordsTab; onChange: (tab: RecordsTab) => void }) {
  return (
    <div className="flex gap-2 border-b border-[#e7ecf5] px-2 pb-2.5">
      <button
        type="button"
        onClick={() => onChange("events")}
        className={cn(
          "flex h-10 min-w-[7rem] items-center justify-center gap-2 rounded-full px-4 text-[0.92rem] font-bold transition-all",
          activeTab === "events"
            ? "bg-[#162a67] text-white shadow-[0_12px_24px_rgba(22,42,103,0.18)]"
            : "bg-[#f3f6fb] text-[#64749a] hover:bg-[#eaf0fb] hover:text-[#162a67]",
        )}
      >
        <List size={16} />
        比赛记录
      </button>
      <button
        type="button"
        onClick={() => onChange("opponents")}
        className={cn(
          "flex h-10 min-w-[7rem] items-center justify-center gap-2 rounded-full px-4 text-[0.92rem] font-bold transition-all",
          activeTab === "opponents"
            ? "bg-[#162a67] text-white shadow-[0_12px_24px_rgba(22,42,103,0.18)]"
            : "bg-[#f3f6fb] text-[#64749a] hover:bg-[#eaf0fb] hover:text-[#162a67]",
        )}
      >
        <UsersRound size={18} />
        对手
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

function HeroPlayerAvatar({ player }: { player: Player }) {
  const [error, setError] = React.useState(false);
  const displayName = displayPlayerName(player);
  const filename = player.avatarFile || `player_${player.playerId}_${player.name.replace(/ /g, "_")}.png`;

  if (error) {
    return (
      <div className="grid h-full w-full place-items-center rounded-[2rem] bg-[linear-gradient(135deg,#31406c_0%,#162655_100%)]">
        <span className="text-[2.5rem] font-black text-white/88">{displayName.slice(0, 1)}</span>
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/images/avatars/${filename}`}
      alt={displayName}
      className="h-full w-full object-cover"
      onError={() => setError(true)}
    />
  );
}

function PlayerHero({ player, winRate }: { player: Player; winRate: number | null }) {
  return (
    <section className="relative overflow-hidden px-5 pb-4 pt-4 text-white">
      <div className="absolute inset-0 bg-[linear-gradient(145deg,#050914_0%,#08143a_38%,#0e1f58_100%)]" />
      <div className="absolute inset-0 opacity-90 [background:radial-gradient(circle_at_18%_20%,rgba(255,255,255,0.15)_0%,transparent_18%),radial-gradient(circle_at_82%_18%,rgba(105,132,255,0.38)_0%,transparent_22%),radial-gradient(circle_at_54%_74%,rgba(16,38,105,0.82)_0%,transparent_42%)]" />
      <div className="absolute inset-y-0 right-[-3.5rem] w-[17rem] bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.18)_0%,rgba(255,255,255,0.03)_38%,transparent_68%)] blur-2xl" />
      <div className="absolute left-8 top-22 h-2.5 w-2.5 rounded-full bg-white/40 shadow-[0_0_22px_rgba(255,255,255,0.8)]" />
      <div className="absolute left-28 top-32 h-1.5 w-1.5 rounded-full bg-white/30 shadow-[0_0_16px_rgba(255,255,255,0.7)]" />
      <div className="absolute right-16 top-12 h-3 w-3 rounded-full bg-[#9ab2ff]/55 blur-[1px]" />

      <div className="relative z-10">
        <PlayerBackButton />

        <div className="flex justify-between"></div>
        <div className="my-1 grid grid-cols-[7.25rem_minmax(0,1fr)] items-start gap-4">
          <div className="relative h-48 overflow-hidden">
            <HeroPlayerAvatar player={player} />
          </div>

          <div className="min-w-0 py-2">
            <h1 className="truncate text-3xl font-black leading-none tracking-[-0.04em]">
              {displayPlayerName(player)}
            </h1>
            <div className="mt-2 flex min-w-0 items-center gap-2">
              <p className="min-w-0 truncate text-[1.02rem] font-bold uppercase italic tracking-[0.08em] text-white/72">
                {player.name}
              </p>
              {player.countryCode && (
                <div className="flex shrink-0 items-center gap-1.5 px-2.5 py-1 backdrop-blur-md">
                  <Flag code={player.countryCode} className="origin-center scale-100" />
                  <span className="text-[0.8rem] font-bold text-white/86">{player.country || player.countryCode}</span>
                </div>
              )}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <HeroBadge>{genderLabel(player.gender)}</HeroBadge>
              <HeroBadge>{displayBio(player)}</HeroBadge>
              {player.styleZh && (
                <HeroBadge>{player.styleZh}</HeroBadge>
              )}
            </div>
            <div className="flex item-start mt-2">
              <p className="text-[9px] tracking-[0.08em] text-center text-white/68">世界排名</p>
            </div>
            <div className="flex items-start flex px-1 gap-1">
              <div className="flex justify-start items-start gap-2 pr-2">
                <span className="font-numeric text-5xl font-black text-[#ffd36a] tabular-nums">
                  {player.rank ?? "-"}
                </span>
              </div>
              <div className="flex flex-col items-start justify-start border-l border-white/14 px-2">
                <strong className="py-1 block font-numeric text-xl leading-none text-white tabular-nums">
                  {player.careerBestRank ?? "-"}
                </strong>
                <p className="text-[9px] tracking-[0.08em] text-white/68">最高排名</p>
              </div>
              <div className="flex flex-col items-start justify-start border-l border-white/14 px-2">
                <strong className="py-1 block font-numeric text-xl leading-none text-white tabular-nums">
                  {formatNumber(player.points)}
                </strong>
                <p className="text-[9px] tracking-[0.08em] text-white/68">积分</p>
              </div>
            </div>
          </div>
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
  const careerWinRate = stats.winRate;
  const summaryItems = [
    { label: "总赛事", value: stats.eventsTotal },
    { label: "七大赛出战", value: stats.sevenEvents },
    { label: "今年参赛", value: player.yearEvents ?? 0 },
  ];

  return (
    <section className="relative z-20 -mt-5 px-5 pt-0">

      <div className="flex flex-col gap-3">
        <div className="rounded-md border border-white/70 bg-white/98 backdrop-blur- px-5 py-2 shadow-[0_24px_60px_rgba(15,36,95,0.12)]">
          <div className="grid grid-cols-3 gap-3">
            {summaryItems.map((item, index) => (
              <div
                key={item.label}
                className={cn(
                  "text-center",
                  index !== 0 && "border-l border-[#edf1f7]",
                )}
              >
                <p className="font-numeric text-xl font-black leading-none text-[#132865] tabular-nums">
                  {item.value}
                </p>
                <p className="mt-1 text-xs font-semibold text-[#68789e]">{item.label}</p>
              </div>
            ))}
          </div>
          {sevenFinalsRate != null ? (
            <div className="mt-2 border-t border-[#edf1f7] pt-2">
              <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-3">
                <p className="text-xs font-bold text-[#162a67]">决赛进入率 {formatPercent(sevenFinalsRate)}</p>
                <div className="h-2 rounded-full bg-[#e8edf8]">
                  <div
                    className="h-full rounded-full bg-[linear-gradient(90deg,#162a67_0%,#2e4aa2_100%)]"
                    style={{ width: `${Math.max(0, Math.min(100, sevenFinalsRate))}%` }}
                  />
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="relative overflow-hidden rounded-md border border-white/70 bg-[linear-gradient(135deg,#ffffff_0%,#f8fbff_100%)] p-5 shadow-[0_24px_60px_rgba(15,36,95,0.1)]">
          <div className="absolute right-[-0.5rem] top-2 opacity-[0.14]">
            <div className="relative h-36 w-36">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/images/cup3.png"
                alt="Trophy background"
                className="h-full w-full object-contain"
              />
            </div>
          </div>

          <div className="relative z-10">
            <StatSectionTitle label="生涯胜率" />
            <div className="mb-4">
              <p className="font-numeric text-4xl font-black leading-none tracking-[-0.05em] text-[#132865] tabular-nums">
                {formatPercent(careerWinRate)}
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <MetricBar label="外战胜率" value={stats.foreignWinRate} />
              <MetricBar label="内战胜率" value={stats.domesticWinRate} />
              <MetricBar label="年度胜率" value={yearWinRate} />
            </div>
          </div>
        </div>

        <div>
          <SectionHeader title="世界冠军" />
          <div className="grid grid-cols-2 gap-3">
            <div className="relative overflow-hidden rounded-[1rem] bg-[linear-gradient(135deg,#f1b12d_0%,#ffd978_55%,#f9c450_100%)] p-4 text-[#1d1a12] shadow-[0_20px_40px_rgba(240,181,44,0.28)] flex items-center justify-center min-h-[6.5rem]">
              <div className="flex flex-col items-start w-fit">
                <p className="text-[0.85rem] font-black tracking-[0.02em] mb-2 opacity-90">三大赛</p>
                <div className="flex items-center gap-4">
                  <div className="flex flex-col items-center min-w-[2.5rem]">
                    <p className="font-numeric text-[1.8rem] font-black leading-none tabular-nums">{stats.allThreeTitles}</p>
                    <p className="mt-1 text-[0.7rem] font-bold opacity-75">冠军</p>
                  </div>
                  <div className="w-[1px] h-7 bg-[#1d1a12]/15"></div>
                  <div className="flex flex-col items-center min-w-[2.5rem]">
                    <p className="font-numeric text-[1.6rem] font-black leading-none tabular-nums">{stats.singleThreeTitles}</p>
                    <p className="mt-1 text-[0.7rem] font-bold opacity-75">单打</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="relative overflow-hidden rounded-[1rem] bg-[linear-gradient(135deg,#10245f_0%,#1e357f_60%,#2f4ea6_100%)] p-4 text-white shadow-[0_20px_40px_rgba(22,42,103,0.26)] flex items-center justify-center min-h-[6.5rem]">
              <div className="flex flex-col items-start w-fit">
                <p className="text-[0.85rem] font-black tracking-[0.02em] text-white/80 mb-2">七大赛</p>
                <div className="flex items-center gap-4">
                  <div className="flex flex-col items-center min-w-[2.5rem]">
                    <p className="font-numeric text-[1.8rem] font-black leading-none text-[#ffd36a] tabular-nums">{stats.allSevenTitles}</p>
                    <p className="mt-1 text-[0.7rem] font-bold text-white/60">冠军</p>
                  </div>
                  <div className="w-[1px] h-7 bg-white/15"></div>
                  <div className="flex flex-col items-center min-w-[2.5rem]">
                    <p className="font-numeric text-[1.6rem] font-black leading-none tabular-nums">{stats.singleSevenTitles}</p>
                    <p className="mt-1 text-[0.7rem] font-bold text-white/60">单打</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function PlayerEventRecords({ events }: { events: EventRecord[] }) {
  const [championsOnly, setChampionsOnly] = useState(false);
  const [eventTierFilter, setEventTierFilter] = useState<EventTierFilter>("all");
  const [subEventFilter, setSubEventFilter] = useState<EventSubTypeFilter>("all");
  const [expanded, setExpanded] = useState(false);

  const filteredEvents = events.filter((event) => {
    if (!matchesEventTier(event, eventTierFilter)) return false;
    if (!matchesSubEventFilter(event, subEventFilter)) return false;
    if (championsOnly && !getMatchingSubEvents(event, subEventFilter).some((subEvent) => subEvent.isChampion)) return false;
    return true;
  });

  React.useEffect(() => {
    setExpanded(false);
  }, [championsOnly, eventTierFilter, subEventFilter]);

  const displayEvents = expanded ? filteredEvents : filteredEvents.slice(0, 10);
  const hasMore = filteredEvents.length > 10;
  const filterButtonClass =
    "rounded-full border px-3.5 py-1.5 text-[0.82rem] font-bold transition-all";
  const activeFilterButtonClass = "border-[#162a67] bg-[#162a67] text-white shadow-[0_10px_18px_rgba(22,42,103,0.14)]";
  const inactiveFilterButtonClass = "border-[#e5eaf4] bg-[#f7f9fd] text-[#607095] hover:border-[#cbd6ef] hover:text-[#162a67]";

  if (events.length === 0) {
    return <EmptyState title="赛事记录暂无数据" />;
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="mb-2 flex flex-col gap-2.5 border-b border-[#edf1f7] px-1 pb-3">
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
            { value: "WS", label: getSubEventShortName("WS") || "WS" },
            { value: "WD", label: getSubEventShortName("WD") || "WD" },
            { value: "XD", label: getSubEventShortName("XD") || "XD" },
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
      </div>

      {filteredEvents.length === 0 ? (
        <div className="px-2 py-6 text-center text-caption font-medium text-text-tertiary">
          当前筛选下暂无比赛记录
        </div>
      ) : null}

      {displayEvents.map((event, idx) => (
        <Link
          key={event.eventId}
          href={route(`/events/${event.eventId}`)}
          className={cn(
            "grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-[1.25rem] px-2 py-2.5 transition-colors group hover:bg-[#f7f9fe]",
            idx !== displayEvents.length - 1 && "mb-1"
          )}
        >
          <div className="grid h-10 w-10 place-items-center rounded-2xl bg-[linear-gradient(180deg,#fff6da_0%,#f4c851_100%)] text-[#d39200] shadow-[0_12px_20px_rgba(244,200,81,0.28)]">
            <Trophy size={20} strokeWidth={2} />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-body font-bold text-text-primary group-hover:text-brand-strong transition-colors">{displayEventName(event)}</h3>
            <p className="mt-0.5 text-caption font-medium text-text-tertiary">
              {displayDate(event.date)} · {getDisplaySubEventLabel(event, subEventFilter)}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-[#fff3d9] px-3 py-1 text-[0.82rem] font-bold text-[#d39200] uppercase tracking-wider">
              {getDisplayResult(event, subEventFilter)}
            </span>
            <ChevronRight size={16} className="text-text-tertiary/50 group-hover:text-brand-strong transition-colors" />
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
                        <Flag code={opponent.countryCode} className="shrink-0 scale-[1.05]" />
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
    <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-[linear-gradient(180deg,#f3f6fb_0%,#ffffff_30%,#f8fbff_100%)] pb-12">
      <PlayerHero player={detail.player} winRate={detail.stats.winRate} />
      <PlayerStatsBento player={detail.player} stats={detail.stats} />
      <section className="px-5 pt-5 pb-2">
        <div className="relative overflow-hidden rounded-[1.75rem] bg-white px-4 pt-4 shadow-[0_24px_60px_rgba(15,36,95,0.1)] ring-1 ring-[#eef2f8]">
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
