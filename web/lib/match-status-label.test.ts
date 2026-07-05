// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { matchStatusLabel } = require('./match-status-label.ts');

test('labels live match details as in progress', () => {
  assert.equal(matchStatusLabel('live', null), '进行中');
});

test('falls back to result state when status is unavailable', () => {
  assert.equal(matchStatusLabel(null, 'A'), '已结束');
  assert.equal(matchStatusLabel(null, null), '未开始');
});
