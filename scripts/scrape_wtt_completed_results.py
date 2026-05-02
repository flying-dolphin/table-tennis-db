#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyze WTT team event Completed Results page via headless browser.

This script is intentionally standalone and does not affect the existing
scrape/import pipeline. It opens the public Results page, clicks the
"Load more" button until exhausted, and saves:

1. captured network responses related to the page
2. final DOM snapshot
3. extracted visible result blocks

Primary use: discover a stable full-history completed-results source for
in-progress team events where GetOfficialResult only returns a rolling window.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.browser_runtime import close_browser_page, open_browser_page

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "wtt_results_analysis"
RESULTS_URL_TEMPLATE = (
    "https://www.worldtabletennis.com/teamseventInfo"
    "?selectedTab=Results&innerselectedTab=Completed&eventId={event_id}"
)


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def capture_relevant_responses(page: Any) -> list[dict[str, Any]]:
    captures: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    def on_response(resp: Any) -> None:
        try:
            url = resp.url
            status = int(resp.status)
            if not any(token in url for token in ("worldtabletennis.com", "liveeventsapi.worldtabletennis.com", "ittf.link")):
                return

            headers = resp.headers or {}
            content_type = (headers.get("content-type") or "").lower()
            if "json" not in content_type and "javascript" not in content_type:
                return

            key = (url, status)
            suffix = 1
            while key in seen:
                suffix += 1
                key = (f"{url}#{suffix}", status)
            seen.add(key)

            record: dict[str, Any] = {
                "url": url,
                "status": status,
                "content_type": content_type,
            }
            try:
                record["json"] = resp.json()
            except Exception:
                try:
                    record["text"] = resp.text()
                except Exception as exc:
                    record["error"] = str(exc)
            captures.append(record)
        except Exception as exc:
            captures.append({"error": str(exc)})

    page.on("response", on_response)
    return captures


