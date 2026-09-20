# Asian Games Player Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve Asian Games source-name variants to existing ITTF players without unsafe fuzzy matches, so team-tie rosters and rubbers retain `player_id` and Chinese display metadata.

**Architecture:** Move player resolution into a focused module shared by roster and match-side imports. Resolve only deterministic country/project-gender matches (strict normalized name, compact punctuation/space-insensitive name, token-order variant), then apply explicit source aliases for verified truncations such as `KUAN Cheok`; ambiguous or unsupported names remain unresolved for audit. Keep the alias registry as data so future verified mappings do not require resolver code changes.

**Tech Stack:** Python 3, SQLite, unittest, JSON.

---

### Task 1: Add failing resolver tests

**Files:**
- Create: `scripts/asian_games_2026/tests/test_player_resolution.py`

- [x] **Step 1: Write tests for strict, compact, token-order, alias, gender, and ambiguity behavior.**

  The fixture will create the project schema in memory and insert:
  `ZHU Yuling` (MAC/Female), `KUAN Cheok Lam` (MAC/Female),
  `TAN Zhao Yun` (SGP/Female), `TAN Zhao Ray` (SGP/Male), and
  `LE Ellsworth` (SGP/Male). Assertions will require:
  `ZHU Yu Ling`/`WS` → Zhu, `KUAN Cheok`/`WT` → Kuan,
  `TAN Zhao`/`WT` → Zhao Yun, `TAN Zhao`/`MT` → no match,
  `ELLSWORTH Le`/`MT` → Le Ellsworth, and an unknown/truly ambiguous
  name → no match.

- [x] **Step 2: Run the focused test and verify it fails because the resolver module does not exist.**

  Run: `python -m unittest scripts.asian_games_2026.tests.test_player_resolution -v`

  Expected: import failure for `scripts.asian_games_2026.player_resolution`.

### Task 2: Implement the shared conservative resolver

**Files:**
- Create: `scripts/asian_games_2026/player_resolution.py`
- Create: `scripts/data/asian_games_player_aliases.json`

- [x] **Step 1: Add the verified source alias registry.**

  Store `MAC / KUAN Cheok` → `KUAN Cheok Lam`, scoped to the relevant women/doubles project codes, with a note explaining that the official source truncates the name.

- [x] **Step 2: Implement `player_resolver(conn, aliases_path=...)`.**

  Build indexes from `players` and resolve in this order:
  source alias, strict normalized name, compact name with spaces/punctuation removed, then order-insensitive token equality. Scope candidates by country and by project gender (`M*` / `W*`); require exactly one candidate at every relaxed stage and return `None` otherwise.

- [x] **Step 3: Run the focused tests and verify they pass.**

  Run: `python -m unittest scripts.asian_games_2026.tests.test_player_resolution -v`

  Expected: all resolver tests pass.

### Task 3: Wire the resolver into both import paths

**Files:**
- Modify: `scripts/asian_games_2026/import_current.py`
- Modify: `scripts/asian_games_2026/tests/test_import_current.py`

- [x] **Step 1: Pass the parent sub-event code into both roster and match-side resolution.**

  `_replace_tie_sides` and `_replace_match_sides` will call the shared resolver with `WT`, `WS`, etc., so gender filtering applies consistently to both tables.

- [x] **Step 2: Add an integration regression fixture for one tie containing Zhu, Kuan, and a deliberately ambiguous source name.**

  Assert the imported rows contain the two expected IDs and leave the ambiguous row `NULL`.

- [x] **Step 3: Run the Asian Games import test module.**

  Run: `python -m unittest scripts.asian_games_2026.tests.test_import_current -v`

  Expected: all existing and new import tests pass.

### Task 4: Verify the original symptom and the wider audit

**Files:**
- No production files modified in this task.

- [x] **Step 1: Run the full focused Asian Games test suite.**

  Run: `python -m unittest discover -s scripts/asian_games_2026/tests -p 'test_*.py' -v`

- [x] **Step 2: Import the normalized snapshot into a temporary SQLite copy and query tie 287.**

  Verify the two rows have `player_id` 117332 and 207486 and non-empty `name_zh`; verify ambiguous/unresolved source names remain auditable rather than being guessed.

- [x] **Step 3: Run lint/compile checks for changed Python files and inspect the diff.**

  Run: `python -m compileall scripts/asian_games_2026/player_resolution.py scripts/asian_games_2026/import_current.py` and `git diff --check`.
