from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import re
from urllib.parse import urlsplit, urlunsplit

# Buildings/resorts that compete directly with Marenas in or near Sunny Isles.
TARGET_RESORTS = [
    "marenas", "marenas resort", "sole miami", "solé miami", "sole", "solé",
    "trump international", "trump", "ocean reserve", "doubletree ocean point",
    "doubletree", "marco polo", "ramada", "newport", "hyde"
]

LOCATION_KEYWORDS = [
    "sunny isles", "sunny isles beach", "collins ave", "collins avenue",
    "beach resort", "ocean view", "beachfront", "oceanfront", "beach access"
]

BANNED_PROPERTY_TYPES = [
    "entire home", "home in", "house", "villa", "townhouse", "private room", "shared room"
]

EXCLUDED_HOSTS = ["hosted by ritta", "hosted by rita", "hosted by marritta"]

OFFICIAL_SPEC_PATTERN = re.compile(
    r"(?P<guests>\d+)\s+guests?\s*(?:[·•]|\s)+\s*"
    r"(?P<bedrooms>\d+)\s+bedrooms?\s*(?:[·•]|\s)+\s*"
    r"(?P<beds>\d+)\s+beds?\s*(?:[·•]|\s)+\s*"
    r"(?P<baths>\d+(?:\.\d+)?)\s+baths?",
    re.IGNORECASE,
)

PRICE_PATTERN = re.compile(r"\$[\d,]+")


def _clean_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _extract_price(card_text: str) -> int | None:
    prices = []
    for match in PRICE_PATTERN.findall(card_text):
        value = int(match.replace("$", "").replace(",", ""))
        if value >= 100:
            prices.append(value)
    return prices[-1] if prices else None


def _extract_official_specs(text: str):
    """Extract the exact Airbnb headline specs line, e.g. '6 guests · 2 bedrooms · 2 beds · 3 baths'."""
    if not text:
        return None

    normalized = re.sub(r"\s+", " ", text.replace("•", "·")).strip()
    match = OFFICIAL_SPEC_PATTERN.search(normalized)
    if not match:
        return None

    guests = int(match.group("guests"))
    bedrooms = int(match.group("bedrooms"))
    beds = int(match.group("beds"))
    baths = float(match.group("baths"))
    if baths.is_integer():
        baths = int(baths)

    return {
        "guest_count": guests,
        "bedroom_count": bedrooms,
        "bed_count": beds,
        "bathroom_count": baths,
        "specs_line": match.group(0),
    }


def _extract_official_specs_from_page(page):
    """
    Airbnb renders the headline specs as an <ol> with four <li> elements:
    6 guests · 2 bedrooms · 2 beds · 3 baths.
    This reads that exact visual block instead of depending on the full body text.
    """
    try:
        ol_texts = page.locator("ol").all_inner_texts(timeout=5000)
    except TypeError:
        ol_texts = page.locator("ol").all_inner_texts()
    except Exception:
        ol_texts = []

    for text in ol_texts:
        normalized = re.sub(r"\s+", " ", text.replace("\n", " ").replace("•", "·")).strip()
        lower = normalized.lower()
        if all(word in lower for word in ["guest", "bedroom", "bed", "bath"]):
            specs = _extract_official_specs(normalized)
            if specs:
                return specs

    # Fallback: read li elements directly and combine nearby items.
    try:
        li_texts = page.locator("li").all_inner_texts(timeout=5000)
    except TypeError:
        li_texts = page.locator("li").all_inner_texts()
    except Exception:
        li_texts = []

    clean_items = [re.sub(r"\s+", " ", x).strip() for x in li_texts if x and x.strip()]
    for i in range(max(0, len(clean_items) - 3)):
        block = " · ".join(clean_items[i:i+4])
        lower = block.lower()
        if all(word in lower for word in ["guest", "bedroom", "bed", "bath"]):
            specs = _extract_official_specs(block)
            if specs:
                return specs

    return None


def _is_exact_marenas_competitor(combined_text: str, specs: dict | None) -> tuple[bool, list[str], list[str]]:
    reasons = []
    penalties = []
    text = combined_text.lower()

    if any(host in text for host in EXCLUDED_HOSTS):
        return False, reasons, ["excluded host: Ritta/Rita/Marritta"]

    if any(bad in text for bad in BANNED_PROPERTY_TYPES):
        return False, reasons, ["excluded property type"]

    # User's hard requirement: exact Airbnb specs below title/photo.
    if not specs:
        return False, reasons, ["official Airbnb specs line not found"]

    if not (
        specs["guest_count"] == 6
        and specs["bedroom_count"] == 2
        and specs["bed_count"] == 2
        and float(specs["bathroom_count"]) == 3.0
    ):
        return False, reasons, ["not exact 6 guests · 2 bedrooms · 2 beds · 3 baths"]

    reasons.append("exact 6 guests · 2 bedrooms · 2 beds · 3 baths")

    location_match = any(k in text for k in LOCATION_KEYWORDS)
    resort_match = any(k in text for k in TARGET_RESORTS)

    if not (location_match or resort_match):
        return False, reasons, ["not clearly in/near Sunny Isles or a target resort"]

    if resort_match:
        reasons.append("target Sunny Isles resort/building")
    elif location_match:
        reasons.append("Sunny Isles / beach location signal")

    return True, reasons, penalties


