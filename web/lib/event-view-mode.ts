type ScheduleDayLike = {
  localDate: string | null;
};

export function shouldUseScheduleTabs({
  sessionScheduleCount,
  scheduleDays,
}: {
  lifecycleStatus?: string | null;
  sessionScheduleCount: number;
  scheduleDays: ScheduleDayLike[];
}) {
  if (sessionScheduleCount > 0) return true;
  return scheduleDays.some((day) => day.localDate != null && day.localDate !== '日期待定');
}

export function shouldShowBeijingTimeForEvent(
  _lifecycleStatus: string | null | undefined,
  eventTimeZone: string | null | undefined,
) {
  return Boolean(eventTimeZone && eventTimeZone !== 'Asia/Shanghai');
}
