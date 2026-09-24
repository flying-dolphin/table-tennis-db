// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { getEventDetail, getScheduleMatchDetail } = require('./events.ts');
const {
  buildTeamBracketRounds,
  buildTeamRoundFeeders,
  orderTeamRoundsByFeeders,
} = require('../team-knockout-bracket.ts');

test('Asian Games team byes complete the bracket without creating schedule matches', () => {
  const { db } = require('./db.ts');
  db.exec('BEGIN');
  try {
    for (const [code, byePositions] of [['WT', [1, 4, 5, 8]], ['MT', [1, 8]]]) {
      const eventId = code === 'WT' ? 966661 : 966662;
      db.prepare("INSERT INTO events(event_id,year,name,lifecycle_status,time_zone) VALUES (?,2026,'Team bye fixture','in_progress','Asia/Tokyo')").run(eventId);
      for (let position = 1; position <= 8; position++) {
        const external = `${code}.8FNL.${String(position).padStart(4, '0')}0000`;
        const bye = byePositions.includes(position);
        const a = `A${position}`;
        const b = bye ? 'BYE' : `B${position}`;
        db.prepare(`INSERT INTO current_event_brackets(event_id,sub_event_type_code,external_unit_code,
          stage_code,round_code,round_order,bracket_position,side_a_team_code,side_b_team_code,winner_side,status)
          VALUES (?, ?, ?, 'MAIN_DRAW','R16',40,?,?,?,'A','completed')`).run(eventId, code, external, position, a, b);
        if (!bye) {
          const id = db.prepare(`INSERT INTO current_event_team_ties(event_id,sub_event_type_code,external_match_code,
            stage_code,round_code,status,match_score,winner_side,winner_team_code,scheduled_local_at)
            VALUES (?,?,?,'MAIN_DRAW','R16','completed','3-0','A',?,'2026-09-22T10:00:00')`).run(eventId, code, external, a).lastInsertRowid;
          for (const [side, team] of [[1, a], [2, b]]) {
            db.prepare('INSERT INTO current_event_team_tie_sides(current_team_tie_id,side_no,team_code) VALUES (?,?,?)').run(id, side, team);
          }
        }
      }
      const detail = getEventDetail(eventId, code);
      const round = detail.teamKnockoutView.rounds.find((r) => r.code === 'R16');
      assert.equal(round.ties.length, 8);
      const byes = round.ties.filter((t) => t.teamA.code === 'BYE' || t.teamB.code === 'BYE');
      assert.equal(byes.length, byePositions.length);
      assert.ok(byes.every((t) => t.scheduleMatchId === null && t.winnerCode));
      const teams = new Set(round.ties.flatMap((t) => [t.teamA.code, t.teamB.code]).filter((c) => c !== 'BYE'));
      assert.equal(teams.size, code === 'WT' ? 12 : 14);
      assert.equal(db.prepare('SELECT count(*) n FROM current_event_team_ties WHERE event_id=?').get(eventId).n, 8 - byePositions.length);
    }
  } finally {
    db.exec('ROLLBACK');
  }
});

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
