from playwright.sync_api import sync_playwright
import re

TARGET_RESORTS = [
    "sole miami",
    "solé miami",
    "sole",
    "solé",
    "trump international",
    "trump",
    "marco polo",
    "ramada",
    "doubletree ocean point",
    "doubletree",
    "the sunny curio",
    "curio",
    "ocean reserve",
    "marenas",
    "private condos at trump",
    "private condos at marenas",
]

BANNED_PROPERTY_TYPES = [
    "entire home",
    "home in",
    "house",
    "villa",
    "townhouse",
]

OCEANFRONT_KEYWORDS = [
    "oceanfront",
    "ocean front",
    "beachfront",
    "beach front",
    "direct ocean view",
    "ocean view",
    "beach access",
    "private beach",
    "waterfront",
]


def extract_number(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(float(match.group(1)))
    return None

def extract_airbnb_specs(detail_text):
    specs_line = ""

    for line in detail_text.split("\n"):
        line_clean = line.strip().lower()

        if (
            "guest" in line_clean
            and "bedroom" in line_clean
            and "bed" in line_clean
            and "bath" in line_clean
        ):
            specs_line = line_clean
            break

    if not specs_line:
        return None, None, None, None, ""

    guest_count = extract_number([r"(\d+)\s+guests?"], specs_line)
    bedroom_count = extract_number([r"(\d+)\s+bedrooms?"], specs_line)
    bed_count = extract_number([r"(\d+)\s+beds?"], specs_line)
    bathroom_count = extract_number([r"(\d+(?:\.\d+)?)\s+baths?"], specs_line)

    return guest_count, bedroom_count, bed_count, bathroom_count, specs_line
    
def get_airbnb_prices(checkin, checkout):

    listings = []

    url = (
    "https://www.airbnb.com/s/Sunny-Isles-Beach--Florida--United-States/homes"
    f"?checkin={checkin}"
    f"&checkout={checkout}"
    "&adults=6"
    "&min_bedrooms=2"
    "&min_bathrooms=3"
    "&query=Sunny%20Isles%20Beach%20resort%20hotel%20ocean%20view%20beach%20access%20kitchen"
    )

    allowed_keywords = [
        "marenas",
        "sunny isles",
        "beach resort",
        "ocean view",
        "intracoastal",
        "collins",
        "solé",
        "sole",
        "hyde",
        "trump",
        "ocean reserve"
    ]

    with sync_playwright() as p:

        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        page = browser.new_page()
        page.goto(url)
        page.wait_for_timeout(7000)
        for _ in range(6):
            page.mouse.wheel(0, 5000)
            page.wait_for_timeout(2500)

        cards = page.locator("div[itemprop='itemListElement']")
        count = cards.count()

        for i in range(count):

            try:
                card = cards.nth(i)
                text = card.inner_text()
                text_lower = text.lower()

                #No eliminar por keywords aquí. Mejor analizar todos y clasificarlos después.

                link = None
                hrefs = card.locator("a").evaluate_all(
                    "(els) => els.map(a => a.href)"
                )

                for href in hrefs:
                    if "/rooms/" in href:
                        link = href
                        break

                lines = [
                    line.strip()
                    for line in text.split("\n")
                    if line.strip()
                ]

                title = lines[0] if len(lines) > 0 else "Airbnb Listing"

                dollar_matches = re.findall(
                    r"\$[\d,]+",
                    text
                )

                price = None

                if len(dollar_matches) > 0:

                    clean_prices = []

                    for p in dollar_matches:
                        number = int(
                            p.replace("$", "").replace(",", "")
                        )

                        if number >= 100:
                            clean_prices.append(number)

                    if len(clean_prices) > 0:
                        price = clean_prices[-1]

                if price is None:
                    continue

                relevance_score = 0

                if "marenas" in text_lower:
                    relevance_score += 6

                if "sunny isles" in text_lower:
                    relevance_score += 3

                if "collins" in text_lower:
                    relevance_score += 2

                if "ocean" in text_lower or "beach" in text_lower:
                    relevance_score += 2

                if "condo" in text_lower or "apartment" in text_lower:
                    relevance_score += 2

                if "resort" in text_lower:
                    relevance_score += 2

                if "private room" in text_lower or "shared room" in text_lower:
                    relevance_score -= 5

                if relevance_score >= 8:
                    relevance = "High"

                elif relevance_score >= 5:
                    relevance = "Medium"

                else:
                    relevance = "Low"

                direct_competitor = False

                direct_keywords = [
                    "marenas",
                    "marenas resort",
                    "resort",
                    "hotel",
                    "beachfront",
                    "beach front",
                    "oceanfront",
                    "ocean front",
                    "direct ocean view",
                    "ocean view",
                    "beach access",
                    "private beach",
                    "sunny isles",
                    "sole",
                    "trump",
                    "newport",
                    "ocean reserve"
                ]

                for keyword in direct_keywords:

                    if keyword.lower() in text.lower():
                        direct_competitor = True
                        break

                detail_text = ""

                if link:

                    try:

                        detail_page = browser.new_page()
                        detail_page.goto(link)
                        detail_page.wait_for_timeout(4000)

                        detail_text = detail_page.locator("body").inner_text().lower()

                        detail_page.close()

                    except:
                        detail_text = ""

                combined_text = (text + " " + detail_text).lower()

                # Excluir listings de tu mamá
                if "hosted by ritta" in combined_text:
                    continue

                for keyword in direct_keywords:

                    if keyword.lower() in combined_text:
                        direct_competitor = True
                        break


                combined_text = f"{title} {text} {detail_text}".lower()

                guest_count, bedroom_count, bed_count, bathroom_count, specs_line = extract_airbnb_specs(detail_text)

                # Fallback por si Airbnb cambia el formato o no aparece la línea oficial
                if guest_count is None:
                    guest_count = extract_number([r"(\d+)\s+guests?", r"up to\s+(\d+)\s+people", r"sleeps\s+(\d+)"], combined_text)

                if bedroom_count is None:
                    bedroom_count = extract_number([r"(\d+)\s+bedrooms?", r"(\d+)\s+bedroom"], combined_text)

                if bed_count is None:
                    bed_count = extract_number([r"(\d+)\s+beds?"], combined_text)

                if bathroom_count is None:
                    bathroom_count = extract_number([r"(\d+(?:\.\d+)?)\s+baths?", r"(\d+(?:\.\d+)?)\s+bathrooms?"], combined_text)

                fit_score = 0
                fit_reasons = []
                penalty_reasons = []

                is_target_resort = any(x in combined_text for x in TARGET_RESORTS)
                is_banned_type = any(x in combined_text for x in BANNED_PROPERTY_TYPES)
                is_oceanfront = any(x in combined_text for x in OCEANFRONT_KEYWORDS)

                # HARD FILTERS — Marenas-like competitors only

                # 1. Exclude your mom's listings
                if "hosted by ritta" in combined_text:
                    continue

                # 2. Exclude obvious houses / villas / townhouses
                if any(x in combined_text for x in ["villa", "townhouse", "entire home", "home in", "house"]):
                    continue

                # 3. Must be max 6 guests
                if guest_count is None or guest_count > 6:
                    continue

                # 4. Must have exactly 2 bedrooms
                if bedroom_count is None or bedroom_count != 2:
                    continue

                # 5. Must have at least 3 bathrooms
                if bathroom_count is None and bathroom_count < 3:
                    continue

                # 6. Must be in / near Sunny Isles or in one of your target resort buildings
                location_or_resort_match = any(
                    x in combined_text
                    for x in TARGET_RESORTS + [
                        "sunny isles",
                        "collins ave",
                        "collins avenue",
                        "marenas",
                        "trump",
                        "sole",
                        "solé",
                        "ocean reserve",
                        "newport",
                        "doubletree",
                        "marco polo",
                        "ramada"
                    ]
                )

                if not location_or_resort_match:
                    continue

                # 7. Should be ocean/beach related, but do not eliminate if missing
                if not is_oceanfront:
                    penalty_reasons.append("oceanfront/beach access not confirmed")
                
                # SCORING
                if is_target_resort:
                    fit_score += 5
                    fit_reasons.append("target resort/building")

                if guest_count is not None and guest_count <= 6:
                    fit_score += 2
                    fit_reasons.append("max 6 guests")

                if bedroom_count is not None and bedroom_count == 2:
                    fit_score += 2
                    fit_reasons.append("exactly 2 bedrooms")

                if bed_count is not None and bed_count >= 3:
                    fit_score += 2
                    fit_reasons.append("3+ beds")

                if bathroom_count is not None and bathroom_count >= 3:
                    fit_score += 2
                    fit_reasons.append("3+ bathrooms")

                if is_oceanfront:
                    fit_score += 3
                    fit_reasons.append("oceanfront/beach access")

                if "kitchen" in combined_text:
                    fit_score += 1
                    fit_reasons.append("kitchen")

                qualified_competitor = fit_score >= 4

                if fit_score >= 10:
                    match_quality = "Strong match"
                elif fit_score >= 4:
                    match_quality = "Qualified match"
                else:
                    match_quality = "Partial match"

                relevance_score = fit_score

                if relevance_score >= 10:
                    relevance = "High"
                elif relevance_score >= 4:
                    relevance = "Medium"
                else:
                    relevance = "Low"

                direct_competitor = is_target_resort or is_oceanfront or fit_score >= 4

                listings.append({
                    "title": title,
                    "link": link,
                    "raw_text": text,
                    "price": price,
                    "relevance": relevance,
                    "relevance_score": relevance_score,
                    "direct_competitor": direct_competitor,
                    "fit_score": fit_score,
                    "fit_reasons": ", ".join(fit_reasons),
                    "penalty_reasons": ", ".join(penalty_reasons),
                    "guest_count": guest_count,
                    "qualified_competitor": qualified_competitor,
                    "match_quality": match_quality,
                    "guest_count": guest_count,
                    "bedroom_count": bedroom_count,
                    "bed_count": bed_count,
                    "bathroom_count": bathroom_count,
                    "match_quality": match_quality,
                    "specs_line": specs_line,
                })

            except:
                pass

        browser.close()
        print("TOTAL CARDS SCRAPED:", count)
        print("TOTAL LISTINGS AFTER FILTERS:", len(listings))

        for x in listings[:10]:
            print(
                x["title"],
                "| guests:", x.get("guest_count"),
                "| fit:", x.get("fit_score"),
                "| direct:", x.get("direct_competitor")
            )

        return listings
