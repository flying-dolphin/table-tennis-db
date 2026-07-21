# Ranking Profile Database Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover player IDs missing from the results ranking list by verifying database profile candidates against the official weekly rank.

**Architecture:** Add focused, dependency-injected recovery functions to the results scraper so SQLite lookup and live profile verification can be tested separately. Run recovery in the existing browser lifetime, append verified candidates with a resolution hint, then let the existing merge pipeline produce the final weekly snapshot.

**Tech Stack:** Python 3.12, sqlite3, unittest, BeautifulSoup, Patchright.

---

### Task 1: Database candidate lookup and profile-rank recovery

**Files:**
- Modify: `tests/test_results_rankings.py`
- Modify: `scripts/scrape_results_rankings.py`

- [ ] Write failing tests that create a temporary SQLite database with `players` and `player_profiles`, then assert normalized `name + country_code` candidate lookup.
- [ ] Write failing tests that inject a profile scraper and assert exact-rank acceptance, mismatch rejection, multiple-candidate disambiguation, ambiguous rejection, caching, and used-ID exclusion.
- [ ] Run `python -m unittest tests.test_results_rankings -v` and confirm failures are caused by missing recovery APIs.
- [ ] Implement read-only lookup and recovery with `sqlite3.connect("file:...?mode=ro", uri=True)`.
- [ ] Re-run `python -m unittest tests.test_results_rankings -v` and confirm the recovery tests pass.

### Task 2: Resolution source propagation

**Files:**
- Modify: `tests/test_merge_ranking_ids.py`
- Modify: `scripts/merge_ranking_ids.py`

- [ ] Write a failing test whose candidate contains `id_resolution_hint: db_profile_rank` and assert the merged row status and matched count.
- [ ] Run the focused test and confirm it fails with the existing `matched` status.
- [ ] Make the merge use the verified candidate hint and count `db_profile_rank` as matched.
- [ ] Re-run `python -m unittest tests.test_merge_ranking_ids -v`.

### Task 3: Scraper and orchestrator integration

**Files:**
- Modify: `tests/test_results_rankings.py`
- Modify: `tests/test_ranking_profile_deploy_config.py`
- Modify: `scripts/scrape_results_rankings.py`
- Modify: `scripts/run_ranking_profile.py`

- [ ] Write failing tests for results payload source/recovery counts and for weekly/database arguments passed by the orchestrator.
- [ ] Run the focused tests and confirm the new expectations fail.
- [ ] Add optional `--weekly-file` and `--db-path` arguments, load weekly rows, recover unresolved candidates after normal profile refresh, and persist augmented output metadata.
- [ ] Pass the weekly snapshot and configured database path from `run_ranking_profile.py`.
- [ ] Re-run focused tests.

### Task 4: Verification

**Files:**
- Verify all modified Python files and tests.

- [ ] Run `python -m unittest tests.test_results_rankings tests.test_merge_ranking_ids tests.test_ranking_profile_deploy_config -v`.
- [ ] Run `python -m unittest discover -s tests -p 'test_*.py'`.
- [ ] Run `python -m py_compile scripts/scrape_results_rankings.py scripts/merge_ranking_ids.py scripts/run_ranking_profile.py`.
- [ ] Re-run the original week-30 merge reproduction and report the remaining unresolved count without performing live profile traffic.

### Task 5: Detect rate-limited pagination correctly

**Files:**
- Modify: `tests/test_page_ops.py`
- Modify: `scripts/lib/page_ops.py`
- Modify: `scripts/scrape_results_rankings.py`

- [ ] Write failing tests proving HTTP 429 is retried with `Retry-After`/bounded backoff and ultimately raises `RiskControlTriggered`.
- [ ] Write a failing test proving `click_next_page_if_any` propagates `RiskControlTriggered` instead of returning `False`.
- [ ] Run the focused tests and confirm they fail for the missing response-status handling.
- [ ] Centralize guarded navigation in `guarded_goto`, use it for href pagination, and log non-risk navigation exceptions instead of silently swallowing them.
- [ ] Re-run the focused tests and confirm they pass.

### Task 6: Resume a validated partial results snapshot

**Files:**
- Modify: `tests/test_results_rankings.py`
- Modify: `scripts/scrape_results_rankings.py`

- [ ] Write failing tests for partial snapshot validation, newest-compatible selection, next-page URL persistence, and continuation from accumulated rows.
- [ ] Run the focused tests and confirm failures are caused by missing partial-resume APIs.
- [ ] Save the continuation URL after every successful page and mark an interrupted ranking scrape as failed with its output metadata.
- [ ] When `--resume` has no complete snapshot, select the newest valid partial snapshot, verify it against the live reported total, navigate directly to its next offset, and append only new rows.
- [ ] Run focused and full ranking/profile tests, compile modified Python files, and run `git diff --check`.

### Task 7: Reduce results ranking pagination traffic

**Files:**
- Modify: `tests/test_results_rankings.py`
- Modify: `scripts/scrape_results_rankings.py`

- [ ] Write failing tests for selecting `Display # = 100` and rejecting a select value that still renders only 25 rows/39 pages.
- [ ] Implement verified display-size selection after the first-page load and before both fresh scraping and partial-resume validation.
- [ ] Keep partial continuation record-offset based so the existing 825-row snapshot resumes at `limitstart58=825`.
- [ ] Run focused regression tests, compile modified Python files, and run `git diff --check`.

### Task 8: Target arbitrary missing results pages

**Files:**
- Modify: `tests/test_results_rankings.py`
- Modify: `scripts/scrape_results_rankings.py`

- [ ] Write failing tests for scattered missing weekly rows, tied ranks crossing a page boundary, footer URL extraction, adjacent-page fallback, and per-page progress persistence.
- [ ] Plan primary offsets from unresolved weekly list indexes and deduplicate offsets before fetching.
- [ ] Fetch only primary pages, recalculate unresolved identities, then search adjacent pages until resolved or exhausted.
- [ ] Validate each fetched page before merging and persist its offset checkpoint immediately.
- [ ] Preserve page-size and page-checkpoint metadata through completion, failure, and database/profile augmentation.
- [ ] Verify the real week-30/825 snapshot plans offsets `800` and `900` without network access.
