from __future__ import annotations

import logging
import time
from typing import Any

from .anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep, move_mouse_to_locator

logger = logging.getLogger(__name__)


def guarded_goto(
    page: Any,
    url: str,
    delay_cfg: DelayConfig,
    reason: str,
    referer: str | None = None,
    retries: int = 2,
) -> None:
    human_sleep(delay_cfg.min_request_sec, delay_cfg.max_request_sec, reason)

    goto_kwargs: dict[str, Any] = {"wait_until": "domcontentloaded", "timeout": 45000}
    if referer:
        goto_kwargs["referer"] = referer

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            page.goto(url, **goto_kwargs)
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                wait_sec = 8 * (attempt + 1)
                logger.warning(
                    "goto failed (attempt %s/%s): %s, retry in %ss",
                    attempt + 1, retries + 1, exc, wait_sec,
                )
                time.sleep(wait_sec)
    if last_exc:
        raise last_exc

    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass

    risk = detect_risk(page)
    if risk:
        raise RiskControlTriggered(risk)


def click_next_page_if_any(page: Any) -> bool:
    candidates = [
        "li.next:not(.disabled) a",
        "a[aria-label='Next']",
        "a:has-text('Next')",
        "button:has-text('Next')",
    ]
    for sel in candidates:
        loc = page.locator(sel).first
        try:
            if loc.count() == 0:
                continue
            if not loc.is_visible():
                continue
            cls = (loc.get_attribute("class") or "").lower()
            aria_disabled = (loc.get_attribute("aria-disabled") or "").lower()
            if "disabled" in cls or aria_disabled == "true":
                continue
            move_mouse_to_locator(page, loc)
            page.wait_for_load_state("networkidle", timeout=10000)
            return True
        except Exception:
            continue
    return False
