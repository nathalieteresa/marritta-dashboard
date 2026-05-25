from playwright.sync_api import sync_playwright
import re


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
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process"
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

                if not any(keyword in text_lower for keyword in allowed_keywords):
                    continue

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

                guest_match = re.search(r"(\d+)\s+guests?", combined_text)

                guest_count = None
                if guest_match:
                    guest_count = int(guest_match.group(1))

                # Exclude properties for more than 6 guests
                if guest_count is not None and guest_count > 6:
                    continue

                fit_score = 0
                fit_reasons = []

                if any(x in combined_text for x in ["resort", "hotel", "marenas", "sole", "trump", "newport"]):
                    fit_score += 2
                    fit_reasons.append("resort/hotel")

                if any(x in combined_text for x in ["2 bedroom", "2 bedrooms", "2 bed", "2 beds", "two bedroom"]):
                    fit_score += 2
                    fit_reasons.append("2 bedrooms")

                if any(x in combined_text for x in ["3 bathroom", "3 bathrooms", "3 bath", "3 baths"]):
                    fit_score += 2
                    fit_reasons.append("3 bathrooms")

                if any(x in combined_text for x in ["6 guests", "sleeps 6", "up to 6", "6 people"]):
                    fit_score += 2
                    fit_reasons.append("6 guests")

                if any(x in combined_text for x in ["kitchen", "full kitchen", "complete kitchen"]):
                    fit_score += 1
                    fit_reasons.append("kitchen")

                if any(x in combined_text for x in ["direct ocean view", "ocean view", "oceanfront", "beachfront", "beach access", "private beach"]):
                    fit_score += 3
                    fit_reasons.append("ocean view/access")

                penalty_score = 0
                penalty_reasons = []

                if "aventura" in combined_text and "marenas" not in combined_text:
                    penalty_score += 4
                    penalty_reasons.append("possible Aventura location")

                if any(x in combined_text for x in ["house", "villa", "townhouse"]):
                    penalty_score += 3
                    penalty_reasons.append("not condo/resort style")

                if "home in" in combined_text and not any(
                    x in combined_text for x in ["marenas", "resort", "condo", "apartment"]
                ):
                    penalty_score += 2
                    penalty_reasons.append("possible private home")

                fit_score = fit_score - penalty_score

                qualified_competitor = fit_score >= 3

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
                })

            except:
                pass

        browser.close()

        print("TOTAL LISTINGS:", len(listings))
        for x in listings[:10]:
            print(
                x["title"],
                "| FIT:", x["fit_score"],
                "| QUALIFIED:", x["qualified_competitor"]
            )
    return listings
