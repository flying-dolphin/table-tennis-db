"""Bind cleanup authority to a complete, validated set of daily responses."""
import hashlib
import json
from pathlib import Path


def digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def verified_capture(raw_root: Path, rows_by_date: dict) -> dict | None:
    try:
        capture = json.loads((raw_root / 'schedule' / 'capture.json').read_text())
        if (capture.get('complete') is not True or not capture.get('batch_id')
                or set(capture.get('dates', [])) != set(rows_by_date)):
            return None
        if capture.get('hashes') != {day: digest(rows) for day, rows in rows_by_date.items()}:
            return None
        return capture
    except (OSError, ValueError, TypeError, AttributeError):
        return None
