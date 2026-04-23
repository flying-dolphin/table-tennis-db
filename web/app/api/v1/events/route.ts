import { ok } from '@/lib/server/api';
import { getEvents } from '@/lib/server/events';

export function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const yearParam = searchParams.get('year');
  const q = (searchParams.get('q') ?? '').trim();
  const ageGroupParam = (searchParams.get('age_group') ?? 'senior').trim().toLowerCase();
  const limitParam = Number(searchParams.get('limit'));
  const offsetParam = Number(searchParams.get('offset'));
  const includeAllYears = yearParam === 'all';
  const year = includeAllYears || !yearParam ? undefined : Number(yearParam);
  const ageGroup: 'senior' | 'non_senior' | 'all' =
    ageGroupParam === 'all' || ageGroupParam === 'non_senior' ? ageGroupParam : 'senior';
  const limit = Number.isFinite(limitParam) && limitParam > 0 ? Math.min(100, Math.floor(limitParam)) : 20;
  const offset = Number.isFinite(offsetParam) && offsetParam >= 0 ? Math.floor(offsetParam) : 0;

  return ok(
    getEvents({
      year: Number.isFinite(year) ? year : undefined,
      includeAllYears,
      keyword: q || undefined,
      ageGroup,
      limit,
      offset,
    }),
  );
}
