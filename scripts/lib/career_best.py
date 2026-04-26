from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CareerBestMonthResult:
    month: str | None
    raw_period: str
    granularity: str | None


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _extract_period_token(value: str) -> str:
    normalized = _normalize_space(value)
    match = re.search(r"(\d{1,2}/\d{4}|\d{4}-\d{1,2}|\d{1,2}/\d{4})", normalized)
    if match:
        return match.group(1)
    return normalized


def iso_week_to_month(week_value: str) -> str | None:
    token = _extract_period_token(week_value)
    match = re.fullmatch(r"(\d{1,2})/(\d{4})", token)
    if not match:
        return None
    week = int(match.group(1))
    year = int(match.group(2))
    if week < 1 or week > 53:
        return None
    try:
        week_start = date.fromisocalendar(year, week, 1)
    except ValueError:
        return None
    return f"{week_start.year:04d}-{week_start.month:02d}"


def parse_month_value(month_value: str) -> str | None:
    token = _extract_period_token(month_value)
    match = re.fullmatch(r"(\d{4})-(\d{1,2})", token)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"

    match = re.fullmatch(r"(\d{1,2})/(\d{4})", token)
    if match:
        month = int(match.group(1))
        year = int(match.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"
    return None


def normalize_career_best_month(raw_period: str, raw_granularity: str | None = None) -> CareerBestMonthResult:
    granularity = _normalize_space(raw_granularity or "").lower() or None
    cleaned = _normalize_space(raw_period)
    if not cleaned:
        return CareerBestMonthResult(month=None, raw_period="", granularity=granularity)

    if granularity == "month":
        return CareerBestMonthResult(
            month=parse_month_value(cleaned),
            raw_period=cleaned,
            granularity="month",
        )

    month = iso_week_to_month(cleaned)
    if month:
        return CareerBestMonthResult(month=month, raw_period=cleaned, granularity=granularity or "week")

    if granularity is None:
        parsed_month = parse_month_value(cleaned)
        if parsed_month:
            return CareerBestMonthResult(month=parsed_month, raw_period=cleaned, granularity="month")

    return CareerBestMonthResult(month=None, raw_period=cleaned, granularity=granularity)
