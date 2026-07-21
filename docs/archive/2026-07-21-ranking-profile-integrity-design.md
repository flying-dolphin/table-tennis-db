# Ranking/Profile Integrity Design

## Problem

The profile scraper can receive a successful HTTP response that does not contain the requested player's profile data. `extract_profile_info` then returns a ranking-derived skeleton, and `scrape_player_profile` overwrites the last good JSON and marks the checkpoint complete. A later player import explicitly inserts a null `gender`, collects the resulting SQLite error, commits the other rows, and exits non-zero. The deployment shell consequently stops before importing rankings, leaving a partially updated database.

## Approved behavior

### Profile scraping

A scraped profile is publishable only when its `player_id` matches the requested player and it contains a non-empty `gender`, the database-required field that proves profile content was parsed. An incomplete response is retried once with a fresh navigation. If both attempts are incomplete, scraping returns failure, records a failed checkpoint, and never overwrites an existing profile JSON or marks the checkpoint complete.

HTTP risk responses retain their current behavior: they are propagated immediately rather than retried by the semantic-content retry.

### Player import

Profile payload validation is available independently of database writes. It reports unreadable JSON, missing identity fields, and missing gender. For compatibility with historical profiles, it may read the existing database in read-only mode to resolve a missing country code exactly as the importer already does. The CLI exposes this as `--validate-only` and exits non-zero when validation errors exist.

Normal imports are atomic with respect to data errors. If any input profile fails validation or SQL import, the transaction is rolled back, so a direct importer invocation cannot commit only part of the batch.

### Deployment

The remote preflight calls `import_players.py --validate-only` before the database backup and before either import. Invalid profile payloads therefore stop deployment before any database write. With valid payloads, the existing player-then-ranking order and post-import verification remain unchanged.

## Testing

- A skeleton response followed by a complete profile is retried and saved once.
- Two skeleton responses return failure without saving or completing the checkpoint.
- HTTP risk responses are still propagated without semantic retry.
- A batch containing one valid and one gender-less profile produces validation errors and leaves the database unchanged.
- A valid batch still imports normally.
- The deployment script invokes profile validation before backup/import.

## Operational impact

After this change, the normal ranking/profile scraping, translation, and deployment commands do not change. Existing malformed files must be re-scraped and translated before deployment; the new preflight will deliberately reject them until then.
