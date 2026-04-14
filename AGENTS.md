# ITTF Rankings Project - Agent Instructions

## Project Structure

```
ittf/                          # Root of the project
├── scripts/                   # Python web scraping & data processing
├── web/                       # Next.js frontend + SQLite
│   ├── app/                   # App Router pages and API routes
│   ├── db/                    # SQLite schema (schema.sql) and client
│   ├── lib/                   # Data access, types, utilities
│   └── scripts/               # DB migrate and seed scripts
├── data/                      # Scraped JSON data (rankings, profiles, matches)
└── design-system/             # Component library
```

## Web Frontend (`web/`)

**Tech Stack:** Next.js 15 + TypeScript + Tailwind CSS v4 + better-sqlite3

**Setup:**
```bash
cd web
npm install
npm run db:migrate    # Initialize SQLite schema
npm run db:seed       # Import from ../data/ (women_singles_top50.json, matches_complete/*.json)
npm run dev
```

**Important:** Seed reads from the parent directory's `data/`, not `web/data/`.

**Commands:**
- `npm run dev` - Start dev server (port 3000)
- `npm run build` - Production build
- `npm run lint` - Run ESLint
- `npm run db:migrate` - Apply schema.sql
- `npm run db:seed` - Import JSON data to SQLite

**Tailwind v4 note:** Uses `@tailwindcss/postcss` in postcss.config.mjs, not the traditional tailwindcss/postcss setup.

## Python Scripts (`scripts/`)

**Setup:**
```bash
pip install -r requirements.txt
cp .env.example .env  # Add MINIMAX_API_KEY for translations
```

**Run from repo root** (not from `scripts/`), e.g., `python scripts/run_rankings.py`.

**Key scripts:**
```bash
python scripts/run_rankings.py --top 100 --headless    # Scrape rankings
python scripts/run_profiles.py --category women --top 50 --headless  # Scrape player profiles
python scripts/scrape_matches.py --players-file data/women_singles_top50.json  # Scrape matches
python scripts/scrape_events_calendar.py --year 2026  # Scrape event calendar
python scripts/run_rankings.py --force --output-dir data/rankings/orig
```

**Translation workflow:**
- Dictionary: `scripts/data/translation_dict_v2.json` (v1 is deprecated)
- Categories: `players / terms / events / locations / others`
- Validate: `python scripts/validate_translation_dict.py --input scripts/data/translation_dict_v2.json`
- Translate events: `python scripts/translate_events_calendar.py --year 2026`

**Browser automation:** Uses `playwright` or `patchright` (Chromium). Session state saved to `data/session/`.

## Data Flow

1. **Scraping** (Python) → JSON in `data/`
2. **Seeding** (`npm run db:seed`) → SQLite in `web/db/ittf_rankings.sqlite`
3. **Frontend** reads from SQLite via `web/db/client.ts`

## Design System

- Tailwind config extends colors: `mint`, `dark`, `soft`, `primary`, `cta`
- Fonts: `Archivo` (headings), `Space Grotesk` (body)
- Design tokens in `design-system/ittf-hub/`

## API Endpoints

- `GET /api/rankings` - Rankings JSON
- `GET /api/players/[slug]` - Player details JSON

## Env Variables

```bash
MINIMAX_API_KEY=...  # Required for translation scripts
```
