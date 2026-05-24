import requests
import streamlit as st

def get_miami_events(start_date=None, end_date=None):

    api_key = st.secrets["TICKETMASTER_API_KEY"]

    cities = [
        "Miami",
        "Miami Gardens",
        "Hollywood",
        "Fort Lauderdale"
    ]

    all_events = []

    for city in cities:

        url = (
            "https://app.ticketmaster.com/discovery/v2/events.json"
            f"?city={city}"
            "&stateCode=FL"
            "&size=50"
            f"&apikey={api_key}"
        )

        if start_date and end_date:
            url += f"&startDateTime={start_date}T00:00:00Z"
            url += f"&endDateTime={end_date}T23:59:59Z"

        try:
            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                continue

            data = response.json()
            events = data.get("_embedded", {}).get("events", [])

            all_events.extend(events)

        except:
            pass

    # Remove duplicate events
    unique_events = {}

    for event in all_events:
        event_id = event.get("id")
        if event_id:
            unique_events[event_id] = event

    return list(unique_events.values())
