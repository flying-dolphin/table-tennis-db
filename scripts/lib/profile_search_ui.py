from __future__ import annotations

import logging
import random
import re
import time
from typing import Any

from .anti_bot import move_mouse_to_locator, type_like_human

logger = logging.getLogger(__name__)


def open_or_select_autocomplete(page: Any, player_name: str, country_code: str) -> bool:
    search_key = f"{player_name} ({country_code})" if country_code else player_name

    logger.info("[autocomplete] start player=%s country=%s search_key=%s", player_name, country_code or "", search_key)

    search_input = page.locator("input[type='text']").first
    input_count = search_input.count()
    logger.info("[autocomplete] text inputs found, using first locator count=%s", input_count)
    if input_count == 0:
        logger.warning("[autocomplete] no text input found")
        return False

    def wait_and_click_option(target_text: str, fallback_text: str) -> bool:
        target_lower = target_text.lower()
        fallback_lower = fallback_text.lower()
        name_lower = player_name.lower()
        country_lower = country_code.lower().strip()

        def _normalize_words(text: str) -> list[str]:
            return [part for part in re.split(r"[^a-z0-9]+", (text or "").lower()) if part]

        player_words = sorted(_normalize_words(player_name))

        def selection_matches_value(value: str) -> bool:
            normalized = " ".join((value or "").split()).lower()
            if not normalized:
                return False
            if target_lower and target_lower in normalized:
                return True
            if fallback_lower and fallback_lower in normalized:
                return True

            candidate_name = normalized
            if "(" in candidate_name:
                candidate_name = candidate_name.split("(", 1)[0].strip()
            candidate_words = sorted(_normalize_words(candidate_name))
            if player_words and candidate_words and player_words == candidate_words:
                if not country_lower:
                    return True
                country_match = re.search(r"\(([a-z]{3})\)", normalized)
                return bool(country_match and country_match.group(1) == country_lower)
            return False

        def read_selected_player_id() -> str:
            selectors = [
                "input[name='vw_profiles___player_id_raw']",
                "input[name='player_id_raw']",
                "input[id*='player_id_raw']",
            ]
            for selector in selectors:
                loc = page.locator(selector).first
                try:
                    if loc.count() == 0:
                        continue
                    value = (loc.input_value() or loc.get_attribute("value") or "").strip()
                    if re.fullmatch(r"\d+", value):
                        return value
                except Exception:
                    continue
            return ""

        def wait_for_selected_player_id(timeout_sec: float = 2.5) -> str:
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                player_id = read_selected_player_id()
                if player_id:
                    return player_id
                time.sleep(0.2)
            return ""

        def inject_selected_player_id(player_id: str) -> None:
            if not re.fullmatch(r"\d+", player_id or ""):
                return
            selectors = [
                "input[name='vw_profiles___player_id_raw']",
                "input[name='player_id_raw']",
                "input[id*='player_id_raw']",
            ]
            for selector in selectors:
                loc = page.locator(selector).first
                try:
                    if loc.count() == 0:
                        continue
                    loc.evaluate(
                        """(el, v) => {
                            el.value = v;
                            el.setAttribute('value', v);
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            el.dispatchEvent(new Event('blur', { bubbles: true }));
                        }""",
                        player_id,
                    )
                except Exception:
                    continue

        def candidate_score(text: str) -> int:
            normalized = " ".join(text.split()).lower()
            if not normalized:
                return -1

            score = 0
            if selection_matches_value(text):
                score += 100

            candidate_name = normalized
            if "(" in candidate_name:
                candidate_name = candidate_name.split("(", 1)[0].strip()
            candidate_words = sorted(_normalize_words(candidate_name))

            if player_words and candidate_words:
                if player_words == candidate_words:
                    score += 80
                else:
                    overlap = len(set(player_words) & set(candidate_words))
                    score += overlap * 10

            country_match = re.search(r"\(([a-z]{3})\)", normalized)
            if country_lower and country_match:
                if country_match.group(1) == country_lower:
                    score += 30
                else:
                    score -= 20

            if target_lower and target_lower == normalized:
                score += 50
            if fallback_lower and fallback_lower == candidate_name:
                score += 40

            return score

        def click_best_effort(loc: Any) -> None:
            try:
                loc.click(timeout=1500)
                return
            except Exception as exc:
                logger.warning("[autocomplete] click failed: %s", exc)
            try:
                loc.click(force=True, timeout=1500)
                logger.info("[autocomplete] force click ok")
                return
            except Exception as exc:
                logger.warning("[autocomplete] force click failed: %s", exc)
            try:
                loc.evaluate(
                    """(el) => {
                        const options = { bubbles: true, cancelable: true, view: window };
                        el.dispatchEvent(new MouseEvent('mousedown', options));
                        el.dispatchEvent(new MouseEvent('mouseup', options));
                        el.dispatchEvent(new MouseEvent('click', options));
                    }"""
                )
                logger.info("[autocomplete] dom click dispatched")
                return
            except Exception as exc:
                logger.warning("[autocomplete] dom click failed: %s", exc)
            move_mouse_to_locator(page, loc)
            logger.info("[autocomplete] mouse click ok")

        for attempt in range(12):
            exact = page.get_by_text(target_text, exact=True).first
            try:
                exact_count = exact.count()
            except Exception:
                exact_count = 0
            logger.info("[autocomplete] attempt=%s exact_count=%s target=%s", attempt + 1, exact_count, target_text)
            try:
                if exact_count > 0 and exact.is_visible():
                    logger.info("[autocomplete] exact option visible, trying click: %s", target_text)
                    exact_data_value = ""
                    try:
                        exact_data_value = (exact.get_attribute("data-value") or "").strip()
                    except Exception:
                        exact_data_value = ""
                    click_best_effort(exact)
                    if re.fullmatch(r"\d+", exact_data_value):
                        inject_selected_player_id(exact_data_value)
                        logger.info("[autocomplete] exact option selected with data-value player_id=%s", exact_data_value)
                        return True
                    selected_player_id = wait_for_selected_player_id(timeout_sec=1.2)
                    if selected_player_id:
                        logger.info("[autocomplete] exact option selected with hidden player_id=%s", selected_player_id)
                        return True
                    logger.info("[autocomplete] exact option clicked but hidden player_id not ready yet, retrying")
            except Exception as exc:
                logger.info("[autocomplete] exact option probe failed: %s", exc)

            autocomplete_root = page.locator(
                "ul.dropdown-menu[role='menu']:visible, ul.ui-autocomplete:visible, ul[id*='ui-id']:visible, .ui-autocomplete:visible, [role='listbox']:visible"
            ).first
            root_count = 0
            try:
                root_count = autocomplete_root.count()
            except Exception:
                root_count = 0

            if root_count > 0:
                candidates = autocomplete_root.locator("li > a[data-value]")
                logger.info("[autocomplete] using scoped autocomplete container")
            else:
                candidates = page.locator("ul.dropdown-menu[role='menu'] li > a[data-value]")
                logger.info("[autocomplete] autocomplete container not found, using a[data-value] fallback selectors")

            try:
                count = min(candidates.count(), 20)
            except Exception:
                count = 0
            logger.info("[autocomplete] attempt=%s candidate_count=%s", attempt + 1, count)

            best_candidate: tuple[int, int, Any, str] | None = None
            for i in range(count):
                item = candidates.nth(i)
                try:
                    if not item.is_visible():
                        continue
                    txt = " ".join((item.inner_text() or "").split())
                    data_value = item.get_attribute("data-value") if item.count() > 0 else None
                    if not txt:
                        continue
                    score = candidate_score(txt)
                    logger.info("[autocomplete] candidate[%s]=%s data-value=%s score=%s", i, txt[:120], data_value, score)
                    if score > 0 and (best_candidate is None or score > best_candidate[0]):
                        best_candidate = (score, i, item, txt)
                except Exception as exc:
                    logger.info("[autocomplete] candidate[%s] probe failed: %s", i, exc)
                    continue

            if best_candidate is not None:
                score, best_idx, best_item, best_text = best_candidate
                logger.info("[autocomplete] best candidate[%s]=%s score=%s, trying click", best_idx, best_text[:120], score)
                before_value = None
                try:
                    before_value = search_input.input_value()
                except Exception:
                    pass
                best_data_value = ""
                try:
                    best_data_value = (best_item.get_attribute("data-value") or "").strip()
                except Exception:
                    best_data_value = ""
                click_best_effort(best_item)
                if re.fullmatch(r"\d+", best_data_value):
                    inject_selected_player_id(best_data_value)
                    logger.info("[autocomplete] selected by candidate data-value player_id=%s", best_data_value)
                    return True

                time.sleep(0.4)
                try:
                    after_value = search_input.input_value()
                except Exception:
                    after_value = None
                logger.info("[autocomplete] input before click=%s after click=%s", before_value, after_value)
                if selection_matches_value(after_value or ""):
                    selected_player_id = wait_for_selected_player_id(timeout_sec=1.2)
                    if selected_player_id:
                        logger.info("[autocomplete] selected with player_id=%s", selected_player_id)
                        return True
                    logger.info("[autocomplete] text matched but hidden player_id not ready yet, retrying")
                time.sleep(0.4)
                try:
                    settled_value = search_input.input_value()
                except Exception:
                    settled_value = None
                if selection_matches_value(settled_value or ""):
                    selected_player_id = wait_for_selected_player_id()
                    if selected_player_id:
                        logger.info("[autocomplete] settled selection with player_id=%s", selected_player_id)
                        return True
                    logger.info("[autocomplete] settled text matched but hidden player_id missing, retrying")
                logger.info("[autocomplete] selection did not settle, retrying")

            time.sleep(0.25)
        logger.warning("[autocomplete] no option matched after retries for target=%s fallback=%s", target_text, fallback_text)
        return False

    short_query = player_name[:20]
    logger.info("[autocomplete] typing short query=%s", short_query)
    type_like_human(page, search_input, short_query)
    try:
        logger.info("[autocomplete] input value after short query=%s", search_input.input_value())
    except Exception as exc:
        logger.info("[autocomplete] could not read input after short query: %s", exc)
    time.sleep(random.uniform(0.8, 1.6))
    if wait_and_click_option(search_key, player_name):
        logger.info("[autocomplete] selected by short query: %s", search_key)
        return True

    logger.info("[autocomplete] typing full query=%s", search_key)
    type_like_human(page, search_input, search_key)
    try:
        logger.info("[autocomplete] input value after full query=%s", search_input.input_value())
    except Exception as exc:
        logger.info("[autocomplete] could not read input after full query: %s", exc)
    time.sleep(random.uniform(0.8, 1.8))
    if wait_and_click_option(search_key, player_name):
        logger.info("[autocomplete] selected by full query: %s", search_key)
        return True

    logger.warning("[autocomplete] option not selected: %s", search_key)
    return False


