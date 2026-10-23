// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { getDefaultScheduleDate } = require('./schedule-default-date.ts');

test('schedule tab defaults to the last displayed day even when today has matches', (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2026-09-20T04:00:00Z') });
  assert.equal(
    getDefaultScheduleDate(
      [{ localDate: '2026-09-20' }, { localDate: '2026-09-23' }],
    ),
    '2026-09-23',
  );
});

test('schedule tab defaults to the last displayed day when today has no matches', (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2026-09-26T04:00:00Z') });
  assert.equal(
    getDefaultScheduleDate(
      [{ localDate: '2026-09-23' }, { localDate: '2026-09-25' }],
    ),
    '2026-09-25',
  );
});

test('schedule tab selects the last day for upcoming schedules too', (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2026-09-20T04:00:00Z') });
  assert.equal(
    getDefaultScheduleDate(
      [{ localDate: '2026-09-23' }, { localDate: '2026-09-25' }],
    ),
    '2026-09-25',
  );
});

test('schedule tab returns null when the sub-event has no dated schedule', () => {
  assert.equal(getDefaultScheduleDate([]), null);
});

test('schedule tab returns the only day for a single-day schedule', () => {
  assert.equal(getDefaultScheduleDate([{ localDate: '2026-09-23' }]), '2026-09-23');
});
