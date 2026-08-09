# Current Event Upcoming Fetch Handling Implementation Plan

**Goal:** Prevent not-yet-published match details for scheduled matches from aborting current-event refreshes while preserving failures that require operator attention.

**Architecture:** Match-detail fetching will classify each target result as fetched, not published, or failed. The scraper will treat an empty/absent response for upcoming or scheduled targets as an expected retry state, while technical failures and missing results for live/completed targets remain visible and non-zero. Existing JSON summaries will expose the classification counts.

**Tech Stack:** Python 3.10+, `urllib.request`, `unittest`, existing current-event shell pipeline.

---

### Task 1: Add failing tests for outcome classification

**Files:**
- Modify: `scripts/runtime/test_scrape_wtt_match_details.py`

- [ ] Add tests proving an upcoming target with no card is non-fatal, a live target with no card is fatal, and mixed results preserve both counts and the non-zero exit code.
- [ ] Run the focused test module and confirm the new expectations fail against the current boolean `errors` behavior.

### Task 2: Implement explicit match-detail outcomes

**Files:**
- Modify: `scripts/runtime/scrape_wtt_match_details.py:234-246,385-485`

- [ ] Preserve enough fetch information to distinguish absent/unpublished responses from transport or malformed-response failures.
- [ ] Classify absent responses for `upcoming` and `db_scheduled` targets as `not_published` rather than `errors`.
- [ ] Keep `live`, `db_live`, `missing_official`, and `db_completed_missing_score` misses as failures.
- [ ] Add summary counters and make the process return zero when only expected not-published targets remain.

### Task 3: Document retry semantics

**Files:**
- Modify: `docs/scripts_overview.md`
- Modify: `docs/event-data-update-workflow.md`

- [ ] Explain that scheduled match details can legitimately be unavailable before start time and will be retried by the next refresh.
- [ ] Document that non-zero status now represents technical failures or missing data for targets expected to have results.

### Task 4: Verify the complete change

**Files:**
- Read: `scripts/runtime/test_scrape_wtt_match_details.py`
- Read: `scripts/runtime/scrape_wtt_match_details.py`

- [ ] Run the focused match-detail tests.
- [ ] Run adjacent runtime tests if the focused suite passes.
- [ ] Inspect `git diff` and confirm no production data or unrelated files changed.