def get_airbnb_prices(checkin, checkout, max_detail_pages: int = 18):
    """
    Fast competitor scan:
    1. Scrape search result cards for links/prices.
    2. Open detail pages only for the most likely candidates, not every card.
    3. Keep only exact matches: 6 guests · 2 bedrooms · 2 beds · 3 baths.
    4. Exclude listings hosted by Ritta/Rita/Marritta.
    """
    url = (
        "https://www.airbnb.com/s/Sunny-Isles-Beach--Florida--United-States/homes"
        f"?checkin={checkin}"
        f"&checkout={checkout}"
        "&adults=6"
        "&min_bedrooms=2"
        "&min_bathrooms=3"
        "&query=Sunny%20Isles%20Beach%20Marenas%20resort%20ocean%20view%20beachfront%20Collins"
    )

    listings = []
    candidates = []
    seen_links = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(locale="en-US")

        # Speed: do not download heavy assets. Text is enough for specs/host/price.
        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["image", "media", "font", "stylesheet"]
            else route.continue_(),
        )

        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)

        # Less scrolling = faster. Airbnb usually loads enough cards after 3 scrolls.
        for _ in range(3):
            page.mouse.wheel(0, 4500)
            page.wait_for_timeout(900)

        cards = page.locator("div[itemprop='itemListElement']")
        count = cards.count()

        for i in range(count):
            try:
                card = cards.nth(i)
                text = card.inner_text(timeout=2500)
                text_lower = text.lower()
                price = _extract_price(text)
                if price is None:
                    continue

                hrefs = card.locator("a").evaluate_all("els => els.map(a => a.href)")
                link = next((_clean_url(href) for href in hrefs if "/rooms/" in href), None)
                if not link or link in seen_links:
                    continue
                seen_links.add(link)

                # Prioritize likely direct competitors before opening detail pages.
                priority = 0
                if any(k in text_lower for k in TARGET_RESORTS):
                    priority += 10
                if any(k in text_lower for k in LOCATION_KEYWORDS):
                    priority += 5
                if "sunny isles" in text_lower or "collins" in text_lower:
                    priority += 3
                if any(bad in text_lower for bad in BANNED_PROPERTY_TYPES):
                    priority -= 20

                title_lines = [line.strip() for line in text.split("\n") if line.strip()]
                title = title_lines[0] if title_lines else "Airbnb Listing"

                candidates.append({
                    "title": title,
                    "link": link,
                    "raw_text": text,
                    "price": price,
                    "priority": priority,
                })
            except Exception:
                continue

        candidates = sorted(candidates, key=lambda x: x["priority"], reverse=True)[:max_detail_pages]

        for candidate in candidates:
            detail_text = ""
            detail_specs = None
            try:
                detail_page = context.new_page()
                detail_page.goto(candidate["link"], wait_until="domcontentloaded", timeout=25000)
                detail_page.wait_for_timeout(1600)
                # First read the specific Airbnb <ol>/<li> block that contains:
                # 6 guests · 2 bedrooms · 2 beds · 3 baths
                detail_specs = _extract_official_specs_from_page(detail_page)
                detail_text = detail_page.locator("body").inner_text(timeout=5000)
                detail_page.close()
            except (PlaywrightTimeoutError, Exception):
                try:
                    detail_page.close()
                except Exception:
                    pass

            combined_text = f"{candidate['title']}\n{candidate['raw_text']}\n{detail_text}"
            specs = detail_specs or _extract_official_specs(detail_text) or _extract_official_specs(candidate["raw_text"])

            is_qualified, reasons, penalties = _is_exact_marenas_competitor(combined_text, specs)
            if not is_qualified:
                continue

            fit_score = 12
            if any(k in combined_text.lower() for k in TARGET_RESORTS):
                fit_score += 3
            if any(k in combined_text.lower() for k in ["oceanfront", "beachfront", "ocean view", "beach access", "private beach"]):
                fit_score += 2

            listings.append({
                "title": candidate["title"],
                "link": candidate["link"],
                "raw_text": candidate["raw_text"],
                "price": candidate["price"],
                "relevance": "High",
                "relevance_score": fit_score,
                "direct_competitor": True,
                "fit_score": fit_score,
                "fit_reasons": ", ".join(reasons),
                "penalty_reasons": ", ".join(penalties),
                "qualified_competitor": True,
                "guest_count": specs["guest_count"],
                "bedroom_count": specs["bedroom_count"],
                "bed_count": specs["bed_count"],
                "bathroom_count": specs["bathroom_count"],
                "match_quality": "Exact Marenas-style match",
                "specs_line": specs["specs_line"],
            })

        browser.close()

    return listings
