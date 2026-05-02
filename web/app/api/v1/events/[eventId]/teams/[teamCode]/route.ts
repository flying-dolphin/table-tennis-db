import { error, ok } from '@/lib/server/api';
import { getEventTeamRoster } from '@/lib/server/events';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ eventId: string; teamCode: string }> },
) {
  const { eventId, teamCode } = await params;
  const parsedEventId = Number(eventId);

  if (!Number.isFinite(parsedEventId)) {
    return error(400, 40002, 'eventId must be a number');
  }

  const { searchParams } = new URL(request.url);
  const subEvent = searchParams.get('sub_event');
  if (!subEvent) {
    return error(400, 40002, 'sub_event is required');
  }

  const result = getEventTeamRoster(parsedEventId, subEvent, teamCode);
  if (!result) {
    return error(404, 40403, 'Team roster not found');
  }

  return ok(result);
}
