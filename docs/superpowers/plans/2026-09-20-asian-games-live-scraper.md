# Asian Games 2026 Live Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a one-off Aichi–Nagoya 2026 table-tennis pipeline that captures official daily schedules and result details, imports them into the existing current-event model, refreshes them on a Beijing-time cron, and safely promotes completed data to historical tables.

**Architecture:** All event-specific code lives under `scripts/asian_games_2026/`; no WTT scraper is modified. Official Bornan API responses are preserved under `data/asian_games/2026/raw/`, normalized into a source-neutral snapshot, and imported into the existing `current_event_*` tables. Team nomination rosters and actually played rubbers remain separate through the existing team-tie and match-side tables.

**Tech Stack:** Python 3.11 standard library, SQLite, unittest, POSIX shell, official Asian Games Bornan JSON API.

---

### Task 1: Shared API, mapping, and time-zone layer

**Files:**
- Create: `scripts/asian_games_2026/common.py`
- Create: `scripts/asian_games_2026/__init__.py`
- Create: `scripts/asian_games_2026/tests/test_common.py`

- [ ] Test UTF-8-wrapped zlib and normal JSON decoding.
- [ ] Test Tokyo ISO timestamps convert to UTC and Beijing without changing the instant.
- [ ] Test Bornan event/phase/status mappings for team, singles, doubles, group, R64/R32/R16/QF/SF/F.
- [ ] Implement constants for event `6666`, discipline `TTE`, source zone `Asia/Tokyo`, display zone `Asia/Shanghai`, API URLs, and data roots.
- [ ] Run `python -m unittest discover -s scripts/asian_games_2026/tests -v` and require all Task 1 tests to pass.

### Task 2: Schedule scraper and corrected Beijing schedule

**Files:**
- Create: `scripts/asian_games_2026/scrape_schedule.py`
- Create: `scripts/asian_games_2026/tests/test_scrape_schedule.py`
- Remove: `scripts/scrape_asian_games_schedule.py`
- Remove: `scripts/test_scrape_asian_games_schedule.py`
- Regenerate: `data/asian_games/2026/table_tennis_schedule.json`
- Regenerate: `data/event_schedule/6666.json`

- [ ] Test identical Tokyo instants are grouped before their labels are converted to Beijing.
- [ ] Test `2026-09-20T10:00:00+09:00` becomes `9月20日 09:00` in output.
- [ ] Implement date discovery and daily schedule fetching with raw responses saved under `raw/schedule/`.
- [ ] Preserve the existing WTT-compatible Chinese keys and `_parsed` values in both output files.
- [ ] Run the schedule tests and a live official-API scrape.

### Task 3: Match detail capture and normalized snapshot

**Files:**
- Create: `scripts/asian_games_2026/scrape_matches.py`
- Create: `scripts/asian_games_2026/tests/test_scrape_matches.py`
- Generate: `data/asian_games/2026/raw/results/*.json`
- Generate: `data/asian_games/2026/normalized/current_matches.json`
- Generate: `data/asian_games/2026/state/latest_scrape.json`

- [ ] Test selection of `RUNNING` plus `OFFICIAL` linked units and exclusion of aggregate child rows from the daily list.
- [ ] Test team normalization keeps `Competitors[].Members` as each side's nominated roster.
- [ ] Test `SubUnits[]` become actually played/planned rubbers with scores, game scores, status, competitors, and parent tie code.
- [ ] Test ordinary singles/doubles detail becomes one normalized match without a team tie.
- [ ] Implement atomic writes so a failed refresh cannot replace the last good snapshot.
- [ ] Run tests and capture today's real Running/Official details.

### Task 4: Current-event SQLite importer

**Files:**
- Create: `scripts/asian_games_2026/import_current.py`
- Create: `scripts/asian_games_2026/tests/test_import_current.py`

- [ ] Build a minimal SQLite fixture containing the existing current-event schema and representative players.
- [ ] Test idempotent upserts for team ties, nomination rosters, rubbers, individual matches, sides, game scores, and status advancement.
- [ ] Test exact normalized `(country, player name)` player resolution and safe NULL fallback for ambiguous/unmatched names.
- [ ] Test source Tokyo local time and UTC are both stored correctly and `events.time_zone` becomes `Asia/Tokyo`.
- [ ] Implement one transaction per import and preserve completed status against stale scheduled snapshots.
- [ ] Run importer tests, then import the real snapshot into a temporary database copy before touching the workspace database.

### Task 5: Refresh runner and Beijing-time cron

**Files:**
- Create: `scripts/asian_games_2026/refresh.py`
- Create: `scripts/asian_games_2026/generate_crontab.py`
- Create: `scripts/asian_games_2026/install_crontab.sh`
- Create: `scripts/asian_games_2026/tests/test_generate_crontab.py`

- [ ] Test cron windows are calculated from Tokyo source timestamps and emitted with `CRON_TZ=Asia/Shanghai`.
- [ ] Test generated commands contain a 2026 date guard, five-minute refresh cadence, daily final reconciliation, and post-event finalization.
- [ ] Implement refresh as schedule scrape → detail scrape → transactional import.
- [ ] Implement marker-delimited crontab output/install without altering unrelated cron entries.
- [ ] Run cron tests and inspect generated output for all nine competition days.

### Task 6: Safe final reconciliation and historical promotion

**Files:**
- Create: `scripts/asian_games_2026/finalize.py`
- Create: `scripts/asian_games_2026/tests/test_finalize.py`

- [ ] Test finalization refuses to promote while any normalized/current match is live or scheduled unless `--force` is supplied.
- [ ] Test it requires completed matches, team rosters for completed team ties, two sides per played match, and winners for completed non-walkovers.
- [ ] Implement a final full schedule/detail sweep and current import before validation.
- [ ] Invoke the existing transactional historical promotion only after Asian-specific validation succeeds; report historical row counts afterward.
- [ ] Run finalizer tests and a `--dry-run` against the workspace database.

### Task 7: End-to-end verification and operations guide

**Files:**
- Create: `scripts/asian_games_2026/README.md`

- [ ] Document manual scrape, refresh, cron generation/installation, dry-run finalization, and final promotion commands.
- [ ] Run the complete Asian Games test suite.
- [ ] Validate all generated JSON with `python -m json.tool` or programmatic loading.
- [ ] Verify today’s normalized snapshot contains official/running matches, nominated team rosters, actual rubber players, Tokyo local timestamps, UTC timestamps, and Beijing display timestamps.
- [ ] Review `git status` and confirm unrelated user changes remain untouched.
