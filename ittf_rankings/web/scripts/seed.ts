import path from 'node:path';
import { db } from '@/db/client';
import { readMatchFiles, readRankingFile } from '@/lib/data';
import { slugifyName } from '@/lib/utils';

function upsertPlayer(payload: {
  playerExternalId?: string;
  slug: string;
  chineseName: string;
  englishName: string;
  country?: string;
  countryCode?: string;
  continent?: string;
}) {
  const stmt = db.prepare(`
    INSERT INTO players (player_external_id, slug, chinese_name, english_name, country, country_code, continent)
    VALUES (@playerExternalId, @slug, @chineseName, @englishName, @country, @countryCode, @continent)
    ON CONFLICT(slug) DO UPDATE SET
      player_external_id = excluded.player_external_id,
      chinese_name = excluded.chinese_name,
      english_name = excluded.english_name,
      country = excluded.country,
      country_code = excluded.country_code,
      continent = excluded.continent,
      updated_at = CURRENT_TIMESTAMP
  `);
  stmt.run({
    playerExternalId: payload.playerExternalId ?? null,
    slug: payload.slug,
    chineseName: payload.chineseName,
    englishName: payload.englishName,
    country: payload.country ?? null,
    countryCode: payload.countryCode ?? null,
    continent: payload.continent ?? null,
  });

  return db.prepare('SELECT id FROM players WHERE slug = ?').get(payload.slug) as { id: number };
}

function main() {
  const rankingFile = readRankingFile();
  const matchFiles = readMatchFiles();

  db.exec('BEGIN');
  try {
    db.exec('DELETE FROM matches; DELETE FROM events; DELETE FROM player_match_sources; DELETE FROM rankings; DELETE FROM ranking_snapshots;');

    const snapshotResult = db
      .prepare(
        `INSERT INTO ranking_snapshots (category, week, update_date, total_players, source_file)
         VALUES (?, ?, ?, ?, ?)`,
      )
      .run(
        rankingFile.category,
        rankingFile.week,
        rankingFile.update_date,
        rankingFile.total_players,
        path.relative(process.cwd(), path.resolve(process.cwd(), '..', 'data', 'women_singles_top50.json')),
      );

    const snapshotId = Number(snapshotResult.lastInsertRowid);

    for (const player of rankingFile.rankings) {
      const slug = slugifyName(player.english_name);
      const playerRow = upsertPlayer({
        playerExternalId: player.player_id ?? undefined,
        slug,
        chineseName: player.name,
        englishName: player.english_name,
        country: player.country,
        countryCode: player.country_code,
        continent: player.continent,
      });

      db.prepare(
        `INSERT INTO rankings (snapshot_id, player_id, rank, points, rank_change)
         VALUES (?, ?, ?, ?, ?)`,
      ).run(snapshotId, playerRow.id, player.rank, player.points, player.change);
    }

    for (const file of matchFiles) {
      const slug = slugifyName(file.player_name);
      const rankingPlayer = rankingFile.rankings.find((item) => slugifyName(item.english_name) === slug);
      const playerRow = upsertPlayer({
        playerExternalId: file.player_id ?? rankingPlayer?.player_id ?? undefined,
        slug,
        chineseName: rankingPlayer?.name ?? file.player_name,
        englishName: file.english_name ?? file.player_name,
        country: file.country ?? rankingPlayer?.country,
        countryCode: file.country_code ?? rankingPlayer?.country_code,
        continent: file.continent ?? rankingPlayer?.continent,
      });

      const sourceResult = db
        .prepare(
          `INSERT INTO player_match_sources (player_id, source_file, captured_at, from_date, raw_payload)
           VALUES (?, ?, ?, ?, json(?))`,
        )
        .run(
          playerRow.id,
          `${file.player_name}.json`,
          file.captured_at ?? null,
          file.from_date ?? null,
          JSON.stringify(file),
        );

      const sourceId = Number(sourceResult.lastInsertRowid);

      for (const [season, yearData] of Object.entries(file.years)) {
        for (const event of yearData.events ?? []) {
          const eventResult = db
            .prepare(
              `INSERT INTO events (player_id, source_id, season, event_name, event_type, detail_url, match_count, raw_capture_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
            )
            .run(
              playerRow.id,
              sourceId,
              Number(season),
              event.event_name,
              event.event_type ?? null,
              event.detail_url ?? null,
              event.match_count ?? event.matches?.length ?? 0,
              event.raw_capture_file ?? null,
            );

          const eventId = Number(eventResult.lastInsertRowid);

          for (const match of event.matches ?? []) {
            db.prepare(
              `INSERT INTO matches (
                event_id, player_id, stage, round, sub_event, result, winner, perspective,
                match_score, opponents_json, teammates_json, games_json, raw_row_text, side_a, side_b, all_players_json
              ) VALUES (@eventId, @playerId, @stage, @round, @subEvent, @result, @winner, @perspective, @matchScore, json(@opponents), json(@teammates), json(@games), @rawRowText, @sideA, @sideB, json(@allPlayers))`,
            ).run({
              eventId,
              playerId: playerRow.id,
              stage: match.stage ?? null,
              round: match.round ?? null,
              subEvent: match.sub_event ?? null,
              result: match.result_for_player ?? null,
              winner: match.winner ?? null,
              perspective: match.perspective ?? null,
              matchScore: match.match_score ?? null,
              opponents: JSON.stringify(match.opponents ?? []),
              teammates: JSON.stringify(match.teammates ?? []),
              games: JSON.stringify(match.games ?? []),
              rawRowText: match.raw_row_text ?? null,
              sideA: typeof match.side_a === 'string' ? match.side_a : JSON.stringify(match.side_a ?? null),
              sideB: typeof match.side_b === 'string' ? match.side_b : JSON.stringify(match.side_b ?? null),
              allPlayers: JSON.stringify(match.all_players_in_row ?? []),
            });
          }
        }
      }
    }

    db.exec('COMMIT');
    console.log('Database seeded successfully');
  } catch (error) {
    db.exec('ROLLBACK');
    throw error;
  }
}

main();
