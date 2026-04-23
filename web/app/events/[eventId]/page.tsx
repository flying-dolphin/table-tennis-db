"use client";

import React, { Suspense } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useParams, useSearchParams } from "next/navigation";
import { ArrowLeft, Crown, ListTree, Medal } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import "@/public/images/flags_local.css";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function route(path: string) {
  return path as Route;
}

type SidePlayer = {
  playerId: number | null;
  slug: string | null;
  name: string;
  nameZh: string | null;
  countryCode: string | null;
};

type BracketMatch = {
  matchId: number;
  drawRound: string;
  roundLabel: string;
  roundOrder: number;
  matchScore: string | null;
  games: Array<{ player: number; opponent: number }>;
  sides: Array<{ sideNo: number; isWinner: boolean; players: SidePlayer[] }>;
};

type EventDetail = {
  event: {
    eventId: number;
    year: number;
    name: string;
    nameZh: string | null;
    eventKind: string | null;
    eventKindZh: string | null;
    categoryNameZh: string | null;
    totalMatches: number | null;
    startDate: string | null;
    endDate: string | null;
    location: string | null;
  };
  subEvents: Array<{
    code: string;
    nameZh: string | null;
    disabled: boolean;
    hasDraw: boolean;
    drawMatches: number;
    importedMatches: number;
  }>;
  selectedSubEvent: string;
  subEventDetails: Array<{
    code: string;
    champion: {
      championName: string | null;
      championCountryCode: string | null;
      players: Array<{
        playerId: number;
        slug: string;
        name: string;
        nameZh: string | null;
        countryCode: string | null;
        avatarFile: string | null;
      }>;
    } | null;
    bracket: Array<{ code: string; label: string; order: number; matches: BracketMatch[] }>;
  }>;
  champion: {
    championName: string | null;
    championCountryCode: string | null;
    players: Array<{
      playerId: number;
      slug: string;
      name: string;
      nameZh: string | null;
      countryCode: string | null;
      avatarFile: string | null;
    }>;
  } | null;
  bracket: Array<{ code: string; label: string; order: number; matches: BracketMatch[] }>;
};

type EventDetailResponse = {
  code: number;
  data: EventDetail;
};

function displayName(name: string, nameZh: string | null) {
  return nameZh?.trim() || name;
}

function displayDateRange(startDate: string | null, endDate: string | null) {
  if (!startDate && !endDate) return "时间待补";
  if (startDate && startDate === endDate) return startDate;
  return [startDate, endDate].filter(Boolean).join(" - ");
}

function sideName(side: BracketMatch["sides"][number]) {
  return side.players.map((player) => player.nameZh?.trim() || player.name).join(" / ");
}

function sideCountry(side: BracketMatch["sides"][number]) {
  const countries = Array.from(new Set(side.players.map((player) => player.countryCode).filter(Boolean)));
  return countries.join(" / ");
}

