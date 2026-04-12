from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# 风控页面检测关键词（页面被拦截/验证时才会出现）
RISK_PATTERNS = [
    "captcha",
    "verify you are human",
    "access denied",
    "too many requests",
    "forbidden",
    "temporarily blocked",
    "security check",
    "blocked",
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
        title = page.title().lower()
    except Exception:
        body_text = ""
        title = ""

    # 1. 通用风控关键词检测
    for pattern in RISK_PATTERNS:
        if pattern in body_text or pattern in title:
            return f"risk text detected: {pattern}"

    # 2. Cloudflare 挑战页面检测（更精确）
    # 只有当同时包含 "cloudflare" 和挑战页面特征时才认为是风控
    if "cloudflare" in body_text or "cloudflare" in title:
        risk_indicators = [
            "just a moment",
            "checking your browser",
            "please wait",
            "challenge",
            "cf-challenge",
        ]
        if any(ind in body_text or ind in title for ind in risk_indicators):
            return "risk text detected: cloudflare challenge"

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
