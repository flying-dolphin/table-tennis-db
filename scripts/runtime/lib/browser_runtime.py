from __future__ import annotations

import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def try_connect_cdp(
    playwright: Any,
    cdp_port: int,
    log_prefix: str = "CDP",
) -> tuple[bool, Any | None, Any | None]:
    """Try to connect to an existing Chromium instance via CDP."""
    cdp_url = f"http://localhost:{cdp_port}"
    try:
        urllib.request.urlopen(f"{cdp_url}/json/version", timeout=2)
    except Exception:
        return False, None, None

    try:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        contexts = browser.contexts
        context = contexts[0] if contexts else browser.new_context()
        logger.info("%s: connected to existing Chrome via CDP at %s", log_prefix, cdp_url)
        return True, browser, context
    except Exception as exc:
        logger.warning("%s: CDP handshake failed: %s", log_prefix, exc)
        return False, None, None


def open_browser_page(
    playwright: Any,
    *,
    use_cdp: bool = False,
    cdp_port: int = 9222,
    cdp_only: bool = False,
    launch_kwargs: dict[str, Any] | None = None,
    context_kwargs: dict[str, Any] | None = None,
    log_prefix: str = "browser",
) -> tuple[bool, Any, Any, Any]:
    """Open a browser/context/page with optional CDP reuse and launch fallback."""
    launch_kwargs = launch_kwargs or {}
    context_kwargs = context_kwargs or {}

    via_cdp = False
    browser = None
    context = None

    if use_cdp:
        via_cdp, browser, context = try_connect_cdp(playwright, cdp_port, log_prefix=log_prefix)
        if (not via_cdp) and cdp_only:
            raise RuntimeError(f"{log_prefix}: cdp-only enabled but no CDP Chrome found on port {cdp_port}")

    if not via_cdp:
        browser = playwright.chromium.launch(**launch_kwargs)
        context = browser.new_context(**context_kwargs)
        logger.info("%s: launched new browser", log_prefix)

    page = context.new_page()
    return via_cdp, browser, context, page


def close_browser_page(via_cdp: bool, browser: Any, page: Any) -> None:
    """Close only the new page for CDP sessions; close browser for owned sessions."""
    if via_cdp:
        try:
            page.close()
        except Exception:
            pass
        return

    try:
        browser.close()
    except Exception:
        pass
