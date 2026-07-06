// @ts-nocheck

const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const projectRoot = path.resolve(__dirname, '..');

function read(relativePath) {
  return readFileSync(path.join(projectRoot, relativePath), 'utf8');
}

test('dense list screens route item links through DenseLink', () => {
  const denseFiles = [
    'app/events/[eventId]/page.tsx',
    'app/events/[eventId]/teams/[teamCode]/page.tsx',
    'app/events/page.tsx',
    'app/compare/page.tsx',
    'app/matches/[matchId]/page.tsx',
    'components/rankings/RankingsPageClient.tsx',
    'components/home/RankingTable.tsx',
    'components/player/PlayerDetailPageClient.tsx',
  ];

  for (const file of denseFiles) {
    const source = read(file);
    assert.match(source, /DenseLink/, `${file} should use DenseLink for dense navigable lists`);
  }

  assert.doesNotMatch(
    read('app/events/[eventId]/page.tsx'),
    /from "next\/link"/,
    'event detail has many match/team/player links and should not import raw next/link directly',
  );
});

test('pre-generated player avatars bypass Next image optimization', () => {
  const source = read('components/PlayerAvatar.tsx');
  assert.match(source, /<Image[\s\S]*\bunoptimized\b/, 'PlayerAvatar should serve static thumbnail files directly');
});

test('local static images bypass Next image optimization', () => {
  const files = [
    'app/auth/page.tsx',
    'app/events/[eventId]/page.tsx',
    'components/events/EventCategoryIcon.tsx',
    'components/home/Hero.tsx',
    'components/player/PlayerDetailPageClient.tsx',
  ];

  for (const file of files) {
    const source = read(file);
    const imageTags = source.match(/<Image[\s\S]*?\/>/g) ?? [];
    for (const tag of imageTags) {
      if (!/src=["']\/(?:images|icons)\//.test(tag)) continue;
      assert.match(tag, /\bunoptimized\b/, `${file} local static image should use unoptimized: ${tag}`);
    }
  }
});
