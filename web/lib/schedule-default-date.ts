import { getCurrentBeijingDate } from '@/lib/schedule-beijing-days';

export function getDefaultScheduleDate(
  days: Array<{ localDate: string }>,
  today = getCurrentBeijingDate(),
  options?: { preferLatest?: boolean },
) {
  if (days.length === 0) return null;
  if (options?.preferLatest) return days[days.length - 1].localDate;
  return days.find((day) => day.localDate === today)?.localDate ?? days[0].localDate;
}
