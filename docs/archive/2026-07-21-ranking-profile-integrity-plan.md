# Ranking/Profile Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent incomplete profile pages from corrupting JSON and prevent invalid profile batches from partially updating the remote database.

**Architecture:** Validate scraped profiles at the persistence boundary and retry one semantic-content failure. Centralize import payload validation in `import_players.py`, reuse it for atomic imports and a deployment preflight CLI mode.

**Tech Stack:** Python 3.12, unittest, SQLite, Bash

---

### Task 1: Reject incomplete scraped profiles

**Files:**
- Modify: `tests/test_scrape_profiles.py`
- Modify: `scripts/scrape_profiles.py`

- [ ] Add a test where extraction first returns only identity fields and then returns a profile containing `gender`; assert two navigations and one save.
- [ ] Run `python -m unittest tests.test_scrape_profiles -v` and confirm the new test fails because the skeleton is saved immediately.
- [ ] Add a test where both extraction attempts omit `gender`; assert no save, a failed result, and a failed checkpoint.
- [ ] Implement a focused completeness predicate and a two-attempt navigation/extraction loop. Raise an incomplete-profile error before avatar download, JSON save, or checkpoint completion.
- [ ] Re-run `python -m unittest tests.test_scrape_profiles -v` and confirm all tests pass.

### Task 2: Validate and atomically import profile batches

**Files:**
- Modify: `tests/test_player_id_imports.py`
- Modify: `scripts/db/import_players.py`

- [ ] Add a test with one valid profile and one profile missing `gender`; assert an error is reported and the players table remains empty.
- [ ] Run the focused test and confirm it fails because the valid row is committed.
- [ ] Add a `validate_player_profiles` pass that parses all files and checks `player_id`, name, country code, and gender before SQL writes; resolve legacy missing country codes from the existing database read-only.
- [ ] Make `import_players` return validation errors without opening a write transaction, and roll back rather than commit if an SQL error is collected.
- [ ] Add CLI `--validate-only`; print the validation summary and return non-zero on errors.
- [ ] Re-run `python -m unittest tests.test_player_id_imports -v`.

### Task 3: Add deployment profile preflight

**Files:**
- Modify: `tests/test_ranking_profile_deploy_config.py`
- Modify: `deploy/server/update_rankings_profiles.sh`

- [ ] Add a source-level deployment test requiring `import_players.py --dir ... --validate-only` before backup/import.
- [ ] Run `python -m unittest tests.test_ranking_profile_deploy_config -v` and confirm failure.
- [ ] Invoke the importer validation at the beginning of `run_remote_preflight`, before ranking dry-run and database backup.
- [ ] Re-run the deployment configuration test.

### Task 4: Verification

**Files:**
- Verify all modified Python, Bash, tests, and documentation.

- [ ] Run `python -m unittest tests.test_scrape_profiles tests.test_player_id_imports tests.test_ranking_profile_deploy_config -v`.
- [ ] Run `python -m unittest discover -s tests -p 'test_*.py'`.
- [ ] Run `python -m py_compile scripts/scrape_profiles.py scripts/db/import_players.py`.
- [ ] Run `bash -n deploy/server/update_rankings_profiles.sh`.
- [ ] Run `git diff --check` and inspect `git diff --stat`.
