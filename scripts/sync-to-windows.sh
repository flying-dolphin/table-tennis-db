#!/usr/bin/env bash
set -euo pipefail

SRC="$HOME/projects/ittf/"
DST="/mnt/d/dev/project/ittf/"

#rsync -aH --info=progress2 \
rsync -aH --delete --info=progress2 \
  --exclude='.SynologyWorkingDirectory/' \
  --exclude='.git/' \
  --exclude='desktop.ini' \
  --exclude='*.tar' \
  --exclude='**/node_modules/' \
  --exclude='.venv/' \
  --exclude='.tmp/' \
  --exclude='tmp/' \
  --exclude='.claude/' \
  --exclude='.codex/' \
  --exclude='.agent/' \
  --exclude='.agents/' \
  --exclude='.vscode/' \
  --exclude='web/.next/' \
  --exclude='web/out/' \
  --exclude='web/coverage/' \
  --exclude='web/reports/' \
  --exclude='**/__pycache__/' \
  --exclude='**/.pytest_cache/' \
  --exclude='**/.mypy_cache/' \
  --exclude='**/.vitest-cache/' \
  --exclude='**/*.pyc' \
  "$SRC" "$DST"