def wait_settle(page: Any, timeout_ms: int = 8000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        try:
            page.wait_for_timeout(1200)
        except Exception:
            pass


def results_summary(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
          const text = (node) => (node?.textContent || '').replace(/\\s+/g, ' ').trim();
          const blocks = Array.from(document.querySelectorAll('main *, #__next *'));
          const resultLike = blocks.filter((node) => {
            if (!(node instanceof HTMLElement)) return false;
            const t = text(node);
            if (!t || t.length < 12) return false;
            const hasScore = /\\b\\d+\\s*-\\s*\\d+\\b/.test(t);
            const hasVs = /\\bvs\\b/i.test(t);
            const hasStageCode = /GP\\d{2}|RND1|QFNL|SFNL|FNL/i.test(t);
            return hasScore || (hasVs && hasStageCode);
          });
          const loadMoreCandidates = Array.from(document.querySelectorAll('button, a, div[role="button"]'))
            .map((node) => ({
              tag: node.tagName,
              text: text(node),
              visible: !!(node instanceof HTMLElement && node.offsetParent),
              disabled: !!node.disabled,
            }))
            .filter((item) => /load more/i.test(item.text));

          return {
            title: document.title,
            url: location.href,
            result_like_count: resultLike.length,
            load_more_candidates: loadMoreCandidates,
            body_text_preview: text(document.body).slice(0, 5000),
          };
        }
        """
    )


def extract_result_blocks(page: Any) -> list[dict[str, Any]]:
    return page.evaluate(
        """
        () => {
          const text = (node) => (node?.textContent || '').replace(/\\s+/g, ' ').trim();
          const nodes = Array.from(document.querySelectorAll('main *, #__next *'));
          const seen = new Set();
          const blocks = [];

          for (const node of nodes) {
            if (!(node instanceof HTMLElement)) continue;
            const t = text(node);
            if (!t || t.length < 12) continue;
            const hasScore = /\\b\\d+\\s*-\\s*\\d+\\b/.test(t);
            const hasStageCode = /GP\\d{2}|RND1|QFNL|SFNL|FNL/i.test(t);
            if (!hasScore && !hasStageCode) continue;

            const normalized = t.slice(0, 300);
            if (seen.has(normalized)) continue;
            seen.add(normalized);

            blocks.push({
              tag: node.tagName,
              className: node.className || '',
              text: t,
            });
          }

          return blocks;
        }
        """
    )


def click_load_more_until_done(page: Any, max_clicks: int) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []

    for idx in range(max_clicks):
        summary_before = results_summary(page)
        try:
            locator = page.get_by_role("button", name=re.compile("load more", re.I)).first
            if locator.count() == 0:
                history.append({"step": idx, "action": "stop", "reason": "no_load_more_button", "summary": summary_before})
                break
            if not locator.is_visible():
                history.append({"step": idx, "action": "stop", "reason": "load_more_hidden", "summary": summary_before})
                break

            logger.info("Load more click %s", idx + 1)
            locator.click(timeout=5000)
            wait_settle(page)
            page.wait_for_timeout(1000)
            summary_after = results_summary(page)
            history.append({"step": idx, "action": "click", "before": summary_before, "after": summary_after})

            if summary_after == summary_before:
                history.append({"step": idx, "action": "stop", "reason": "no_dom_change_after_click"})
                break
        except Exception as exc:
            history.append({"step": idx, "action": "stop", "reason": f"click_error:{exc}"})
            break

    return history


def analyze_event(event_id: int, output_root: Path, *, headless: bool, cdp_port: int, use_cdp: bool, verbose: bool) -> int:
    run_dir = output_root / str(event_id) / utc_now_compact()
    run_dir.mkdir(parents=True, exist_ok=True)
    url = RESULTS_URL_TEMPLATE.format(event_id=event_id)

    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("patchright/playwright not installed")
            return 2

    with sync_playwright() as p:
        via_cdp, browser, _, page = open_browser_page(
            p,
            use_cdp=use_cdp,
            cdp_port=cdp_port,
            cdp_only=False,
            launch_kwargs={"headless": headless},
            context_kwargs={"viewport": {"width": 1440, "height": 2000}, "locale": "en-US", "timezone_id": "Asia/Shanghai"},
            log_prefix="wtt-completed-results",
        )

        captures = capture_relevant_responses(page)
        try:
            logger.info("Opening %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            wait_settle(page, timeout_ms=12000)
            page.wait_for_timeout(1500)

            click_history = click_load_more_until_done(page, max_clicks=60)
            final_summary = results_summary(page)
            final_blocks = extract_result_blocks(page)
            final_html = page.content()
            final_text = page.locator("body").inner_text(timeout=5000)

            (run_dir / "network_captures.json").write_text(
                json.dumps(captures, ensure_ascii=False, indent=2),
                encoding="utf-8",
                newline="",
            )
            (run_dir / "click_history.json").write_text(
                json.dumps(click_history, ensure_ascii=False, indent=2),
                encoding="utf-8",
                newline="",
            )
            (run_dir / "final_summary.json").write_text(
                json.dumps(final_summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
                newline="",
            )
            (run_dir / "result_blocks.json").write_text(
                json.dumps(final_blocks, ensure_ascii=False, indent=2),
                encoding="utf-8",
                newline="",
            )
            (run_dir / "page.html").write_text(final_html, encoding="utf-8", newline="")
            (run_dir / "page.txt").write_text(final_text, encoding="utf-8", newline="")

            logger.info("Saved analysis to %s", run_dir)
        finally:
            close_browser_page(via_cdp, browser, page)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze WTT Completed Results page via headless browser.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--use-cdp", action="store_true", help="Reuse existing Chrome via CDP instead of launching a fresh browser.")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.verbose)
    return analyze_event(
        args.event_id,
        args.output_root.resolve(),
        headless=bool(args.headless),
        cdp_port=args.cdp_port,
        use_cdp=bool(args.use_cdp),
        verbose=bool(args.verbose),
    )


if __name__ == "__main__":
    sys.exit(main())
