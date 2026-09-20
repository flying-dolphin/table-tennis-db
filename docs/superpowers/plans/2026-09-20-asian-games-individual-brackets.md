# Asian Games 2026 Individual Brackets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch, store, import, and display the official 2026 Asian Games men's singles, women's singles, men's doubles, women's doubles, and mixed doubles knockout brackets.

**Architecture:** Add a tournament-specific bracket scraper that preserves the official Bornan response and produces a small normalized snapshot for the existing `current_event_brackets` table. Extend the existing atomic current-event import and refresh pipeline, then teach the server-side bracket reader to decode Bornan `Home`/`Away` competitors alongside the existing WTT ODF payload without adding client-side fetching.

**Tech Stack:** Python 3.12, `urllib`, SQLite, unittest, Next.js 15, TypeScript, Node test runner.

---

### Task 1: Normalize and capture official individual brackets

**Files:**
- Create: `scripts/asian_games_2026/scrape_brackets.py`
- Create: `scripts/asian_games_2026/tests/test_scrape_brackets.py`

- [ ] **Step 1: Write failing normalization tests**

Cover round mapping, bracket positions, R64 BYEs, doubles `Members`, score/winner extraction, and deterministic feeder links from adjacent rounds.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `.venv/bin/python -m unittest scripts.asian_games_2026.tests.test_scrape_brackets -v`

Expected: import failure because `scrape_brackets.py` does not exist.

- [ ] **Step 3: Implement the scraper**

Fetch `/s/AG2026/en/TTE/brackets/{official-code}` for MS, WS, MD, WD, and XD; validate each payload; save official responses under `raw/brackets/`; normalize every phase match into `normalized/current_brackets.json`. Derive `side_a_previous_unit` and `side_b_previous_unit` from the two preceding-round positions so bracket connectors remain deterministic before results are populated.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/python -m unittest scripts.asian_games_2026.tests.test_scrape_brackets -v`

Expected: all bracket scraper tests pass.

### Task 2: Import brackets atomically with current matches

**Files:**
- Modify: `scripts/asian_games_2026/import_current.py`
- Modify: `scripts/asian_games_2026/tests/test_import_current.py`

- [ ] **Step 1: Write failing import tests**

Exercise insertion into `current_event_brackets`, replacement of stale rows for a supplied sub-event, preservation of other sub-events, and idempotent re-import.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `.venv/bin/python -m unittest scripts.asian_games_2026.tests.test_import_current -v`

Expected: failures because the importer does not consume bracket snapshots.

- [ ] **Step 3: Extend the transaction**

Accept an optional bracket snapshot in `import_snapshot`, replace only the five supplied sub-events inside the same transaction as matches, serialize the unmodified Bornan match object into `raw_source_payload`, and report a `brackets` count. Add a `--brackets-input` CLI option defaulting to `normalized/current_brackets.json`.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/python -m unittest scripts.asian_games_2026.tests.test_import_current -v`

Expected: all current import tests pass.

### Task 3: Wire bracket capture into refresh and final validation

**Files:**
- Modify: `scripts/asian_games_2026/refresh.py`
- Modify: `scripts/asian_games_2026/finalize.py`
- Modify: `scripts/asian_games_2026/tests/test_finalize.py`
- Modify: `scripts/asian_games_2026/README.md`
- Modify: `deploy/server/update_asian_games_2026.sh`

- [ ] **Step 1: Add failing pipeline and validation coverage**

Verify refresh runs schedule, bracket, result, and import stages in that order. Verify finalization rejects a dataset missing any of MS, WS, MD, WD, or XD brackets unless `--force` is used.

- [ ] **Step 2: Implement workflow changes**

Add `scrape_brackets` to every refresh, report per-event bracket counts in final validation, document raw/normalized paths plus the standalone bracket command, and require/import/verify the normalized bracket snapshot in the production deployment flow.

- [ ] **Step 3: Run Python module tests**

Run: `.venv/bin/python -m unittest discover -s scripts/asian_games_2026/tests -v`

Expected: all Asian Games tests pass.

### Task 4: Decode Bornan competitors in the event detail service

**Files:**
- Modify: `web/lib/server/events.ts`
- Modify: `web/lib/server/events.current-event.test.ts`

- [ ] **Step 1: Add a failing current-bracket fixture**

Insert one singles bracket row and one doubles bracket row whose `raw_source_payload` uses official `Home`, `Away`, and `Members` fields. Assert the event detail returns the correct player IDs, names, countries, and feeder references.

- [ ] **Step 2: Run the focused frontend test and verify failure**

Run: `cd web && npx tsx --test lib/server/events.current-event.test.ts`

Expected: player assertions fail because only WTT `CompetitorPlace` is parsed.

- [ ] **Step 3: Add server-side payload normalization**

Extend the existing bracket payload parser to expose a common two-side representation for both WTT ODF and Bornan payloads. Keep parsing on the server, use maps for repeated player metadata lookup, and avoid additional client requests or serialized payload fields.

- [ ] **Step 4: Run focused frontend tests**

Run: `cd web && npx tsx --test lib/server/events.current-event.test.ts`

Expected: all current-event tests pass.

### Task 5: End-to-end verification

**Files:**
- Verify only; no new files expected.

- [ ] **Step 1: Run all Asian Games tests**

Run: `.venv/bin/python -m unittest discover -s scripts/asian_games_2026/tests -v`

- [ ] **Step 2: Run relevant frontend tests**

Run: `cd web && npx tsx --test lib/server/events.current-event.test.ts lib/bracket-virtual-byes.test.ts`

- [ ] **Step 3: Run lint and production build**

Run: `cd web && npm run lint && npm run build`

- [ ] **Step 4: Exercise live capture against a temporary database**

Run the bracket scraper, import a copy of the database under `/tmp`, and query counts by sub-event. Expected result: 63 bracket nodes for each of MS, WS, MD, WD, and XD, with no mutation of `data/db/ittf.db` during verification.

- [ ] **Step 5: Review the final diff**

Confirm only the agreed files changed and all pre-existing user modifications remain intact.
