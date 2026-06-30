// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { getVisibleSideAvatarPlayers } = require('./match-side-avatars.ts');

test('uses one visible avatar for singles sides', () => {
  const players = [
    { playerId: 1, name: 'A' },
  ];

  assert.deepEqual(getVisibleSideAvatarPlayers(players), players);
});

test('uses two visible avatars for doubles sides', () => {
  const players = [
    { playerId: 1, name: 'A' },
    { playerId: 2, name: 'B' },
  ];

  assert.deepEqual(getVisibleSideAvatarPlayers(players), players);
});

test('limits visible avatars to the first two players', () => {
  const players = [
    { playerId: 1, name: 'A' },
    { playerId: 2, name: 'B' },
    { playerId: 3, name: 'C' },
  ];

  assert.deepEqual(getVisibleSideAvatarPlayers(players), players.slice(0, 2));
});
