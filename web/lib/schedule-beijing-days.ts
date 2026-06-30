export type BeijingScheduleMatchLike = {
  scheduledLocalAt: string | null;
  scheduledUtcAt: string | null;
};

export type ScheduleDayLike<T extends BeijingScheduleMatchLike> = {
  localDate: string;
  matches: T[];
};

function formatDateInTimeZone(date: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);
  const year = parts.find((part) => part.type === 'year')?.value;
  const month = parts.find((part) => part.type === 'month')?.value;
  const day = parts.find((part) => part.type === 'day')?.value;
  return year && month && day ? `${year}-${month}-${day}` : null;
}

function zonedLocalDateTimeToDate(localDateTime: string, timeZone: string) {
  const dateMatch = localDateTime.slice(0, 10).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const timeMatch = localDateTime.slice(11, 16).match(/^(\d{2}):(\d{2})$/);
  if (!dateMatch || !timeMatch) return null;

  const targetUtcMs = Date.UTC(
    Number(dateMatch[1]),
    Number(dateMatch[2]) - 1,
    Number(dateMatch[3]),
    Number(timeMatch[1]),
    Number(timeMatch[2]),
  );

  let guessMs = targetUtcMs;
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  for (let i = 0; i < 3; i += 1) {
    const parts = formatter.formatToParts(new Date(guessMs));
    const year = Number(parts.find((part) => part.type === 'year')?.value);
    const month = Number(parts.find((part) => part.type === 'month')?.value);
    const day = Number(parts.find((part) => part.type === 'day')?.value);
    const hour = Number(parts.find((part) => part.type === 'hour')?.value);
    const minute = Number(parts.find((part) => part.type === 'minute')?.value);
    if (![year, month, day, hour, minute].every(Number.isFinite)) return null;

    const zonedUtcMs = Date.UTC(year, month - 1, day, hour, minute);
    const diffMs = targetUtcMs - zonedUtcMs;
    if (diffMs === 0) return new Date(guessMs);
    guessMs += diffMs;
  }

  return new Date(guessMs);
}

export function getCurrentBeijingDate() {
  return formatDateInTimeZone(new Date(), 'Asia/Shanghai') ?? '';
}

export function getScheduleMatchBeijingDate<T extends BeijingScheduleMatchLike>(
  match: T,
  eventTimeZone: string | null,
) {
  if (match.scheduledUtcAt) {
    const date = new Date(match.scheduledUtcAt);
    if (!Number.isNaN(date.getTime())) {
      return formatDateInTimeZone(date, 'Asia/Shanghai');
    }
  }

  if (match.scheduledLocalAt && eventTimeZone) {
    const date = zonedLocalDateTimeToDate(match.scheduledLocalAt, eventTimeZone);
    if (date && !Number.isNaN(date.getTime())) {
      return formatDateInTimeZone(date, 'Asia/Shanghai');
    }
  }

  return null;
}

export function regroupScheduleDaysByBeijingDate<
  T extends BeijingScheduleMatchLike & { subEventTypeCode: string },
>(
  days: Array<ScheduleDayLike<T>>,
  eventTimeZone: string | null,
  subEventCode: string,
) {
  const grouped = new Map<string, ScheduleDayLike<T>>();

  for (const day of days) {
    for (const match of day.matches) {
      if (match.subEventTypeCode !== subEventCode) continue;

      const beijingDate = getScheduleMatchBeijingDate(match, eventTimeZone) ?? '日期待定';
      const current = grouped.get(beijingDate) ?? { localDate: beijingDate, matches: [] };
      current.matches.push(match);
      grouped.set(beijingDate, current);
    }
  }

  return Array.from(grouped.values()).sort((left, right) => {
    if (left.localDate === '日期待定') return 1;
    if (right.localDate === '日期待定') return -1;
    return left.localDate.localeCompare(right.localDate);
  });
}
