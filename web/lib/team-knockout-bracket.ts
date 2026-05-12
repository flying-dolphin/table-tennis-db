export type TeamBracketTeam = {
  code: string;
  name: string;
  nameZh: string | null;
};

export type TeamBracketTie = {
  tieId: string;
  winnerCode: string | null;
  teamA: TeamBracketTeam;
  teamB: TeamBracketTeam;
};

export type TeamKnockoutRoundLike = {
  code: string;
  label: string;
  order: number;
  ties: TeamBracketTie[];
};

export type TeamBracketNode<T extends TeamBracketTie = TeamBracketTie> = {
  key: string;
  tie: T;
  teamA: TeamBracketTeam;
  teamB: TeamBracketTeam;
};

export type TeamBracketRound<T extends TeamBracketTie = TeamBracketTie> = {
  code: string;
  label: string;
  order: number;
  nodes: TeamBracketNode<T>[];
};

export type TeamBracketFeeder = {
  sideNo: number;
  nodeIndex: number;
};

function tieConnectivityScore<T extends TeamKnockoutRoundLike>(tie: T["ties"][number], historyRounds: T[]): number {
  let score = 0;
  for (const round of historyRounds) {
    for (const historyTie of round.ties) {
      if (historyTie.teamA.code === tie.teamA.code || historyTie.teamB.code === tie.teamA.code) score += 1;
      if (historyTie.teamA.code === tie.teamB.code || historyTie.teamB.code === tie.teamB.code) score += 1;
    }
  }
  return score;
}

export function orderTeamRoundsByFeeders<T extends TeamKnockoutRoundLike>(rounds: T[]): T[] {
  if (rounds.length <= 1) return rounds;
  const result = rounds.map((round) => ({ ...round, ties: [...round.ties] })) as T[];

  for (let roundIndex = result.length - 1; roundIndex > 0; roundIndex -= 1) {
    const nextRound = result[roundIndex];
    const prevRound = result[roundIndex - 1];
    const historyRounds = result.slice(0, Math.max(0, roundIndex - 1));
    const used = new Set<string>();
    const ordered: TeamBracketTie[] = [];

    for (const nextTie of nextRound.ties) {
      for (const teamCode of [nextTie.teamA.code, nextTie.teamB.code]) {
        const feeder = prevRound.ties
          .filter((prevTie) => !used.has(prevTie.tieId) && prevTie.winnerCode === teamCode)
          .sort((left, right) => tieConnectivityScore(right, historyRounds) - tieConnectivityScore(left, historyRounds))[0];
        if (!feeder) continue;
        ordered.push(feeder);
        used.add(feeder.tieId);
      }
    }

    for (const prevTie of prevRound.ties) {
      if (!used.has(prevTie.tieId)) ordered.push(prevTie);
    }

    result[roundIndex - 1] = { ...prevRound, ties: ordered } as T;
  }

  return result;
}

export function buildTeamBracketRounds<T extends TeamKnockoutRoundLike>(rounds: T[]): TeamBracketRound<T["ties"][number]>[] {
  return rounds
    .filter((round) => round.ties.length > 0)
    .map((round) => ({
      code: round.code,
      label: round.label,
      order: round.order,
      nodes: round.ties.map((tie) => ({
        key: tie.tieId,
        tie,
        teamA: tie.teamA,
        teamB: tie.teamB,
      })),
    }));
}

export function buildTeamRoundFeeders<T extends TeamBracketTie>(
  prevRound: TeamBracketRound<T> | undefined,
  nextRound: TeamBracketRound<T> | undefined,
): TeamBracketFeeder[][] {
  if (!prevRound || !nextRound) return [];

  const used = new Set<number>();
  return nextRound.nodes.map((node) => {
    const feeders: TeamBracketFeeder[] = [];
    const sides = [
      { sideNo: 1, teamCode: node.teamA.code },
      { sideNo: 2, teamCode: node.teamB.code },
    ];

    for (const side of sides) {
      const nodeIndex = prevRound.nodes.findIndex(
        (prevNode, index) => !used.has(index) && prevNode.tie.winnerCode === side.teamCode,
      );
      if (nodeIndex === -1) continue;
      used.add(nodeIndex);
      feeders.push({ sideNo: side.sideNo, nodeIndex });
    }

    return feeders;
  });
}
