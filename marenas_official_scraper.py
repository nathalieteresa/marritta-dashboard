# -*- coding: utf-8 -*-
"""
Scraper for the official Marenas Resort booking page.
Returns official hotel/resort rates for selected dates.
Designed to fail safely: if the site changes or blocks automation, it returns [] instead of crashing Streamlit.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional


def _to_mmddyyyy(date_str: str) -> str:
    """Accepts YYYY-MM-DD or MM/DD/YYYY and returns MM/DD/YYYY."""
    if not date_str:
        return date_str
    if "/" in date_str:
        return date_str
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%m/%d/%Y")
    except Exception:
        return date_str


def _money_to_float(value: str) -> Optional[float]:
    if not value:
        return None
    m = re.search(r"\$\s*([0-9][0-9,]*(?:\.\d{2})?)", value)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except Exception:
        return None


def _extract_price_near_text(text: str) -> Optional[float]:
    """Extracts a plausible rate from a room-card text block."""
    if not text:
        return None

    # Prefer price labels commonly used by hotel booking engines.
    patterns = [
        r"(?:from|starting from|avg(?:erage)?|nightly|rate|total)\s*\$\s*([0-9][0-9,]*(?:\.\d{2})?)",
        r"\$\s*([0-9][0-9,]*(?:\.\d{2})?)\s*(?:/\s*night|per night|night)",
        r"\$\s*([0-9][0-9,]*(?:\.\d{2})?)",
    ]
    for pat in patterns:
        matches = re.findall(pat, text, flags=re.I)
        for raw in matches:
            try:
                price = float(str(raw).replace(",", ""))
                # Avoid accidentally picking taxes/fees like $0 or small promo text.
                if 50 <= price <= 5000:
                    return price
            except Exception:
                pass
    return None


def _clean_title(text: str) -> str:
    if not text:
        return "Official Marenas accommodation"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    skip = {"book now", "select", "view details", "details", "rate details", "more details"}
    for ln in lines[:12]:
        low = ln.lower()
        if len(ln) >= 6 and "$" not in ln and low not in skip:
            return ln[:120]
    return lines[0][:120] if lines else "Official Marenas accommodation"


def _build_url(checkin: str, checkout: str, adults: int = 1, rooms: int = 1) -> str:
    datein = _to_mmddyyyy(checkin)
    dateout = _to_mmddyyyy(checkout)
    return (
        "https://www.marenasresortmiami.com/book/accommodations"
        f"?adults={adults}&datein={datein}&dateout={dateout}"
        "&domain=www.marenasresortmiami.com&languageid=1"
        f"&rooms={rooms}"
    )


def get_marenas_official_prices(
    checkin: str,
    checkout: str,
    adults: int = 1,
    rooms: int = 1,
    max_seconds: int = 70,
) -> List[Dict[str, Any]]:
    """
    Returns a list like:
    [{title, price, nightly_price, source, link, raw_text, relevance, direct_competitor}]

    price is treated as nightly when the booking engine shows a nightly room rate.
    If the site displays total-stay prices instead, the dashboard still labels the source as official.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []

    url = _build_url(checkin, checkout, adults=adults, rooms=rooms)
    start = time.time()
    results: List[Dict[str, Any]] = []
    seen = set()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1400, "height": 1200},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=min(max_seconds, 60) * 1000)
            page.wait_for_timeout(3500)

            # Try common booking-engine card containers first.
            selectors = [
                "[data-testid*='room']",
                "[class*='room']",
                "[class*='Room']",
                "[class*='accommodation']",
                "[class*='Accommodation']",
                "[class*='rate']",
                "article",
                "section",
            ]

            for selector in selectors:
                if time.time() - start > max_seconds:
                    break
                try:
                    loc = page.locator(selector)
                    count = min(loc.count(), 40)
                except Exception:
                    continue

                for i in range(count):
                    if time.time() - start > max_seconds:
                        break
                    try:
                        el = loc.nth(i)
                        txt = el.inner_text(timeout=1800).strip()
                    except Exception:
                        continue
                    if not txt or "$" not in txt:
                        continue
                    if len(txt) < 30:
                        continue

                    price = _extract_price_near_text(txt)
                    if price is None:
                        continue

                    title = _clean_title(txt)
                    key = (title.lower(), int(price))
                    if key in seen:
                        continue
                    seen.add(key)

                    results.append({
                        "title": title,
                        "price": price,
                        "nightly_price": price,
                        "source": "Marenas Official Website",
                        "link": url,
                        "raw_text": txt[:650],
                        "relevance": "Official",
                        "relevance_score": 100,
                        "direct_competitor": True,
                        "qualified_competitor": True,
                        "fit_score": 100,
                        "fit_reasons": "Official Marenas Resort rate",
                    })

            # Fallback: parse full page text if card selectors fail.
            if not results:
                try:
                    full_text = page.locator("body").inner_text(timeout=3000)
                    price = _extract_price_near_text(full_text)
                    if price is not None:
                        results.append({
                            "title": "Marenas official available rate",
                            "price": price,
                            "nightly_price": price,
                            "source": "Marenas Official Website",
                            "link": url,
                            "raw_text": full_text[:650],
                            "relevance": "Official",
                            "relevance_score": 100,
                            "direct_competitor": True,
                            "qualified_competitor": True,
                            "fit_score": 100,
                            "fit_reasons": "Official Marenas Resort rate",
                        })
                except Exception:
                    pass

            context.close()
            browser.close()
    except Exception:
        return []

    # Keep top reasonable results only.
    return results[:12]
