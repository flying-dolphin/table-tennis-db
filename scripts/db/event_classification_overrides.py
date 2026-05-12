#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations


def override_event_type(event_name: str | None, event_type: str | None, event_kind: str | None) -> tuple[str | None, str | None]:
    """Apply hard classification rules for known multi-sport naming inconsistencies."""
    name = (event_name or "").strip()
    if not name:
        return event_type, event_kind

    # Asian Games should always be treated as Continental Games.
    # Asian Para Games stays untouched per product rule.
    if "Asian Para Games" in name:
        return event_type, event_kind
    if "Asian Games" in name:
        return "Continental Games", "--"

    return event_type, event_kind
