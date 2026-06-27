// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { shouldUseScheduleTabs } = require('./event-view-mode.ts');

test('uses schedule tabs for completed current events with session data', () => {
  assert.equal(
    shouldUseScheduleTabs({
      lifecycleStatus: 'completed',
      sessionScheduleCount: 13,
      scheduleDays: [{ localDate: '2026-05-01' }],
    }),
    true,
  );
});

test('uses schedule tabs for completed current events with real dated schedule days', () => {
  assert.equal(
    shouldUseScheduleTabs({
      lifecycleStatus: 'completed',
      sessionScheduleCount: 0,
      scheduleDays: [{ localDate: '2026-05-01' }],
    }),
    true,
  );
});

test('does not use schedule tabs for historical fallback days without real dates', () => {
  assert.equal(
    shouldUseScheduleTabs({
      lifecycleStatus: 'completed',
      sessionScheduleCount: 0,
      scheduleDays: [{ localDate: '日期待定' }],
    }),
    false,
  );
});

test('shows Beijing time for completed events outside China', () => {
  const { shouldShowBeijingTimeForEvent } = require('./event-view-mode.ts');

  assert.equal(shouldShowBeijingTimeForEvent('completed', 'Europe/London'), true);
});

test('does not show duplicate Beijing time for China events', () => {
  const { shouldShowBeijingTimeForEvent } = require('./event-view-mode.ts');

  assert.equal(shouldShowBeijingTimeForEvent('in_progress', 'Asia/Shanghai'), false);
});
