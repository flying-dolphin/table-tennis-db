import Link from 'next/link';
import type { Route } from 'next';
import { notFound } from 'next/navigation';
import { ArrowUpRight, ChevronRight } from 'lucide-react';
import { PlayerAvatar } from '@/components/PlayerAvatar';
import { PlayerBackButton } from '@/components/player/PlayerBackButton';
import { getPlayerDetail } from '@/lib/server/players';
import '@/public/images/flags_local.css';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type PlayerDetail = NonNullable<ReturnType<typeof getPlayerDetail>>;
type Player = PlayerDetail['player'];
type PlayerStats = PlayerDetail['stats'];
type RecentMatch = PlayerDetail['recentMatches'][number];
type EventRecord = PlayerDetail['events'][number];
type TopOpponent = PlayerDetail['topOpponents'][number];

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
      <div className="absolute inset-0 [background:linear-gradient(165deg,#2e2e42_0%,#565568_50%,#767484_100%)]" />
      <div className="absolute inset-0 opacity-50 [background:radial-gradient(circle_at_85%_10%,#4e4868_0%,transparent_60%),radial-gradient(circle_at_15%_90%,#888796_0%,transparent_60%)]" />
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
                <p className="truncate text-caption font-bold text-white/40 tracking-wider uppercase italic">
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

function EventRecords({ events }: { events: EventRecord[] }) {
  return (
    <section className="px-5 pt-6">
      <div className="bg-white/60 backdrop-blur-md rounded-lg p-4 shadow-[0_1px_0_rgba(255,255,255,0.5)] border border-white/50 relative overflow-hidden">
        <div className="flex justify-between items-end mb-3 px-1 relative z-10">
          <h2 className="text-heading-2 font-black tracking-tight text-text-primary">比赛记录</h2>
        </div>
        {events.length === 0 ? (
          <EmptyState title="赛事记录暂无数据" />
        ) : (
          <div className="flex flex-col gap-1 relative z-10">
            {events.map((event, idx) => (
              <Link
                key={event.eventId}
                href={route(`/events/${event.eventId}`)}
                className={cn(
                  "grid grid-cols-[1fr_auto] gap-3 px-2 py-3 transition-colors hover:bg-white/40 group",
                  idx !== events.length - 1 && "border-b border-black/[0.04]"
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
          </div>
        )}
      </div>
    </section>
  );
}

function TopOpponents({ opponents }: { opponents: TopOpponent[] }) {
  return (
    <section className="px-5 pb-8 pt-6">
      <div className="bg-white/60 backdrop-blur-md rounded-lg p-4 shadow-[0_1px_0_rgba(255,255,255,0.5)] border border-white/50 relative overflow-hidden">
        <div className="mb-3 px-1 relative z-10">
          <h2 className="text-heading-2 font-black tracking-tight text-text-primary">Top 3 对手</h2>
          <p className="mt-0.5 text-caption font-medium text-text-tertiary uppercase tracking-widest">按交手次数排序</p>
        </div>
        {opponents.length === 0 ? (
          <EmptyState title="对手交手数据暂无记录" />
        ) : (
          <div className="flex flex-col gap-1 relative z-10">
            {opponents.map((opponent, index) => {
              const content = (
                <div className={cn(
                  "flex items-center gap-3 py-3 px-2 group transition-colors",
                  index !== opponents.length - 1 && "border-b border-black/[0.04]"
                )}>
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand-mist/50 text-body font-black text-brand-strong tabular-nums group-hover:bg-brand-strong group-hover:text-white transition-all">
                    {index + 1}
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate text-body font-bold text-text-primary group-hover:text-brand-strong transition-colors">
                      {opponent.nameZh?.trim() || opponent.name}
                    </h3>
                    <p className="mt-0.5 truncate text-caption font-medium text-text-tertiary uppercase tracking-wider">
                      {opponent.countryCode || '国家待补'} · 最近 {displayDate(opponent.latestDate)}
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-right">
                    <div>
                      <p className="text-[9px] font-black text-text-tertiary uppercase tracking-widest leading-none">交手</p>
                      <strong className="text-body font-black text-text-primary tabular-nums block mt-1">{opponent.matches}</strong>
                    </div>
                    <div>
                      <p className="text-[9px] font-black text-text-tertiary uppercase tracking-widest leading-none">胜率</p>
                      <strong className="text-body font-black text-text-primary tabular-nums block mt-1">{formatPercent(opponent.winRate)}</strong>
                    </div>
                  </div>
                </div>
              );

              if (!opponent.slug) {
                return (
                  <article key={`${opponent.playerId ?? 'unknown'}-${opponent.name}`}>
                    {content}
                  </article>
                );
              }

              return (
                <Link
                  key={opponent.slug}
                  href={route(`/players/${opponent.slug}`)}
                  className="block hover:bg-white/40 transition-colors"
                >
                  {content}
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

export default async function PlayerDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const detail = getPlayerDetail(slug);
  if (!detail) notFound();

  return (
    <main className="mx-auto min-h-screen max-w-lg overflow-hidden pb-12 bg-gray-50/30">
      <PlayerHero player={detail.player} />
      <PlayerRankCard player={detail.player} />
      <PlayerStatsBento player={detail.player} stats={detail.stats} />
      <EventRecords events={detail.events} />
      <TopOpponents opponents={detail.topOpponents} />
    </main>
  );
}
