export function getGameScoreCellState(
  score: number | null | undefined,
  opponentScore: number | null | undefined,
) {
  if (score == null || opponentScore == null || score === opponentScore) return "neutral" as const;
  return score > opponentScore ? ("winner" as const) : ("loser" as const);
}
