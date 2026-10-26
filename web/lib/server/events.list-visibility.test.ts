// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const originalCwd = process.cwd();
const schema = fs.readFileSync(path.resolve(originalCwd, '../scripts/db/schema.sql'), 'utf8');
const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'ittf-event-list-'));
fs.mkdirSync(path.join(temporaryRoot, 'web'));
process.chdir(path.join(temporaryRoot, 'web'));

const { db } = require('./db.ts');
db.exec(schema);
const { getEvents } = require('./events.ts');

test.after(() => {
  db.close();
  process.chdir(originalCwd);
  fs.rmSync(temporaryRoot, { recursive: true, force: true });
});

test('future events with session schedules appear as upcoming and count toward pagination', () => {
  db.exec('BEGIN');
  try {
    const insertEvent = db.prepare(`
      INSERT INTO events (event_id, year, name, start_date, end_date, lifecycle_status, time_zone)
      VALUES (?, 2099, ?, ?, ?, 'upcoming', 'Europe/Paris')
    `);
    insertEvent.run(990080, 'Visibility scheduled future', '2099-10-27', '2099-11-01');
    insertEvent.run(990081, 'Visibility unscheduled future', '2099-10-28', '2099-11-01');
    insertEvent.run(990082, 'Visibility scheduled past', '2020-01-01', '2020-01-02');
    insertEvent.run(990083, 'Visibility scheduled unknown date', null, null);
    const insertSession = db.prepare(`
      INSERT INTO current_event_session_schedule (event_id, day_index, session_index, local_date)
      VALUES (?, 1, 1, ?)
    `);
    insertSession.run(990080, '2099-10-27');
    insertSession.run(990082, '2020-01-01');
    insertSession.run(990083, '2099-10-27');

    const result = getEvents({ year: 2099, keyword: 'Visibility', limit: 1 });
    assert.equal(result.total, 3);
    assert.equal(result.hasMore, true);
    assert.equal(result.events[0]?.eventId, 990080);
    assert.equal(result.events[0]?.displayStatus, 'upcoming');
    assert.equal(result.events[0]?.lifecycleStatus, 'upcoming');

    const remaining = getEvents({ year: 2099, keyword: 'Visibility', limit: 10, offset: 1 });
    assert.deepEqual(remaining.events.map((event) => event.eventId), [990082, 990083]);
    assert.equal(remaining.total, 3);
    assert.equal(remaining.hasMore, false);
    assert.equal(getEvents({ year: 2099, keyword: 'unscheduled future' }).total, 0);
  } finally {
    db.exec('ROLLBACK');
  }
});
