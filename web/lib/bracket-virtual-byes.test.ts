// @ts-nocheck

const test = require('node:test');
const assert = require('node:assert/strict');

const { expandVirtualByeNodes, isVirtualByeMatch, realBracketMatchCount } = require('./bracket-virtual-byes.ts');

test('expands a partial previous round with virtual bye nodes', () => {
  const rounds = [
    {
      code: 'R64',
      label: '64 强',
      order: 20,
      matches: [
        {
          matchId: 101,
          scheduleMatchId: null,
          externalUnitCode: null,
          drawRound: 'R64',
          roundLabel: '64 强',
          roundOrder: 20,
          matchScore: '3-0',
          games: [],
          sides: [
            { sideNo: 1, isWinner: true, players: [{ playerId: 1, slug: null, name: 'Qualifier', nameZh: null, countryCode: 'QAT' }] },
            { sideNo: 2, isWinner: false, players: [{ playerId: 2, slug: null, name: 'Opponent', nameZh: null, countryCode: 'SLO' }] },
          ],
        },
      ],
    },
    {
      code: 'R32',
      label: '32 强',
      order: 30,
      matches: [
        {
          matchId: 201,
          scheduleMatchId: null,
          externalUnitCode: null,
          drawRound: 'R32',
          roundLabel: '32 强',
          roundOrder: 30,
          matchScore: null,
          games: [],
          sides: [
            {
              sideNo: 1,
              isWinner: false,
              previousUnit: 'match:101',
              players: [{ playerId: 1, slug: null, name: 'Qualifier', nameZh: null, countryCode: 'QAT' }],
            },
            {
              sideNo: 2,
              isWinner: false,
              players: [{ playerId: 3, slug: null, name: 'Seed Player', nameZh: null, countryCode: 'CHN' }],
            },
          ],
        },
      ],
    },
  ];

  const expanded = expandVirtualByeNodes(rounds);
  const roundOf64 = expanded[0];
  const roundOf32 = expanded[1];

  assert.equal(roundOf64.matches.length, 2);
  assert.equal(realBracketMatchCount(roundOf64), 1);
  assert.equal(roundOf64.matches[0].matchId, 101);
  assert.ok(isVirtualByeMatch(roundOf64.matches[1]));
  assert.equal(roundOf64.matches[1].sides[0].players[0].name, 'Seed Player');
  assert.equal(roundOf64.matches[1].sides[1].players[0].name, '轮空');
  assert.equal(roundOf64.matches[1].sides[1].players[0].countryCode, null);
  assert.equal(roundOf32.matches[0].sides[1].previousUnit, roundOf64.matches[1].externalUnitCode);
});
