from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import re
import csv
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, quote
from datetime import datetime

# =========================
# CONFIG
# =========================

# Strong host exclusion. If one of your own listings still appears, add its room ID below.
EXCLUDED_HOST_KEYWORDS = ["ritta", "rita", "marritta", "maritta"]
EXCLUDED_ROOM_IDS = set()
# Example:
# EXCLUDED_ROOM_IDS = {"32068829", "615927273042282673"}

# Property type filter intentionally disabled for now.
# Reason: Airbnb body text can contain words like "home" or "house rules" even for condos/apartments.
BANNED_PROPERTY_TYPES = []

ROOM_ID_RE = re.compile(r"/rooms/(\d+)")
PRICE_RE = re.compile(r"\$\s?([1-9][0-9,]{1,6})(?!\d)")
BAD_TITLE_SNIPPETS = [
    "skip to content",
    "start your search",
    "new new experiences",
    "new new services",
    "homes new new",
]

# =========================
# BASIC HELPERS
# =========================

def _nights(checkin, checkout):
    try:
        d1 = datetime.strptime(str(checkin), "%Y-%m-%d").date()
        d2 = datetime.strptime(str(checkout), "%Y-%m-%d").date()
        return max((d2 - d1).days, 1)
    except Exception:
        return 1


def _clean_url(url):
    if not url:
        return None
    parts = urlsplit(url)
    if "/rooms/" not in parts.path:
        return None
    return urlunsplit((parts.scheme or "https", parts.netloc or "www.airbnb.com", parts.path, "", ""))


def _room_id(url):
    m = ROOM_ID_RE.search(url or "")
    return m.group(1) if m else ""


