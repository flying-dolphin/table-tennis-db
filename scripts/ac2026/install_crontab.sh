#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$PROJECT_DIR/scripts/ac2026/resolve_python.sh"
PYTHON_BIN="$(ac2026_resolve_python "$PROJECT_DIR")"
cd "$PROJECT_DIR"
mkdir -p data/ac2026/3474/logs
existing="$(mktemp)"
updated="$(mktemp)"
trap 'rm -f "$existing" "$updated"' EXIT
if crontab -l > "$existing" 2>/dev/null; then
    :
else
    # Only treat the documented "no crontab" case as an empty crontab.
    error="$(crontab -l 2>&1 || true)"
    if [[ "$error" != *"no crontab"* ]]; then
        printf '%s\n' "$error" >&2
        exit 1
    fi
fi
"$PYTHON_BIN" - "$existing" "$updated" <<'PY'
import sys
from pathlib import Path
from scripts.ac2026.generate_crontab import BEGIN, END, generate_crontab

source = Path(sys.argv[1]).read_text()
lines = source.splitlines()
if lines.count(BEGIN) != lines.count(END) or lines.count(BEGIN) > 1:
    raise SystemExit('Malformed AC2026 cron block; leaving crontab unchanged')
if BEGIN in lines:
    first, last = lines.index(BEGIN), lines.index(END)
    if first > last:
        raise SystemExit('Malformed AC2026 cron block')
    lines = lines[:first] + lines[last + 1:]
Path(sys.argv[2]).write_text('\n'.join(lines).rstrip() + '\n\n' + generate_crontab(python=sys.executable))
PY
crontab "$updated"
printf '%s\n' 'Installed the AC2026 3474 cron block.'
