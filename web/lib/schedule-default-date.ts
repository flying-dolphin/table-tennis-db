export function getDefaultScheduleDate(
  days: Array<{ localDate: string }>,
) {
  if (days.length === 0) return null;
  return days[days.length - 1].localDate;
}
