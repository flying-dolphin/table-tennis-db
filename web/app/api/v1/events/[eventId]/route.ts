import { error, ok } from '@/lib/server/api';
import { getEventDetail } from '@/lib/server/events';

export async function GET(request: Request, { params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;
  const parsedEventId = Number(eventId);

  if (!Number.isFinite(parsedEventId)) {
    return error(400, 40002, 'eventId must be a number');
  }

  const { searchParams } = new URL(request.url);
  const subEvent = searchParams.get('sub_event');
  const lean = searchParams.get('lean') === '1';
  const result = getEventDetail(parsedEventId, subEvent, { lean });

  if (!result) {
    return error(404, 40403, 'Event not found');
  }

  return ok(result);
}