def click_go(
    page: Any,
    *,
    prefer_same_form_as: str | None = "input.vw_profiles___player_idvalue-auto-complete",
    require_effect: bool = False,
    expected_url_contains: str | None = None,
    effect_timeout_sec: float = 3.0,
) -> bool:
    def _effect_observed(before_url: str, timeout_sec: float) -> bool:
        if not require_effect:
            return True
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            current_url = page.url
            if current_url != before_url:
                if expected_url_contains:
                    if expected_url_contains in current_url:
                        return True
                else:
                    return True
            time.sleep(0.2)
        return False

    def _locator_diag(loc: Any) -> dict[str, str]:
        try:
            info = loc.evaluate(
                """(el) => {
                    const form = el.closest('form');
                    const cls = (el.className || '').toString().trim().slice(0, 120);
                    return {
                        tag: (el.tagName || '').toLowerCase(),
                        id: el.id || '',
                        type: el.type || '',
                        name: el.name || '',
                        value: el.value || '',
                        className: cls,
                        formAction: form ? (form.getAttribute('action') || '') : '',
                        formId: form ? (form.id || '') : '',
                    };
                }"""
            )
            if isinstance(info, dict):
                return {k: str(v or "") for k, v in info.items()}
        except Exception:
            pass
        return {}

    def _element_from_point_diag(loc: Any) -> str:
        try:
            box = loc.bounding_box()
            if not box:
                return "N/A"
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            text = page.evaluate(
                """([x, y]) => {
                    const el = document.elementFromPoint(x, y);
                    if (!el) return 'none';
                    const cls = (el.className || '').toString().trim().slice(0, 80);
                    const id = el.id ? '#' + el.id : '';
                    return `${el.tagName.toLowerCase()}${id}[name="${el.getAttribute('name') || ''}"][type="${el.getAttribute('type') || ''}"][value="${el.getAttribute('value') || ''}"].${cls}`;
                }""",
                [x, y],
            )
            return str(text or "N/A")
        except Exception:
            return "N/A"

    def _click_and_verify(loc: Any, click_mode: str, before_url: str) -> bool:
        try:
            if click_mode == "locator":
                loc.click(timeout=2000)
            elif click_mode == "force":
                loc.click(force=True, timeout=2000)
            elif click_mode == "mouse":
                move_mouse_to_locator(page, loc)
            elif click_mode == "dom":
                loc.evaluate(
                    """(el) => {
                        const options = { bubbles: true, cancelable: true, view: window };
                        el.dispatchEvent(new MouseEvent('mousedown', options));
                        el.dispatchEvent(new MouseEvent('mouseup', options));
                        el.dispatchEvent(new MouseEvent('click', options));
                    }"""
                )
            else:
                return False
        except Exception as exc:
            logger.info("click_go: click mode=%s failed: %s", click_mode, exc)
            return False

        if _effect_observed(before_url, effect_timeout_sec):
            return True
        logger.info("click_go: click mode=%s had no observed effect within %.1fs", click_mode, effect_timeout_sec)
        return False

    candidate_selectors = [
        "input[type='button'][value='Go'][name='filter']",
        "input[type='button'][value='Go']",
        "input[type='submit'][value='Go']",
        "button:has-text('Go')",
        "button[type='submit']",
    ]

    candidates: list[Any] = []
    if prefer_same_form_as:
        try:
            anchor = page.locator(f"{prefer_same_form_as}:visible").first
            if anchor.count() > 0:
                form = anchor.locator("xpath=ancestor::form[1]").first
                if form.count() > 0:
                    for sel in candidate_selectors:
                        loc = form.locator(sel).first
                        if loc.count() > 0 and loc.is_visible():
                            candidates.append(loc)
        except Exception:
            pass

    for sel in candidate_selectors:
        loc = page.locator(sel).first
        try:
            if loc.count() > 0 and loc.is_visible():
                candidates.append(loc)
        except Exception:
            continue

    seen_keys: set[str] = set()
    deduped_candidates: list[Any] = []
    for loc in candidates:
        diag = _locator_diag(loc)
        key = "|".join([diag.get("tag", ""), diag.get("id", ""), diag.get("name", ""), diag.get("value", ""), diag.get("formId", "")])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_candidates.append(loc)

    for loc in deduped_candidates:
        before_url = page.url
        diag = _locator_diag(loc)
        hit = _element_from_point_diag(loc)
        logger.info(
            "click_go: try candidate tag=%s id=%s type=%s name=%s value=%s form_id=%s form_action=%s url=%s hit=%s",
            diag.get("tag", ""),
            diag.get("id", ""),
            diag.get("type", ""),
            diag.get("name", ""),
            diag.get("value", ""),
            diag.get("formId", ""),
            diag.get("formAction", ""),
            before_url,
            hit,
        )
        for mode in ("locator", "force", "mouse", "dom"):
            if _click_and_verify(loc, mode, before_url):
                logger.info("click_go: success by mode=%s, url_now=%s", mode, page.url)
                return True

    try:
        btn_values = []
        for el in page.query_selector_all("input[type='button'], input[type='submit'], button"):
            val = (el.get_attribute("value") or el.inner_text() or "").strip()
            cls = (el.get_attribute("class") or "").strip()
            name = (el.get_attribute("name") or "").strip()
            if val:
                btn_values.append({"value": val, "name": name, "class": cls[:80]})
        logger.warning("click_go failed. button candidates on page: %s", btn_values[:20])
    except Exception:
        pass
    return False
