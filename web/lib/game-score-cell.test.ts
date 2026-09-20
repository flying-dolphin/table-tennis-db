// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { getGameScoreCellState } = require('./game-score-cell.ts');

test('score table marks the side with the higher game score as the winner', () => {
  assert.equal(getGameScoreCellState(11, 6), 'winner');
  assert.equal(getGameScoreCellState(6, 11), 'loser');
});

test('score table leaves tied or unavailable game scores neutral', () => {
  assert.equal(getGameScoreCellState(0, 0), 'neutral');
  assert.equal(getGameScoreCellState(null, 11), 'neutral');
});
