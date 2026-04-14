from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CheckpointStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._dirty = False
        self._defer_save = 0
        self.data: dict[str, Any] = {
            "updated_at": "",
            "completed": {},
            "failed": {},
        }
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Checkpoint load failed, start fresh: %s", exc)

        # Normalize schema for forward/backward compatibility
        if not isinstance(self.data, dict):
            self.data = {"updated_at": "", "completed": {}, "failed": {}}
        self.data.setdefault("updated_at", "")
        self.data.setdefault("completed", {})
        self.data.setdefault("failed", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = utc_now_iso()
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8", newline="")
        self._dirty = False

    def _touch(self) -> None:
        self._dirty = True
        if self._defer_save <= 0:
            self.save()

    def key(self, player_id: Any, player_name: str, from_date_str: str) -> str:
        return f"{player_id}|{player_name}|from:{from_date_str}"

    def is_done(self, key: str) -> bool:
        value = self.data.get("completed", {}).get(key)
        if not value:
            return False
        # Old schema stored a timestamp string; new schema stores dict with at/meta.
        if isinstance(value, str):
            return True
        if isinstance(value, dict):
            return True
        return False

    def get_completed(self, key: str) -> dict[str, Any] | None:
        value = self.data.get("completed", {}).get(key)
        if not value:
            return None
        if isinstance(value, str):
            return {"at": value}
        if isinstance(value, dict):
            return value
        return None

    def mark_done(self, key: str, meta: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"at": utc_now_iso()}
        if meta:
            payload["meta"] = meta
        self.data.setdefault("completed", {})[key] = payload
        self.data.get("failed", {}).pop(key, None)
        self._touch()

    def mark_failed(self, key: str, reason: str, meta: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "at": utc_now_iso(),
            "reason": reason,
        }
        if meta:
            payload["meta"] = meta
        self.data.setdefault("failed", {})[key] = {
            **payload,
        }
        self._touch()

    def has_any_completed(self) -> bool:
        return bool(self.data.get("completed", {}))

    def reset(self) -> None:
        """Clear all checkpoint marks."""
        self.data = {
            "updated_at": "",
            "completed": {},
            "failed": {},
        }
        self._touch()

    @contextmanager
    def bulk(self) -> Any:
        """Defer checkpoint file writes until the context exits.

        Useful for bootstrapping from existing output files.
        """
        self._defer_save += 1
        try:
            yield self
        finally:
            self._defer_save -= 1
            if self._defer_save <= 0 and self._dirty:
                self.save()
