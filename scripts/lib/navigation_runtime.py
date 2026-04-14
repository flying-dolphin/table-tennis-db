from __future__ import annotations

import logging
import sys
from typing import Any

from .anti_bot import DelayConfig, RiskControlTriggered, detect_risk, human_sleep
from .page_ops import guarded_goto

logger = logging.getLogger(__name__)


def page_has_real_content(page: Any) -> bool:
    try:
        if "cf-chl" in page.url or "challenges.cloudflare" in page.url:
            return False

        challenge_selectors = [
            "#challenge-form",
            "#cf-challenge-title",
            "[data-ray]",
            "#challenge-title",
            ".challenge-title",
            "iframe[src*='challenges.cloudflare']",
        ]
        for sel in challenge_selectors:
            if page.locator(sel).count() > 0:
                return False

        body_text = page.inner_text("body")
        return len(body_text.strip()) >= 100
    except Exception:
        return False


def page_has_cloudflare_challenge(page: Any) -> bool:
    try:
        selectors = [
            "#challenge-title",
            ".challenge-title",
            "#cf-challenge-title",
            "[data-ray]",
            "#challenge-form",
        ]
        for selector in selectors:
            if page.locator(selector).count() > 0:
                return True

        title = page.title()
        if "Just a moment" in title or "Cloudflare" in title:
            return True

        if "challenges.cloudflare" in page.url:
            return True
    except Exception:
        pass
    return False


def prompt_manual_verification(message_lines: list[str], prompt: str) -> None:
    if not sys.stdin.isatty():
        raise RuntimeError("Manual verification required, but no interactive TTY is available.")
    for line in message_lines:
        print(line)
    input(prompt)


def open_page_with_verification(
    page: Any,
    url: str,
    delay_cfg: DelayConfig,
    reason: str,
    *,
    sleep_first: bool = True,
    require_real_content: bool = False,
    check_cloudflare: bool = False,
    manual_prompt_lines: list[str] | None = None,
    manual_prompt: str = "Press ENTER after verification is completed...",
    settle_reason: str = "after manual verification",
) -> None:
    guarded_goto(page, url, delay_cfg, reason, sleep_first=sleep_first)

    need_manual = False
    if require_real_content and not page_has_real_content(page):
        need_manual = True
    if check_cloudflare and page_has_cloudflare_challenge(page):
        need_manual = True

    if need_manual:
        lines = manual_prompt_lines or [
            "Verification page detected.",
            "Complete the verification in the browser window, then return here.",
        ]
        prompt_manual_verification(lines, manual_prompt)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        human_sleep(2.0, 4.0, settle_reason)

    risk = detect_risk(page)
    if risk:
        raise RiskControlTriggered(risk)


def verify_cdp_session_or_prompt(
    page: Any,
    url: str,
    delay_cfg: DelayConfig,
    *,
    login_selector: str = "input[name='username']",
) -> None:
    open_page_with_verification(page, url, delay_cfg, "verify CDP session", sleep_first=False)
    if page.locator(login_selector).count() == 0:
        return

    prompt_manual_verification(
        [
            "",
            "=== CDP session requires login ===",
            "1) Complete login in the opened browser window",
            "2) Return here and press ENTER",
        ],
        "Press ENTER after login is completed...",
    )
    if page.locator(login_selector).count() > 0:
        raise RuntimeError("Login not completed. Aborting.")
