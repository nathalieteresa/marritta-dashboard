import requests
import pandas as pd

SUNNY_ISLES_LAT = 25.9407
SUNNY_ISLES_LON = -80.1248

def get_weather_forecast():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={SUNNY_ISLES_LAT}"
        f"&longitude={SUNNY_ISLES_LON}"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,weather_code"
        "&temperature_unit=fahrenheit"
        "&wind_speed_unit=mph"
        "&forecast_days=16"
        "&timezone=America/New_York"
    )

    response = requests.get(url, timeout=10)

    if response.status_code != 200:
        return pd.DataFrame()

    data = response.json().get("daily", {})

    df = pd.DataFrame(data)

    if df.empty:
        return df

    df["time"] = pd.to_datetime(df["time"]).dt.date

    return df


def get_weather_signal(weather_df, checkin, checkout):
    if weather_df.empty:
        return {
            "score": 0,
            "label": "Unknown",
            "reason": "Weather forecast unavailable."
        }

    selected = weather_df[
        (weather_df["time"] >= checkin) &
        (weather_df["time"] <= checkout)
    ]

    if selected.empty:
        return {
            "score": 0,
            "label": "Unavailable",
            "reason": "Weather forecast is only available for the next 16 days."
        }

    avg_rain = selected["precipitation_probability_max"].mean()
    avg_temp = selected["temperature_2m_max"].mean()
    avg_wind = selected["wind_speed_10m_max"].mean()

    score = 0
    reasons = []

    if avg_temp >= 78 and avg_temp <= 92:
        score += 8
        reasons.append("good beach temperature")

    if avg_rain <= 35:
        score += 8
        reasons.append("low rain probability")

    elif avg_rain >= 65:
        score -= 12
        reasons.append("high rain probability")

    if avg_wind >= 25:
        score -= 8
        reasons.append("high wind")

    if score >= 10:
        label = "Strong"
    elif score >= 3:
        label = "Moderate"
    elif score < 0:
        label = "Weak"
    else:
        label = "Neutral"

    return {
        "score": score,
        "label": label,
        "reason": ", ".join(reasons) if reasons else "neutral weather conditions"
    }