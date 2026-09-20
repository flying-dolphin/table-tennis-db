from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data" / "asian_games" / "2026"
RAW_ROOT = DATA_ROOT / "raw"
NORMALIZED_ROOT = DATA_ROOT / "normalized"
STATE_ROOT = DATA_ROOT / "state"
EVENT_SCHEDULE_PATH = PROJECT_ROOT / "data" / "event_schedule" / "6666.json"
DISPLAY_SCHEDULE_PATH = DATA_ROOT / "table_tennis_schedule.json"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ittf.db"

EVENT_ID = 6666
CHAMPIONSHIP_CODE = "AG2026"
DISCIPLINE_CODE = "TTE"
LANGUAGE = "en"
API_BASE = "https://back.results.asiangames2026.org"
SOURCE_TIME_ZONE = "Asia/Tokyo"
DISPLAY_TIME_ZONE = "Asia/Shanghai"

REQUEST_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://results.asiangames2026.org",
    "Referer": "https://results.asiangames2026.org/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

SUB_EVENT_CODES = {
    "Men's Team": "MT",
    "Women's Team": "WT",
    "Mixed Team": "XT",
    "Men's Singles": "MS",
    "Women's Singles": "WS",
    "Men's Doubles": "MD",
    "Women's Doubles": "WD",
    "Mixed Doubles": "XD",
}

SUB_EVENT_ZH = {
    "Men's Team": "男团",
    "Women's Team": "女团",
    "Mixed Team": "混团",
    "Men's Singles": "男单",
    "Women's Singles": "女单",
    "Men's Doubles": "男双",
    "Women's Doubles": "女双",
    "Mixed Doubles": "混双",
}

STATUS_MAP = {
    "PROVISIONAL": "scheduled",
    "SCHEDULED": "scheduled",
    "START_LIST": "scheduled",
    "RUNNING": "live",
    "LIVE": "live",
    "UNOFFICIAL": "live",
    "OFFICIAL": "completed",
    "FINISHED": "completed",
    "CANCELLED": "cancelled",
    "CANCELED": "cancelled",
}


@dataclass(frozen=True)
class ConvertedTimestamp:
    source_local: str
    utc: str
    beijing: str


def decode_api_payload(raw: bytes) -> Any:
    decoders = (
        lambda: json.loads(raw.decode("utf-8")),
        lambda: json.loads(zlib.decompress(raw).decode("utf-8")),
        lambda: json.loads(
            zlib.decompress(raw.decode("utf-8").encode("latin-1")).decode("utf-8")
        ),
    )
    last_error: Exception | None = None
    for decoder in decoders:
        try:
            return decoder()
        except (UnicodeDecodeError, UnicodeEncodeError, json.JSONDecodeError, zlib.error) as exc:
            last_error = exc
    raise ValueError(f"unable to decode Asian Games API response: {last_error}")


def api_path(suffix: str) -> str:
    suffix = suffix if suffix.startswith("/") else f"/{suffix}"
    return f"/s/{CHAMPIONSHIP_CODE}/{LANGUAGE}/{DISCIPLINE_CODE}{suffix}"


def fetch_json(path: str, *, timeout: int = 30) -> Any:
    url = path if path.startswith("http") else f"{API_BASE}{path}"
    request = urllib.request.Request(url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return decode_api_payload(response.read())


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def convert_source_timestamp(value: str) -> ConvertedTimestamp:
    parsed = datetime.fromisoformat(value)
    source_tz = ZoneInfo(SOURCE_TIME_ZONE)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=source_tz)
    else:
        parsed = parsed.astimezone(source_tz)
    utc_value = parsed.astimezone(timezone.utc)
    beijing_value = parsed.astimezone(ZoneInfo(DISPLAY_TIME_ZONE))
    return ConvertedTimestamp(
        source_local=parsed.replace(tzinfo=None).isoformat(timespec="seconds"),
        utc=utc_value.isoformat(timespec="seconds").replace("+00:00", "Z"),
        beijing=beijing_value.isoformat(timespec="seconds"),
    )


def sub_event_code(event_desc: str | None) -> str:
    return SUB_EVENT_CODES.get((event_desc or "").strip(), "UNKNOWN")


def round_meta(phase_desc: str | None) -> tuple[str, str, str | None]:
    phase = (phase_desc or "").strip()
    group = re.search(r"\bGroup\s+([A-Z0-9]+)\b", phase, re.IGNORECASE)
    if group:
        return "MAIN_DRAW", "RR", group.group(1).upper()

    round_match = re.search(r"Round of\s+(\d+)", phase, re.IGNORECASE)
    if round_match:
        return "MAIN_DRAW", f"R{int(round_match.group(1))}", None

    compact = re.sub(r"[\s-]", "", phase).lower()
    if "quarterfinal" in compact:
        return "MAIN_DRAW", "QF", None
    if "semifinal" in compact:
        return "MAIN_DRAW", "SF", None
    if compact.endswith("final") or "goldmedalmatch" in compact:
        return "MAIN_DRAW", "F", None
    return "UNKNOWN", "UNKNOWN", None


def normalize_status(value: str | None) -> str:
    return STATUS_MAP.get((value or "").strip().upper(), "scheduled")


def translate_phase(event_desc: str, phase_desc: str) -> str:
    prefix = SUB_EVENT_ZH.get(event_desc)
    if not prefix:
        return phase_desc
    suffix = phase_desc[len(event_desc) :].strip() if phase_desc.lower().startswith(event_desc.lower()) else phase_desc
    group = re.fullmatch(r"(?:First Stage\s*-?\s*)?Group\s+([A-Z0-9]+)", suffix, re.IGNORECASE)
    if group:
        return f"{prefix}小组赛{group.group(1).upper()}组"
    round_match = re.fullmatch(r"Round of\s+(\d+)", suffix, re.IGNORECASE)
    if round_match:
        return f"{prefix}{int(round_match.group(1))}强赛"
    compact = re.sub(r"[\s-]", "", suffix).lower()
    if compact == "quarterfinals":
        return f"{prefix}四分之一决赛"
    if compact == "semifinals":
        return f"{prefix}半决赛"
    if compact in {"final", "goldmedalmatch"}:
        return f"{prefix}决赛"
    return phase_desc


def normalized_name(value: str | None) -> str:
    return " ".join((value or "").replace(",", " ").split()).upper()


def extension_value(items: list[dict] | None, code: str) -> str | None:
    for item in items or []:
        if isinstance(item, dict) and item.get("Code") == code:
            value = item.get("Value")
            return str(value) if value is not None else None
    return None
