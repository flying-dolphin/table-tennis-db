import Link from 'next/link';
import type { Route } from 'next';
import { notFound } from 'next/navigation';
import { ArrowUpRight, CalendarDays, ChevronRight, Medal, Target, Trophy } from 'lucide-react';
import { PlayerAvatar } from '@/components/PlayerAvatar';
import { PlayerBackButton } from '@/components/player/PlayerBackButton';
import { getPlayerDetail } from '@/lib/server/players';

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
    parts.push(`${player.birthYear}${player.age ? ` (${player.age}岁)` : ''}`);
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
        <h2 className="text-[18px] font-black tracking-tight text-text-primary">{title}</h2>
        {hint ? <p className="mt-0.5 text-[12px] font-medium text-text-tertiary">{hint}</p> : null}
      </div>
    </div>
  );
}

function EmptyState({ title, action = '想要' }: { title: string; action?: string }) {
  return (
    <div className="rounded-[24px] border border-white/60 bg-white/55 p-5 text-center shadow-sm">
      <p className="text-[14px] font-bold text-text-secondary">{title}</p>
      <Link
        href={route('/search')}
        className="mt-3 inline-flex items-center rounded-full border border-border-subtle bg-white/75 px-4 py-2 text-[12px] font-bold text-brand-strong shadow-sm transition-colors hover:bg-white"
      >
        {action}
        <ArrowUpRight size={13} className="ml-1" strokeWidth={2} />
      </Link>
    </div>
  );
}

