// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { db } = require('./db.ts');
const { getEventDetail, getEvents, getMatchDetail, getScheduleMatchDetail } = require('./events.ts');

function insertCompletedTeamTieFixture(eventId) {
  const tieId = eventId;
  db.prepare(`
    INSERT INTO events (
      event_id, year, name, name_zh, start_date, end_date, lifecycle_status, time_zone
    ) VALUES (?, 2026, 'Team Tie Fixture', '团体赛测试', '2026-09-20', '2026-09-20',
      'in_progress', 'Asia/Tokyo')
  `).run(eventId);
  db.prepare(`
    INSERT INTO current_event_team_ties (
      current_team_tie_id, event_id, sub_event_type_code, external_match_code,
      scheduled_local_at, scheduled_utc_at, status, match_score, winner_side, winner_team_code
    ) VALUES (?, ?, 'WT', 'FIXTURE-WT-1', '2026-09-20T10:00:00',
      '2026-09-20T01:00:00Z', 'completed', '3-0', 'A', 'JPN')
  `).run(tieId, eventId);

  for (const [sideNo, teamCode, names] of [
    [1, 'JPN', ['Roster A1', 'Roster A2', 'Roster A3', 'Roster A4', 'Roster A5']],
    [2, 'KOR', ['Roster B1', 'Roster B2', 'Roster B3', 'Roster B4', 'Roster B5']],
  ]) {
    const sideId = db.prepare(`
      INSERT INTO current_event_team_tie_sides (current_team_tie_id, side_no, team_code, is_winner)
      VALUES (?, ?, ?, ?)
    `).run(tieId, sideNo, teamCode, sideNo === 1 ? 1 : 0).lastInsertRowid;
    names.forEach((name, index) => {
      db.prepare(`
        INSERT INTO current_event_team_tie_side_players (
          current_team_tie_side_id, player_order, player_name, player_country
        ) VALUES (?, ?, ?, ?)
      `).run(sideId, index + 1, name, teamCode);
    });
  }

  const insertMatch = db.prepare(`
    INSERT INTO current_event_matches (
      current_match_id, event_id, current_team_tie_id, sub_event_type_code,
      external_match_code, scheduled_local_at, scheduled_utc_at, status,
      match_score, games, winner_side, winner_name
    ) VALUES (?, ?, ?, 'WT', ?, '2026-09-20T10:00:00', '2026-09-20T01:00:00Z', ?, ?, ?, ?, ?)
  `);
  for (let index = 1; index <= 5; index += 1) {
    const matchId = eventId + index;
    const played = index <= 3;
    insertMatch.run(
      matchId,
      eventId,
      tieId,
      `FIXTURE-WT-1${index}`,
      played ? 'completed' : 'cancelled',
      played ? '3-0' : null,
      played ? JSON.stringify([{ player: 11, opponent: index }]) : '[]',
      played ? 'A' : null,
      played ? `Actual A${index}` : null,
    );
    for (const [sideNo, teamCode, playerName] of [
      [1, 'JPN', played ? `Actual A${index}` : `Planned A${index}`],
      [2, 'KOR', played ? `Actual B${index}` : `Planned B${index}`],
    ]) {
      const matchSideId = db.prepare(`
        INSERT INTO current_event_match_sides (current_match_id, side_no, team_code, is_winner)
        VALUES (?, ?, ?, ?)
      `).run(matchId, sideNo, teamCode, played && sideNo === 1 ? 1 : 0).lastInsertRowid;
      db.prepare(`
        INSERT INTO current_event_match_side_players (
          current_match_side_id, player_order, player_name, player_country
        ) VALUES (?, 1, ?, ?)
      `).run(matchSideId, playerName, teamCode);
    }
  }
  return { tieId };
}

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

