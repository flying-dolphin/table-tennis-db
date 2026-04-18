from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .anti_bot import DelayConfig, RiskControlTriggered, detect_risk
from .navigation_runtime import open_page_with_verification, page_requires_login, prompt_manual_verification

logger = logging.getLogger(__name__)


def ensure_logged_in(
    page: Any,
    search_url: str,
    delay_cfg: DelayConfig,
    storage_state_file: Path,
    init_session: bool,
) -> None:
    open_page_with_verification(page, search_url, delay_cfg, "open search page for login check")

    if page_requires_login(page):
        prompt_manual_verification(
            [
                "",
                "=== Manual login required ===",
                "1) Complete login in the opened browser window",
                "2) If MFA/captcha appears, complete it manually",
                "3) Return here and press ENTER",
            ],
            "Press ENTER after login is completed...",
        )

        risk = detect_risk(page)
        if risk:
            raise RiskControlTriggered(risk)

        if page_requires_login(page):
            raise RuntimeError("Login still appears not completed. Aborting.")

    if init_session or not storage_state_file.exists():
        storage_state_file.parent.mkdir(parents=True, exist_ok=True)
        page.context.storage_state(path=str(storage_state_file))
        logger.info("Saved storage state to %s", storage_state_file)
