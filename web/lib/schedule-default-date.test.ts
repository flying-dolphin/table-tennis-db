// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { getDefaultScheduleDate } = require('./schedule-default-date.ts');

test('schedule tab defaults to today when that sub-event has matches today', () => {
  assert.equal(
    getDefaultScheduleDate(
      [{ localDate: '2026-09-20' }, { localDate: '2026-09-23' }],
      '2026-09-20',
    ),
    '2026-09-20',
  );
});

test('schedule tab falls back to the earliest available date when today has no matches', () => {
  assert.equal(
    getDefaultScheduleDate(
      [{ localDate: '2026-09-23' }, { localDate: '2026-09-25' }],
      '2026-09-20',
    ),
    '2026-09-23',
  );
});

test('completed events default to the latest available date', () => {
  assert.equal(
    getDefaultScheduleDate(
      [{ localDate: '2026-09-23' }, { localDate: '2026-09-25' }],
      '2026-09-20',
      { preferLatest: true },
    ),
    '2026-09-25',
  );
});

test('schedule tab returns null when the sub-event has no dated schedule', () => {
  assert.equal(getDefaultScheduleDate([], '2026-09-20'), null);
});
