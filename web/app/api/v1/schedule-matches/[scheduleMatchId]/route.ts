import { error, ok } from '@/lib/server/api';
import { getScheduleMatchDetail } from '@/lib/server/events';

export async function GET(_: Request, { params }: { params: Promise<{ scheduleMatchId: string }> }) {
  const { scheduleMatchId } = await params;
  const parsedScheduleMatchId = Number(scheduleMatchId);

  if (!Number.isFinite(parsedScheduleMatchId)) {
    return error(400, 40003, 'scheduleMatchId must be a number');
  }

  const result = getScheduleMatchDetail(parsedScheduleMatchId);

  if (!result) {
    return error(404, 40404, 'Schedule match not found');
  }

  return ok(result);
}
