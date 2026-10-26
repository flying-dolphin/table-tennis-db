import { getCurrentBeijingDate } from './schedule-beijing-days';

export function getDefaultScheduleDate(
  days: Array<{ localDate: string }>,
) {
  if (days.length === 0) return null;

  const today = getCurrentBeijingDate();
  const dates = days
    .map((day) => day.localDate)
    .filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date))
    .sort();

  return dates.find((date) => date >= today)
    ?? dates[dates.length - 1]
    ?? days[days.length - 1].localDate;
}
