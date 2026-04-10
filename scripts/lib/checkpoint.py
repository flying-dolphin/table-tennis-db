from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CheckpointStore:
    def __init__(self, path: Path) -> None:
        self.path = path
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

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = utc_now_iso()
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def key(self, player_id: Any, player_name: str, from_date_str: str) -> str:
        return f"{player_id}|{player_name}|from:{from_date_str}"

    def is_done(self, key: str) -> bool:
        return bool(self.data.get("completed", {}).get(key))

    def mark_done(self, key: str) -> None:
        self.data.setdefault("completed", {})[key] = utc_now_iso()
        self.data.get("failed", {}).pop(key, None)
        self._save()

    def mark_failed(self, key: str, reason: str) -> None:
        self.data.setdefault("failed", {})[key] = {
            "at": utc_now_iso(),
            "reason": reason,
        }
        self._save()
