from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
EVENT_ID = 3474
BASE_URL = "https://results.ittf.com/ittf-web-results/html/TTE3474/"
DATA_ROOT = ROOT / "data/ac2026/3474"
DB_PATH = ROOT / "data/db/ittf.db"
SOURCE_ZONE = "Asia/Tashkent"
EVENT_NAME = "ITTF-ATTU Asian Championships Tashkent 2026"
EVENT_NAME_ZH = "2026年塔什干亚洲乒乓球锦标赛"
PROJECTS = {
    "M.SINGLES-----------": "MS", "W.SINGLES-----------": "WS",
    "M.DOUBLES-----------": "MD", "W.DOUBLES-----------": "WD",
    "X.DOUBLES-----------": "XD", "M.TEAM--------------": "MT",
    "W.TEAM--------------": "WT",
}
PROJECT_NAMES = {
    "MS": ("Men's Singles", "男子单打"), "WS": ("Women's Singles", "女子单打"),
    "MD": ("Men's Doubles", "男子双打"), "WD": ("Women's Doubles", "女子双打"),
    "XD": ("Mixed Doubles", "混合双打"), "MT": ("Men's Teams", "男子团体"),
    "WT": ("Women's Teams", "女子团体"),
}
STAGE_NAMES = {
    "MAIN_DRAW": ("Main Draw", "正赛"), "PRELIMINARY": ("Preliminary Round", "预赛"),
    "POSITION_DRAW": ("Position Draw", "排位赛"),
}
ROUND_NAMES = {
    "RR": ("Round Robin", "小组赛"), "R1": ("Round 1", "第1轮"),
    "R2": ("Round 2", "第2轮"), "R3": ("Round 3", "第3轮"),
    "QF": ("QuarterFinal", "四分之一决赛"), "SF": ("SemiFinal", "半决赛"), "F": ("Final", "决赛"),
    **{f"R{n}": (f"Round of {n}", f"{n}强赛") for n in (256, 128, 64, 32, 16)},
    **{f"P{low}_{high}": (f"Pos. {low}-{high}", f"第{low}至{high}名排位赛")
       for low, high in ((9, 16), (13, 16), (13, 14), (15, 16), (17, 32), (25, 32), (25, 28), (27, 28), (25, 26))},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".capture-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def fetch_json(path: str, *, no_proxy: bool = False) -> Any:
    opener = urllib.request.build_opener(*([urllib.request.ProxyHandler({})] if no_proxy else []))
    request = urllib.request.Request(BASE_URL + path, headers={
        "User-Agent": "ITTF-Rankings/1.0", "Accept": "application/json",
        "Cache-Control": "no-cache",
    })
    for attempt in range(3):
        try:
            with opener.open(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise
            if attempt == 2:
                raise
        except (OSError, ValueError):
            if attempt == 2:
                raise
        time.sleep(1 + attempt)
    raise RuntimeError("request retries exhausted")


def add_options(parser: argparse.ArgumentParser, *, database: bool = False) -> None:
    parser.add_argument("--event-id", type=int, choices=[EVENT_ID], default=EVENT_ID)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    if database:
        parser.add_argument("--db-path", type=Path, default=DB_PATH)


def timestamp(date: str | None, clock: str | None) -> tuple[str | None, str | None]:
    if not date or not clock or "TBD" in clock:
        return None, None
    local = datetime.fromisoformat(f"{date}T{clock}").replace(tzinfo=ZoneInfo(SOURCE_ZONE))
    return local.replace(tzinfo=None).isoformat(timespec="seconds"), local.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
