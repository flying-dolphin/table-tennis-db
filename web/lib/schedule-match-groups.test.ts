// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { groupChinaScheduleMatches } = require('./schedule-match-groups.ts');

function match(scheduleMatchId, sides) {
  return { scheduleMatchId, sides };
}

test('groups China team matches before other schedule matches while preserving order inside groups', () => {
  const matches = [
    match('other-first', [{ teamCode: 'JPN', players: [{ countryCode: 'JPN' }] }]),
    match('china-team', [{ teamCode: 'CHN', players: [] }]),
    match('china-player', [{ teamCode: null, players: [{ countryCode: 'CHN' }] }]),
    match('other-last', [{ teamCode: 'KOR', players: [{ countryCode: 'KOR' }] }]),
  ];

  assert.deepEqual(groupChinaScheduleMatches(matches), {
    chinaMatches: [matches[1], matches[2]],
    otherMatches: [matches[0], matches[3]],
  });
});
