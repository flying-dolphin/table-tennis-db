import Link from 'next/link';
import type { Route } from 'next';
import { notFound } from 'next/navigation';
import { ChevronLeft, Users } from 'lucide-react';
import { Flag } from '@/components/Flag';
import { PlayerAvatar } from '@/components/PlayerAvatar';
import { getEventTeamRoster } from '@/lib/server/events';
import { formatSubEventLabel } from '@/lib/sub-event-label';

function displayName(name: string, nameZh: string | null) {
  return nameZh?.trim() || name;
}

function route(path: string) {
  return path as Route;
}

export default async function TeamRosterPage({
  params,
  searchParams,
}: {
  params: Promise<{ eventId: string; teamCode: string }>;
  searchParams: Promise<{ sub_event?: string; from?: string }>;
}) {
  const { eventId, teamCode } = await params;
  const { sub_event, from } = await searchParams;
  const parsedEventId = Number(eventId);

  if (!Number.isFinite(parsedEventId) || !sub_event) {
    notFound();
  }

  const data = getEventTeamRoster(parsedEventId, sub_event, teamCode);
  if (!data) {
    notFound();
  }

  const backHref = from || `/events/${eventId}?sub_event=${encodeURIComponent(sub_event)}&view=draw`;

  return (
    <main className="mx-auto min-h-screen max-w-lg bg-[#f8fafc] px-5 pb-10 pt-4">
      <Link
        href={route(backHref)}
        replace
        className="inline-flex items-center gap-1 rounded-full bg-white px-3 py-1.5 text-[0.9rem] font-semibold text-slate-600 ring-1 ring-[#e8edf8]"
      >
        <ChevronLeft size={16} />
        返回
      </Link>

      <section className="mt-4 overflow-hidden rounded-[1.6rem] bg-white shadow-[0_12px_30px_rgba(165,178,196,0.16)] ring-1 ring-white/80">
        <div className="bg-[linear-gradient(135deg,#1d4ed8,#60a5fa)] px-5 py-5 text-white">
          <p className="text-[0.82rem] font-semibold uppercase tracking-[0.12em] text-white/70">
            {formatSubEventLabel(data.roster.subEventCode, null)}
          </p>
          <div className="mt-3 flex items-center gap-3">
            <Flag code={data.roster.teamCode} className="scale-[1.6]" />
            <div>
              <h1 className="text-[1.7rem] font-black leading-none">{data.roster.teamCode}</h1>
              <p className="mt-1 text-[0.98rem] font-medium text-white/80">
                {data.event.nameZh || data.event.name}
              </p>
            </div>
          </div>
          <div className="mt-4 inline-flex items-center gap-2 rounded-full bg-white/14 px-3 py-1 text-[0.85rem] font-semibold text-white/88">
            <Users size={15} />
            {data.roster.players.length} 名参赛运动员
          </div>
        </div>

        <div className="px-4 py-4">
          {data.roster.players.length === 0 ? (
            <div className="rounded-[1.2rem] bg-[#f6f8fd] px-4 py-8 text-center text-[0.95rem] text-slate-500">
              暂无队伍名单
            </div>
          ) : (
            <div className="space-y-3">
              {data.roster.players.map((player, index) => {
                const content = (
                  <div className="flex items-center gap-3 rounded-[1.2rem] bg-[#f6f8fd] px-3.5 py-3 transition hover:bg-[#eef4ff]">
                    <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#dbeafe] text-[0.95rem] font-black text-[#1d4ed8]">
                      {player.order ?? index + 1}
                    </div>
                    <PlayerAvatar
                      player={{
                        playerId: player.playerId ?? `${player.name}-${index}`,
                        name: player.name,
                        nameZh: player.nameZh,
                        avatarFile: player.avatarFile,
                      }}
                      size="md"
                      className="h-12 w-12 shrink-0 rounded-full ring-2 ring-white"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[1rem] font-black text-slate-950">
                        {displayName(player.name, player.nameZh)}
                      </p>
                      <p className="mt-0.5 truncate text-[0.82rem] font-medium text-slate-500">
                        {player.name}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2 text-[0.82rem] font-semibold text-slate-500">
                      <Flag code={player.countryCode} />
                      <span>{player.countryCode || data.roster.teamCode}</span>
                    </div>
                  </div>
                );

                return player.slug ? (
                  <Link key={`${player.playerId ?? player.name}-${index}`} href={route(`/players/${player.slug}`)}>
                    {content}
                  </Link>
                ) : (
                  <div key={`${player.playerId ?? player.name}-${index}`}>{content}</div>
                );
              })}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
