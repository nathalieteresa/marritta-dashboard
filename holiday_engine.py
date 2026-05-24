import holidays
import pandas as pd

def get_us_holidays_in_range(start_date, end_date):
    years = list(range(start_date.year, end_date.year + 1))
    us_holidays = holidays.US(years=years)

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

    return detected