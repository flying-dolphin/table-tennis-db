import Link from 'next/link';
import { buildPlayerIndex, readRankingFile } from '@/lib/data';
import { changeLabel, changeTone, formatPoints } from '@/lib/utils';

export default function HomePage() {
  const rankingFile = readRankingFile();
  const players = buildPlayerIndex();
  const topThree = players.slice(0, 3);

  return (
    <main className="page-shell">
      <section className="hero-card">
        <div className="hero-copy">
          <span className="eyebrow">ITTF 世界排名观察站</span>
          <h1>女子单打 TOP 50</h1>
          <p>
            用温和、清晰的方式看排名、积分、比赛数量和胜率，先把信息做得舒服，再把洞察做深。
          </p>
          <div className="hero-meta">
            <span>更新日期 {rankingFile.update_date}</span>
            <span>第 {rankingFile.week} 周</span>
            <span>{rankingFile.total_players} 位球员</span>
          </div>
        </div>
        <div className="hero-orbs" aria-hidden>
          <span className="orb orb-a">🏓</span>
          <span className="orb orb-b">✨</span>
          <span className="orb orb-c">☁️</span>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>领奖台</h2>
            <p>当前积分最高的三位球员</p>
          </div>
        </div>
        <div className="podium-grid">
          {topThree.map((player, index) => (
            <article key={player.slug} className={`podium-card podium-${index + 1}`}>
              <div className="podium-rank">#{player.rank}</div>
              <h3>{player.name}</h3>
              <p>{player.english_name}</p>
              <strong>{formatPoints(player.points)} 分</strong>
              <span>{player.country}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header sticky-like">
          <div>
            <h2>完整榜单</h2>
            <p>点击球员可查看赛事详情与基础统计</p>
          </div>
        </div>
        <div className="mobile-list">
          {players.map((player) => (
            <Link key={player.slug} href={`/players/${player.slug}`} className="player-card">
              <div className="player-card-main">
                <div className="rank-chip">#{player.rank}</div>
                <div>
                  <h3>{player.name}</h3>
                  <p>{player.english_name}</p>
                </div>
              </div>
              <div className="player-card-stats">
                <span>{player.country}</span>
                <span>{formatPoints(player.points)} 分</span>
              </div>
              <div className="player-card-footer">
                <span className={`trend ${changeTone(player.change)}`}>{changeLabel(player.change)}</span>
                <span>{player.totalMatches} 场比赛</span>
                <span>{player.totalEvents} 站赛事</span>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
