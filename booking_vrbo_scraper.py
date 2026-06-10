# -*- coding: utf-8 -*-
"""Lightweight Booking.com + VRBO scrapers for the Marritta dashboard.
Returns rows using the same structure as competitor_scraper.get_airbnb_prices().

Goal: Sunny Isles Beach competitors with the existing core filters:
6 guests, 2 bedrooms, 2 / 2.5 / 3 baths when the site exposes those specs.
If a site hides bath/spec details, the row is still marked with a lower fit score
only when it is clearly a Sunny Isles vacation rental and has a price.
"""
from playwright.sync_api import sync_playwright
from urllib.parse import quote
from pathlib import Path
import re, time, json

EXCLUDED_HOST_KEYWORDS = ["ritta", "rita", "marritta", "maritta"]
PRICE_RE = re.compile(r"\$\s?([1-9][0-9,]*(?:\.\d{2})?)")


def _norm(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ").replace("·", " ")).strip()


def _is_excluded(text):
    return bool(re.search(r"\b(ritta|rita|marritta|maritta)\b", (text or "").lower()))


def _price_from_text(text):
    text = _norm(text)
    # Prefer explicit total prices for the stay.
    patterns = [
        r"\$\s?([1-9][0-9,]*(?:\.\d{2})?)\s*(?:total|for\s+\d+\s+nights?)",
        r"(?:total|price)\D{0,30}\$\s?([1-9][0-9,]*(?:\.\d{2})?)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                return round(float(m.group(1).replace(",", "")))
            except Exception:
                pass

    vals = []
    for m in PRICE_RE.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
            # Remove tiny taxes/fees and unrealistic totals.
            if 80 <= v <= 50000:
                vals.append(v)
        except Exception:
            pass
    if not vals:
        return None
    # For cards/details, the largest visible number is usually the total stay price.
    return round(max(vals))


def _parse_specs(text):
    t = _norm(text).lower()
    guests = None
    bedrooms = None
    beds = None
    baths = None

    for pat in [r"(\d+)\s+guests?", r"sleeps\s+(\d+)", r"(\d+)\s+people", r"max\s+occupancy\s+(\d+)"]:
        m = re.search(pat, t)
        if m:
            guests = int(m.group(1)); break
    m = re.search(r"(\d+)\s+bedrooms?", t)
    if m: bedrooms = int(m.group(1))
    m = re.search(r"(\d+)\s+beds?\b", t)
    if m: beds = int(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s+baths?", t)
    if m: baths = float(m.group(1))

    if guests or bedrooms or beds or baths:
        parts = []
        if guests: parts.append(f"{guests} guests")
        if bedrooms: parts.append(f"{bedrooms} bedrooms")
        if beds: parts.append(f"{beds} beds")
        if baths: parts.append(f"{baths:g} baths")
        return {
            "guest_count": guests,
            "bedroom_count": bedrooms,
            "bed_count": beds or 0,
            "bathroom_count": baths,
            "specs_line": " · ".join(parts),
        }
    return None


def _matches_core_specs(specs, text):
    if _is_excluded(text):
        return False, "Excluded host/name: Ritta/Rita/Marritta"
    if not specs:
        # Booking/VRBO sometimes hide details until the detail page. Keep clear Sunny Isles vacation rentals
        # but mark them as partial confidence.
        low = (text or "").lower()
        if "sunny isles" in low and any(x in low for x in ["condo", "apartment", "suite", "vacation", "beach"]):
            return True, "Partial source match: Sunny Isles rental, specs not fully visible"
        return False, "Specs not visible"

    g = specs.get("guest_count")
    br = specs.get("bedroom_count")
    ba = specs.get("bathroom_count")

    # Enforce only when visible. If hidden, allow but lower confidence.
    if g is not None and g != 6:
        return False, f"Guests mismatch: {specs.get('specs_line')}"
    if br is not None and br != 2:
        return False, f"Bedrooms mismatch: {specs.get('specs_line')}"
    if ba is not None and float(ba) not in [2.0, 2.5, 3.0]:
        return False, f"Bathrooms mismatch: {specs.get('specs_line')}"

    if (g == 6 and br == 2 and ba in [2.0, 2.5, 3.0]):
        return True, "Core specs match: 6 guests · 2 bedrooms · 2/2.5/3 baths"
    return True, f"Partial core match: {specs.get('specs_line')}"


def _cache_file(source, checkin, checkout):
    d = Path("market_cache")
    d.mkdir(exist_ok=True)
    return d / f"{source}_{checkin}_{checkout}.json"


def _read_cache(source, checkin, checkout, ttl=60*60*3):
    p = _cache_file(source, checkin, checkout)
    try:
        if p.exists() and time.time() - p.stat().st_mtime < ttl:
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _write_cache(source, checkin, checkout, rows):
    try:
        _cache_file(source, checkin, checkout).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _make_row(title, link, text, price, source, specs, reason):
    strong = reason.startswith("Core specs match")
    return {
        "title": title or f"{source} listing",
        "link": link or "",
        "raw_text": _norm(text)[:1200],
        "price": price,
        "relevance": "High" if strong else "Medium",
        "relevance_score": 14 if strong else 8,
        "direct_competitor": True,
        "fit_score": 14 if strong else 8,
        "fit_reasons": f"{source}: {reason}; Ritta/Marritta excluded",
        "penalty_reasons": "" if strong else "Some specs may not be visible on this source",
        "qualified_competitor": strong,
        "guest_count": specs.get("guest_count") if specs else None,
        "bedroom_count": specs.get("bedroom_count") if specs else None,
        "bed_count": specs.get("bed_count") if specs else None,
        "bathroom_count": specs.get("bathroom_count") if specs else None,
        "match_quality": reason,
        "specs_line": specs.get("specs_line") if specs else "Specs not fully visible",
        "source": source,
    }


def _launch_browser(p):
    return p.chromium.launch(
        executable_path="/usr/bin/chromium",
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )


def _accept_cookies_if_present(page):
    """Try common cookie/consent buttons without failing the scraper."""
    labels = [
        "Accept", "Accept all", "Accept All", "I agree", "OK", "Got it",
        "Aceptar", "Aceptar todo", "Acepto", "Estoy de acuerdo",
    ]
    for label in labels:
        try:
            page.get_by_text(label, exact=False).first.click(timeout=2500)
            page.wait_for_timeout(1500)
            return True
        except Exception:
            pass
    return False


def _slow_scroll(page, rounds=7, pixels=2200, pause_ms=1800):
    """Give Booking/VRBO more time to lazy-load cards, prices, and details."""
    for _ in range(rounds):
        try:
            page.mouse.wheel(0, pixels)
            page.wait_for_timeout(pause_ms)
        except Exception:
            break


def _wait_for_body(page, timeout=15000):
    try:
        page.locator("body").wait_for(timeout=timeout)
    except Exception:
        pass


def get_vrbo_prices(checkin, checkout, max_detail_pages=12, max_seconds=180, use_cache=True):
    if use_cache:
        cached = _read_cache("vrbo", checkin, checkout)
        if cached is not None:
            return cached

    rows, seen = [], set()
    start = time.time()
    destination = quote("Sunny Isles Beach, Florida, United States")
    search_url = (
        f"https://www.vrbo.com/search?destination={destination}"
        f"&startDate={checkin}&endDate={checkout}&adults=6&rooms=2"
    )

    with sync_playwright() as p:
        browser = _launch_browser(p)
        context = browser.new_context(locale="en-US", viewport={"width": 1440, "height": 1200}, user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())
        page = context.new_page()
        candidates = []
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            _wait_for_body(page)
            _accept_cookies_if_present(page)
            page.wait_for_timeout(15000)
            _slow_scroll(page, rounds=8, pixels=3000, pause_ms=2000)
            anchors = page.locator("a[href]")
            for i in range(min(anchors.count(), 250)):
                try:
                    href = anchors.nth(i).evaluate("el => el.href") or ""
                    if not href or href in seen:
                        continue
                    if not any(x in href.lower() for x in ["/vacation-rental/", "/p", "h" ]):
                        continue
                    if "vrbo.com" not in href:
                        continue
                    card = anchors.nth(i).evaluate("el => el.closest('div')?.innerText || el.innerText || ''") or ""
                    if "sunny" not in (href + card).lower():
                        continue
                    seen.add(href)
                    candidates.append({"url": href.split("?")[0], "card_text": _norm(card)})
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try: page.close()
            except Exception: pass

        for c in candidates[:max_detail_pages]:
            if time.time() - start > max_seconds:
                break
            d = context.new_page()
            try:
                url = c["url"]
                detail_url = f"{url}?chkin={checkin}&chkout={checkout}&adults=6"
                d.goto(detail_url, wait_until="domcontentloaded", timeout=35000)
                _wait_for_body(d)
                _accept_cookies_if_present(d)
                d.wait_for_timeout(9000)
                _slow_scroll(d, rounds=3, pixels=2200, pause_ms=1200)
                body = _norm(d.locator("body").inner_text(timeout=5000))
                title = _norm(d.locator("h1").first.inner_text(timeout=2500)) if d.locator("h1").count() else "VRBO listing"
                text = c.get("card_text", "") + " " + body
                price = _price_from_text(text)
                specs = _parse_specs(text)
                ok, reason = _matches_core_specs(specs, text)
                if ok and price:
                    rows.append(_make_row(title, url, text, price, "VRBO", specs, reason))
            except Exception:
                pass
            finally:
                try: d.close()
                except Exception: pass
        browser.close()
    if rows and use_cache:
        _write_cache("vrbo", checkin, checkout, rows)
    return rows


def get_booking_prices(checkin, checkout, max_detail_pages=12, max_seconds=180, use_cache=True):
    if use_cache:
        cached = _read_cache("booking", checkin, checkout)
        if cached is not None:
            return cached

    rows = []
    start = time.time()
    search_url = (
        "https://www.booking.com/searchresults.html?"
        f"ss={quote('Sunny Isles Beach, Florida, United States')}"
        f"&checkin={checkin}&checkout={checkout}&group_adults=6&no_rooms=1&group_children=0&selected_currency=USD"
    )

    with sync_playwright() as p:
        browser = _launch_browser(p)
        context = browser.new_context(locale="en-US", viewport={"width": 1440, "height": 1200}, user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())
        page = context.new_page()
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            _wait_for_body(page)
            _accept_cookies_if_present(page)
            page.wait_for_timeout(15000)
            _slow_scroll(page, rounds=8, pixels=3000, pause_ms=2000)

            cards = page.locator("[data-testid='property-card']")
            count = min(cards.count(), max_detail_pages)
            for i in range(count):
                if time.time() - start > max_seconds:
                    break
                try:
                    card = cards.nth(i)
                    text = _norm(card.inner_text(timeout=4000))
                    title = "Booking.com listing"
                    try:
                        title = _norm(card.locator("[data-testid='title']").first.inner_text(timeout=1500))
                    except Exception:
                        lines = [x.strip() for x in text.split(" ") if x.strip()]
                    href = ""
                    try:
                        href = card.locator("a[href]").first.evaluate("el => el.href")
                    except Exception:
                        pass
                    price = _price_from_text(text)
                    specs = _parse_specs(text)

                    # Open details when the card does not expose enough specs/price.
                    if href and (not specs or not price):
                        d = context.new_page()
                        try:
                            d.goto(href, wait_until="domcontentloaded", timeout=35000)
                            _wait_for_body(d)
                            _accept_cookies_if_present(d)
                            d.wait_for_timeout(7000)
                            _slow_scroll(d, rounds=2, pixels=2200, pause_ms=1000)
                            body = _norm(d.locator("body").inner_text(timeout=5000))
                            text = text + " " + body
                            if not price:
                                price = _price_from_text(text)
                            if not specs:
                                specs = _parse_specs(text)
                            if title == "Booking.com listing":
                                try: title = _norm(d.locator("h2, h1").first.inner_text(timeout=1500))
                                except Exception: pass
                        except Exception:
                            pass
                        finally:
                            try: d.close()
                            except Exception: pass

                    ok, reason = _matches_core_specs(specs, text)
                    if ok and price:
                        rows.append(_make_row(title, href, text, price, "Booking.com", specs, reason))
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try: page.close()
            except Exception: pass
        browser.close()

    if rows and use_cache:
        _write_cache("booking", checkin, checkout, rows)
    return rows
