"""Capture a complete batch before publishing the raw manifest."""
from __future__ import annotations

import argparse
import hashlib
import urllib.error
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from .common import BASE_URL, EVENT_ID, PROJECTS, add_options, fetch_json, read_json, utc_now, write_json


def capture(data_root: Path, *, no_proxy: bool = False, all_linked: bool = False,
            full: bool = False, fetch: Callable | None = None) -> Path:
    fetch = fetch or (lambda path: fetch_json(path, no_proxy=no_proxy))
    batch = data_root / "raw" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:10])
    started = utc_now()
    files: dict = {}
    previous = read_json(data_root / "raw/latest.json") if (data_root / "raw/latest.json").exists() else {}
    previous_files = previous.get("files", {})

    def get(path: str, expected: type, *, unpublished: bool = False, cached: bool = False):
        old = previous_files.get(path)
        available = True
        if cached and old:
            old_path = data_root / old["file"]
            if hashlib.sha256(old_path.read_bytes()).hexdigest() != old["sha256"]:
                raise ValueError(f"cached capture digest mismatch: {path}")
            value = read_json(old_path)
            available = old.get("available", True)
        else:
            try:
                value = fetch(path)
            except urllib.error.HTTPError as exc:
                if not unpublished or exc.code != 404:
                    raise
                value = []
                available = False
        if not isinstance(value, expected):
            raise ValueError(f"{path}: expected {expected.__name__}")
        target = batch / path
        write_json(target, value)
        files[path] = {"file": str(target.relative_to(data_root)), "url": BASE_URL + path,
                       "available": available,
                       "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                       "fetched_at": old["fetched_at"] if cached and old else utc_now()}
        return value

    champ = get("champ.json", dict)
    if champ.get("champ") != "TTE3474" or not champ.get("events") or not champ.get("dates"):
        raise ValueError("invalid Asian Championships metadata")
    keys = [item["Key"] for item in champ["events"]]
    if set(keys) != set(PROJECTS) or len(keys) != len(set(keys)):
        raise ValueError("championship must declare exactly all seven projects")
    dates = [item["raw"] for item in champ["dates"]]
    for date in dates:
        if datetime.fromisoformat(date).year != 2026:
            raise ValueError(f"unexpected date: {date}")
    # The newest two published days are refreshed; terminal older days can be
    # replayed from the last successful batch. --full reconciles official fixes.
    for date in dates:
        path = f"match/d{date}.json"
        old = previous_files.get(path)
        cached = False
        if not full and not all_linked and old and date not in sorted(dates)[-2:]:
            rows = read_json(data_root / old["file"])
            cached = bool(rows) and all(row.get("Status") == 1 for row in rows)
        rows = get(path, list, cached=cached)
        if any(not isinstance(row, dict) or not row.get("Key") or "Status" not in row for row in rows):
            raise ValueError(f"invalid daily match rows: {path}")
        if all_linked:
            for row in rows:
                key = row["Key"]
                if "/" in key or ".." in key:
                    raise ValueError("unsafe match key")
                get(f"match/{key}.json", list)
    get("match/live.json", list)
    for key in keys:
        for section in ("entries", "groups", "brackets"):
            get(f"{section}/{key}.json", list, unpublished=True)
    manifest = {"event_id": EVENT_ID, "batch_id": batch.name, "started_at": started,
                "captured_at": utc_now(), "files": files, "full": full or all_linked}
    write_json(batch / "manifest.json", manifest)
    write_json(data_root / "raw/latest.json", manifest)
    return batch / "manifest.json"


def load_capture(data_root: Path, manifest_path: Path | None = None) -> tuple[dict, dict]:
    manifest = read_json(manifest_path or data_root / "raw/latest.json")
    if manifest.get("event_id") != EVENT_ID:
        raise ValueError("capture is not event 3474")
    payloads = {}
    for key, entry in manifest["files"].items():
        path = (data_root / entry["file"]).resolve()
        if not path.is_relative_to(data_root.resolve()):
            raise ValueError("capture path outside data root")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"capture digest mismatch: {key}")
        payloads[key] = read_json(path)
    return manifest, payloads


def main() -> int:
    parser = argparse.ArgumentParser(description="采集 2026 亚锦赛官方 JSON")
    add_options(parser)
    parser.add_argument("--no-proxy", action="store_true")
    parser.add_argument("--all-linked", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    print(capture(args.data_root, no_proxy=args.no_proxy, all_linked=args.all_linked, full=args.full))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
