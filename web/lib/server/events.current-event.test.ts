// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { getEventDetail, getMatchDetail } = require('./events.ts');

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

test('current main draw bracket rounds are ordered from early rounds to final', () => {
  const detail = getEventDetail(3242, 'MS');
  const mainRounds = detail.bracket.filter((round) => round.drawCode === 'MAIN');

  assert.deepEqual(
    mainRounds.map((round) => round.code),
    ['R64', 'R32', 'R16', 'QF', 'SF', 'F'],
  );
  assert.deepEqual(
    mainRounds.map((round) => round.order),
    [20, 30, 40, 50, 60, 80],
  );
});

test('historical main draw bracket rounds are ordered from early rounds to final', () => {
  const detail = getEventDetail(3240, 'WS');

  assert.deepEqual(
    detail.bracket.map((round) => round.code),
    ['R32', 'R16', 'QuarterFinal', 'SemiFinal', 'Final'],
  );
  assert.deepEqual(
    detail.bracket.map((round) => round.order),
    [30, 40, 50, 60, 80],
  );
});

test('historical single-elimination bracket exposes inferred feeders for partial round of 64', () => {
  const women = getEventDetail(3241, 'WS');
  const womenRoundOf64 = women.bracket.find((round) => round.code === 'R64');
  const womenRoundOf32 = women.bracket.find((round) => round.code === 'R32');

  assert.ok(womenRoundOf64, 'expected WS R64 bracket for event 3241');
  assert.ok(womenRoundOf32, 'expected WS R32 bracket for event 3241');
  assert.equal(womenRoundOf64.matches.length, 16);
  assert.equal(womenRoundOf32.matches.length, 16);
  const firstWomenFeeder = womenRoundOf32.matches[0].sides.find((side) => side.previousUnit != null);
  assert.equal(firstWomenFeeder?.previousUnit, `match:${womenRoundOf64.matches[0].matchId}`);
  const womenAkaeR64 = womenRoundOf64.matches.find((match) => match.sides.some((side) => side.isWinner && side.players[0]?.name === 'AKAE Kaho'));
  const womenAkaeR32 = womenRoundOf32.matches.find((match) => match.sides.some((side) => side.players[0]?.name === 'AKAE Kaho'));
  assert.ok(womenAkaeR64, 'expected AKAE Kaho R64 match');
  assert.ok(womenAkaeR32, 'expected AKAE Kaho R32 match');
  assert.ok(womenAkaeR32.sides.some((side) => side.previousUnit === `match:${womenAkaeR64.matchId}`));

  const men = getEventDetail(3241, 'MS');
  const menRoundOf64 = men.bracket.find((round) => round.code === 'R64');
  const menRoundOf32 = men.bracket.find((round) => round.code === 'R32');

  assert.ok(menRoundOf64, 'expected MS R64 bracket for event 3241');
  assert.ok(menRoundOf32, 'expected MS R32 bracket for event 3241');
  assert.equal(menRoundOf64.matches.length, 16);
  assert.equal(menRoundOf32.matches.length, 16);
  const firstMenFeeder = menRoundOf32.matches[0].sides.find((side) => side.previousUnit != null);
  assert.equal(firstMenFeeder?.previousUnit, `match:${menRoundOf64.matches[0].matchId}`);
  const menKuoR64 = menRoundOf64.matches.find((match) => match.sides.some((side) => side.isWinner && side.players[0]?.name === 'KUO Guan-Hong'));
  const menKuoR32 = menRoundOf32.matches.find((match) => match.sides.some((side) => side.players[0]?.name === 'KUO Guan-Hong'));
  assert.ok(menKuoR64, 'expected KUO Guan-Hong R64 match');
  assert.ok(menKuoR32, 'expected KUO Guan-Hong R32 match');
  assert.ok(menKuoR32.sides.some((side) => side.previousUnit === `match:${menKuoR64.matchId}`));
});

test('current individual bracket links completed matches to current match details', () => {
  const detail = getEventDetail(3242, 'WS');
  const roundOf64 = detail.bracket.find((round) => round.drawCode === 'MAIN' && round.code === 'R64');

  assert.ok(roundOf64, 'expected WS MAIN R64 bracket');
  const shaoMeshref = roundOf64.matches.find((match) => match.externalUnitCode === 'TTEWSINGLES-----------R64-000300--');

  assert.ok(shaoMeshref, 'expected SHAO Jieni vs MESHREF Dina bracket match');
  assert.equal(shaoMeshref.scheduleMatchId, 'cm:1320');
});

test('current match detail parses comma-separated game scores', () => {
  const detail = getMatchDetail('cm:1320');

  assert.ok(detail, 'expected current match detail');
  assert.equal(detail.match.matchId, 'cm:1320');
  assert.equal(detail.match.status, 'completed');
  assert.equal(detail.match.matchScore, '1-3');
  assert.deepEqual(detail.match.games, [
    { player: 8, opponent: 11 },
    { player: 11, opponent: 9 },
    { player: 8, opponent: 11 },
    { player: 5, opponent: 11 },
  ]);
});

test('historical individual bracket keeps match id for match-detail links', () => {
  const detail = getEventDetail(3379, 'WS');
  const final = detail.bracket.find((round) => round.code === 'Final');

  assert.ok(final, 'expected WS final bracket');
  assert.equal(final.matches[0].matchId, 309247);
  assert.equal(final.matches[0].scheduleMatchId, null);
});
