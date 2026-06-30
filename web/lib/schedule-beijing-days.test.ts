// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { regroupScheduleDaysByBeijingDate } = require('./schedule-beijing-days.ts');

test('groups schedule matches by Beijing date instead of event-local date', () => {
  const days = [
    {
      localDate: '2026-06-30',
      matches: [
        {
          scheduleMatchId: 'cm:1',
          subEventTypeCode: 'WS',
          scheduledLocalAt: '2026-06-30T21:30:00',
          scheduledUtcAt: '2026-06-30T16:30:00Z',
        },
      ],
    },
  ];

  assert.deepEqual(regroupScheduleDaysByBeijingDate(days, 'Europe/London', 'WS'), [
    {
      localDate: '2026-07-01',
      matches: days[0].matches,
    },
  ]);
});
