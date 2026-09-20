type MatchDetailLinkInput = {
  hasScore: boolean;
  allowUnscored?: boolean;
  isBye?: boolean;
  scheduleMatchId?: number | string | null;
  matchId?: number | string | null;
  kind?: 'match' | 'tie';
};

export function matchDetailPath({ hasScore, allowUnscored = false, isBye = false, scheduleMatchId, matchId, kind = 'match' }: MatchDetailLinkInput) {
  if (isBye) return null;
  if (!hasScore && !allowUnscored) return null;

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
