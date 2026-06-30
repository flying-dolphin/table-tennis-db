type ScheduleSide = {
  teamCode?: string | null;
  players?: Array<{ countryCode?: string | null }>;
};

type ScheduleMatch = {
  sides: ScheduleSide[];
};

function normalizeCountryCode(value: string | null | undefined) {
  return value?.trim().toUpperCase() ?? null;
}

export function isChinaScheduleMatch(match: ScheduleMatch) {
  return match.sides.some((side) => {
    if (normalizeCountryCode(side.teamCode) === 'CHN') return true;
    return (side.players ?? []).some((player) => normalizeCountryCode(player.countryCode) === 'CHN');
  });
}

export function groupChinaScheduleMatches<T extends ScheduleMatch>(matches: T[]) {
  const chinaMatches: T[] = [];
  const otherMatches: T[] = [];

  for (const match of matches) {
    if (isChinaScheduleMatch(match)) {
      chinaMatches.push(match);
    } else {
      otherMatches.push(match);
    }
  }

  return { chinaMatches, otherMatches };
}
