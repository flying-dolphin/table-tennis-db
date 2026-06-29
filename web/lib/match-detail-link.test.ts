// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { matchDetailPath } = require('./match-detail-link.ts');

test('does not link matches without a score', () => {
  assert.equal(matchDetailPath({ hasScore: false, scheduleMatchId: 'cm:1371', matchId: 6395 }), null);
  assert.equal(matchDetailPath({ hasScore: false, scheduleMatchId: 11, matchId: 4921 }), null);
});

test('links current individual matches directly without tie prefix', () => {
  assert.equal(matchDetailPath({ hasScore: true, scheduleMatchId: 'cm:1371', matchId: 6395 }), '/matches/cm:1371');
});

test('links team ties with tie prefix', () => {
  assert.equal(matchDetailPath({ hasScore: true, scheduleMatchId: 11, matchId: 4921, kind: 'tie' }), '/matches/tie:11');
  assert.equal(
    matchDetailPath({ hasScore: true, scheduleMatchId: 'override:896:WT:KOR-PRK-JPN', kind: 'tie' }),
    '/matches/tie:override:896:WT:KOR-PRK-JPN',
  );
});

test('links historical individual matches by match id', () => {
  assert.equal(matchDetailPath({ hasScore: true, scheduleMatchId: null, matchId: 309247 }), '/matches/309247');
});
