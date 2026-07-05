export type BracketSidePlayer = {
  playerId: number | null;
  slug: string | null;
  name: string;
  nameZh: string | null;
  countryCode: string | null;
};

export type BracketSide = {
  sideNo: number;
  isWinner: boolean;
  previousUnit?: string | null;
  players: BracketSidePlayer[];
};

export type BracketMatchLike = {
  matchId: number;
  scheduleMatchId: number | string | null;
  externalUnitCode?: string | null;
  drawRound: string;
  roundLabel: string;
  roundOrder: number;
  matchScore: string | null;
  games: Array<{ player: number; opponent: number }>;
  sides: BracketSide[];
  isVirtualBye?: boolean;
};

export type BracketRoundLike<TMatch extends BracketMatchLike = BracketMatchLike> = {
  code: string;
  drawCode?: string | null;
  label: string;
  order: number;
  matches: TMatch[];
};

export function isVirtualByeMatch(match: BracketMatchLike) {
  return match.isVirtualBye === true || (match.externalUnitCode ?? "").startsWith("virtual-bye:");
}

export function realBracketMatchCount(round: { matches: BracketMatchLike[] }) {
  return round.matches.filter((match) => !isVirtualByeMatch(match)).length;
}

function matchUnitKey(match: BracketMatchLike) {
  return match.externalUnitCode ?? `match:${match.matchId}`;
}

function virtualByeUnit(round: BracketRoundLike, nextMatch: BracketMatchLike, sideNo: number, slotIndex: number) {
  return `virtual-bye:${round.drawCode ?? "main"}:${round.code}:${nextMatch.matchId}:${sideNo}:${slotIndex}`;
}

function virtualByeMatch(round: BracketRoundLike, nextMatch: BracketMatchLike, side: BracketSide, slotIndex: number): BracketMatchLike {
  const unit = virtualByeUnit(round, nextMatch, side.sideNo, slotIndex);
  return {
    matchId: -Math.abs((nextMatch.matchId * 10) + side.sideNo),
    scheduleMatchId: null,
    externalUnitCode: unit,
    drawRound: round.code,
    roundLabel: round.label,
    roundOrder: round.order,
    matchScore: null,
    games: [],
    isVirtualBye: true,
    sides: [
      {
        sideNo: 1,
        isWinner: true,
        players: side.players,
      },
      {
        sideNo: 2,
        isWinner: false,
        players: [
          {
            playerId: null,
            slug: null,
            name: "轮空",
            nameZh: null,
            countryCode: null,
          },
        ],
      },
    ],
  };
}

export function expandVirtualByeNodes<TRound extends BracketRoundLike>(rounds: TRound[]): TRound[] {
  if (rounds.length <= 1) return rounds;

  const result = rounds.map((round) => ({
    ...round,
    matches: round.matches.map((match) => ({
      ...match,
      sides: match.sides.map((side) => ({ ...side, players: [...side.players] })),
    })),
  })) as TRound[];

  for (let roundIndex = 0; roundIndex < result.length - 1; roundIndex += 1) {
    const prevRound = result[roundIndex];
    const nextRound = result[roundIndex + 1];
    const expectedPreviousSlots = nextRound.matches.length * 2;

    if (prevRound.matches.length >= expectedPreviousSlots) continue;

    const previousByUnit = new Map(prevRound.matches.map((match) => [matchUnitKey(match), match]));
    const expandedPrevious: BracketMatchLike[] = [];

    nextRound.matches.forEach((nextMatch, nextMatchIndex) => {
      const sortedSides = [...nextMatch.sides].sort((a, b) => a.sideNo - b.sideNo);
      for (const side of sortedSides) {
        const previousUnit = side.previousUnit?.trim();
        const previousMatch = previousUnit ? previousByUnit.get(previousUnit) : null;

        if (previousMatch) {
          expandedPrevious.push(previousMatch);
          continue;
        }

        if (side.players.length === 0) continue;

        const slotIndex = (nextMatchIndex * 2) + side.sideNo;
        const bye = virtualByeMatch(prevRound, nextMatch, side, slotIndex);
        side.previousUnit = bye.externalUnitCode;
        expandedPrevious.push(bye);
      }
    });

    if (expandedPrevious.length === expectedPreviousSlots) {
      prevRound.matches = expandedPrevious as typeof prevRound.matches;
    }
  }

  return result;
}