function ChampionCard({ data, selectedSubEvent }: { data: EventDetail; selectedSubEvent: string }) {
  const detail = data.subEventDetails.find((d) => d.code === selectedSubEvent);
  const champion = detail?.champion;
  const displayChampion = champion?.players.length
    ? champion.players.map((player) => player.nameZh?.trim() || player.name).join(" / ")
    : champion?.championName?.split(",").join(" / ");

  return (
    <section className="px-5 pt-4">
      <div className="rounded-lg border border-white/60 bg-white/75 p-4 shadow-sm backdrop-blur-md">
        <div className="mb-3 flex items-center gap-2">
          <Crown size={18} className="text-gold" />
          <h2 className="text-heading-2 font-black text-text-primary">冠军摘要</h2>
        </div>
        {displayChampion ? (
          <div className="flex items-center gap-3">
            {champion?.players[0] ? (
              <PlayerAvatar player={champion.players[0]} size="md" />
            ) : (
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-brand-mist text-body-lg font-black text-brand-strong">
                冠
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate text-heading-1 font-black text-text-primary">{displayChampion}</p>
              <p className="mt-1 text-caption font-semibold text-text-tertiary">
                {data.subEvents.find((item) => item.code === selectedSubEvent)?.nameZh || selectedSubEvent}
                {champion?.championCountryCode ? ` · ${champion.championCountryCode}` : ""}
              </p>
            </div>
          </div>
        ) : (
          <div className="rounded-lg bg-surface-secondary p-4 text-center">
            <p className="text-body font-bold text-text-secondary">这项冠军还没补齐</p>
          </div>
        )}
      </div>
    </section>
  );
}

function MatchNode({ match }: { match: BracketMatch }) {
  const [sideA, sideB] = match.sides.sort((left, right) => left.sideNo - right.sideNo);

  return (
    <Link
      href={route(`/matches/${match.matchId}`)}
      className="block rounded-lg border border-border-subtle bg-white p-3 shadow-sm transition-all hover:border-brand-deep hover:shadow-md"
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-micro font-black uppercase tracking-widest text-text-tertiary">#{match.matchId}</span>
        <span className="rounded-full bg-brand-mist px-2 py-0.5 text-micro font-bold text-brand-strong">
          {match.matchScore || "比分待补"}
        </span>
      </div>
      {[sideA, sideB].filter(Boolean).map((side) => (
        <div
          key={side.sideNo}
          className={cn(
            "mb-1.5 grid grid-cols-[1fr_auto] items-center gap-2 rounded-md px-2 py-2 last:mb-0",
            side.isWinner ? "bg-brand-mist text-text-primary" : "bg-surface-secondary text-text-secondary",
          )}
        >
          <div className="min-w-0">
            <p className="truncate text-body font-black">{sideName(side)}</p>
            <p className="mt-0.5 truncate text-micro font-bold uppercase tracking-wider text-text-tertiary">
              {sideCountry(side) || "国家待补"}
            </p>
          </div>
          <span
            className={cn(
              "grid h-7 min-w-7 place-items-center rounded text-micro font-black",
              side.isWinner ? "bg-brand-deep text-white" : "bg-white text-text-tertiary",
            )}
          >
            {side.isWinner ? "胜" : ""}
          </span>
        </div>
      ))}
    </Link>
  );
}

function EventDetailContent() {
  const params = useParams<{ eventId: string }>();
  const searchParams = useSearchParams();
  const urlSubEvent = searchParams.get("sub_event");
  const [data, setData] = React.useState<EventDetail | null>(null);
  const [selectedSubEvent, setSelectedSubEvent] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetch(`/api/v1/events/${params.eventId}`);
        const json = (await res.json()) as EventDetailResponse;
        if (json.code === 0) {
          setData(json.data);
          if (!selectedSubEvent && json.data.selectedSubEvent) {
            setSelectedSubEvent(json.data.selectedSubEvent);
          }
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }

    if (params.eventId) load();
  }, [params.eventId]);

  const selectSubEvent = (code: string) => {
    setSelectedSubEvent(code);
  };

  if (loading || !data) {
    return (
      <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-gray-50/30 pb-28">
        <div className="flex justify-center py-20 text-body text-text-tertiary">加载中...</div>
      </main>
    );
  }

  const validSubEventCodes = ["WS", "WD", "XD"];
  const filteredSubEvents = data.subEvents.filter((subEvent) => validSubEventCodes.includes(subEvent.code));
  const currentSubEvent = selectedSubEvent ?? urlSubEvent ?? data.selectedSubEvent;
  const currentDetail = data.subEventDetails.find((d) => d.code === currentSubEvent);
  const currentBracket = currentDetail?.bracket ?? [];
  const currentChampion = currentDetail?.champion;

  return (
    <main className="mx-auto min-h-screen max-w-lg overflow-hidden bg-gray-50/30 pb-28">
      <section className="relative overflow-hidden px-5 pb-6 pt-5 text-white shadow-lg">
        <div className="absolute inset-0 [background:linear-gradient(45deg,#242536_0%,#45465a_54%,#6b8cab_100%)]" />
        <div className="absolute inset-0 opacity-50 [background:radial-gradient(circle_at_88%_10%,#b9d5ee_0%,transparent_44%),radial-gradient(circle_at_10%_86%,#1e2a3d_0%,transparent_58%)]" />
        <div className="relative z-10">
          <Link
            href="/events"
            className="mb-5 inline-flex min-h-11 items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3 text-caption font-bold text-white/85 backdrop-blur-sm transition-colors hover:bg-white/15"
          >
            <ArrowLeft size={14} />
            赛事列表
          </Link>
          <p className="text-caption font-bold uppercase tracking-widest text-white/66">
            {data.event.categoryNameZh || data.event.eventKindZh || "赛事详情"}
          </p>
          <h1 className="mt-2 text-heading-1 font-black leading-tight">{displayName(data.event.name, data.event.nameZh)}</h1>
          <p className="mt-3 text-caption font-bold leading-relaxed text-white/72">
            {displayDateRange(data.event.startDate, data.event.endDate)}
            {data.event.location ? ` · ${data.event.location}` : ""}
          </p>
        </div>
      </section>

      {filteredSubEvents.length > 0 && (
        <section className="px-5 pt-4">
          <div className="flex gap-2 overflow-x-auto pb-2">
            {filteredSubEvents.map((subEvent) => (
              <button
                key={subEvent.code}
                type="button"
                disabled={subEvent.disabled}
                onClick={() => selectSubEvent(subEvent.code)}
                className={cn(
                  "min-h-11 shrink-0 rounded-full border px-4 text-body font-bold transition-all active:scale-95 disabled:cursor-not-allowed disabled:opacity-45",
                  currentSubEvent === subEvent.code
                    ? "border-brand-deep bg-brand-deep text-white shadow-sm"
                    : "border-border-subtle bg-white/70 text-text-secondary hover:bg-white",
                )}
              >
                {subEvent.nameZh || subEvent.code}
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="px-5 pt-4">
        <div className="rounded-lg border border-white/60 bg-white/75 p-4 shadow-sm backdrop-blur-md">
          <div className="mb-3 flex items-center gap-2">
            <Crown size={18} className="text-gold" />
            <h2 className="text-heading-2 font-black text-text-primary">冠军摘要</h2>
          </div>
          {currentChampion?.players.length || currentChampion?.championName ? (
            <div className="flex items-center gap-3">
              {currentChampion?.players[0] ? (
                <PlayerAvatar player={currentChampion.players[0]} size="md" />
              ) : (
                <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-brand-mist text-body-lg font-black text-brand-strong">
                  冠
                </div>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-heading-1 font-black text-text-primary">
                  {currentChampion?.players.length
                    ? currentChampion.players.map((p) => p.nameZh?.trim() || p.name).join(" / ")
                    : currentChampion?.championName?.split(",").join(" / ")}
                </p>
                <p className="mt-1 text-caption font-semibold text-text-tertiary">
                  {data.subEvents.find((item) => item.code === currentSubEvent)?.nameZh || currentSubEvent}
                  {currentChampion?.championCountryCode ? ` · ${currentChampion.championCountryCode}` : ""}
                </p>
              </div>
            </div>
          ) : (
            <div className="rounded-lg bg-surface-secondary p-4 text-center">
              <p className="text-body font-bold text-text-secondary">这项冠军还没补齐</p>
            </div>
          )}
        </div>
      </section>

      <section className="px-5 pt-5">
        <div className="mb-3 flex items-center justify-between gap-3 px-1">
          <div>
            <div className="flex items-center gap-2">
              <ListTree size={18} className="text-brand-strong" />
              <h2 className="text-heading-2 font-black text-text-primary">正赛路径</h2>
            </div>
            <p className="mt-1 text-caption font-semibold text-text-tertiary">点击节点查看完整比赛详情</p>
          </div>
          <Medal size={18} className="text-gold" />
        </div>

        {currentBracket.length === 0 ? (
          <div className="rounded-lg border border-white/60 bg-white/70 p-6 text-center shadow-sm">
            <p className="text-body font-bold text-text-secondary">这项对战图还没收进来</p>
          </div>
        ) : (
          <div className="space-y-4">
            {currentBracket.map((round) => (
              <section key={round.code} className="rounded-lg border border-white/60 bg-white/60 p-3 shadow-sm backdrop-blur-md">
                <div className="mb-3 flex items-center justify-between px-1">
                  <h3 className="text-body-lg font-black text-text-primary">{round.label}</h3>
                  <span className="text-micro font-bold text-text-tertiary">{round.matches.length} 场</span>
                </div>
                <div className="grid gap-2">
                  {round.matches.map((match) => (
                    <MatchNode key={match.matchId} match={match} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default function EventDetailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-page-background py-20 text-center text-text-tertiary">页面加载中...</div>}>
      <EventDetailContent />
    </Suspense>
  );
}