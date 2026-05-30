from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import re
import csv
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, quote

EXCLUDED_HOSTS = ["hosted by ritta", "hosted by rita", "hosted by marritta", "hosted by maritta"]
BANNED_PROPERTY_TYPES = ["entire home", "home in", "house", "villa", "townhouse", "private room", "shared room"]
LOCATION_SIGNALS = [
    "sunny isles", "sunny isles beach", "collins", "marenas", "sole", "solé",
    "trump international", "ocean reserve", "doubletree", "marco polo", "newport", "hyde",
    "beachfront", "oceanfront", "ocean view", "beach access", "private beach"
]

PRICE_RE = re.compile(r"\$\s?([1-9][0-9]{2,4})(?!\d)")


def _clean_url(url):
    if not url:
        return None
    parts = urlsplit(url)
    if "/rooms/" not in parts.path:
        return None
    return urlunsplit((parts.scheme or "https", parts.netloc or "www.airbnb.com", parts.path, "", ""))


def _norm(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ").replace("·", " ")).strip()


def _first_reasonable_price(text):
    values = []
    for m in PRICE_RE.finditer(text or ""):
        val = int(m.group(1).replace(",", ""))
        if 100 <= val <= 5000:
            values.append(val)
    if not values:
        return None
    # Airbnb detail pages often show lots of totals. For nightly pricing, the first few $ values
    # are usually the nightly/search card values. Use the smallest reasonable value as fallback.
    return min(values)


def _parse_specs_from_text(text):
    """Flexible parser for '6 guests 2 bedrooms 2 beds 3 baths'."""
    t = _norm(text).lower()
    if not t:
        return None

    g = re.search(r"(\d+)\s+guests?", t)
    br = re.search(r"(\d+)\s+bedrooms?", t)
    # Important: use singular/plural bed but do NOT capture bedroom.
    beds = re.search(r"(\d+)\s+beds?\b", t)
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
    """
    Airbnb renders the official headline as <ol><li> items:
    6 guests / 2 bedrooms / 2 beds / 3 baths.
    This reads the official list first, then falls back to body text.
    """
    # 1) Best target based on the HTML you inspected: consecutive OL LI items.
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

    # Look for 4 consecutive items containing guest/bedroom/bed/bath.
    for i in range(max(0, len(items) - 3)):
        block_items = items[i:i+4]
        joined = " ".join(block_items)
        low = joined.lower()
        if all(word in low for word in ["guest", "bedroom", "bed", "bath"]):
            specs = _parse_specs_from_text(joined)
            if specs:
                specs["specs_line"] = " · ".join(block_items)
                return specs

    # 2) Sometimes the entire OL inner_text is easier.
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

    # 3) Fallback: body text.
    try:
        body = page.locator("body").inner_text(timeout=6000)
        return _parse_specs_from_text(body)
    except Exception:
        return None


def _extract_title(page, fallback="Airbnb Listing"):
    for selector in ["h1", "[data-testid='listing-card-title']", "title"]:
        try:
            text = page.locator(selector).first.inner_text(timeout=2500)
            if text and len(text.strip()) > 3:
                return _norm(text)
        except Exception:
            pass
    try:
        title = page.title()
        if title:
            return _norm(title.replace(" - Airbnb", ""))
    except Exception:
        pass
    return fallback


def _build_search_urls(checkin, checkout):
    base = "https://www.airbnb.com/s/Sunny-Isles-Beach--Florida--United-States/homes"
    common = (
        f"checkin={checkin}&checkout={checkout}&adults=6&min_bedrooms=2&min_bathrooms=3"
        "&room_types%5B%5D=Entire%20home%2Fapt"
    )
    queries = [
        "Sunny Isles Beach Marenas resort 6 guests 2 bedrooms 2 beds 3 baths",
        "Sunny Isles Beach Collins ocean view 2 bedroom 3 bath",
        "Marenas Sunny Isles 2 bedroom 3 bath",
    ]
    return [f"{base}?{common}&query={quote(q)}" for q in queries]


def _collect_room_links(page):
    links = []

    # Main robust method: every Airbnb room link on the search page.
    try:
        hrefs = page.locator("a[href*='/rooms/']").evaluate_all("els => els.map(a => a.href)")
        for href in hrefs:
            clean = _clean_url(href)
            if clean and clean not in links:
                links.append(clean)
    except Exception:
        pass

    # Fallback from raw HTML.
    try:
        html = page.content()
        for href in re.findall(r'https://www\.airbnb\.com/rooms/[0-9]+', html):
            clean = _clean_url(href)
            if clean and clean not in links:
                links.append(clean)
    except Exception:
        pass

    return links


def _qualified(specs, full_text):
    text = (full_text or "").lower()

    if any(host in text for host in EXCLUDED_HOSTS):
        return False, "Excluded host: Ritta/Rita/Marritta"
    if any(bad in text for bad in BANNED_PROPERTY_TYPES):
        return False, "Excluded property type"
    if not specs:
        return False, "Specs not found"
    if not (
        specs.get("guest_count") == 6 and
        specs.get("bedroom_count") == 2 and
        specs.get("bed_count") == 2 and
        float(specs.get("bathroom_count")) == 3.0
    ):
        return False, f"Specs mismatch: {specs.get('specs_line', specs)}"

    # Since the search URL itself is Sunny Isles Beach, exact specs are the hard filter.
    # Location signals are helpful, not mandatory, because Airbnb detail text can hide location.
    return True, "Exact match"


def get_airbnb_prices(checkin, checkout, max_detail_pages=12, debug=True):
    listings = []
    debug_rows = []
    seen = set()
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

        # Do NOT block stylesheets for now. Airbnb sometimes needs CSS/JS timing for rendered text.
        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["image", "media", "font"]
            else route.continue_(),
        )

        search_links = []
        for idx, url in enumerate(_build_search_urls(checkin, checkout), start=1):
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=18000)
            except Exception:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=18000)
                except Exception:
                    pass
            page.wait_for_timeout(1200)
            for _ in range(2):
                page.mouse.wheel(0, 3500)
                page.wait_for_timeout(500)

            if debug:
                try:
                    (debug_dir / f"search_{idx}.html").write_text(page.content(), encoding="utf-8")
                    (debug_dir / f"search_{idx}.txt").write_text(page.locator("body").inner_text(timeout=5000), encoding="utf-8")
                except Exception:
                    pass

            for link in _collect_room_links(page):
                if link not in seen:
                    seen.add(link)
                    search_links.append(link)
            page.close()

        for n, link in enumerate(search_links[:max_detail_pages], start=1):
            detail_page = context.new_page()
            status = "opened"
            specs = None
            title = "Airbnb Listing"
            price = None
            body = ""
            try:
                try:
                    detail_page.goto(link, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    detail_page.goto(link, wait_until="domcontentloaded", timeout=15000)
                detail_page.wait_for_timeout(1200)

                specs = _extract_airbnb_specs_from_detail_page(detail_page)
                title = _extract_title(detail_page)
                body = detail_page.locator("body").inner_text(timeout=4000)
                price = _first_reasonable_price(body)

                if debug and n <= 5:
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

            ok, reason = _qualified(specs, body)
            debug_rows.append({
                "n": n,
                "url": link,
                "title": title,
                "status": status,
                "specs_found": specs.get("specs_line") if specs else "",
                "qualified": ok,
                "reason": reason,
                "price": price or "",
            })

            if ok:
                listings.append({
                    "title": title,
                    "link": link,
                    "raw_text": body[:1200],
                    "price": price or 0,
                    "relevance": "High",
                    "relevance_score": 15,
                    "direct_competitor": True,
                    "fit_score": 15,
                    "fit_reasons": "Exact 6 guests · 2 bedrooms · 2 beds · 3 baths; Sunny Isles search; Ritta excluded",
                    "penalty_reasons": "",
                    "qualified_competitor": True,
                    "guest_count": specs["guest_count"],
                    "bedroom_count": specs["bedroom_count"],
                    "bed_count": specs["bed_count"],
                    "bathroom_count": specs["bathroom_count"],
                    "match_quality": "Exact Airbnb specs match",
                    "specs_line": specs["specs_line"],
                })
                if len(listings) >= 8:
                    break

        browser.close()

    if debug:
        try:
            with open(debug_dir / "debug_report.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["n", "url", "title", "status", "specs_found", "qualified", "reason", "price"])
                writer.writeheader()
                writer.writerows(debug_rows)
        except Exception:
            pass

    return listings
