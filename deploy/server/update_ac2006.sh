#!/usr/bin/env bash
# Run on the deployment host after publishing the repository files.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$PROJECT_DIR/scripts/ac2006/resolve_python.sh"
PYTHON_BIN="$(ac2006_resolve_python "$PROJECT_DIR")"
cd "$PROJECT_DIR"
BACKUP_DB_PATH="data/db/ittf.db"
expect_db=0
for argument in "$@"; do
    if [[ "$expect_db" -eq 1 ]]; then
        BACKUP_DB_PATH="$argument"
        expect_db=0
    elif [[ "$argument" == --db-path=* ]]; then
        BACKUP_DB_PATH="${argument#--db-path=}"
    elif [[ "$argument" == --db-path ]]; then
        expect_db=1
    fi
done
if [[ " ${*} " != *" --dry-run "* ]]; then
    mkdir -p data/db/backups
    AC2006_BACKUP_DB_PATH="$BACKUP_DB_PATH" "$PYTHON_BIN" - <<'PY'
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

source_path = Path(os.environ['AC2006_BACKUP_DB_PATH']).resolve()
source = sqlite3.connect(f'{source_path.as_uri()}?mode=ro', uri=True)
backup = Path('data/db/backups') / ('ittf-before-ac2006-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.db')
target = sqlite3.connect(backup)
try:
    source.backup(target)
finally:
    target.close()
    source.close()
print(f'Database backup: {backup}')
PY
fi
exec "$PYTHON_BIN" -m scripts.ac2006.refresh "$@"
