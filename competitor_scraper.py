from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import re
import csv
import time
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, quote

# Host exclusion
EXCLUDED_HOST_KEYWORDS = ["ritta", "rita", "marritta", "maritta"]
EXCLUDED_ROOM_IDS = set()

# Property type filter intentionally disabled for now.
# We rely on: Sunny Isles Airbnb search + 6 guests + 2 bedrooms + 3 baths + host exclusion.
BANNED_PROPERTY_TYPES = []

# Strict Marenas Resort filter
MARENAS_MATCH_TERMS = [
    "marenas",
    "marenas beach",
    "marenas beach resort",
    "marenas resort",
    "18683 collins",
    "18683 collins ave",
    "18683 collins avenue",
]

def _is_marenas_listing(text):
    low = _norm(text).lower()
    return any(term in low for term in MARENAS_MATCH_TERMS)

# Sunny Isles Beach filter
SUNNY_ISLES_TERMS = [
    "sunny isles",
    "sunny isles beach",
    "sunny isles beach, fl",
    "sunny isles beach florida",
]

def _is_sunny_isles_listing(text):
    low = _norm(text).lower()
    return any(term in low for term in SUNNY_ISLES_TERMS)

PRICE_RE = re.compile(r"\$\s?([1-9][0-9,]*(?:\.\d{2})?)")
ROOM_ID_RE = re.compile(r"/rooms/(\d+)")
BAD_TITLE_SNIPPETS = [
    "skip to content",
    "start your search",
    "new new experiences",
    "new new services",
    "homes new new",
]


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


def _first_reasonable_price(text):
    text = _norm(text or "")

    # 1. Intento A: Busca precio atado a "noches" (Ej: "$7,738 for 10 nights")
    m1 = re.search(
        r"\$\s?([1-9][0-9,]*(?:\.\d{2})?)\s+for\s+\d+\s+nights?",
        text,
        re.IGNORECASE
    )
    if m1:
        return round(float(m1.group(1).replace(",", "")))

    # 2. Intento B: Busca precio desglosado (Ej: "10 nights x $773 = $7,737")
    m2 = re.search(
        r"\d+\s+nights?\s*x\s*(?:.*?)\$\s?([1-9][0-9,]*(?:\.\d{2})?)",
        text,
        re.IGNORECASE
    )
    if m2:
        return round(float(m2.group(1).replace(",", "")))

    # 3. PLAN C (El salvavidas): Extraer el precio total por fuerza bruta.
    # Recoge todos los precios mayores a $400 y devuelve el más alto (que siempre es el total).
    values = []
    for m in PRICE_RE.finditer(text):
        val = float(m.group(1).replace(",", ""))
        if 400 <= val <= 50000:
            values.append(val)

    if values:
        return round(max(values))

    return None

def _extract_booking_panel_price(page):
    # Selectores específicos del panel de reserva o el botón flotante en móvil
    selectors = [
        "[data-section-id='BOOK_IT_SIDEBAR']", # Busca dentro de la caja lateral completa
        "[data-testid='price-item-total']",    # El total desglosado
        "[data-testid='book-it-default-price']",
        "div[data-testid='book-it-default']"
    ]

    for selector in selectors:
        try:
            elements = page.locator(selector)
            if elements.count() > 0:
                # Leemos el texto de ese cuadro en específico
                text = elements.first.inner_text()
                
                # Buscamos el total explícito primero (Ej: "$1,250 Total")
                total_match = re.search(r"Total.*?\$\s?([0-9,]+(?:\.\d{2})?)", text, re.IGNORECASE)
                if total_match:
                    return round(float(total_match.group(1).replace(",", "")))
                
                # Si no dice "Total", agarramos el primer precio grande que aparezca en la caja
                m = re.search(r"\$\s?([0-9,]+(?:\.\d{2})?)", text)
                if m:
                    return round(float(m.group(1).replace(",", "")))
        except:
            continue

    return None


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
        li_texts = page.locator("ol li").all_inner_texts(timeout=6000)
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
        ol_texts = page.locator("ol").all_inner_texts(timeout=6000)
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
        body = page.locator("body").inner_text(timeout=6000)
        return _parse_specs_from_text(body)
    except Exception:
        return None


def _extract_title(page, fallback="Airbnb Listing"):
    # page.title() is usually cleaner than the body text when Airbnb renders weird accessibility text.
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
            text = page.locator(selector).first.inner_text(timeout=2500)
            clean = _norm(text)
            if clean and len(clean) > 3 and not _is_bad_title(clean):
                return clean
        except Exception:
            pass

    clean_fallback = _norm(fallback)
    return clean_fallback if clean_fallback and not _is_bad_title(clean_fallback) else "Airbnb Listing"


def _is_bad_title(title):
    low = (title or "").lower()
    return any(s in low for s in BAD_TITLE_SNIPPETS)


def _is_excluded_host(text):
    low = (text or "").lower()
    # Match names as words so we don't accidentally match random substrings.
    return bool(re.search(r"\b(ritta|rita|marritta|maritta)\b", low))


