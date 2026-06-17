// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { getPlayerDetailAvatarSources, getRankingAvatarSources } = require('./avatar-paths.ts');

test('ranking avatars use crop-derived thumbnails and crop fallback', () => {
  assert.deepEqual(getRankingAvatarSources('player_123_NAME.png'), {
    primary: '/images/avatar-thumbs/player_123_NAME.webp',
    fallbacks: [],
    default: '/images/avatar-thumbs/player_default.webp',
  });
});

test('player detail avatars use full-avatar thumbnails and full avatar fallback', () => {
  assert.deepEqual(getPlayerDetailAvatarSources('player_123_NAME.png'), {
    primary: '/images/avatar-full-thumbs/player_123_NAME.webp',
    fallbacks: [],
    default: '/images/avatar-full-thumbs/player_default.webp',
  });
});

test('ranking avatars use default avatar when no avatar file is available', () => {
  assert.deepEqual(getRankingAvatarSources(null), {
    primary: '/images/avatar-thumbs/player_default.webp',
    fallbacks: [],
    default: '/images/avatar-thumbs/player_default.webp',
  });
});

test('player detail avatars use default avatar when no avatar file is available', () => {
  assert.deepEqual(getPlayerDetailAvatarSources(null), {
    primary: '/images/avatar-full-thumbs/player_default.webp',
    fallbacks: [],
    default: '/images/avatar-full-thumbs/player_default.webp',
  });
});
