type MatchDetailLinkInput = {
  hasScore: boolean;
  scheduleMatchId?: number | string | null;
  matchId?: number | string | null;
  kind?: 'match' | 'tie';
};

export function matchDetailPath({ hasScore, scheduleMatchId, matchId, kind = 'match' }: MatchDetailLinkInput) {
  if (!hasScore) return null;

  if (typeof scheduleMatchId === 'string' && scheduleMatchId.startsWith('cm:')) {
    return `/matches/${scheduleMatchId}`;
  }

  if (kind === 'tie' && scheduleMatchId != null) {
    return `/matches/tie:${scheduleMatchId}`;
  }

  if (matchId != null) {
    return `/matches/${matchId}`;
  }

  return null;
}
