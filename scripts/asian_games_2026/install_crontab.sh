#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${PROJECT_ROOT}/.venv/bin/python}"
BEGIN_MARKER="# BEGIN ITTF ASIAN GAMES 2026"
END_MARKER="# END ITTF ASIAN GAMES 2026"
CURRENT_FILE="$(mktemp)"
OUTPUT_FILE="$(mktemp)"
BLOCK_FILE="$(mktemp)"
trap 'rm -f "$CURRENT_FILE" "$OUTPUT_FILE" "$BLOCK_FILE"' EXIT

mkdir -p "$PROJECT_ROOT/data/asian_games/2026/logs"
crontab -l > "$CURRENT_FILE" 2>/dev/null || true
"$PYTHON_BIN" -m scripts.asian_games_2026.generate_crontab \
  --project-root "$PROJECT_ROOT" \
  --python "$PYTHON_BIN" > "$BLOCK_FILE"
awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" '
  $0 == begin { skipping=1; next }
  $0 == end { skipping=0; next }
  !skipping { print }
' "$CURRENT_FILE" > "$OUTPUT_FILE"
cat "$BLOCK_FILE" >> "$OUTPUT_FILE"
crontab "$OUTPUT_FILE"
echo "Asian Games 2026 cron block installed."