test('Asian Games defaults to the team event when no sub-event is requested', () => {
  assert.equal(getEventDetail(6666).selectedSubEvent, 'WT');
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

test('current event champion is inferred from a completed final before sub_events exists', () => {
  const eventId = 990001;
  const currentMatchId = 990001;

  const rollback = db.transaction(() => {
    db.prepare(`
      INSERT INTO events (
        event_id, year, name, name_zh, total_matches, start_date, end_date,
        lifecycle_status, time_zone
      ) VALUES (?, 2026, 'Current Champion Fixture', '当前冠军测试赛事', 1, '2026-07-01', '2026-07-02',
        'in_progress', 'America/New_York')
    `).run(eventId);

    db.prepare(`
      INSERT INTO current_event_matches (
        current_match_id, event_id, sub_event_type_code, stage_label, stage_code,
        round_label, round_code, external_match_code, status, match_score,
        winner_side, winner_name
      ) VALUES (?, ?, 'WS', 'Main Draw', 'MAIN', 'FNL', 'F', 'FIXTURE-WS-F', 'completed',
        '4-2', 'A', 'SUN Yingsha')
    `).run(currentMatchId, eventId);

    const sideA = db.prepare(`
      INSERT INTO current_event_match_sides (current_match_id, side_no, is_winner)
      VALUES (?, 1, 1)
    `).run(currentMatchId).lastInsertRowid;
    const sideB = db.prepare(`
      INSERT INTO current_event_match_sides (current_match_id, side_no, is_winner)
      VALUES (?, 2, 0)
    `).run(currentMatchId).lastInsertRowid;

    db.prepare(`
      INSERT INTO current_event_match_side_players (
        current_match_side_id, player_order, player_id, player_name, player_country
      ) VALUES (?, 1, 131163, 'SUN Yingsha', 'CHN')
    `).run(sideA);
    db.prepare(`
      INSERT INTO current_event_match_side_players (
        current_match_side_id, player_order, player_id, player_name, player_country
      ) VALUES (?, 1, 135049, 'KUAI Man', 'CHN')
    `).run(sideB);

    const detail = getEventDetail(eventId, 'WS');
    assert.equal(detail.subEvents[0].champion.championName, 'SUN Yingsha');
    assert.equal(detail.subEvents[0].champion.championCountryCode, 'CHN');
    assert.deepEqual(
      detail.subEvents[0].champion.players.map((player) => ({
        playerId: player.playerId,
        name: player.name,
        nameZh: player.nameZh,
        countryCode: player.countryCode,
      })),
      [{ playerId: 131163, name: 'SUN Yingsha', nameZh: '孙颖莎', countryCode: 'CHN' }],
    );
    assert.equal(detail.subEventDetails[0].champion.championName, 'SUN Yingsha');

    throw new Error('rollback fixture');
  });

  assert.throws(() => rollback(), /rollback fixture/);
});

test('current event does not infer a champion from a completed semifinal', () => {
  const eventId = 990003;
  const semifinalMatchId = 990003;

  const rollback = db.transaction(() => {
    db.prepare(`
      INSERT INTO events (
        event_id, year, name, name_zh, total_matches, start_date, end_date,
        lifecycle_status, time_zone
      ) VALUES (?, 2026, 'Current Semifinal Fixture', '半决赛未结束测试赛事', 2, '2026-07-01', '2026-07-02',
        'in_progress', 'America/New_York')
    `).run(eventId);

    db.prepare(`
      INSERT INTO current_event_matches (
        current_match_id, event_id, sub_event_type_code, stage_label, stage_code,
        round_label, round_code, external_match_code, status, match_score,
        winner_side, winner_name
      ) VALUES
        (?, ?, 'WS', 'Main Draw', 'MAIN', 'Women''s Singles - Semi-Final', 'SF', 'FIXTURE-WS-SF', 'completed', '4-2', 'A', 'SUN Yingsha'),
        (?, ?, 'WS', 'Main Draw', 'MAIN', 'Women''s Singles - Final', 'F', 'FIXTURE-WS-F', 'scheduled', NULL, NULL, NULL)
    `).run(semifinalMatchId, eventId, semifinalMatchId + 1, eventId);

    const sideA = db.prepare(`
      INSERT INTO current_event_match_sides (current_match_id, side_no, is_winner)
      VALUES (?, 1, 1)
    `).run(semifinalMatchId).lastInsertRowid;
    const sideB = db.prepare(`
      INSERT INTO current_event_match_sides (current_match_id, side_no, is_winner)
      VALUES (?, 2, 0)
    `).run(semifinalMatchId).lastInsertRowid;

    db.prepare(`
      INSERT INTO current_event_match_side_players (
        current_match_side_id, player_order, player_id, player_name, player_country
      ) VALUES (?, 1, 131163, 'SUN Yingsha', 'CHN')
    `).run(sideA);
    db.prepare(`
      INSERT INTO current_event_match_side_players (
        current_match_side_id, player_order, player_id, player_name, player_country
      ) VALUES (?, 1, 135049, 'KUAI Man', 'CHN')
    `).run(sideB);

    const detail = getEventDetail(eventId, 'WS');
    assert.equal(detail.subEvents[0].champion, null);

    throw new Error('rollback fixture');
  });

  assert.throws(() => rollback(), /rollback fixture/);
});

test('event list counts current matches for finished current events before promotion', () => {
  const eventId = 990002;

  const rollback = db.transaction(() => {
    db.prepare(`
      INSERT INTO events (
        event_id, year, name, name_zh, total_matches, start_date, end_date,
        lifecycle_status, time_zone
      ) VALUES (?, 2026, 'Finished Current Fixture', '已完赛未归档测试赛事', 0, '2026-07-01', '2026-07-02',
        'in_progress', 'America/New_York')
    `).run(eventId);

    db.prepare(`
      INSERT INTO current_event_matches (
        event_id, sub_event_type_code, stage_label, stage_code, round_label, round_code,
        external_match_code, status, match_score, winner_side, winner_name
      ) VALUES
        (?, 'WS', 'Main Draw', 'MAIN', 'FNL', 'F', 'FIXTURE-LIST-WS-F', 'completed', '4-2', 'A', 'SUN Yingsha'),
        (?, 'MS', 'Main Draw', 'MAIN', 'FNL', 'F', 'FIXTURE-LIST-MS-F', 'completed', '4-1', 'B', 'MATSUSHIMA Sora')
    `).run(eventId, eventId);

    const result = getEvents({ year: 2026, limit: 100, ageGroup: 'all' });
    const event = result.events.find((item) => item.eventId === eventId);

    assert.ok(event, 'expected fixture event in list');
    assert.equal(event.matchCount, 2);
    assert.equal(event.importedMatches, 2);
    assert.equal(event.displayStatus, 'finished_pending_promotion');

    throw new Error('rollback fixture');
  });

  assert.throws(() => rollback(), /rollback fixture/);
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

test('current team schedule keeps the tie score and lists all mandatory-rubber players', () => {
  const eventId = 990010;
  const rollback = db.transaction(() => {
    const { tieId } = insertCompletedTeamTieFixture(eventId);
    const detail = getEventDetail(eventId, 'WT');
    const scheduleMatch = detail.scheduleDays.flatMap((day) => day.matches)[0];

    assert.equal(scheduleMatch.scheduleMatchId, tieId, 'schedule must keep the aggregate team-tie link');
    assert.equal(scheduleMatch.matchScore, '3-0', 'schedule must keep the aggregate team score');
    assert.deepEqual(
      scheduleMatch.sides.map((side) => side.players.map((player) => player.name)),
      [['Actual A1', 'Actual A2', 'Actual A3'], ['Actual B1', 'Actual B2', 'Actual B3']],
    );
    assert.deepEqual(scheduleMatch.games, [], 'team-tie list must not expose individual game scores');
    throw new Error('rollback fixture');
  });

  assert.throws(() => rollback(), /rollback fixture/);
});

test('current team tie detail shows all played rubbers and hides unplayed cancellations', () => {
  const eventId = 990020;
  const rollback = db.transaction(() => {
    const { tieId } = insertCompletedTeamTieFixture(eventId);
    const detail = getScheduleMatchDetail(tieId);

    assert.ok(detail, 'expected aggregate team-tie detail');
    assert.equal(detail.match.scheduleMatchId, tieId);
    assert.equal(detail.match.matchScore, '3-0');
    assert.deepEqual(
      detail.sides.map((side) => side.players.map((player) => player.name)),
      [['Actual A1', 'Actual A2', 'Actual A3'], ['Actual B1', 'Actual B2', 'Actual B3']],
    );
    assert.equal(detail.rubbers.length, 3, 'cancelled M4/M5 must not be displayed');
    assert.deepEqual(
      detail.rubbers.map((rubber) => rubber.sides.map((side) => side.players.map((player) => player.name))),
      [
        [['Actual A1'], ['Actual B1']],
        [['Actual A2'], ['Actual B2']],
        [['Actual A3'], ['Actual B3']],
      ],
    );
    assert.deepEqual(detail.rubbers[0].games, [{ player: 11, opponent: 1 }]);
    throw new Error('rollback fixture');
  });

  assert.throws(() => rollback(), /rollback fixture/);
});

test('historical individual bracket keeps match id for match-detail links', () => {
  const detail = getEventDetail(3379, 'WS');
  const final = detail.bracket.find((round) => round.code === 'Final');

  assert.ok(final, 'expected WS final bracket');
  assert.equal(final.matches[0].matchId, 309247);
  assert.equal(final.matches[0].scheduleMatchId, null);
});