function PlayerHero({ player }: { player: Player }) {
  const rankChange = player.rankChange ?? 0;

  return (
    <section className="relative overflow-hidden rounded-b-[34px] bg-[rgb(var(--hero-anchor))] px-5 pb-6 pt-5 text-white shadow-lg">
      <div className="absolute inset-0 opacity-55 [background:radial-gradient(circle_at_20%_15%,rgba(127,169,217,0.75),transparent_32%),linear-gradient(140deg,rgba(26,35,44,1),rgba(80,113,145,0.92))]" />
      <div className="relative z-10">
        <PlayerBackButton />

        <div className="flex items-end gap-4">
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
            <h1 className="mt-1 truncate text-[32px] font-black leading-none tracking-tight">{displayPlayerName(player)}</h1>
            <p className="mt-2 truncate text-[14px] font-semibold text-white/66">{player.name}</p>
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="rounded-full bg-white/14 px-2.5 py-0.5 text-[11px] font-bold text-white/90 backdrop-blur-sm">
                {player.country || player.countryCode}
              </span>
              {player.styleZh && (
                <span className="rounded-full bg-white/14 px-2.5 py-0.5 text-[11px] font-bold text-white/90 backdrop-blur-sm">
                  {player.styleZh}
                </span>
              )}
              {player.careerBestRank && (
                <span className="rounded-full bg-brand-primary/40 px-2.5 py-0.5 text-[11px] font-bold text-white backdrop-blur-sm">
                  生涯最高 #{player.careerBestRank}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-2.5">
          <div className="rounded-[24px] border border-white/14 bg-white/12 p-4 backdrop-blur-sm">
            <p className="flex items-center gap-1.5 text-[11px] font-bold text-white/55">
              当前排名
              <span className={`text-[10px] ${rankChange > 0 ? 'text-state-success' : rankChange < 0 ? 'text-state-danger' : 'text-white/40'}`}>
                {rankChange > 0 ? '↑' : rankChange < 0 ? '↓' : '•'} {rankChange !== 0 ? Math.abs(rankChange) : ''}
              </span>
            </p>
            <strong className="mt-1 block text-[30px] leading-none">#{player.rank ?? '-'}</strong>
          </div>
          <div className="rounded-[24px] border border-white/14 bg-white/12 p-4 backdrop-blur-sm">
            <p className="text-[11px] font-bold text-white/55">当前积分</p>
            <strong className="mt-1 block text-[30px] leading-none">{formatNumber(player.points)}</strong>
          </div>
        </div>
      </div>
    </section>
  );
}

function PlayerStatsBento({ player, stats }: { player: Player; stats: PlayerStats }) {
  const yearWinRate = player.yearMatches ? (player.yearWins ?? 0) / player.yearMatches * 100 : null;

  return (
    <section className="px-5 pt-5">
      <SectionHeader title="职业看板" hint="全维度数据与年度对照" />

      <div className="bento-grid">
        {/* Bio Info - Basic Attributes */}
        <div className="bento-span-6 bento-card bento-card-hover flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div>
              <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider">性别</p>
              <p className="text-[14px] font-black text-text-primary">{player.gender === 'Female' ? '女' : player.gender === 'Male' ? '男' : '待补'}</p>
            </div>
            <div className="h-6 w-px bg-border-subtle" />
            <div>
              <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider">出生 & 年龄</p>
              <p className="text-[14px] font-black text-text-primary">{displayBio(player)}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider">打球风格</p>
            <p className="text-[14px] font-black text-brand-strong">{player.styleZh || '待补'}</p>
          </div>
        </div>

        {/* Core Ranks */}
        <div className="bento-span-2 bento-card bento-card-hover">
          <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider">当前排名</p>
          <p className="mt-1 text-[22px] font-black text-brand-strong">#{player.rank ?? '-'}</p>
          <div className="mt-1 h-1 w-8 rounded-full bg-brand-strong/20" />
        </div>
        <div className="bento-span-2 bento-card bento-card-hover">
          <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider">生涯最高</p>
          <p className="mt-1 text-[22px] font-black text-text-primary">#{player.careerBestRank ?? '-'}</p>
          <div className="mt-1 h-1 w-8 rounded-full bg-text-tertiary/20" />
        </div>
        <div className="bento-span-2 bento-card bento-card-hover">
          <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider">当前积分</p>
          <p className="mt-1 text-[20px] font-black text-text-primary whitespace-nowrap">{formatNumber(player.points)}</p>
        </div>

        {/* Win Rate Comparison */}
        <div className="bento-span-4 bento-card bento-card-hover relative overflow-hidden">
          <div className="relative z-10 flex h-full flex-col justify-between">
            <div>
              <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider">生涯总胜率</p>
              <p className="text-[28px] font-black text-text-primary leading-none mt-1">{formatPercent(stats.winRate)}</p>
            </div>
            <div className="mt-3">
              <div className="mb-1.5 flex items-center justify-between text-[11px] font-bold">
                <span className="text-brand-strong">2026 年度胜率</span>
                <span className="text-text-primary">{formatPercent(yearWinRate)}</span>
              </div>
              <div className="h-2 w-full rounded-full bg-brand-mist overflow-hidden">
                <div
                  className="h-full bg-brand-strong rounded-full transition-all duration-1000 ease-out"
                  style={{ width: `${yearWinRate ?? 0}%` }}
                />
              </div>
            </div>
          </div>
          <Target className="absolute -bottom-2 -right-2 h-16 w-16 text-brand-mist/30" />
        </div>

        {/* Activity */}
        <div className="bento-span-2 bento-card bento-card-hover">
          <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider">赛事总数</p>
          <p className="text-[24px] font-black text-text-primary mt-0.5">{stats.eventsTotal}</p>
          <div className="mt-2 text-[11px] font-bold text-brand-strong bg-brand-soft/50 px-2 py-0.5 rounded-md inline-block">
            今年 {player.yearEvents ?? 0}
          </div>
        </div>

        {/* Sub Win Rates */}
        <div className="bento-span-3 bento-card bento-card-hover flex items-center justify-between">
          <div>
            <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider">外战胜率</p>
            <p className="text-[19px] font-black text-state-success mt-0.5">{formatPercent(stats.foreignWinRate)}</p>
          </div>
          <div className="h-9 w-9 rounded-xl bg-state-success/10 flex items-center justify-center">
            <Target size={16} className="text-state-success" />
          </div>
        </div>
        <div className="bento-span-3 bento-card bento-card-hover flex items-center justify-between">
          <div>
            <p className="text-[10px] font-bold text-text-tertiary uppercase tracking-wider">内战胜率</p>
            <p className="text-[19px] font-black text-text-primary mt-0.5">{formatPercent(stats.domesticWinRate)}</p>
          </div>
          <div className="h-9 w-9 rounded-xl bg-brand-mist flex items-center justify-center">
            <Target size={16} className="text-brand-strong" />
          </div>
        </div>

        {/* Honor Wall - 3 Majors */}
        <div className="bento-span-3 bento-card honor-diamond bento-card-hover">
          <div className="flex items-center gap-1.5">
            <Trophy size={14} className="text-brand-strong" />
            <p className="text-[11px] font-black text-brand-strong uppercase tracking-wider">三大赛记录</p>
          </div>
          <div className="mt-3.5 grid grid-cols-2 gap-2">
            <div>
              <p className="text-[9px] font-bold text-text-tertiary uppercase">单打冠军</p>
              <p className="text-[20px] font-black text-text-primary leading-none mt-1">{stats.singleThreeTitles}</p>
            </div>
            <div>
              <p className="text-[9px] font-bold text-text-tertiary uppercase">总冠军</p>
              <p className="text-[20px] font-black text-text-primary leading-none mt-1">{stats.allThreeTitles}</p>
            </div>
          </div>
        </div>

        {/* Honor Wall - 7 Majors */}
        <div className="bento-span-3 bento-card honor-silver bento-card-hover">
          <div className="flex items-center gap-1.5">
            <Medal size={14} className="text-text-secondary" />
            <p className="text-[11px] font-black text-text-secondary uppercase tracking-wider">七大赛记录</p>
          </div>
          <div className="mt-3.5 grid grid-cols-2 gap-2">
            <div>
              <p className="text-[9px] font-bold text-text-tertiary uppercase">单打冠军</p>
              <p className="text-[20px] font-black text-text-primary leading-none mt-1">{stats.singleSevenTitles}</p>
            </div>
            <div>
              <p className="text-[9px] font-bold text-text-tertiary uppercase">总冠军</p>
              <p className="text-[20px] font-black text-text-primary leading-none mt-1">{stats.allSevenTitles}</p>
            </div>
          </div>
        </div>

        {/* 7 Major Finals */}
        <div className="bento-span-6 bento-card bento-card-hover flex items-center justify-between border-dashed bg-white/30">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-white flex items-center justify-center shadow-sm border border-state-warning/20">
              <Target size={18} className="text-state-warning" />
            </div>
            <p className="text-[14px] font-bold text-text-secondary">七大赛单打决赛次数</p>
          </div>
          <p className="text-[24px] font-black text-text-primary">{stats.sevenFinals}</p>
        </div>
      </div>
    </section>
  );
}

function RecentMatches({ matches }: { matches: RecentMatch[] }) {
  return (
    <section className="px-5 pt-6">
      <SectionHeader title="最近比赛" hint="固定展示最近 3 场 match" />
      {matches.length === 0 ? (
        <EmptyState title="最近比赛暂无数据" />
      ) : (
        <div className="space-y-2.5">
          {matches.map((match) => (
            <Link
              key={match.matchId}
              href={route(`/matches/${match.matchId}`)}
              className="flex items-center gap-3 rounded-[26px] border border-white/70 bg-white/70 p-3 shadow-sm backdrop-blur-md transition-colors hover:bg-white"
            >
              <div
                className={`grid h-12 w-12 shrink-0 place-items-center rounded-full text-[13px] font-black ${match.didWin ? 'bg-state-success/12 text-state-success' : 'bg-state-danger/12 text-state-danger'
                  }`}
              >
                {match.didWin ? '胜' : '负'}
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="truncate text-[14px] font-black text-text-primary">{displayEventName(match)}</h3>
                <p className="mt-1 truncate text-[12px] font-semibold text-text-tertiary">
                  {displayDate(match.date)} · vs {match.opponentName || '对手待补'}
                  {match.opponentCountry ? ` (${match.opponentCountry})` : ''}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-[13px] font-black text-text-secondary">{match.matchScore || '-'}</p>
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
      <SectionHeader title="比赛记录" hint="按赛事倒序，不逐场展开" />
      {events.length === 0 ? (
        <EmptyState title="赛事记录暂无数据" />
      ) : (
        <div className="space-y-2.5">
          {events.map((event) => (
            <Link
              key={event.eventId}
              href={route(`/events/${event.eventId}`)}
              className="grid grid-cols-[1fr_auto] gap-3 rounded-[24px] border border-white/65 bg-white/62 p-4 shadow-sm backdrop-blur-md transition-colors hover:bg-white"
            >
              <div className="min-w-0">
                <h3 className="truncate text-[14px] font-black text-text-primary">{displayEventName(event)}</h3>
                <p className="mt-1 text-[12px] font-semibold text-text-tertiary">
                  {displayDate(event.date)} · {subEventLabel(event)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-brand-soft/75 px-3 py-1 text-[12px] font-black text-brand-strong">
                  {event.result || '成绩待补'}
                </span>
                <ArrowUpRight size={15} className="text-text-tertiary" strokeWidth={2} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

function TopOpponents({ opponents }: { opponents: TopOpponent[] }) {
  return (
    <section className="px-5 pb-5 pt-6">
      <SectionHeader title="Top 3 对手" hint="按交手次数排序，最近交手作为次级排序" />
      {opponents.length === 0 ? (
        <EmptyState title="对手交手数据暂无记录" />
      ) : (
        <div className="space-y-2.5">
          {opponents.map((opponent, index) => {
            const content = (
              <>
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[rgb(var(--hero-anchor))] text-[13px] font-black text-white">
                  {index + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="truncate text-[14px] font-black text-text-primary">
                    {opponent.nameZh?.trim() || opponent.name}
                  </h3>
                  <p className="mt-1 truncate text-[12px] font-semibold text-text-tertiary">
                    {opponent.countryCode || '国家待补'} · 最近 {displayDate(opponent.latestDate)}
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2 text-right">
                  <div>
                    <p className="text-[11px] font-bold text-text-tertiary">交手</p>
                    <strong className="text-[15px] text-text-primary">{opponent.matches}</strong>
                  </div>
                  <div>
                    <p className="text-[11px] font-bold text-text-tertiary">胜率</p>
                    <strong className="text-[15px] text-text-primary">{formatPercent(opponent.winRate)}</strong>
                  </div>
                </div>
              </>
            );

            if (!opponent.slug) {
              return (
                <article
                  key={`${opponent.playerId ?? 'unknown'}-${opponent.name}`}
                  className="flex items-center gap-3 rounded-[24px] border border-white/65 bg-white/62 p-4 shadow-sm backdrop-blur-md"
                >
                  {content}
                </article>
              );
            }

            return (
              <Link
                key={opponent.slug}
                href={route(`/players/${opponent.slug}`)}
                className="flex items-center gap-3 rounded-[24px] border border-white/65 bg-white/62 p-4 shadow-sm backdrop-blur-md transition-colors hover:bg-white"
              >
                {content}
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}

export default async function PlayerDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const detail = getPlayerDetail(slug);
  if (!detail) notFound();

  return (
    <main className="mx-auto min-h-screen max-w-lg overflow-hidden pb-12">
      <PlayerHero player={detail.player} />
      <PlayerStatsBento player={detail.player} stats={detail.stats} />
      <RecentMatches matches={detail.recentMatches} />
      <EventRecords events={detail.events} />
      <TopOpponents opponents={detail.topOpponents} />
    </main>
  );
}
