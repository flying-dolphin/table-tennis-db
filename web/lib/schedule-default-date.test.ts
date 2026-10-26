// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { getDefaultScheduleDate } = require('./schedule-default-date.ts');

test('schedule tab selects today when today has matches', (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2026-09-20T04:00:00Z') });
  assert.equal(
    getDefaultScheduleDate(
      [{ localDate: '2026-09-20' }, { localDate: '2026-09-23' }],
    ),
    '2026-09-20',
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

test('schedule tab selects the first day for upcoming schedules', (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2026-09-20T04:00:00Z') });
  assert.equal(
    getDefaultScheduleDate(
      [{ localDate: '2026-09-23' }, { localDate: '2026-09-25' }],
    ),
    '2026-09-23',
  );
});

test('schedule tab selects the next match day during a gap', (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2026-09-24T04:00:00Z') });
  assert.equal(
    getDefaultScheduleDate([
      { localDate: '2026-09-23' },
      { localDate: '2026-09-25' },
      { localDate: '2026-09-27' },
    ]),
    '2026-09-25',
  );
});

test('schedule tab determines today in Beijing time across UTC midnight', (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2026-09-23T17:00:00Z') });
  assert.equal(
    getDefaultScheduleDate([{ localDate: '2026-09-23' }, { localDate: '2026-09-24' }]),
    '2026-09-24',
  );
});

test('schedule tab ignores undated entries when selecting the last match day', (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2026-09-26T04:00:00Z') });
  assert.equal(
    getDefaultScheduleDate([
      { localDate: '2026-09-25' },
      { localDate: '2026-09-23' },
      { localDate: '日期待定' },
    ]),
    '2026-09-25',
  );
});

test('schedule tab keeps the undated tab when no match has a date', () => {
  assert.equal(getDefaultScheduleDate([{ localDate: '日期待定' }]), '日期待定');
});

test('schedule tab returns null when the sub-event has no dated schedule', () => {
  assert.equal(getDefaultScheduleDate([]), null);
});

test('schedule tab returns the only day for a single-day schedule', () => {
  assert.equal(getDefaultScheduleDate([{ localDate: '2026-09-23' }]), '2026-09-23');
});
