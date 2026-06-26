#!/usr/bin/env bash
set -euo pipefail

YEAR="${1:-${YEAR:-2026}}"
CDP_PORT="${CDP_PORT:-9223}"

python scripts/scrape_events_calendar.py \
  --year "$YEAR" \
  --cdp-port "$CDP_PORT" \
  --headless \
  --force

python scripts/translate_events_calendar.py \
  --year "$YEAR" \
  --force

python scripts/db/import_events_calendar.py \
  --year "$YEAR"
