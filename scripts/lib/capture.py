from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_filename(value: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return s[:120] if s else "unknown"


def capture_json_responses_for_page(page: Any, visit: Callable[[], None]) -> list[dict[str, Any]]:
    captures: list[dict[str, Any]] = []

    def on_response(resp: Any) -> None:
        try:
            if resp.status >= 400:
                captures.append({"url": resp.url, "status": resp.status, "error": f"http_{resp.status}"})
                return

            headers = resp.headers or {}
            content_type = (headers.get("content-type") or "").lower()
            if "application/json" not in content_type:
                return
            if "ittf.link" not in resp.url:
                return

            payload = resp.json()
            captures.append({"url": resp.url, "status": resp.status, "json": payload})
        except Exception as exc:
            captures.append({"url": resp.url, "status": getattr(resp, "status", 0), "error": str(exc)})

    page.on("response", on_response)
    try:
        visit()
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
    return captures
