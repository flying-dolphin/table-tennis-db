# Ranking Profile Database Fallback Design

## Problem

The `results.ittf.link` women-singles ranking list is not a complete or fully reliable copy of the current ITTF ranking. The 2026 week-30 snapshot contains 825 rows, while the official ranking contains more players, and some list positions disagree with the corresponding profile `current_rank`. Players absent from that list therefore cannot receive a player ID through the normal list merge.

## Approved behavior

The normal `results.ittf.link` list remains the primary player-ID source. For weekly ranking rows that remain unresolved after that merge:

1. Open the configured SQLite database read-only.
2. Find player/profile candidates whose normalized English name and country code equal the weekly row.
3. Ignore candidates without a player ID or profile URL and IDs already consumed by another ranking row.
4. Scrape each candidate profile, caching results by player ID during the run.
5. Accept a candidate only when its parsed `current_rank` exactly equals the official weekly ranking row's `rank`.
6. Resolve only when exactly one candidate passes. Zero or multiple passing candidates remain unresolved.

Accepted rows are appended to the in-memory results candidates before the final merge. They carry the resolution hint `db_profile_rank`, so output consumers can distinguish the fallback from an ordinary results-list match.

## Integration

`run_ranking_profile.py` passes the weekly snapshot and database path to `scrape_results_rankings.py`. The results scraper performs its normal list scrape and profile refresh first, then runs fallback recovery while the same browser page is still available. It saves the augmented results snapshot before returning to the existing merge step.

The results payload records:

- `site_total_players`: rows obtained from the ranking list.
- `db_profile_recovered`: rows accepted by database/profile-rank fallback.
- `total_players`: total candidate rows after recovery.

## Failure handling

Missing database files, missing profiles, profile scrape failures, missing `current_rank`, rank mismatches, and ambiguous matches are logged and left unresolved. They do not cause an incorrect player ID to be accepted. SQLite access never writes to the database.

### Results-list rate limiting and partial resume

The results list is paginated by record offset. A successful page is durable progress: after parsing it, the snapshot stores the accumulated rows, page count, reported total, and the next-page URL. HTTP 429/403/503 responses and recognized risk pages are navigation failures, never end-of-pagination signals.

Before either a fresh scrape or a partial resume, the scraper selects `Display # = 100` on the first page. It accepts the change only after the select value, parsed row count, and reported page count agree with a 100-row page. If the site does not apply the change, the scraper logs the failed verification and continues from the actual page state instead of assuming a page size. Partial resume remains record-offset based, so an existing 825-row snapshot continues at offset 825 even after the live page size changes from 25 to 100.

On a rate-limited navigation, the scraper honors a numeric `Retry-After` response header when present; otherwise it uses bounded exponential backoff. If retries remain unsuccessful, it raises `RiskControlTriggered`, retains the partial snapshot, and records a failed ranking checkpoint with the output path and continuation URL.

With `--resume`, a complete snapshot is still preferred. When no complete snapshot exists, the scraper may resume the newest compatible partial snapshot. Compatibility requires matching category, a non-empty ranking prefix, positive ordered ranks, unique player IDs, and agreement between every player ID and its profile URL. The scraper opens the current first page to confirm the live total and obtain a pagination URL template, then jumps directly to the saved continuation URL or the offset immediately after the saved rows. Existing rows are not fetched again. A partial snapshot that fails validation is ignored and a fresh output file is used.

Partial recovery is page-targeted rather than tail-only. The scraper merges the partial results rows against the ordered weekly ranking and uses each unresolved weekly row's list index—not its rank value—to calculate the primary page offset. This keeps page selection correct when rank values are tied. All unresolved rows mapping to the same offset share one request. If the expected page does not contain a player, only its adjacent pages are considered; after each adjacent page the merge is recalculated, and expansion stops when the unresolved set is empty. Remaining identity mismatches proceed to database/profile verification.

The first page's footer is parsed into an offset-to-URL map after Display 100 is verified. Missing links use the same `limitstart` URL template as a fallback. Every successfully validated target page is persisted immediately with row count, parsed count, first/last rank, and completion status in both the results snapshot and ranking checkpoint. A page is not complete unless it has the expected number of rows and every row passes required-field, unique-ID, and profile-URL consistency checks.

## Tests

Tests cover normalized name/country lookup, unique rank-verified recovery, rank mismatch rejection, multiple-candidate rank disambiguation, ambiguous verified candidates, merge status propagation, metadata, orchestration argument wiring, HTTP risk responses, non-swallowed navigation risk, partial-snapshot validation, continuation URL construction, and resuming without refetching saved rows.
