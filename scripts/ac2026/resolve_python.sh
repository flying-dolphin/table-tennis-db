#!/usr/bin/env bash
# Shared interpreter selection for the championship's deployment entry points.
ac2026_resolve_python() {
    local project_dir="$1"
    local candidate resolved
    if [[ -n "${PYTHON_BIN:-}" ]]; then
        resolved="$(command -v -- "$PYTHON_BIN")" || {
            printf 'ERROR: PYTHON_BIN is not executable: %s\n' "$PYTHON_BIN" >&2
            return 1
        }
        if [[ ! -x "$resolved" ]] || ! "$resolved" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
            printf 'ERROR: PYTHON_BIN must be a working Python 3.11+ interpreter: %s\n' "$PYTHON_BIN" >&2
            return 1
        fi
        printf '%s\n' "$resolved"
        return 0
    fi
    for candidate in "$project_dir/.venv/bin/python" python python3.11 python3; do
        resolved="$(command -v -- "$candidate")" || continue
        if [[ -x "$resolved" ]] && "$resolved" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
            printf '%s\n' "$resolved"
            return 0
        fi
    done
    printf '%s\n' 'ERROR: Python 3.11+ not found. Set PYTHON_BIN to an installed interpreter.' >&2
    return 1
}