def _extract_full_detail_text(page):
    """Scrolls the detail page to force-load host text and pricing text."""
    parts = []
    try:
        parts.append(page.locator("body").inner_text(timeout=4000))
    except Exception:
        pass

    for y in [1800, 5000, 8500]:
        try:
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(250)
            parts.append(page.locator("body").inner_text(timeout=3000))
        except Exception:
            pass

    return _norm(" ".join(parts))


def _build_search_urls(checkin, checkout):
    base = "https://www.airbnb.com/s/Sunny-Isles-Beach--Florida--United-States/homes"
    common = (
        f"checkin={checkin}&checkout={checkout}&adults=6"
        "&min_bedrooms=2"
        "&min_bathrooms=2"
        "&room_types%5B%5D=Entire%20home%2Fapt"
    )

    # Balanced search: broad enough to find competitors in Sunny Isles,
    # but avoids known unrelated buildings such as Trump / Ocean Reserve.
    queries = [
        "Sunny Isles Beach beachfront condo",
        "Sunny Isles Beach condo Collins Avenue",
        "Marenas Beach Resort",
        "Marenas Sunny Isles",
        "18683 Collins Ave",
    ]

    urls = []

    for q in queries:
        urls.append(f"{base}?{common}&query={quote(q)}")

    return urls

def _collect_room_candidates(page):
    """Collect room URLs plus card-level text/price to avoid $0 competitors."""
    candidates = []
    seen = set()

    try:
        anchors = page.locator("a[href*='/rooms/']")
        count = anchors.count()
        for i in range(count):
            try:
                a = anchors.nth(i)
                href = a.evaluate("el => el.href")
                clean = _clean_url(href)
                if not clean or clean in seen:
                    continue
                seen.add(clean)

                card_text = ""
                # Try to read the closest listing card text, not the whole page.
                for js in [
                    "el => el.closest('[itemprop=\\\"itemListElement\\\"]')?.innerText",
                    "el => el.closest('div')?.innerText",
                    "el => el.innerText",
                ]:
                    try:
                        card_text = a.evaluate(js) or ""
                        if card_text and len(card_text.strip()) > 20:
                            break
                    except Exception:
                        pass

                card_text = _norm(card_text)
                candidates.append({
                    "url": clean,
                    "card_text": card_text,
                    "card_price": _first_reasonable_price(card_text),
                })
            except Exception:
                continue
    except Exception:
        pass

    # Raw HTML fallback.
    try:
        html = page.content()
        for href in re.findall(r'https://www\.airbnb\.com/rooms/[0-9]+', html):
            clean = _clean_url(href)
            if clean and clean not in seen:
                seen.add(clean)
                candidates.append({"url": clean, "card_text": "", "card_price": None})
    except Exception:
        pass

    return candidates


def _qualified(specs, combined_text, title, url, price):
    rid = _room_id(url)
    if rid in EXCLUDED_ROOM_IDS:
        return False, "Excluded manual room ID", True

    ritta_detected = _is_excluded_host(" ".join([combined_text or "", title or "", url or ""]))
    if ritta_detected:
        return False, "Excluded host: Ritta/Rita/Marritta", True

    if _is_bad_title(title):
        return False, "Bad/non-listing title", False

    location_text = " ".join([combined_text or "", title or "", url or ""])
    marenas_confirmed = _is_marenas_listing(location_text)
    sunny_isles_confirmed = _is_sunny_isles_listing(location_text)

    # User requirement: show only competitors that can be confirmed as Sunny Isles Beach.
    # Marenas is allowed because it is located in Sunny Isles Beach.
    if not (sunny_isles_confirmed or marenas_confirmed):
        return False, "Not confirmed as Sunny Isles Beach", False

    if not specs:
        return False, "Specs not found", False

    if not (
        specs.get("guest_count") == 6 and
        specs.get("bedroom_count") == 2 and
        float(specs.get("bathroom_count")) in [2.0, 2.5, 3.0]
    ):
        return False, f"Specs mismatch: {specs.get('specs_line', specs)}", False

    if not price or price <= 0:
        return False, "Price not found", False

    if marenas_confirmed:
        return True, "Confirmed Marenas + core specs: 6 guests · 2 bedrooms · 2/2.5/3 baths", False

    return True, "Confirmed Sunny Isles Beach competitor + core specs: 6 guests · 2 bedrooms · 2/2.5/3 baths", False

def _cache_file(checkin, checkout):
    cache_dir = Path("airbnb_cache")
    cache_dir.mkdir(exist_ok=True)
    safe = re.sub(r"[^0-9A-Za-z_-]+", "_", f"{checkin}_{checkout}")
    return cache_dir / f"airbnb_{safe}.json"

def _read_cache(checkin, checkout, ttl_seconds=60*60*3):
    path = _cache_file(checkin, checkout)
    try:
        if path.exists() and time.time() - path.stat().st_mtime < ttl_seconds:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None

