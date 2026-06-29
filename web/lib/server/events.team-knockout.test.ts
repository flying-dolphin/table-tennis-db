// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { getEventDetail, getScheduleMatchDetail } = require('./events.ts');
const {
  buildTeamBracketRounds,
  buildTeamRoundFeeders,
  orderTeamRoundsByFeeders,
} = require('../team-knockout-bracket.ts');

function normalizeTeamRoundCode(code) {
  const rawCode = code.includes(':') ? code.slice(code.lastIndexOf(':') + 1) : code;
  const aliases = {
    F: 'Final',
    FNL: 'Final',
    'FNL-': 'Final',
    Final: 'Final',
    SF: 'SemiFinal',
    SFNL: 'SemiFinal',
    SemiFinal: 'SemiFinal',
    QF: 'QuarterFinal',
    QFNL: 'QuarterFinal',
    QuarterFinal: 'QuarterFinal',
    '8FNL': 'R16',
    R16: 'R16',
    R32: 'R32',
    R64: 'R64',
    R128: 'R128',
  };
  return aliases[rawCode] ?? rawCode;
}

function teamRoundGroupKey(code) {
  return code.includes(':') ? code.slice(0, code.lastIndexOf(':')) : 'main';
}

function buildBracketGroups(eventId, subEventCode) {
  const detail = getEventDetail(eventId, subEventCode);
  assert.ok(detail?.teamKnockoutView, `expected team knockout view for ${eventId}/${subEventCode}`);

  const groups = new Map();
  for (const round of detail.teamKnockoutView.rounds) {
    const key = teamRoundGroupKey(round.code);
    const current = groups.get(key) ?? [];
    current.push({
      ...round,
      code: normalizeTeamRoundCode(round.code),
    });
    groups.set(key, current);
  }

  return Array.from(groups.entries()).map(([key, rounds]) => ({
    key,
    bracketRounds: buildTeamBracketRounds(orderTeamRoundsByFeeders(rounds.sort((left, right) => left.order - right.order))),
  }));
}

function assertMatchedFeedersOnly(bracketRounds, label) {
  for (let roundIndex = 0; roundIndex < bracketRounds.length - 1; roundIndex += 1) {
    const currentRound = bracketRounds[roundIndex];
    const nextRound = bracketRounds[roundIndex + 1];
    const feedersByNode = buildTeamRoundFeeders(currentRound, nextRound);
    const used = new Set();

    feedersByNode.forEach((feeders, nodeIndex) => {
      const nextNode = nextRound.nodes[nodeIndex];
      feeders.forEach((feeder) => {
        const prevNode = currentRound.nodes[feeder.nodeIndex];
        assert.ok(prevNode, `${label} missing feeder node`);
        assert.equal(
          prevNode.tie.winnerCode,
          feeder.sideNo === 1 ? nextNode.teamA.code : nextNode.teamB.code,
          `${label} feeder winner must match target side`,
        );
        const dedupeKey = `${roundIndex}:${feeder.nodeIndex}`;
        assert.ok(!used.has(dedupeKey), `${label} feeder should not connect to multiple next-round ties`);
        used.add(dedupeKey);
      });
    });
  }
}

test('event 893 main draw keeps valid feeder links', () => {
  for (const subEventCode of ['WT', 'MT']) {
    const groups = buildBracketGroups(893, subEventCode);
    const mainGroup = groups.find((group) => group.key === 'main');
    assert.ok(mainGroup, `expected main group for 893/${subEventCode}`);
    assert.deepEqual(
      mainGroup.bracketRounds.map((round) => round.nodes.length),
      [4, 2, 1],
      `893/${subEventCode} should stay a standard knockout tree`,
    );
    assertMatchedFeedersOnly(mainGroup.bracketRounds, `893/${subEventCode}`);
  }
});

