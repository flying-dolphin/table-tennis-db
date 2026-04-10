from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

RISK_PATTERNS = [
    "captcha",
    "verify you are human",
    "access denied",
    "too many requests",
    "forbidden",
    "temporarily blocked",
    "security check",
    "cloudflare",
]


class RiskControlTriggered(RuntimeError):
    pass


@dataclass
class DelayConfig:
    min_request_sec: float
    max_request_sec: float
    min_player_gap_sec: float
    max_player_gap_sec: float


def human_sleep(min_sec: float, max_sec: float, reason: str) -> None:
    wait_sec = random.uniform(min_sec, max_sec)
    logger.info("Sleep %.2fs (%s)", wait_sec, reason)
    time.sleep(wait_sec)


def detect_risk(page: Any) -> str | None:
    url = page.url.lower()
    if any(p in url for p in ["captcha", "access-denied", "forbidden"]):
        return f"risk url detected: {page.url}"

    try:
        body_text = page.inner_text("body").lower()
    except Exception:
        body_text = ""

    for pattern in RISK_PATTERNS:
        if pattern in body_text:
            return f"risk text detected: {pattern}"
    return None


def move_mouse_to_locator(page: Any, locator: Any) -> None:
    try:
        box = locator.bounding_box()
    except Exception:
        box = None

    if not box:
        locator.click()
        return

    target_x = box["x"] + random.uniform(box["width"] * 0.25, box["width"] * 0.75)
    target_y = box["y"] + random.uniform(box["height"] * 0.25, box["height"] * 0.75)

    steps = random.randint(18, 35)
    for step in range(1, steps + 1):
        t = step / steps
        jitter_x = random.uniform(-1.5, 1.5)
        jitter_y = random.uniform(-1.5, 1.5)
        page.mouse.move(target_x * t + jitter_x, target_y * t + jitter_y)
        time.sleep(random.uniform(0.006, 0.022))

    page.mouse.click(target_x, target_y)


def type_like_human(page: Any, locator: Any, text: str) -> None:
    move_mouse_to_locator(page, locator)
    locator.fill("")
    time.sleep(random.uniform(0.1, 0.25))
    for ch in text:
        locator.type(ch, delay=random.randint(60, 230))
        if random.random() < 0.08:
            time.sleep(random.uniform(0.3, 0.7))
