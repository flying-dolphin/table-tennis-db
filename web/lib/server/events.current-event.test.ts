// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { getEventDetail } = require('./events.ts');

test('current individual bracket uses player names from WTT bracket payload', () => {
  const detail = getEventDetail(3242, 'MS');
  const roundOf64 = detail.bracket.find((round) => round.code === 'R64');

  assert.ok(roundOf64, 'expected R64 bracket for event 3242 MS');
  const firstMatch = roundOf64.matches[0];

  assert.equal(firstMatch.sides[0].players[0]?.name, 'WANG Chuqin');
  assert.equal(firstMatch.sides[0].players[0]?.nameZh, '王楚钦');
  assert.equal(firstMatch.sides[0].players[0]?.countryCode, 'CHN');
  assert.notEqual(firstMatch.sides[0].players[0]?.name, 'CHN');
});

test('current bracket preserves draw groups and feeder previous units', () => {
  const detail = getEventDetail(3242, 'MS');
  const mainRound = detail.bracket.find((round) => round.drawCode === 'MAIN' && round.code === 'R64');
  const preliminaryRound = detail.bracket.find((round) => round.drawCode === 'PREL' && round.code === 'R1');
  const roundOf32 = detail.bracket.find((round) => round.drawCode === 'MAIN' && round.code === 'R32');

  assert.ok(mainRound, 'expected MAIN R64');
  assert.ok(preliminaryRound, 'expected PREL R1');
  assert.ok(roundOf32, 'expected MAIN R32');
  assert.equal(mainRound.matches.length, 32);
  assert.equal(preliminaryRound.matches.length, 32);
  assert.equal(roundOf32.matches[0].sides[0].previousUnit, 'TTEMSINGLES-----------R64-000100--');
});
