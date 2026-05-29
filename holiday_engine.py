import holidays
import pandas as pd
import requests
import streamlit as st


def get_us_holidays_in_range(start_date, end_date):
    detected = []
    seen = set()

    years = list(range(start_date.year, end_date.year + 1))

    # Federal / public US holidays
    us_holidays = holidays.US(years=years)

    for d in pd.date_range(start_date, end_date):
        day = d.date()

        if day in us_holidays:
            name = str(us_holidays[day])
            key = (name, day)

            if key not in seen:
                detected.append({
                    "name": name,
                    "date": day,
                    "impact": classify_holiday_impact(name)
                })
                seen.add(key)

    # Religious / cultural holidays from Calendarific API
    api_key = st.secrets.get("CALENDARIFIC_API_KEY", None)

    if api_key:
        for year in years:
            try:
                url = "https://calendarific.com/api/v2/holidays"
                params = {
                    "api_key": api_key,
                    "country": "US",
                    "year": year,
                    "type": "religious"
                }

                response = requests.get(url, params=params, timeout=10)
                data = response.json()

                holidays_list = data.get("response", {}).get("holidays", [])

                for h in holidays_list:
                    holiday_date = pd.to_datetime(h["date"]["iso"]).date()

                    if start_date <= holiday_date <= end_date:
                        name = h["name"]
                        key = (name, holiday_date)

                        if key not in seen:
                            detected.append({
                                "name": name,
                                "date": holiday_date,
                                "impact": classify_holiday_impact(name)
                            })
                            seen.add(key)

            except Exception:
                pass

    return detected


def classify_holiday_impact(name):
    name_lower = name.lower()

    high_impact_keywords = [
        "passover",
        "easter",
        "christmas",
        "thanksgiving",
        "new year",
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
