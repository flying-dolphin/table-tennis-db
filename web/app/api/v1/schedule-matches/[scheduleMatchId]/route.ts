import { error, ok } from '@/lib/server/api';
import { getScheduleMatchDetail } from '@/lib/server/events';

export async function GET(_: Request, { params }: { params: Promise<{ scheduleMatchId: string }> }) {
  const { scheduleMatchId } = await params;
  const result = getScheduleMatchDetail(scheduleMatchId);

  if (!result) {
    return error(404, 40404, 'Schedule match not found');
  }

  return ok(result);
}