def _norm(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ").replace("·", " ")).strip()


def _is_bad_title(title):
    low = (title or "").lower()
    return any(s in low for s in BAD_TITLE_SNIPPETS)


def _is_excluded_host(text):
    low = (text or "").lower()
    return bool(re.search(r"\b(ritta|rita|marritta|maritta)\b", low))


def _money_to_int(raw):
    try:
        return int(str(raw).replace(",", "").strip())
    except Exception:
        return None


# =========================
# PRICE PARSING
# =========================

def _extract_price_candidates(text):
    """Return list of dicts: value + nearby text window."""
    text = text or ""
    low = text.lower()
    out = []
    for m in PRICE_RE.finditer(text):
        val = _money_to_int(m.group(1))
        if val is None or not (50 <= val <= 50000):
            continue
        start = max(0, m.start() - 90)
        end = min(len(text), m.end() + 140)
        out.append({"value": val, "window": low[start:end]})
    return out


def _best_total_price_from_text(text, nights):
    """
    Returns TOTAL STAY PRICE because app.py divides listing['price'] by nights.
    Airbnb may show:
    - "$250 night" / "$250 per night" => convert to total = 250 * nights
    - "$2,100 total before taxes" => use as total
    - "$2,100 before taxes" => use as total
    """
    candidates = _extract_price_candidates(text)
    if not candidates:
        return None, None, "no_price"

    # 1) Prefer explicit total/before taxes/stay price.
    total_candidates = []
    for c in candidates:
        w = c["window"]
        val = c["value"]
        if any(h in w for h in [" total", "before taxes", "after taxes", "for ", "stay"]):
            # Total stay should usually be > nightly. Avoid tiny fees.
            if val >= 150:
                total_candidates.append(val)
    if total_candidates:
        total = min(total_candidates)
        nightly = round(total / nights) if nights else total
        return total, nightly, "explicit_total"

    # 2) Next prefer nightly prices near night/per night.
    nightly_candidates = []
    for c in candidates:
        w = c["window"]
        val = c["value"]
        if any(h in w for h in [" night", "per night", "/night", "nightly"]):
            if 80 <= val <= 5000:
                nightly_candidates.append(val)
    if nightly_candidates:
        nightly = min(nightly_candidates)
        return nightly * nights, nightly, "nightly_x_nights"

    # 3) Fallback: if values look like nightly prices, use lowest * nights.
    reasonable_nightly = [c["value"] for c in candidates if 80 <= c["value"] <= 3000]
    if reasonable_nightly:
        nightly = min(reasonable_nightly)
        return nightly * nights, nightly, "fallback_lowest_x_nights"

    return None, None, "no_usable_price"


# =========================
# SPECS PARSING
# =========================

def _parse_specs_from_text(text):
    """Flexible parser for strings like '6 guests 2 bedrooms 3 beds 3 baths'."""
    t = _norm(text).lower()
    if not t:
        return None

    g = re.search(r"(\d+)\s+guests?", t)
    br = re.search(r"(\d+)\s+bedrooms?", t)
    beds = re.search(r"(\d+)\s+beds?\b", t)  # does not capture bedroom
    ba = re.search(r"(\d+(?:\.\d+)?)\s+baths?", t)

    if not (g and br and beds and ba):
        return None

    baths = float(ba.group(1))
    return {
        "guest_count": int(g.group(1)),
        "bedroom_count": int(br.group(1)),
        "bed_count": int(beds.group(1)),
        "bathroom_count": int(baths) if baths.is_integer() else baths,
        "specs_line": f"{g.group(1)} guests · {br.group(1)} bedrooms · {beds.group(1)} beds · {ba.group(1)} baths",
    }


def _extract_airbnb_specs_from_detail_page(page):
    """Read Airbnb's official headline specs from <ol><li> first, then fallback to body."""
    try:
        li_texts = page.locator("ol li").all_inner_texts(timeout=5000)
    except TypeError:
        try:
            li_texts = page.locator("ol li").all_inner_texts()
        except Exception:
            li_texts = []
    except Exception:
        li_texts = []

    items = [_norm(x).replace("·", "").strip() for x in li_texts if _norm(x)]
    for i in range(max(0, len(items) - 3)):
        block_items = items[i:i + 4]
        joined = " ".join(block_items)
        low = joined.lower()
        if all(word in low for word in ["guest", "bedroom", "bed", "bath"]):
            specs = _parse_specs_from_text(joined)
            if specs:
                specs["specs_line"] = " · ".join(block_items)
                return specs

    try:
        ol_texts = page.locator("ol").all_inner_texts(timeout=5000)
    except TypeError:
        try:
            ol_texts = page.locator("ol").all_inner_texts()
        except Exception:
            ol_texts = []
    except Exception:
        ol_texts = []

    for text in ol_texts:
        low = _norm(text).lower()
        if all(word in low for word in ["guest", "bedroom", "bed", "bath"]):
            specs = _parse_specs_from_text(text)
            if specs:
                return specs

    try:
        body = page.locator("body").inner_text(timeout=5000)
        return _parse_specs_from_text(body)
    except Exception:
        return None


# =========================
# TITLE / TEXT
# =========================

def _extract_title(page, fallback="Airbnb Listing"):
    try:
        doc_title = page.title()
        if doc_title:
            clean = _norm(doc_title.replace(" - Airbnb", ""))
            if clean and not _is_bad_title(clean):
                return clean
    except Exception:
        pass

    for selector in ["h1", "[data-testid='listing-card-title']"]:
        try:
            text = page.locator(selector).first.inner_text(timeout=2200)
            clean = _norm(text)
            if clean and len(clean) > 3 and not _is_bad_title(clean):
                return clean
        except Exception:
            pass

    clean_fallback = _norm(fallback)
    return clean_fallback if clean_fallback and not _is_bad_title(clean_fallback) else "Airbnb Listing"


def _extract_full_detail_text(page):
    """Scrolls the detail page to force-load host and price text."""
    parts = []
    try:
        parts.append(page.locator("body").inner_text(timeout=3500))
    except Exception:
        pass

    for y in [1200, 3000, 5500, 8500, 12000]:
        try:
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(350)
            parts.append(page.locator("body").inner_text(timeout=2500))
        except Exception:
            pass

    return _norm(" ".join(parts))


# =========================
# SEARCH URLS / CANDIDATES
# =========================

def _build_search_urls(checkin, checkout):
    base = "https://www.airbnb.com/s/Sunny-Isles-Beach--Florida--United-States/homes"
    common = (
        f"checkin={checkin}&checkout={checkout}&adults=6&min_bedrooms=2&min_bathrooms=3"
        "&room_types%5B%5D=Entire%20home%2Fapt"
    )

    # Keep a no-query search first. It usually returns more real Airbnb candidates than very specific text queries.
    queries = [
        "",
        "Sunny Isles Beach 2 bedroom 3 bath",
        "Sunny Isles Beach beachfront condo 2 bedroom 3 bath",
        "Sunny Isles Beach oceanfront condo 2 bedroom 3 bath",
        "Sunny Isles Beach Collins 2 bedroom 3 bath",
        "Marenas Sunny Isles 2 bedroom 3 bath",
        "Sunny Isles Beach resort condo 2 bedroom 3 bath",
    ]

    # Airbnb often paginates with items_offset. This helps collect more than the first 10-18 listings.
    offsets = [0, 18, 36]

    urls = []
    for q in queries:
        for off in offsets:
            extra = f"&items_offset={off}" if off else ""
            query_part = f"&query={quote(q)}" if q else ""
            urls.append(f"{base}?{common}{query_part}{extra}")
    return urls


def _collect_room_candidates(page, nights):
    """Collect room URLs plus card-level text/price."""
    candidates = []
    seen = set()

    js = """
    els => els.map(a => {
        let best = '';
        let node = a;
        for (let i = 0; i < 10 && node; i++) {
            const txt = node.innerText || '';
            if (txt.length > best.length && txt.length < 3500) best = txt;
            node = node.parentElement;
        }
        return {href: a.href, text: best};
    })
    """

    try:
        rows = page.locator("a[href*='/rooms/']").evaluate_all(js)
        for row in rows:
            clean = _clean_url(row.get("href"))
            if not clean or clean in seen:
                continue
            seen.add(clean)
            card_text = _norm(row.get("text") or "")
            total, nightly, method = _best_total_price_from_text(card_text, nights)
            candidates.append({
                "url": clean,
                "card_text": card_text,
                "card_price": total,
                "card_nightly_price": nightly,
                "card_price_method": method,
            })
    except Exception:
        pass

    try:
        html = page.content()
        for href in re.findall(r'https://www\.airbnb\.com/rooms/[0-9]+', html):
            clean = _clean_url(href)
            if clean and clean not in seen:
                seen.add(clean)
                candidates.append({
                    "url": clean,
                    "card_text": "",
                    "card_price": None,
                    "card_nightly_price": None,
                    "card_price_method": "raw_html_no_card",
                })
    except Exception:
        pass

    return candidates


# =========================
# QUALIFICATION
# =========================

def _qualified(specs, combined_text, title, url, price):
    rid = _room_id(url)
    if rid in EXCLUDED_ROOM_IDS:
        return False, "Excluded manual room ID", True

    ritta_detected = _is_excluded_host(" ".join([combined_text or "", title or "", url or ""]))
    if ritta_detected:
        return False, "Excluded host: Ritta/Rita/Marritta", True

    if _is_bad_title(title):
        return False, "Bad/non-listing title", False

    if not specs:
        return False, "Specs not found", False

    # Core competitor filter: bed count can vary.
    if not (
        specs.get("guest_count") == 6 and
        specs.get("bedroom_count") == 2 and
        float(specs.get("bathroom_count")) == 3.0
    ):
        return False, f"Specs mismatch: {specs.get('specs_line', specs)}", False

    if not price or price <= 0:
        return False, "Price not found", False

    return True, "Core match: 6 guests · 2 bedrooms · 3 baths; bed count allowed to vary", False


# =========================
# MAIN FUNCTION
# =========================

def get_airbnb_prices(checkin, checkout, max_detail_pages=60, debug=True, max_seconds=120):
    """
    Returns listings with listing['price'] as TOTAL STAY PRICE.
    app.py divides listing['price'] by nights, so this must be a total, not nightly.
    """
    nights = _nights(checkin, checkout)
    listings = []
    debug_rows = []
    seen = set()
    start_time = time.time()

    debug_dir = Path("airbnb_debug")
    if debug:
        debug_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 1200},
        )

        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["image", "media", "font"]
            else route.continue_(),
        )

        search_candidates = []

        # 1) Collect candidates from multiple searches and offsets.
        for idx, url in enumerate(_build_search_urls(checkin, checkout), start=1):
            if time.time() - start_time > max_seconds:
                break
            if len(search_candidates) >= 90:
                break

            page = context.new_page()
            try:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=17000)
                except Exception:
                    page.goto(url, wait_until="domcontentloaded", timeout=17000)

                page.wait_for_timeout(1200)

                # Scroll enough to trigger lazy loaded cards, but keep bounded.
                for _ in range(8):
                    page.mouse.wheel(0, 3200)
                    page.wait_for_timeout(350)

                if debug and idx <= 8:
                    try:
                        (debug_dir / f"search_{idx}.html").write_text(page.content(), encoding="utf-8")
                        (debug_dir / f"search_{idx}.txt").write_text(
                            page.locator("body").inner_text(timeout=4500), encoding="utf-8"
                        )
                    except Exception:
                        pass

                for c in _collect_room_candidates(page, nights):
                    if c["url"] not in seen:
                        seen.add(c["url"])
                        search_candidates.append(c)
            except Exception:
                pass
            finally:
                try:
                    page.close()
                except Exception:
                    pass

        # 2) Open detail pages only after collecting all candidates.
        for n, candidate in enumerate(search_candidates[:max_detail_pages], start=1):
            if time.time() - start_time > max_seconds:
                break

            link = candidate["url"]
            card_text = candidate.get("card_text", "")
            card_price = candidate.get("card_price")
            card_nightly = candidate.get("card_nightly_price")
            card_price_method = candidate.get("card_price_method", "")

            detail_page = context.new_page()
            status = "opened"
            specs = None
            title = "Airbnb Listing"
            price = card_price
            nightly_price = card_nightly
            price_method = card_price_method
            body = ""
            ritta_detected = False

            try:
                try:
                    detail_page.goto(link, wait_until="domcontentloaded", timeout=14000)
                except Exception:
                    detail_page.goto(link, wait_until="domcontentloaded", timeout=14000)

                detail_page.wait_for_timeout(900)
                specs = _extract_airbnb_specs_from_detail_page(detail_page)
                body = _extract_full_detail_text(detail_page)
                title = _extract_title(detail_page, fallback=card_text[:140] if card_text else "Airbnb Listing")

                detail_total, detail_nightly, detail_method = _best_total_price_from_text(body, nights)
                # Prefer explicit detail total. Otherwise keep card price if it exists.
                if detail_total and (detail_method == "explicit_total" or not price):
                    price = detail_total
                    nightly_price = detail_nightly
                    price_method = f"detail_{detail_method}"

                ritta_detected = _is_excluded_host(" ".join([body, card_text, title, link]))

                if debug and n <= 15:
                    (debug_dir / f"detail_{n}.html").write_text(detail_page.content(), encoding="utf-8")
                    (debug_dir / f"detail_{n}.txt").write_text(body, encoding="utf-8")
            except PlaywrightTimeoutError:
                status = "timeout"
            except Exception as e:
                status = f"error: {type(e).__name__}"
            finally:
                try:
                    detail_page.close()
                except Exception:
                    pass

            combined_text = " ".join([body, card_text])
            ok, reason, forced_ritta = _qualified(specs, combined_text, title, link, price)
            ritta_detected = ritta_detected or forced_ritta

            debug_rows.append({
                "n": n,
                "url": link,
                "room_id": _room_id(link),
                "title": title,
                "status": status,
                "specs_found": specs.get("specs_line") if specs else "",
                "qualified": ok,
                "reason": reason,
                "price_total": price or "",
                "nightly_price": nightly_price or "",
                "price_method": price_method,
                "ritta_detected": ritta_detected,
                "card_price_total": card_price or "",
                "card_nightly_price": card_nightly or "",
                "candidates_found_total": len(search_candidates),
            })

            if ok:
                listings.append({
                    "title": title,
                    "link": link,
                    "raw_text": body[:1200],
                    # IMPORTANT: total stay price; app.py will divide by nights.
                    "price": price,
                    "nightly_price": nightly_price,
                    "price_method": price_method,
                    "relevance": "High",
                    "relevance_score": 15,
                    "direct_competitor": True,
                    "fit_score": 15,
                    "fit_reasons": "Matches 6 guests · 2 bedrooms · 3 baths; bed count allowed to vary; Sunny Isles search; Ritta/Marritta excluded",
                    "penalty_reasons": "",
                    "qualified_competitor": True,
                    "guest_count": specs["guest_count"],
                    "bedroom_count": specs["bedroom_count"],
                    "bed_count": specs["bed_count"],
                    "bathroom_count": specs["bathroom_count"],
                    "match_quality": "Core Airbnb specs match",
                    "specs_line": specs["specs_line"],
                })

                if len(listings) >= 15:
                    break

        browser.close()

    if debug:
        try:
            with open(debug_dir / "debug_report.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "n", "url", "room_id", "title", "status", "specs_found", "qualified", "reason",
                        "price_total", "nightly_price", "price_method", "ritta_detected",
                        "card_price_total", "card_nightly_price", "candidates_found_total",
                    ],
                )
                writer.writeheader()
                writer.writerows(debug_rows)
        except Exception:
            pass

    return listings
