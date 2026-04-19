import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getPlayerDetail } from '@/lib/data';
import { changeLabel, changeTone, formatPoints } from '@/lib/utils';
import { PlayerAvatar } from "@/components/PlayerAvatar";

export default async function PlayerDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const detail = getPlayerDetail(slug);
  if (!detail) notFound();

  const { ranking, events } = detail;
  const recentEvents = events.slice(0, 12);
  const totalMatches = events.reduce((sum, event) => sum + (event.matches?.length ?? 0), 0);
  const wins = events.reduce(
    (sum, event) => sum + event.matches.filter((match) => (match.result_for_player ?? '').toUpperCase() === 'W').length,
    0,
  );
  const winRate = totalMatches ? Math.round((wins / totalMatches) * 100) : 0;

  return (
    <main className="page-shell detail-shell">
      <Link href="/" className="back-link">← 返回榜单</Link>
      <section className="hero-card detail-hero flex items-center gap-6">
        <PlayerAvatar 
          player={{
            playerId: ranking.player_id || '',
            name: ranking.english_name || ranking.name,
            nameZh: ranking.name,
            avatarFile: (ranking as any).avatarFile
          }} 
          size="lg" 
          className="ring-4 ring-white/30 shadow-2xl"
        />
        <div>
          <span className="eyebrow">球员名片</span>
          <h1>{ranking.name}</h1>
          <p>{ranking.english_name}</p>
        </div>
        <div className="detail-scoreboard">
          <div>
            <span>当前排名</span>
            <strong>#{ranking.rank}</strong>
          </div>
          <div>
            <span>积分</span>
            <strong>{formatPoints(ranking.points)}</strong>
          </div>
          <div>
            <span>排名变化</span>
            <strong className={`trend ${changeTone(ranking.change)}`}>{changeLabel(ranking.change)}</strong>
          </div>
        </div>
      </section>

      <section className="stats-grid">
        <article className="stat-card"><span>国家/地区</span><strong>{ranking.country}</strong></article>
        <article className="stat-card"><span>大洲</span><strong>{ranking.continent}</strong></article>
        <article className="stat-card"><span>总赛事数</span><strong>{events.length}</strong></article>
        <article className="stat-card"><span>总比赛数</span><strong>{totalMatches}</strong></article>
        <article className="stat-card"><span>胜场</span><strong>{wins}</strong></article>
        <article className="stat-card"><span>胜率</span><strong>{winRate}%</strong></article>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>近期赛事</h2>
            <p>按年份倒序展示，适合移动端快速浏览</p>
          </div>
        </div>
        <div className="event-list">
          {recentEvents.map((event, index) => (
            <article key={`${event.event_name}-${index}`} className="event-card">
              <div className="event-head">
                <div>
                  <h3>{event.event_name}</h3>
                  <p>{event.year} · {event.event_type ?? '未分类赛事'}</p>
                </div>
                <span>{event.matches.length} 场</span>
              </div>
              <div className="match-list">
                {event.matches.slice(0, 4).map((match, matchIndex) => (
                  <div key={`${event.event_name}-${matchIndex}`} className="match-row">
                    <div>
                      <strong>{match.round ?? match.stage ?? '比赛'}</strong>
                      <p>{(match.opponents ?? []).join(' / ') || '对手信息待补充'}</p>
                    </div>
                    <div className="match-meta">
                      <span className={`trend ${changeTone((match.result_for_player ?? '').toUpperCase() === 'W' ? 1 : -1)}`}>
                        {(match.result_for_player ?? '').toUpperCase() === 'W' ? '胜' : '负'}
                      </span>
                      <span>{match.match_score ?? '-'}</span>
                    </div>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
