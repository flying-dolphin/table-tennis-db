// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');
const { db } = require('./db.ts');
const { getPlayerDetail } = require('./players.ts');
const { getMatchDetail } = require('./events.ts');

test('current matches include named doubles entries and team roster ties', () => {
  const playerId = 9900991;
  const eventId = 9900991;
  db.exec('BEGIN');
  try {
    db.prepare("INSERT INTO players(player_id,name,slug,country_code) VALUES (?, 'Fixture Player', 'current-match-fixture', 'CHN')").run(playerId);
    db.prepare("INSERT INTO events(event_id,year,name,lifecycle_status,time_zone) VALUES (?,2099,'Current match fixture','in_progress','Asia/Shanghai')").run(eventId);

    const matchId = db.prepare(`
      INSERT INTO current_event_matches(event_id,sub_event_type_code,external_match_code,
        scheduled_local_at,scheduled_utc_at,status)
      VALUES (?,'XD','FIXTURE-XD','2099-01-01T10:00:00','2099-01-01T02:00:00Z','scheduled')
    `).run(eventId).lastInsertRowid;
    const doublesSide = db.prepare(`
      INSERT INTO current_event_match_sides(current_match_id,side_no,team_code) VALUES (?,?,?)
    `);
    const doublesPlayer = db.prepare(`
      INSERT INTO current_event_match_side_players(current_match_side_id,player_order,player_name,player_country)
      VALUES (?,?,?,?)
    `);
    const firstSideId = doublesSide.run(matchId, 1, 'CHN').lastInsertRowid;
    doublesPlayer.run(firstSideId, 1, 'Fixture Player', 'CHN');
    doublesPlayer.run(firstSideId, 2, 'Fixture Partner', 'CHN');
    const secondSideId = doublesSide.run(matchId, 2, 'JPN').lastInsertRowid;
    doublesPlayer.run(secondSideId, 1, 'Fixture Opponent A', 'JPN');
    doublesPlayer.run(secondSideId, 2, 'Fixture Opponent B', 'JPN');

    const tieId = db.prepare(`
      INSERT INTO current_event_team_ties(event_id,sub_event_type_code,external_match_code,
        scheduled_local_at,scheduled_utc_at,status)
      VALUES (?,'WT','FIXTURE-WT','2099-01-01T12:00:00','2099-01-01T04:00:00Z','scheduled')
    `).run(eventId).lastInsertRowid;
    const teamSide = db.prepare(`
      INSERT INTO current_event_team_tie_sides(current_team_tie_id,side_no,team_code) VALUES (?,?,?)
    `);
    const teamPlayer = db.prepare(`
      INSERT INTO current_event_team_tie_side_players(current_team_tie_side_id,player_order,player_name,player_country)
      VALUES (?,?,?,?)
    `);
    const homeId = teamSide.run(tieId, 1, 'CHN').lastInsertRowid;
    teamPlayer.run(homeId, 1, 'Fixture Player', 'CHN');
    teamPlayer.run(homeId, 2, 'Fixture Teammate', 'CHN');
    const awayId = teamSide.run(tieId, 2, 'JPN').lastInsertRowid;
    teamPlayer.run(awayId, 1, 'Fixture Opponent', 'JPN');

    const currentMatches = getPlayerDetail('current-match-fixture').currentMatches;
    assert.deepEqual(currentMatches.map((match) => match.subEventTypeCode), ['XD', 'WT']);
    assert.equal(currentMatches[0].sides[0].players.length, 2);
    assert.equal(currentMatches[1].matchId, tieId);
    assert.equal(currentMatches[1].opponentNames[0], 'JPN');
    assert.equal(getMatchDetail(`tie:${tieId}`)?.kind, 'tie');
  } finally {
    db.exec('ROLLBACK');
  }
});
