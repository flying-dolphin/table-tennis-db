from __future__ import annotations

import logging
import time
from urllib.parse import urljoin
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
    sleep_first: bool = True,
) -> None:
    if sleep_first:
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


def _get_active_pagination_page(page: Any) -> int | None:
    selectors = [
        "li.page-item.active a.page-link",
        "li.page-item.active .page-link",
        ".pagination li.active a",
        ".pagination li.active .page-link",
    ]
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.count() == 0 or not loc.is_visible():
                continue
            text = " ".join((loc.inner_text() or "").split())
            if text.isdigit():
                return int(text)
            title = (loc.get_attribute("title") or "").strip()
            if title.isdigit():
                return int(title)
        except Exception:
            continue
    return None


def _wait_for_active_pagination_page(
    page: Any,
    expected_page: int,
    timeout_sec: float = 12.0,
) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        current_page = _get_active_pagination_page(page)
        if current_page == expected_page:
            return True
        time.sleep(0.25)
    return False


def click_next_page_if_any(page: Any) -> bool:
    current_active_page = _get_active_pagination_page(page)
    expected_active_page = current_active_page + 1 if current_active_page is not None else None
    candidates = [
        "li.page-item:not(.disabled) a[rel='next']",
        "li.next:not(.disabled) a",
        "a[rel='next']",
        "a[aria-label='Next']",
        "a[title='Next']",
        ".pagination a:has-text('Next')",
        ".pagination a:has-text('›')",
        ".pagination a:has-text('»')",
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
            parent_class = ""
            try:
                parent_class = (loc.locator("xpath=ancestor::li[1]").get_attribute("class") or "").lower()
            except Exception:
                parent_class = ""
            if "disabled" in cls or "disabled" in parent_class or aria_disabled == "true":
                continue

            href = (loc.get_attribute("href") or "").strip()
            if href:
                next_url = urljoin(page.url, href)
                prev_url = page.url
                logger.info(
                    "Navigating to next page: %s (active page %s -> %s)",
                    next_url,
                    current_active_page if current_active_page is not None else "?",
                    expected_active_page if expected_active_page is not None else "?",
                )
                page.goto(next_url, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                if expected_active_page is not None:
                    if _wait_for_active_pagination_page(page, expected_active_page):
                        return True
                    logger.warning(
                        "Next page active indicator mismatch after goto: expected=%s actual=%s url=%s",
                        expected_active_page,
                        _get_active_pagination_page(page),
                        page.url,
                    )
                    continue
                if page.url != prev_url:
                    return True
                return True

            move_mouse_to_locator(page, loc)
            logger.info(
                "Clicked next page button without href; waiting for active page %s",
                expected_active_page if expected_active_page is not None else "?",
            )
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            if expected_active_page is not None:
                if _wait_for_active_pagination_page(page, expected_active_page):
                    return True
                logger.warning(
                    "Next page active indicator mismatch after click: expected=%s actual=%s url=%s",
                    expected_active_page,
                    _get_active_pagination_page(page),
                    page.url,
                )
                continue
            return True
        except Exception:
            continue
    return False
