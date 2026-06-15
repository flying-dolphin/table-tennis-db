// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { getPlayerBySlug } = require('./players.ts');
const { getPlayerAggregateStats } = require('./stats.ts');

test('does not count a team-final rubber win as a major title', () => {
  const player = getPlayerBySlug('harimoto-miwa');
  assert.ok(player, 'expected HARIMOTO Miwa in the player database');

  const stats = getPlayerAggregateStats([player.playerId]).get(player.playerId);
  assert.ok(stats, 'expected aggregate stats for HARIMOTO Miwa');
  assert.equal(stats.allThreeTitles, 0);
});
