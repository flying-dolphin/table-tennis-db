#!/usr/bin/env python3
"""Infer an event IANA time zone from existing calendar data.

The WTT/ITTF calendar stores location as an ISO-3 country code in many rows.
That is enough for countries with one practical time zone, but not for places
like USA or Australia. For multi-zone countries this script only succeeds when
the event name contains a known city.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import sys
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import config

    DEFAULT_DB_PATH = Path(config.DB_PATH)
except ImportError:
    DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "db" / "ittf.db"


CITY_TIME_ZONES = {
    "asuncion": "America/Asuncion",
    "berlin": "Europe/Berlin",
    "benghazi": "Africa/Tripoli",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "cappadocia": "Europe/Istanbul",
    "chennai": "Asia/Kolkata",
    "christchurch": "Pacific/Auckland",
    "chongqing": "Asia/Shanghai",
    "doha": "Asia/Qatar",
    "dusseldorf": "Europe/Berlin",
    "gold coast": "Australia/Brisbane",
    "haikou": "Asia/Shanghai",
    "havirov": "Europe/Prague",
    "lignano": "Europe/Rome",
    "lille": "Europe/Paris",
    "linz": "Europe/Vienna",
    "manama": "Asia/Bahrain",
    "montreux": "Europe/Zurich",
    "muscat": "Asia/Muscat",
    "otocec": "Europe/Ljubljana",
    "san francisco": "America/Los_Angeles",
    "singapore": "Asia/Singapore",
    "tunis": "Africa/Tunis",
    "vadodara": "Asia/Kolkata",
    "varazdin": "Europe/Zagreb",
    "vila real": "Europe/Lisbon",
    "wladyslawowo": "Europe/Warsaw",
}


SINGLE_COUNTRY_TIME_ZONES = {
    "ARG": "America/Argentina/Buenos_Aires",
    "AUT": "Europe/Vienna",
    "BRN": "Asia/Bahrain",
    "CHN": "Asia/Shanghai",
    "CRO": "Europe/Zagreb",
    "CZE": "Europe/Prague",
    "FRA": "Europe/Paris",
    "GER": "Europe/Berlin",
    "IND": "Asia/Kolkata",
    "ITA": "Europe/Rome",
    "JPN": "Asia/Tokyo",
    "LBA": "Africa/Tripoli",
    "NZL": "Pacific/Auckland",
    "OMA": "Asia/Muscat",
    "PAR": "America/Asuncion",
    "POL": "Europe/Warsaw",
    "POR": "Europe/Lisbon",
    "QAT": "Asia/Qatar",
    "SGP": "Asia/Singapore",
    "SLO": "Europe/Ljubljana",
    "SUI": "Europe/Zurich",
    "TUN": "Africa/Tunis",
    "TUR": "Europe/Istanbul",
}


MULTI_ZONE_COUNTRIES = {
    "AUS",
    "BRA",
    "CAN",
    "CHL",
    "COD",
    "IDN",
    "KAZ",
    "MEX",
    "RUS",
    "USA",
}


@dataclass(frozen=True)
class EventTimezoneInput:
    event_id: int
    name: str
    calendar_location: str | None
    event_location: str | None


@dataclass(frozen=True)
class TimezoneInference:
    time_zone: str | None
    source: str | None
    reason: str


def normalize_lookup_text(value: str | None) -> str:
    if not value:
        return ""
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in ascii_text)
    return " ".join(cleaned.split())


def contains_phrase(text: str, phrase: str) -> bool:
    padded_text = f" {text} "
    padded_phrase = f" {normalize_lookup_text(phrase)} "
    return padded_phrase in padded_text


def validate_time_zone(time_zone: str) -> str:
    try:
        ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"invalid IANA time zone in mapping: {time_zone}") from exc
    return time_zone


def infer_time_zone(event: EventTimezoneInput) -> TimezoneInference:
    search_text = normalize_lookup_text(
        " ".join(part for part in [event.name, event.event_location, event.calendar_location] if part)
    )
    for city, time_zone in sorted(CITY_TIME_ZONES.items(), key=lambda item: len(item[0]), reverse=True):
        if contains_phrase(search_text, city):
            return TimezoneInference(validate_time_zone(time_zone), "city", f"matched city {city!r}")

    country_code = normalize_lookup_text(event.event_location or event.calendar_location).upper()
    if country_code in SINGLE_COUNTRY_TIME_ZONES:
        time_zone = SINGLE_COUNTRY_TIME_ZONES[country_code]
        return TimezoneInference(validate_time_zone(time_zone), "country", f"matched country {country_code}")

    if country_code in MULTI_ZONE_COUNTRIES:
        return TimezoneInference(
            None,
            None,
            f"multi-zone country {country_code}; add a city mapping or pass --time-zone manually",
        )

    location_label = event.event_location or event.calendar_location or "<empty>"
    return TimezoneInference(None, None, f"no mapping for location {location_label!r}")


def load_event(conn: sqlite3.Connection, event_id: int) -> EventTimezoneInput | None:
    row = conn.execute(
        """
        SELECT
            COALESCE(e.name, ec.name) AS name,
            ec.location AS calendar_location,
            e.location AS event_location
        FROM events_calendar ec
        LEFT JOIN events e ON e.event_id = ec.event_id
        WHERE ec.event_id = ?
        LIMIT 1
        """,
        (event_id,),
    ).fetchone()
    if row is None:
        row = conn.execute(
            """
        SELECT e.name, NULL AS calendar_location, e.location AS event_location
        FROM events e
        WHERE e.event_id = ?
        LIMIT 1
            """,
            (event_id,),
        ).fetchone()
    if row is None:
        return None
    return EventTimezoneInput(
        event_id=event_id,
        name=row[0] or "",
        calendar_location=row[1],
        event_location=row[2],
    )


def apply_time_zone(conn: sqlite3.Connection, event_id: int, time_zone: str) -> int:
    cursor = conn.execute(
        """
        UPDATE events
        SET time_zone = ?
        WHERE event_id = ? AND lifecycle_status != 'completed'
        """,
        (time_zone, event_id),
    )
    return cursor.rowcount


def main() -> int:
    parser = argparse.ArgumentParser(description="Infer an event IANA time zone from calendar/event metadata.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true", help="write the inferred time zone to events.time_zone")
    parser.add_argument("--explain", action="store_true", help="print the match source and reason")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    try:
        event = load_event(conn, args.event_id)
        if event is None:
            print(f"event_id {args.event_id} not found in events_calendar or events", file=sys.stderr)
            return 1

        result = infer_time_zone(event)
        if result.time_zone is None:
            print(f"Could not infer time zone for event_id {args.event_id}: {result.reason}", file=sys.stderr)
            return 2

        if args.apply:
            changed = apply_time_zone(conn, args.event_id, result.time_zone)
            if changed == 0:
                conn.rollback()
                print(
                    f"Could not update events.time_zone for event_id {args.event_id}; "
                    "the events row may be missing or completed.",
                    file=sys.stderr,
                )
                return 1
            conn.commit()

        if args.explain:
            print(f"{result.time_zone}\t{result.source}\t{result.reason}")
        else:
            print(result.time_zone)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
