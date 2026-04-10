import fs from 'node:fs';
import path from 'node:path';
import { MATCHES_DIR, RANKING_FILE } from '@/lib/paths';
import type { MatchFile, RankingFile } from '@/lib/types';
import { slugifyName } from '@/lib/utils';

export function readRankingFile(): RankingFile {
  return JSON.parse(fs.readFileSync(RANKING_FILE, 'utf-8')) as RankingFile;
}

export function readMatchFiles(): MatchFile[] {
  const files = fs.readdirSync(MATCHES_DIR).filter((file) => file.endsWith('.json'));
  return files.map((file) => {
    const fullPath = path.join(MATCHES_DIR, file);
    return JSON.parse(fs.readFileSync(fullPath, 'utf-8')) as MatchFile;
  });
}

export function buildPlayerIndex() {
  const rankings = readRankingFile();
  const matches = readMatchFiles();

  return rankings.rankings.map((player) => {
    const slug = slugifyName(player.english_name);
    const matchFile = matches.find((item) => slugifyName(item.player_name) === slug);

    const events = matchFile
      ? Object.values(matchFile.years).flatMap((year) => year.events ?? [])
      : [];

    const totalMatches = events.reduce((sum, event) => sum + (event.matches?.length ?? 0), 0);
    const wins = events.reduce(
      (sum, event) =>
        sum +
        (event.matches?.filter((match) => (match.result_for_player ?? '').toUpperCase() === 'W').length ?? 0),
      0,
    );

    return {
      ...player,
      slug,
      hasMatchData: Boolean(matchFile),
      totalEvents: events.length,
      totalMatches,
      wins,
      losses: Math.max(totalMatches - wins, 0),
      lastCapturedAt: matchFile?.captured_at ?? null,
    };
  });
}

export function getPlayerDetail(slug: string) {
  const rankingFile = readRankingFile();
  const ranking = rankingFile.rankings.find((item) => slugifyName(item.english_name) === slug);
  if (!ranking) return null;

  const matchFiles = readMatchFiles();
  const matchFile = matchFiles.find((item) => slugifyName(item.player_name) === slug);
  const events = matchFile
    ? Object.entries(matchFile.years)
        .sort(([a], [b]) => Number(b) - Number(a))
        .flatMap(([year, value]) =>
          (value.events ?? []).map((event) => ({ ...event, year: Number(year) })),
        )
    : [];

  return {
    ranking,
    matchFile,
    events,
  };
}