def _write_cache(checkin, checkout, listings):
    try:
        _cache_file(checkin, checkout).write_text(json.dumps(listings, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def get_airbnb_prices(checkin, checkout, max_detail_pages=36, debug=True, max_seconds=300, use_cache=True):
    if use_cache:
        cached = _read_cache(checkin, checkout)
        if cached is not None:
            return cached

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
        for idx, url in enumerate(_build_search_urls(checkin, checkout), start=1):
            if time.time() - start_time > max_seconds:
                break

            page = context.new_page()
            try:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=18000)
                except Exception:
                    page.goto(url, wait_until="domcontentloaded", timeout=18000)

                page.wait_for_timeout(800)
                for _ in range(4):
                    page.mouse.wheel(0, 4500)
                    page.wait_for_timeout(350)

                if debug:
                    try:
                        (debug_dir / f"search_{idx}.html").write_text(page.content(), encoding="utf-8")
                        (debug_dir / f"search_{idx}.txt").write_text(
                            page.locator("body").inner_text(timeout=5000), encoding="utf-8"
                        )
                    except Exception:
                        pass

                for c in _collect_room_candidates(page):
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

        print("TOTAL ROOM CANDIDATES FOUND:", len(search_candidates))
        
        for n, candidate in enumerate(search_candidates[:max_detail_pages], start=1):
            if time.time() - start_time > max_seconds:
                break

            link = candidate["url"]
            card_text = candidate.get("card_text", "")
            card_price = candidate.get("card_price")

            # Fast pre-filter: if the search card already clearly shows specs
            # and they do not match, skip opening the detail page.
            card_specs = _parse_specs_from_text(card_text)
            if card_specs and not (
                card_specs.get("guest_count") == 6 and
                card_specs.get("bedroom_count") == 2 and
                float(card_specs.get("bathroom_count")) in [2.0, 2.5, 3.0]
            ):
                debug_rows.append({
                    "n": n,
                    "url": link,
                    "title": _norm(card_text[:90]) or "Airbnb Listing",
                    "status": "skipped_card",
                    "specs_found": card_specs.get("specs_line", ""),
                    "qualified": False,
                    "reason": f"Card specs mismatch: {card_specs.get('specs_line')}",
                    "price": card_price or "",
                    "ritta_detected": _is_excluded_host(card_text),
                    "card_price": card_price or "",
                })
                continue

            detail_page = context.new_page()
            status = "opened"
            specs = None
            title = "Airbnb Listing"
            price = card_price
            body = ""
            ritta_detected = False

            try:
                # ✅ FIX: incluir fechas en la URL del listing para que Airbnb
                # pre-calcule el precio total correcto para esas noches.
                link_with_dates = f"{link}?checkin={checkin}&checkout={checkout}&adults=6"
                try:
                    detail_page.goto(link_with_dates, wait_until="domcontentloaded", timeout=10000)
                except Exception:
                    detail_page.goto(link_with_dates, wait_until="domcontentloaded", timeout=10000)

                # ✅ FIX: esperar más para que carguen los specs y el panel de precios
                detail_page.wait_for_timeout(1200)
                specs = _extract_airbnb_specs_from_detail_page(detail_page)
                body = _extract_full_detail_text(detail_page)
                title = _extract_title(detail_page, fallback=card_text[:90] if card_text else "Airbnb Listing")

                panel_price = _extract_booking_panel_price(detail_page)
                print(
                    "PRICE DEBUG:",
                    title,
                    "| panel:",
                    panel_price,
                    "| card:",
                    card_price
                )

                if panel_price:
                    price = panel_price
                else:
                    detail_price = _first_reasonable_price(body)

                    if detail_price:
                        price = detail_price

                ritta_detected = _is_excluded_host(" ".join([body, card_text, title, link]))

                if debug and n <= 10:
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
                "title": title,
                "status": status,
                "specs_found": specs.get("specs_line") if specs else "",
                "qualified": ok,
                "reason": reason,
                "price": price or "",
                "ritta_detected": ritta_detected,
                "card_price": card_price or "",
            })

            if ok:
                listings.append({
                    "title": title,
                    "link": link,
                    "raw_text": body[:1200],
                    "price": price,
                    "relevance": "High",
                    "relevance_score": 15,
                    "direct_competitor": True,
                    "fit_score": 15,
                    "fit_reasons": reason + "; Ritta/Marritta excluded",
                    "penalty_reasons": "",
                    "qualified_competitor": True,
                    "guest_count": specs["guest_count"],
                    "bedroom_count": specs["bedroom_count"],
                    "bed_count": specs["bed_count"],
                    "bathroom_count": specs["bathroom_count"],
                    "match_quality": reason,
                    "specs_line": specs["specs_line"],
                })

                # Keep collecting qualified Sunny Isles Beach competitors until the time/detail budget ends.
                # No artificial cap here; app.py controls max_detail_pages and max_seconds.

        browser.close()

    if debug:
        try:
            with open(debug_dir / "debug_report.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "n", "url", "title", "status", "specs_found", "qualified", "reason",
                        "price", "ritta_detected", "card_price",
                    ],
                )
                writer.writeheader()
                writer.writerows(debug_rows)
        except Exception:
            pass

    if use_cache and listings:
        _write_cache(checkin, checkout, listings)

    return listings
