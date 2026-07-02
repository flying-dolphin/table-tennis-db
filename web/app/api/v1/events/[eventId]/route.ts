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

  const response = ok(result);
  // 事件详情是公开、无用户态的数据。按生命周期设置缓存，交给 Cloudflare / 浏览器缓存，
  // 避免每次访问都重新查库+构建（首屏 fetch 约 450ms）。
  // - completed：数据基本不变，长缓存 + 长 SWR
  // - in_progress：live 数据，短缓存（与刷新 cron 节奏一致）+ 短 SWR
  // - 其它（upcoming / draw_published）：中等缓存
  const lifecycle = result.event.lifecycleStatus;
  const cacheControl =
    lifecycle === 'completed'
      ? 'public, max-age=60, s-maxage=3600, stale-while-revalidate=86400'
      : lifecycle === 'in_progress'
        ? 'public, max-age=0, s-maxage=30, stale-while-revalidate=60'
        : 'public, max-age=30, s-maxage=300, stale-while-revalidate=3600';
  response.headers.set('Cache-Control', cacheControl);
  return response;
}
