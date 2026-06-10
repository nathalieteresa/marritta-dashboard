# -*- coding: utf-8 -*-
"""
Robust scraper for the official Marenas Resort booking page.
Returns official hotel/resort rates for selected dates.

How it works:
- Opens the official booking URL with Playwright.
- Waits for the dynamic booking engine to render.
- Clicks/activates the RATES view if available.
- Scrolls the page to force room cards to load.
- Extracts room names and the most relevant nightly rate from visible text.
- Fails safely and returns [] if the site blocks automation or no rates are visible.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import quote


ROOM_NAME_HINTS = [
    "classic", "king", "queen", "suite", "bay view", "ocean view", "oceanfront",
    "deluxe", "one-bedroom", "one bedroom", "two-bedroom", "two bedroom", "penthouse",
]

BAD_PRICE_CONTEXT = [
    "tax", "taxes", "fee", "fees", "additional", "deposit", "save", "saved", "%",
]


def _to_mmddyyyy(date_value) -> str:
    """Accepts YYYY-MM-DD, MM/DD/YYYY, datetime/date object and returns MM/DD/YYYY."""
    if not date_value:
        return ""
    if hasattr(date_value, "strftime"):
        return date_value.strftime("%m/%d/%Y")
    date_str = str(date_value)
    if "/" in date_str:
        return date_str
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%m/%d/%Y")
    except Exception:
        return date_str


def _money_numbers_with_context(text: str):
    out = []
    for m in re.finditer(r"\$\s*([0-9][0-9,]*(?:\.\d{2})?)", text or ""):
        raw = m.group(1)
        try:
            value = float(raw.replace(",", ""))
        except Exception:
            continue
        start = max(0, m.start() - 55)
        end = min(len(text), m.end() + 55)
        context = text[start:end].lower()
        out.append((value, context, m.start()))
    return out


def _choose_best_nightly_price(text: str) -> Optional[float]:
    """
    Choose the best nightly room rate from a card.
    In the Marenas engine, the card often shows:
    $249.00 crossed out, $199.20 Avg. per night, $72.73 taxes and fees.
    We prefer prices near 'avg/per night/member offer' and reject taxes/fees.
    """
    candidates = []
    for value, context, pos in _money_numbers_with_context(text):
        if value < 80 or value > 2500:
            continue
        if any(bad in context for bad in BAD_PRICE_CONTEXT):
            # Do not discard member offers because 'save' can appear in a banner above the room.
            if not any(good in context for good in ["avg", "night", "member offer", "per night"]):
                continue
        score = 0
        if "avg" in context:
            score += 5
        if "per night" in context or "night" in context:
            score += 4
        if "member offer" in context or "exclusive reward" in context:
            score += 2
        if "tax" in context or "fee" in context or "additional" in context:
            score -= 6
        if value < 120:
            score -= 3
        candidates.append((score, pos, value))

    if not candidates:
        return None

    # Prefer highest score. If same score, prefer the later price because crossed-out original price
    # often appears before the discounted nightly price.
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def _clean_lines(text: str) -> List[str]:
    lines = []
    for ln in (text or "").splitlines():
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            lines.append(ln)
    return lines


def _looks_like_room_title(line: str) -> bool:
    low = line.lower()
    if len(line) < 6 or len(line) > 120:
        return False
    if "$" in line or "step " in low or "select your stay" in low:
        return False
    return any(h in low for h in ROOM_NAME_HINTS)


def _title_from_block(text: str) -> str:
    lines = _clean_lines(text)
    for ln in lines[:30]:
        if _looks_like_room_title(ln):
            return ln[:120]
    for ln in lines[:12]:
        low = ln.lower()
        if len(ln) >= 6 and "$" not in ln and low not in {"book now", "select", "room details", "rate details", "rates", "suites"}:
            return ln[:120]
    return "Marenas official available rate"


def _build_url(checkin: str, checkout: str, adults: int = 1, rooms: int = 1) -> str:
    datein = quote(_to_mmddyyyy(checkin))
    dateout = quote(_to_mmddyyyy(checkout))
    return (
        "https://www.marenasresortmiami.com/book/accommodations"
        f"?adults={int(adults)}&datein={datein}&dateout={dateout}"
        "&domain=www.marenasresortmiami.com&languageid=1"
        f"&rooms={int(rooms)}"
    )


def _extract_from_blocks(page, url: str, max_results: int = 12) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen = set()

    selectors = [
        "[class*='room']", "[class*='Room']",
        "[class*='suite']", "[class*='Suite']",
        "[class*='rate']", "[class*='Rate']",
        "[class*='product']", "[class*='card']", "article", "section",
    ]

    for selector in selectors:
        try:
            loc = page.locator(selector)
            count = min(loc.count(), 80)
        except Exception:
            continue

        for i in range(count):
            try:
                txt = loc.nth(i).inner_text(timeout=1200).strip()
            except Exception:
                continue
            if not txt or "$" not in txt or len(txt) < 40:
                continue
            low = txt.lower()
            if "additional taxes" in low and not any(h in low for h in ROOM_NAME_HINTS):
                continue

            price = _choose_best_nightly_price(txt)
            if price is None:
                continue
            title = _title_from_block(txt)
            key = (title.lower(), round(price, 2))
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "title": title,
                "price": price,
                "nightly_price": price,
                "source": "Marenas Official Website",
                "link": url,
                "raw_text": txt[:900],
                "relevance": "Official",
                "relevance_score": 100,
                "direct_competitor": True,
                "qualified_competitor": True,
                "fit_score": 100,
                "fit_reasons": "Official Marenas Resort nightly rate",
            })
            if len(results) >= max_results:
                return results
    return results


def _extract_from_full_text(full_text: str, url: str) -> List[Dict[str, Any]]:
    """Fallback parser for visible page text."""
    if not full_text or "$" not in full_text:
        return []
    lines = _clean_lines(full_text)
    results = []
    seen = set()
    for idx, line in enumerate(lines):
        if not _looks_like_room_title(line):
            continue
        block = "\n".join(lines[idx: idx + 18])
        if "$" not in block:
            continue
        price = _choose_best_nightly_price(block)
        if price is None:
            continue
        key = (line.lower(), round(price, 2))
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "title": line[:120],
            "price": price,
            "nightly_price": price,
            "source": "Marenas Official Website",
            "link": url,
            "raw_text": block[:900],
            "relevance": "Official",
            "relevance_score": 100,
            "direct_competitor": True,
            "qualified_competitor": True,
            "fit_score": 100,
            "fit_reasons": "Official Marenas Resort nightly rate",
        })
        if len(results) >= 12:
            break
    return results


def get_marenas_official_prices(
    checkin: str,
    checkout: str,
    adults: int = 1,
    rooms: int = 1,
    max_seconds: int = 90,
) -> List[Dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []

    url = _build_url(checkin, checkout, adults=adults, rooms=rooms)
    start = time.time()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1500, "height": 1200},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=min(max_seconds, 70) * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=18000)
            except Exception:
                pass
            page.wait_for_timeout(5000)

            # Close common chat/cookie overlays when present.
            for text in ["Accept", "I agree", "Close", "×", "No thanks"]:
                try:
                    btn = page.get_by_text(text, exact=True).first
                    if btn.is_visible(timeout=700):
                        btn.click(timeout=1000)
                        page.wait_for_timeout(500)
                except Exception:
                    pass

            # Activate Rates tab if present.
            for label in ["RATES", "Rates"]:
                try:
                    page.get_by_text(label, exact=True).first.click(timeout=1500)
                    page.wait_for_timeout(2500)
                    break
                except Exception:
                    pass

            # Scroll to force lazy-loaded cards/rates.
            for _ in range(4):
                if time.time() - start > max_seconds:
                    break
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(1000)

            results = _extract_from_blocks(page, url)
            if not results:
                try:
                    full_text = page.locator("body").inner_text(timeout=5000)
                    results = _extract_from_full_text(full_text, url)
                except Exception:
                    results = []

            context.close()
            browser.close()
            return results[:12]
    except Exception:
        return []
