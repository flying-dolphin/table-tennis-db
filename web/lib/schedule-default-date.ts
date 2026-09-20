import { getCurrentBeijingDate } from '@/lib/schedule-beijing-days';

export function getDefaultScheduleDate(days: Array<{ localDate: string }>, today = getCurrentBeijingDate()) {
  if (days.length === 0) return null;
  return days.find((day) => day.localDate === today)?.localDate ?? days[0].localDate;
}
