import holidays
import pandas as pd


def get_us_holidays_in_range(start_date, end_date):
    years = list(range(start_date.year, end_date.year + 1))

    holiday_sources = [
        holidays.US(years=years),
        holidays.US(years=years, categories=["public"]),
        holidays.US(years=years, categories=["observed"]),
        holidays.US(years=years, categories=["religious"]),
    ]

    detected = []
    seen = set()

    date_range = pd.date_range(start_date, end_date)

    for d in date_range:
        day = d.date()

        for source in holiday_sources:
            if day in source:
                name = source[day]

                key = (str(name), day)
                if key not in seen:
                    detected.append({
                        "name": str(name),
                        "date": day,
                        "impact": classify_holiday_impact(str(name))
                    })
                    seen.add(key)

    return detected


def classify_holiday_impact(name):
    name_lower = name.lower()

    high_impact_keywords = [
        "passover",
        "easter",
        "christmas",
        "thanksgiving",
        "new year's",
        "new year",
        "independence day",
        "hanukkah",
        "yom kippur",
        "rosh hashanah",
        "eid",
        "ramadan"
    ]

    medium_impact_keywords = [
        "memorial day",
        "labor day",
        "presidents",
        "martin luther king",
        "columbus",
        "veterans"
    ]

    if any(k in name_lower for k in high_impact_keywords):
        return 20

    if any(k in name_lower for k in medium_impact_keywords):
        return 12

    return 8
