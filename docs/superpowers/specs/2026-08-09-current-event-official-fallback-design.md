# Current Event Official Fallback and Reconciliation Design

**Date:** 2026-08-09

## Goal

Keep current-event match statuses timely when WTT's event-specific
`take_10_official_results.json` is unavailable, while also repairing matches that
fall outside its ten-result window. Preserve the existing preference for the
small CDN payload and do not treat either official-results source as a complete
snapshot.

## Context

The live pipeline currently combines two CDN sources:

1. event-specific live match IDs plus match cards;
2. the event-specific `take_10_official_results.json` static file.

This works when WTT publishes the take-10 file. During concurrent events WTT may
publish that file only for the event selected in
`wtt_live_results_event_id.json`. For event 3246 the take-10 path was not valid,
but the failure was converted to an empty list and the scrape still reported no
errors. Completed matches then disappeared from the live-ID list without an
official version replacing them.

The full `GetOfficialResult` endpoint is broader but has also been observed to
be temporarily incomplete. It must therefore supplement existing data rather
than replace it.

The take-10 static resource cannot be expanded by adding `take=20`, and WTT does
not publish a corresponding `take_20_official_results.json` resource. The
paginated `GetOfficialResult` endpoint accepts `take=20`, but that is a separate
source and does not change the static file's limit.

## Design

### 1. Recent-official source selection

Add a small, explicit result type for fetching the take-10 resource. It must
distinguish:

- a valid JSON list, including a valid empty list;
- an unavailable or invalid response, including transport errors, HTML/XML
  fallback bodies, and non-list JSON.

The live scraper keeps the existing fast path:

1. Fetch current live match cards.
2. Fetch take-10.
3. If take-10 is valid, use its items.
4. If take-10 is unavailable or invalid, call the existing paginated full
   Official fetcher and use the returned items as the recent-official fallback.
5. Normalize and merge the live and official items by document code.

When the same document code appears in both sources, an `OFFICIAL` item takes
precedence over a `LIVE` item. Source absence never deletes a match or changes a
completed match back to live.

The full Official fallback is considered supplemental. If both take-10 and the
full Official fallback fail, the scraper still writes and imports successfully
fetched live matches, but marks the run as degraded in its summary.

### 2. Periodic full Official reconciliation

Take-10 can be valid while omitting results during periods with many concurrent
matches. Avoid database-aware gap detection in the live scraper. Instead, add a
separate periodic reconciliation job:

- once per hour during each session refresh window;
- once at the end of each session refresh window.

The job fetches the complete paginated `GetOfficialResult` payload and runs the
existing official-results importer. Import remains upsert-only: missing rows in
one response do not delete data or downgrade an existing completed status.

Introduce an internal cron source named `official_reconcile` that maps only to:

- scrape child source: `completed`;
- import child source: `completed`.

Do not reuse the existing internal `completed` mapping because it also invokes
`match_details`. The new source prevents hourly reconciliation from generating
unnecessary per-match detail traffic and preserves current `completed`
semantics for manual workflows.

Schedule reconciliation at a five-minute offset from the live ten-minute ticks
where possible, avoiding simultaneous SQLite writers for the same event.

### 3. Observability and failure behavior

Extend `_scrape_summary_live.json` with official-source details:

- take-10 URL, availability, count, and failure reason;
- whether full Official fallback was attempted;
- fallback URL, success, count, and page count;
- selected official source;
- `degraded: true` when neither official source is usable.

An unavailable take-10 response is not a terminal error when the full fallback
succeeds. If both official sources fail, record a warning/degraded state rather
than returning a non-zero exit solely for the optional official supplement;
otherwise the shell's `&&` chain would skip importing valid live data.

The standalone periodic reconciliation job retains strict behavior: failure to
fetch full Official results returns non-zero and is visible in the event cron
log, without blocking a separate live refresh.

## Data-flow summary

```text
10-minute live refresh
  live IDs/cards ───────────────────────────────┐
                                                ├─ normalize/merge ── GetLiveResult ── live import
  take-10 ── valid ─────────────────────────────┤
       └──── unavailable ── full Official ──────┘

hourly + session-end reconciliation
  full Official ── GetOfficialResult ── official-results import
```

## Tests

Add focused tests for:

1. valid take-10 avoids calling the full fallback;
2. a valid empty take-10 list avoids fallback;
3. missing, invalid, or non-list take-10 invokes the full fallback;
4. fallback results are normalized and merged into the live output;
5. official data wins over live data for the same document code;
6. failure of both official sources produces a degraded summary while retaining
   valid live output;
7. hourly reconciliation jobs map to `completed` scrape/import only and never
   include `match_details`;
8. reconciliation uses a non-conflicting minute offset and includes a final
   session-end run;
9. existing live-only and completed/manual cron behavior remains unchanged.

## Non-goals

- Do not invent or probe a `take_20` static filename at runtime.
- Do not treat the full Official response as an authoritative deletion snapshot.
- Do not add database queries to the live scraper to infer missing matches.
- Do not change match-detail selection or importing behavior.
- Do not repair production event data as part of the code change; production
  recovery remains a separately confirmed operational action.

## Success criteria

- An event without a take-10 static resource receives completed statuses through
  the full Official fallback on its next live refresh.
- An event with more than ten recent completions is reconciled within one hour,
  and once more at session-window end.
- A transiently incomplete full Official response cannot delete or downgrade
  previously imported matches.
- Live match updates continue even when both official-result sources are
  temporarily unavailable.
- Cron logs and summaries identify which official source was selected and any
  degraded run.
