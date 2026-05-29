import holidays
import pandas as pd
from datetime import date


def get_us_holidays_in_range(start_date, end_date):
    years = list(range(start_date.year, end_date.year + 1))
    us_holidays = holidays.US(years=years)

    custom_holidays = {
        2026: [
            {"name": "Passover", "start": date(2026, 4, 1), "end": date(2026, 4, 9), "impact": 20}
        ],
        2027: [
            {"name": "Passover", "start": date(2027, 4, 21), "end": date(2027, 4, 29), "impact": 20}
        ],
    }

    detected = []
    date_range = pd.date_range(start_date, end_date)

    for d in date_range:
        day = d.date()

        if day in us_holidays:
            detected.append({
                "name": us_holidays[day],
                "date": day,
                "impact": 15
            })

        for h in custom_holidays.get(day.year, []):
            if h["start"] <= day <= h["end"]:
                detected.append({
                    "name": h["name"],
                    "date": day,
                    "impact": h["impact"]
                })

    return detected
