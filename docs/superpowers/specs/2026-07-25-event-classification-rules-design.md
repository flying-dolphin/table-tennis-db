# Event Classification Rules Repair

## Goal

Correct the source classification rules that classify `Europe Smash – Sweden
2026` as a continental championship, cover the other high-confidence rule
defects found in the same audit, and provide SQL for correcting existing
SQLite rows.

The homepage calendar query is not changed. Its existing product rule—showing
only selected continental events—correctly exposed the bad source
classification.

## Confirmed Current Data Errors

| Event | Current category | Correct category | Affected tables |
| --- | --- | --- | --- |
| `3246` Europe Smash – Sweden 2026 | `CONTINENTAL_CHAMPS` | `WTT_GRAND_SMASH` | `events`, `events_calendar` |
| `3406` Central America Youth Championships | `CONTINENTAL_CHAMPS` | `REGIONAL_YOUTH_CHAMPS` | `events_calendar` |
| `3407` South American Championships | `CONTINENTAL_CHAMPS` | `REGIONAL_CHAMPS` | `events_calendar` |
| `3410` ITTF-Americas Youth Championships | `CONTINENTAL_CHAMPS` | `YOUTH_CONTINENTAL_CHAMPS` | `events_calendar` |
| `3455` ITTF-Oceania Youth Championships | `CONTINENTAL_CHAMPS` | `YOUTH_CONTINENTAL_CHAMPS` | `events`, `events_calendar` |
| `3494` ITTF-Africa Youth Cup | `YOUTH_CONTINENTAL_CHAMPS` | `YOUTH_CONTINENTAL_CUP` | `events_calendar` |
| ETTU Europe Youth Top 10 Antibes 2026 | `CONTINENTAL_CUP` | `YOUTH_CONTINENTAL_CUP` | `events_calendar` |

## Audit Findings

Applying the fallback name classifier to authoritative `events` rows from
2024 onward produces 68 category disagreements. Most are not current database
errors because calendar import prefers a matched `events` row. They
nevertheless demonstrate that the fallback is unsafe for new calendar-only
events.

The defects relevant to this repair are:

1. Adult Smash detection uses a venue allowlist and omits Europe and Saudi
   events.
2. Youth and Cup qualifiers are evaluated after broader geographic rules.
3. Geographic spelling variants such as `Central America` and
   `Central American` do not share a rule.
4. Olympic qualification detection assumes `Olympic` and `Qualification` are
   adjacent.
5. The category mapping contains two entries for `(ITTF WTTC, --)`, while the
   JSON loader silently keeps the last entry.
6. Unknown names silently become senior continental championships.

The duplicate WTTC mapping and unknown-name fallback are reported but are not
semantically changed in this repair. Neither causes a confirmed 2026 row
error, and changing either requires a wider taxonomy decision.

## Classification Design

Keep the existing `(event_type, event_kind)` interface and apply rules from
most specific to least specific:

1. Detect `Youth Smash` before adult Smash.
2. Classify any name containing `Smash` and not `Youth` as
   `WTT Grand Smash`.
3. Within continental families, determine the age/cup kind before applying
   the broad senior fallback:
   - Youth Top 10/Top 16 and Youth Cup → `Youth Cup`
   - Youth Championships → `Youth Championships`
   - U21 Championships → `U21 Championships`
   - adult Cup/Top 10/Top 16 → `Senior Cup`
4. Treat North, Central, and South American championship subregions as
   regional while keeping a generic Americas Youth Championship continental.
5. Recognize `Olympic ... Qualification` with intervening words.

Do not add event-ID-specific exceptions. The rules must classify historical
equivalents such as Europe Smash 2025 and Saudi Smash 2024 correctly.

## Tests

Extend the existing classification test module. Tests are written and observed
failing before production code changes.

The regression matrix covers:

- Europe and Saudi adult Smash
- Europe Youth Smash
- Central America Youth Championships
- South American senior and youth championships
- generic ITTF-Americas Youth Championships
- Oceania Youth Championships and senior Cup
- Africa Youth Cup
- ETTU Europe Youth Top 10
- Olympic Singles Qualification
- existing Asian Games behavior

After the rule tests pass:

1. Run the complete classification test module.
2. Run calendar import in `--dry-run` mode for 2026.
3. Query the dry-run classification path or a temporary database fixture to
   confirm the affected names resolve to their expected categories.
4. Run the homepage data reproduction and confirm event `3246` is returned
   after applying the supplied correction SQL to a temporary database copy.

## Data Correction

The production database is not mutated by the code change. A transaction-safe
SQL block updates both denormalized category columns in `events` and the
foreign-key category in `events_calendar`, followed by a verification query.

The checked-in 2026 update SQL is corrected for the seven affected calendar
events so rerunning that artifact cannot restore the bad classifications.

## Non-goals

- Changing homepage continental-event visibility rules
- Redesigning the event category taxonomy
- Merging or deleting the two WTTC categories
- Reclassifying uncertain historical records without an authoritative source
