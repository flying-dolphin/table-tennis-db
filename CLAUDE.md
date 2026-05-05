# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

注意：所有回复用中文！

## Project overview

ITTF/WTT data project for women's table tennis: scrape rankings, events, players, and matches from ITTF/WTT sources, store in SQLite, and present via a Next.js frontend.

Architecture is two decoupled halves:
- **Python scrapers + importers** (`scripts/`) produce JSON in `data/` and load it into SQLite at `data/db/ittf.db`.
- **Next.js 15 web app** (`web/`) reads `data/db/ittf.db` directly via `better-sqlite3`. The frontend never writes the DB.

The canonical schema lives at `scripts/db/schema.sql` and is the source of truth for both halves. `web/db/` and `web/scripts/sync-to-db.ts` are deprecated — the frontend and `/api/v1` only read `data/db/ittf.db`.

## Common commands

### Web (run from `web/`)

```bash
npm install
npm run db:migrate    # Apply scripts/db/schema.sql (resolved via web/lib/paths.ts)
npm run dev           # Next.js dev server on :3000
npm run build         # Production build
npm run lint          # ESLint via next lint
```

Note: `web/lib/paths.ts` resolves `ROOT_DIR = path.resolve(process.cwd(), '..')`, so `npm run *` must be invoked from `web/` (not the repo root) for the SQLite path to resolve correctly.

The `db:seed` script is legacy — production uses the Python import pipeline instead.

### Python (run from repo root)

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env  # Set MINIMAX_API_KEY for translation scripts
```

Common entry points:
- `python scripts/run_rankings.py --top 100 --headless` — scrape + translate rankings
- `python scripts/run_profiles.py --category women --top 50 --headless` — scrape player profiles + avatars
- `python scripts/scrape_matches.py --players-file data/women_singles_top50.json` — scrape match history
- `python scripts/scrape_events_calendar.py --year 2026` — scrape calendar
- `python scripts/runtime/event_refresh.py` — refresh upcoming/in-progress events end-to-end (scrape WTT event, re-import schedule, capture/import Stage Groups standings)

### Database bootstrap order (run from repo root)

```bash
python scripts/db/init_database.py
python scripts/db/import_sub_event_type.py
python scripts/db/import_event_categories.py
python scripts/db/import_players.py
python scripts/db/import_rankings.py
python scripts/db/import_events.py
python scripts/db/import_events_calendar.py
python scripts/db/backfill_events_calendar_event_id.py
python scripts/fix_special_event_2860_stage_round.py   # MUST run before import_matches.py
python scripts/db/import_matches.py
python scripts/db/import_event_draw_matches.py         # MUST run before import_sub_events.py
python scripts/db/import_sub_events.py
```

`import_matches.py` reads from `data/event_matches/cn/*.json`, NOT `data/matches_complete/cn/*.json`. Do not run `scripts/db/import_points_rules.py` — it is a placeholder.

For schema upgrades on an existing DB: `scripts/db/upgrade_schema*.py` (e.g. `upgrade_schema_event_lifecycle.py`, `upgrade_schema_current_event_model.py`). See `docs/DATABASE_MAINTENANCE.md` for the full procedure.

## Code architecture

### Two event data lifecycles

The DB has two parallel sets of tables for the same conceptual event, and code paths must respect which lifecycle stage an event is in:

- **Historical** (completed events): `matches`, `event_draw_matches`, `sub_events`. Populated by the bootstrap import pipeline above.
- **Live / upcoming** (`lifecycle_status` ∈ `upcoming | draw_published | in_progress | completed`): `event_session_schedule`, `event_draw_entries`, `event_draw_entry_players`, `event_schedule_matches`, `event_schedule_match_sides`, `event_schedule_match_side_players`, `event_group_standings`, plus team-tie tables. Populated by `scripts/runtime/*` scripts and orchestrated by `event_refresh.py`.

`docs/event-data-update-workflow.md` is the canonical description of which scripts feed which tables.

### Python script layout

- `scripts/scrape_*.py`, `scripts/run_*.py`, `scripts/translate_*.py` — historical/full-pipeline scrapers and the LLM-assisted translation layer.
- `scripts/runtime/` — incremental refresh for in-progress events (WTT live API, schedule, brackets, pool standings).
- `scripts/db/` — schema, init, and import scripts. `scripts/db/config.py` loads `.env` and resolves `DB_PATH` / `SCHEMA_PATH` from the repo root.
- `scripts/data/translation_dict_v2.json` — the only supported translation dictionary. Categories are fixed: `players / terms / events / locations / others` (locations falls back to others). v1 is removed.

Validate dictionary changes with `python scripts/validate_translation_dict.py --input scripts/data/translation_dict_v2.json` (must report `errors: 0`, `warnings: 0`).

Browser automation uses `playwright` or `patchright` (Chromium). Session state for authenticated scrapers is persisted to `data/session/`. Initialize a session with `python ittf_matches_playwright_v2.py --init-session` (see `RUNBOOK_v2.md`).

### Web app structure

- Tech: Next.js 15 (App Router) + React 19 + TypeScript + Tailwind CSS v4 (`@tailwindcss/postcss`, not the classic plugin) + better-sqlite3 + Sentry.
- `web/lib/server/db.ts` opens `data/db/ittf.db` with `foreign_keys = ON` and an 8s busy timeout. All DB access goes through this module — do not open new connections.
- `web/lib/server/*.ts` — server-side data access (events, players, rankings, home, etc.). Pages and route handlers should call these, not raw SQL.
- `web/app/` — App Router. Public pages: `events/[eventId]`, `players/[slug]`, `matches/[matchId]`, `rankings`, `schedule-matches/[scheduleMatchId]`. APIs under `app/api/v1/` mirror the page data and are the public JSON contract.
- `web/lib/paths.ts` is the single source of truth for filesystem paths shared between web and scripts.

### Data flow

```
WTT/ITTF sites → Python scrapers → data/**/*.json → Python importers → data/db/ittf.db → web/lib/server/* → Next.js pages and /api/v1
```

Avatars: scraped to `data/player_avatars/`, cropped to `web/public/images/crops/` (both gitignored).

## Conventions

- Run Python commands from the repo root (not `scripts/`).
- Run Node/npm commands from `web/` (not the repo root).
- Don't commit anything under `data/` — the directory is gitignored except for the `data/db/` schema artifacts produced by the import pipeline. Scraped JSON, snapshots, and avatars stay local.
- `event_id=2860` (ITTF Mixed Team World Cup Chengdu 2023) has malformed stage data upstream; always run `scripts/fix_special_event_2860_stage_round.py` before `import_matches.py`.

## Environment

`.env` at repo root (see `.env.example`):
- `MINIMAX_API_KEY` — required for translation scripts
- `APP_ORIGIN`, `SESSION_COOKIE_SECURE`, `TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_IP_HEADER` — web app, used in production behind Cloudflare/reverse proxy

## Reference docs

- `docs/design/database.md` — table relationships and data sources
- `docs/DATABASE_MAINTENANCE.md` — full bootstrap, upgrade, and live-event maintenance procedures
- `docs/event-data-update-workflow.md` — historical vs live data lineage
- `docs/scripts_overview.md` — per-script descriptions of the Python pipeline
- `RUNBOOK_v2.md` — Playwright session-based match scraper operations
