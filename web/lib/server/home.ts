import { db } from '@/lib/server/db';

export function getHomeCalendar(year?: number) {
  const availableYears = db
    .prepare('SELECT DISTINCT year FROM events_calendar ORDER BY year DESC')
    .all() as Array<{ year: number }>;

  const resolvedYear = year ?? availableYears[0]?.year ?? new Date().getFullYear();
  const events = db
    .prepare(
      `
        SELECT
          ec.calendar_id AS calendarId,
          ec.year,
          ec.name,
          ec.name_zh AS nameZh,
          ec.date_range AS dateRange,
          ec.date_range_zh AS dateRangeZh,
          ec.start_date AS startDate,
          ec.end_date AS endDate,
          ec.location,
          ec.location_zh AS locationZh,
          ec.status,
          ec.href,
          ec.event_id AS eventId,
          cat.category_id AS categoryCode,
          cat.category_name_zh AS categoryNameZh,
          cat.sort_order AS sortOrder
        FROM events_calendar ec
        LEFT JOIN event_categories cat ON cat.id = ec.event_category_id
        WHERE ec.year = ?
          AND (cat.filtering_only IS NULL OR cat.filtering_only = 0)
          AND cat.sort_order BETWEEN 1 AND 14
        ORDER BY COALESCE(ec.start_date, ''), ec.date_range, ec.name
      `,
    )
    .all(resolvedYear);

  return {
    year: resolvedYear,
    availableYears: availableYears.map((item) => item.year),
    events,
  };
}

export function getHomeRankings(limit = 20, category = 'women_singles') {
  const snapshot = db
    .prepare(
      `
        SELECT snapshot_id AS snapshotId, ranking_week AS rankingWeek, ranking_date AS rankingDate
        FROM ranking_snapshots
        WHERE category = ?
        ORDER BY ranking_date DESC, snapshot_id DESC
        LIMIT 1
      `,
    )
    .get(category) as
    | {
        snapshotId: number;
        rankingWeek: string;
        rankingDate: string;
      }
    | undefined;

  if (!snapshot) {
    return {
      category,
      snapshot: null,
      players: [],
    };
  }

  const players = db
    .prepare(
      `
        SELECT
          re.rank,
          re.points,
          re.rank_change AS rankChange,
          p.player_id AS playerId,
          p.slug,
          p.name,
          p.name_zh AS nameZh,
          p.country,
          p.country_code AS countryCode,
          p.avatar_file AS avatarFile,
          p.avatar_url AS avatarUrl
        FROM ranking_entries re
        JOIN players p ON p.player_id = re.player_id
        WHERE re.snapshot_id = ?
        ORDER BY re.rank
        LIMIT ?
      `,
    )
    .all(snapshot.snapshotId, limit);

  return {
    category,
    snapshot,
    players,
  };
}