test('event 896 main draw uses real nodes and only matched feeder links', () => {
  for (const subEventCode of ['WT', 'MT']) {
    const groups = buildBracketGroups(896, subEventCode).filter((group) => group.key.startsWith('main'));
    assert.ok(groups.length > 0, `expected main groups for 896/${subEventCode}`);
    for (const group of groups) {
      assertMatchedFeedersOnly(group.bracketRounds, `896/${subEventCode}/${group.key}`);
    }
  }

  const wtGroups = buildBracketGroups(896, 'WT');
  const mainDivisionOne = wtGroups.find((group) => group.key === 'main-division-1');
  assert.ok(mainDivisionOne, 'expected WT main division 1 group');
  assert.deepEqual(
    mainDivisionOne.bracketRounds.map((round) => round.nodes.length),
    [4, 3, 2, 1],
    '896/WT main division 1 should render the special unified Korea branch without placeholder nodes',
  );
  assert.deepEqual(
    mainDivisionOne.bracketRounds[2].nodes.map((node) => `${node.tie.teamA.code}-${node.tie.teamB.code}`),
    ['CHN-HKG', 'KOR/PRK-JPN'],
    '896/WT main division 1 semifinals should display the unified Korea branch',
  );
  const quarterToSemiFeeders = buildTeamRoundFeeders(
    mainDivisionOne.bracketRounds[1],
    mainDivisionOne.bracketRounds[2],
  );
  assert.deepEqual(
    quarterToSemiFeeders[1],
    [{ sideNo: 2, nodeIndex: 2 }],
    '896/WT UKR-JPN quarterfinal should feed the unified Korea semifinal branch',
  );
});

test('event 896 SGP-UKR historical tie detail merges the LIN Ye rubber into a 5-match tie', () => {
  const detail = getScheduleMatchDetail(-2921);
  assert.ok(detail, 'expected merged historical schedule match detail');
  assert.equal(detail.match.matchScore, '2-3');
  assert.equal(detail.rubbers.length, 5);
  assert.deepEqual(
    detail.sides.map((side) => side.teamCode),
    ['SGP', 'UKR'],
    'historical player country normalization should merge CAN into SGP for this tie',
  );
  assert.ok(
    detail.rubbers.some((rubber) => rubber.sides.some((side) => side.players.some((player) => player.name === 'LIN Ye'))),
    'merged tie should include the LIN Ye rubber',
  );
});

test('event 896 WT can display the unified KOR/PRK semifinal branch', () => {
  const groups = buildBracketGroups(896, 'WT');
  const mainDivisionOne = groups.find((group) => group.key === 'main-division-1');
  assert.ok(mainDivisionOne, 'expected WT main division 1 group');
  assert.deepEqual(
    mainDivisionOne.bracketRounds.map((round) => round.nodes.length),
    [4, 3, 2, 1],
    '896/WT main division 1 should collapse the special unified Korea branch into a 2-semifinal display',
  );
  assert.deepEqual(
    mainDivisionOne.bracketRounds[2].nodes.map((node) => `${node.tie.teamA.code}-${node.tie.teamB.code}`),
    ['CHN-HKG', 'KOR/PRK-JPN'],
    '896/WT semifinal display should use a unified KOR/PRK branch',
  );
});

test('event 896 WT uses dual bronze podium without a fake bronze tie', () => {
  const detail = getEventDetail(896, 'WT');
  assert.ok(detail?.teamKnockoutView, 'expected team knockout view');
  assert.equal(detail.teamKnockoutView.bronzeTie, null, '896/WT should not fabricate a bronze medal match');
  assert.equal(detail.teamKnockoutView.podium.thirdPlace?.teamCode, 'KOR/PRK');
  assert.equal(detail.teamKnockoutView.podium.thirdPlaceSecond?.teamCode, 'HKG');
});

test('event 896 WT unified KOR/PRK branch exposes an aggregate schedule detail page', () => {
  const detail = getScheduleMatchDetail('override:896:WT:KOR-PRK-JPN');
  assert.ok(detail, 'expected aggregate schedule match detail');
  assert.equal(detail.match.scheduleMatchId, 'override:896:WT:KOR-PRK-JPN');
  assert.equal(detail.match.matchScore, '0-3');
  assert.equal(detail.sides[0]?.teamCode, 'KOR/PRK');
  assert.equal(detail.sides[1]?.teamCode, 'JPN');
  assert.equal(detail.rubbers.length, 3);
  assert.ok(
    detail.rubbers.some((rubber) => rubber.sides.some((side) => side.players.some((player) => player.countryCode === 'PRK'))),
    'aggregate detail should retain original PRK players from the source ties',
  );
});

test('match detail route supports historical team ties', () => {
  const { getMatchDetail } = require('./events.ts');
  const detail = getMatchDetail('tie:-2921');

  assert.ok(detail, 'expected team tie detail from match route');
  assert.equal(detail.kind, 'tie');
  assert.equal(detail.match.scheduleMatchId, -2921);
  assert.equal(detail.match.matchScore, '2-3');
  assert.equal(detail.rubbers.length, 5);
});
