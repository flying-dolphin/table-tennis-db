from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .anti_bot import DelayConfig, RiskControlTriggered, detect_risk
from .page_ops import guarded_goto

logger = logging.getLogger(__name__)


def ensure_logged_in(
    page: Any,
    search_url: str,
    delay_cfg: DelayConfig,
    storage_state_file: Path,
    init_session: bool,
) -> None:
    guarded_goto(page, search_url, delay_cfg, "open search page for login check")

    is_login_form = page.locator("input[name='username']").count() > 0
    if is_login_form:
        print("\n=== Manual login required ===")
        print("1) Complete login in the opened browser window")
        print("2) If MFA/captcha appears, complete it manually")
        print("3) Return here and press ENTER")
        input("Press ENTER after login is completed...")

        risk = detect_risk(page)
        if risk:
            raise RiskControlTriggered(risk)

        if page.locator("input[name='username']").count() > 0:
            raise RuntimeError("Login still appears not completed. Aborting.")

    if init_session or not storage_state_file.exists():
        storage_state_file.parent.mkdir(parents=True, exist_ok=True)
        page.context.storage_state(path=str(storage_state_file))
        logger.info("Saved storage state to %s", storage_state_file)
