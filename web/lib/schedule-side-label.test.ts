// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { scheduleSidePrimaryLabel } = require('./schedule-side-label.ts');

test('team schedule sides always display the country code instead of player names', () => {
  assert.equal(
    scheduleSidePrimaryLabel({
      isTeamMatch: true,
      teamCode: 'CHN',
      playerNames: ['陈熠', '蒯曼', '范姝涵'],
      placeholderText: null,
    }),
    'CHN',
  );
  assert.equal(
    scheduleSidePrimaryLabel({
      isTeamMatch: true,
      teamCode: 'NEP',
      playerNames: [],
      placeholderText: null,
    }),
    'NEP',
  );
});

test('individual schedule sides keep displaying player names', () => {
  assert.equal(
    scheduleSidePrimaryLabel({
      isTeamMatch: false,
      teamCode: 'CHN',
      playerNames: ['孙颖莎'],
      placeholderText: null,
    }),
    '孙颖莎',
  );
});
