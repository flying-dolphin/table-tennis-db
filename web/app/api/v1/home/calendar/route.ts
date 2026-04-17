import { ok } from '@/lib/server/api';
import { getHomeCalendar } from '@/lib/server/home';

export function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const yearParam = searchParams.get('year');
  const year = yearParam ? Number(yearParam) : undefined;

  return ok(getHomeCalendar(Number.isFinite(year) ? year : undefined));
}
