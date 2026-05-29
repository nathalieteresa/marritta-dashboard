# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from events_api import get_miami_events
from database import supabase
from competitor_scraper import get_airbnb_prices
from holiday_engine import get_us_holidays_in_range
from weather_engine import get_weather_forecast, get_weather_signal
from deep_translator import GoogleTranslator

# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------

st.set_page_config(
    page_title="Marritta Dashboard",
    page_icon="🏝️",
    layout="wide"
)

# ---------------------------------------------------
# CUSTOM CSS
# ---------------------------------------------------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {
    --purple: #7C3AED;
    --purple-dark: #5B21B6;
    --purple-soft: #A78BFA;
    --mint: #34D399;
    --pink: #FB7185;
    --yellow: #FDE047;
    --ink: #252A3A;
    --muted: #7A8094;
    --panel: rgba(255,255,255,0.88);
    --line: rgba(255,255,255,0.45);
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background:
        radial-gradient(circle at 20% 10%, rgba(196, 181, 253, 0.95) 0, rgba(196, 181, 253, 0) 28%),
        radial-gradient(circle at 80% 15%, rgba(167, 139, 250, 0.85) 0, rgba(167, 139, 250, 0) 26%),
        linear-gradient(135deg, #8B5CF6 0%, #6D28D9 48%, #A78BFA 100%);
}

.block-container {
    max-width: 1450px;
    margin-top: 34px;
    margin-bottom: 34px;
    padding: 28px 34px 42px 34px;
    background: rgba(255,255,255,0.86);
    border: 1px solid rgba(255,255,255,0.55);
    border-radius: 28px;
    box-shadow: 0 30px 80px rgba(64, 30, 130, 0.28);
    backdrop-filter: blur(18px);
}

h1, h2, h3 {
    color: var(--ink);
    font-weight: 900;
    letter-spacing: -0.035em;
}

h1 { font-size: 2.35rem !important; }
h2 { margin-top: 1.6rem !important; }

.hero-card {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 4px 0 18px 0;
    box-shadow: none;
    margin-bottom: 18px;
}

.hero-title {
    font-size: 42px;
    line-height: 1.05;
    font-weight: 900;
    color: var(--purple-dark);
    margin-bottom: 8px;
}

.hero-subtitle {
    color: var(--muted);
    font-size: 16px;
    font-weight: 600;
}



p code, li code, div code {
    background: transparent !important;
    color: inherit !important;
    font-family: 'Inter', sans-serif !important;
    padding: 0 !important;
    border-radius: 0 !important;
}


/* BIG price decision card */
.decision-card {
    background: linear-gradient(135deg, #6D28D9 0%, #8B5CF6 100%);
    border-radius: 28px;
    padding: 36px 40px;
    color: white;
    margin-bottom: 24px;
    box-shadow: 0 24px 60px rgba(109, 40, 217, 0.35);
}

.decision-price {
    font-size: 72px;
    font-weight: 900;
    line-height: 1;
    letter-spacing: -0.04em;
    color: white;
}

.decision-label {
    font-size: 15px;
    font-weight: 700;
    opacity: 0.75;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
}

.decision-badge {
    display: inline-block;
    padding: 8px 20px;
    border-radius: 100px;
    font-weight: 800;
    font-size: 15px;
    margin-top: 12px;
}

.badge-green  { background: rgba(52,211,153,0.25); color: #34D399; border: 1px solid rgba(52,211,153,0.4); }
.badge-yellow { background: rgba(253,224,71,0.20); color: #FDE047; border: 1px solid rgba(253,224,71,0.4); }
.badge-red    { background: rgba(251,113,133,0.20); color: #FB7185; border: 1px solid rgba(251,113,133,0.4); }

.context-line {
    font-size: 16px;
    opacity: 0.88;
    margin-top: 14px;
    line-height: 1.55;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 24px !important;
    border: 1px solid rgba(255,255,255,0.78) !important;
    box-shadow: 0 14px 35px rgba(88, 28, 135, 0.09);
    background: rgba(255,255,255,0.82);
}

[data-testid="metric-container"] {
    background: rgba(255,255,255,0.92);
    border-radius: 22px;
    padding: 24px 24px;
    box-shadow: 0 16px 35px rgba(88, 28, 135, 0.09);
    border: 1px solid rgba(255,255,255,0.75);
}

[data-testid="metric-container"] label {
    color: #717893 !important;
    font-weight: 700 !important;
}

[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: var(--ink) !important;
    font-weight: 900 !important;
}

[data-testid="stDateInput"] input,
[data-testid="stTextInput"] input {
    border-radius: 16px !important;
    border: 1px solid rgba(167,139,250,0.22) !important;
    background: rgba(255,255,255,0.92) !important;
    min-height: 48px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.9);
}

.stButton>button, .stLinkButton a {
    background: linear-gradient(135deg, #8B5CF6 0%, #6D28D9 100%) !important;
    color: white !important;
    border-radius: 16px !important;
    border: none !important;
    padding: 0.78rem 1.35rem !important;
    font-weight: 900 !important;
    box-shadow: 0 12px 26px rgba(124, 58, 237, 0.32);
}

.stButton>button:hover, .stLinkButton a:hover {
    transform: translateY(-1px);
    box-shadow: 0 16px 32px rgba(124, 58, 237, 0.38);
}

[data-testid="stAlert"] {
    border-radius: 18px !important;
    border: 1px solid rgba(255,255,255,0.55) !important;
    box-shadow: 0 10px 24px rgba(88, 28, 135, 0.05);
}

[data-testid="stDataFrame"] {
    border-radius: 22px !important;
    overflow: hidden;
    box-shadow: 0 16px 36px rgba(88, 28, 135, 0.08);
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #8B5CF6 0%, #6D28D9 58%, #5B21B6 100%);
    border-right: 1px solid rgba(255,255,255,0.25);
    box-shadow: 15px 0 45px rgba(76, 29, 149, 0.22);
}

section[data-testid="stSidebar"] * {
    color: white !important;
}

section[data-testid="stSidebar"] .block-container {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 2rem 1.4rem !important;
}

section[data-testid="stSidebar"] .stButton>button {
    width: 100%;
    background: rgba(255,255,255,0.18) !important;
    border: 1px solid rgba(255,255,255,0.28) !important;
    box-shadow: none !important;
}

.sidebar-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 900;
    font-size: 22px;
    color: white !important;
    margin-bottom: 28px;
}

.sidebar-card {
    background: rgba(255,255,255,0.14);
    border: 1px solid rgba(255,255,255,0.18);
    border-radius: 24px;
    padding: 20px;
    color: white !important;
    margin: 18px 0;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.18);
}

.sidebar-status {
    background: rgba(255,255,255,0.14);
    border-radius: 16px;
    padding: 12px 14px;
    margin: 9px 0;
    border: 1px solid rgba(255,255,255,0.18);
}

[data-testid="stRadio"] {
    background: rgba(255,255,255,0.88);
    border: 1px solid rgba(255,255,255,0.65);
    border-radius: 18px;
    padding: 10px 14px;
    width: fit-content;
    box-shadow: 0 10px 24px rgba(88, 28, 135, 0.10);
}

.js-plotly-plot {
    border-radius: 22px;
}

hr {
    border-color: rgba(255,255,255,0.25) !important;
}

/* CLEAN LOGIN PAGE */
.login-card-new {
    max-width: 460px;
    margin: 90px auto 40px auto;
    background: white;
    border-radius: 28px;
    padding: 44px 42px;
    box-shadow: 0 28px 70px rgba(76, 29, 149, 0.25);
    text-align: center;
    border: 1px solid rgba(124, 58, 237, 0.12);
}

.login-title {
    font-size: 38px !important;
    font-weight: 900 !important;
    color: #5B21B6 !important;
    margin-bottom: 8px !important;
}

.login-subtitle {
    color: #7A8094 !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    margin-bottom: 28px !important;
}

.login-language {
    display: flex;
    justify-content: center;
    margin: 18px 0;
}

/* Error alert */
.login-active [data-testid="stAlert"] {
    background: rgba(255,80,80,0.18) !important;
    border: 1px solid rgba(255,100,100,0.3) !important;
    color: white !important;
    border-radius: 14px !important;
}

</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------
# LANGUAGE SELECTOR — must come before tr() and login
# ---------------------------------------------------

if "login_language" not in st.session_state:
    st.session_state["login_language"] = "English"
language = st.session_state.get("login_language", "English")

# ---------------------------------------------------
# TRANSLATION FUNCTION — defined before everything
# ---------------------------------------------------

def tr(text):
    current_language = st.session_state.get("login_language", language)
    manual = {
        "Check-in": "Entrada",
        "Check-out": "Salida",
        "Nights": "Noches",
        "Analyze Market": "Analizar mercado",
        "Recommended price per night": "Precio recomendado por noche",
        "Recommended nightly price": "Precio recomendado por noche",
        "Airbnb Avg (competitors)": "Promedio Airbnb de competidores",
        "Your price vs market": "Tu precio vs. mercado",
        "Demand score": "Puntuación de demanda",
        "Demand Score": "Puntuación de demanda",
        "Events detected": "Eventos detectados",
        "Available competitors": "Competidores disponibles",
        "Holiday impact": "Impacto de feriados",
        "Weather signal": "Señal del clima",
        "Why this recommendation?": "¿Por qué esta recomendación?",
        "Demand intelligence": "Inteligencia de demanda",
        "Booking urgency signal": "Señal de urgencia de reserva",
        "Competitor overview": "Resumen de la competencia",
        "Avg competitor price": "Precio promedio de la competencia",
        "Lowest price offered": "Precio más bajo ofrecido",
        "Highest price offered": "Precio más alto ofrecido",
        "Listings found": "Anuncios encontrados",
        "Direct competitors": "Competidores directos",
        "Competitor listings": "Listado de competidores",
        "Competitor price": "Precio total de la competencia",
        "Price / night": "Precio por noche",
        "View on Airbnb": "Ver en Airbnb",
        "Market trend analytics": "Análisis de tendencia del mercado",
        "Average Competitor Pricing Trend": "Tendencia del precio promedio de la competencia",
        "Market signals engine": "Motor de señales de mercado",
        "Latest avg market price": "Último precio promedio del mercado",
        "Previous avg market price": "Precio promedio anterior del mercado",
        "Market momentum": "Momento del mercado",
        "Low": "Bajo",
        "Medium": "Medio",
        "High": "Alto",
        "Strong": "Fuerte",
        "Moderate": "Moderado",
        "Weak": "Débil",
        "Neutral": "Neutral",
        "Increase price": "Subir precio",
        "Lower price": "Bajar precio",
        "Keep price stable": "Mantener precio estable",
        "Stable market": "Mercado estable",
        "Monitor closely": "Monitorear de cerca",
        "Competitive pressure": "Presión competitiva",
        "Urgent: Raise prices now": "Urgente: subir precio ahora",
        "Urgency": "Urgencia",
        "Strong competitors": "Competidores fuertes",
        "Daily pricing calendar": "Calendario diario de precios",
        "Date": "Fecha",
        "Day": "Día",
        "Recommended Nightly Price": "Precio recomendado por noche",
        "Holiday": "Feriado",
        "Events": "Eventos",
        "Weather": "Clima",
        "Reason": "Razón",
        "Normal demand": "Demanda normal",
        "Weekend premium": "Prima de fin de semana",
        "Holiday demand": "Demanda por feriado",
        "Event demand": "Demanda por evento",
        "Rain risk": "Riesgo de lluvia",
        "Good beach weather": "Buen clima de playa",
        "Not available": "No disponible",
        "Rain": "Lluvia",
        "View event details": "Ver detalles de eventos",
        "View holiday details": "Ver detalles de feriados",
        "No major events or holidays detected for the selected dates.": "No se detectaron eventos importantes ni feriados para las fechas seleccionadas.",
        "High demand detected. Market conditions support premium pricing.": "Alta demanda detectada. Las condiciones del mercado respaldan precios premium.",
        "Moderate demand detected. Maintain competitive pricing.": "Demanda moderada detectada. Mantén un precio competitivo.",
        "Lower demand environment detected. Aggressive pricing may improve occupancy.": "Demanda más baja detectada. Un precio más competitivo podría mejorar las reservas.",
        "Direct beachfront competitors": "Competidores directos frente a la playa",
        "General market competitors": "Competidores generales del mercado",
        "Sunny Isles Beach / Airbnb": "Sunny Isles Beach / Airbnb",
        "Marritta Dashboard": "Marritta Dashboard",
        "AI-powered pricing recommendations for Airbnb and VRBO": "Recomendaciones de precios para Airbnb y VRBO impulsadas por IA",
        "Latest saved market average": "Último promedio guardado del mercado",
        "Previous saved market average": "Promedio anterior guardado del mercado",
        "What does relevance mean?": "¿Qué significa pertinencia?",
        "Direct competitor": "Competidor directo",
        "General market competitor": "Competidor del mercado general",
        "How to read this chart": "Cómo leer esta gráfica",
        "Average competitor price": "Precio promedio de la competencia",
        "Average competitor price": "Precio promedio de la competencia",

    }
    if current_language == "Español":
        if text in manual:
            return manual[text]
        try:
            return GoogleTranslator(source='auto', target='es').translate(text)
        except:
            return text
    return text

def money(value):
    return f"${value:,.0f}"

def clean_airbnb_title(raw_text, fallback):
    generic = {
        "guest favorite", "superhost", "new", "featured hotel",
        "rare find", "airbnb listing"
    }
    lines = [line.strip() for line in str(raw_text).split("\n") if line.strip()]
    for line in lines[:18]:
        cleaned = line.strip()
        low = cleaned.lower()

        for prefix in ["guest favorite ", "superhost ", "new ", "featured hotel "]:
            if low.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                low = cleaned.lower()

        if low in generic:
            continue
        if "show price" in low or ("for " in low and "night" in low):
            continue
        if "$" in cleaned:
            continue
        if len(cleaned) >= 18:
            return cleaned[:90]
    return fallback if fallback else "Airbnb Listing"

def classify_holiday_pressure(holiday_boost):
    if holiday_boost >= 45:
        return tr("High")
    if holiday_boost >= 15:
        return tr("Medium")
    return tr("Low")

def safe_pct(numerator, denominator):
    if denominator in [0, None] or pd.isna(denominator):
        return 0
    return (numerator / denominator) * 100

def metric_label(label):
    return f"{tr(label)}  ⓘ"

# ---------------------------------------------------
# LOGIN
# ---------------------------------------------------

PASSWORD = "Marenas123"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:

    st.markdown("""
    <style>
    .stApp {
        background:
            radial-gradient(circle at 25% 20%, rgba(37, 24, 140, 0.95), transparent 28%),
            radial-gradient(circle at 78% 28%, rgba(167, 139, 250, 0.75), transparent 30%),
            radial-gradient(circle at 45% 78%, rgba(76, 29, 149, 0.95), transparent 34%),
            linear-gradient(135deg, #1E1065 0%, #4C1D95 48%, #8B5CF6 100%) !important;
    }

    .block-container {
        max-width: 1000px !important;
        min-height: 92vh !important;
        margin: 0 auto !important;
        padding: 0 !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    header[data-testid="stHeader"] {
        background: transparent !important;
    }

    .signin-title {
        text-align: center;
        color: white;
        font-size: 24px;
        font-weight: 900;
        margin-bottom: 26px;
    }

    div[data-testid="stTextInput"] input {
        background: rgba(255,255,255,0.35) !important;
        border: 1px solid rgba(255,255,255,0.30) !important;
        color: white !important;
        border-radius: 999px !important;
        height: 42px !important;
        font-size: 13px !important;
        padding-left: 18px !important;
    }

    div[data-testid="stTextInput"] input::placeholder {
        color: rgba(255,255,255,0.85) !important;
    }

    .stButton > button {
        width: 100% !important;
        height: 44px !important;
        border-radius: 999px !important;
        background: rgba(255,255,255,0.88) !important;
        color: #4C1D95 !important;
        font-weight: 900 !important;
        border: none !important;
        box-shadow: none !important;
        margin-top: 8px !important;
    }

    .login-options {
        display: flex;
        justify-content: space-between;
        color: rgba(255,255,255,0.85);
        font-size: 11px;
        margin: 8px 6px 14px 6px;
    }

    div[data-testid="stRadio"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    margin-top: 30px !important;
    width: 100% !important;
    }

    div[data-testid="stRadio"] > label {
    display: none !important;
    }
    
    div[data-testid="stRadio"] [role="radiogroup"] {
    display: flex !important;
    justify-content: center !important;
    gap: 42px !important;
    }

    div[data-testid="stRadio"] label {
    color: white !important;
    font-size: 20px !important;
    font-weight: 500 !important;
    }

    div[data-testid="stRadio"] p {
    color: white !important;
    font-size: 20px !important;
    }

    div[data-testid="stAlert"] {
        border-radius: 14px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    _, login_col, _ = st.columns([1.3, 1, 1.3])

    with login_col:

        st.markdown(
            '<div class="signin-title">Welcome to Marritta</div>',
            unsafe_allow_html=True
        )

        password = st.text_input(
            "password",
            type="password",
            label_visibility="collapsed",
            placeholder="Password"
        )

        if st.button("Sign in", use_container_width=True):
            if password == PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error(tr("Incorrect password. Please try again."))

        lang_choice = st.radio(
            "",
            ["English", "Español"],
            horizontal=True,
            key="login_language_display"
        )

        st.session_state["login_language"] = (
            "English" if "English" in lang_choice else "Español"
        )

    st.stop()
    
# ---------------------------------------------------
# HERO
# ---------------------------------------------------

st.markdown(
    f"""
    <div class="hero-card">
        <div class="hero-title">Marritta Dashboard</div>
        <div class="hero-subtitle">{tr("AI-powered pricing recommendations for Airbnb and VRBO")}</div>
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------
# STEP 1 — DATE SELECTOR (always visible, top of page)
# ---------------------------------------------------

st.subheader(tr("📅 Select your rental dates"))

col_date1, col_date2, col_date3 = st.columns([2, 2, 1])

with col_date1:
    selected_checkin = st.date_input(
        tr("Check-in"),
        value=date.today() + timedelta(days=7)
    )

with col_date2:
    selected_checkout = st.date_input(
        tr("Check-out"),
        value=date.today() + timedelta(days=12)
    )

nights = (selected_checkout - selected_checkin).days

with col_date3:
    st.metric(tr("Nights"), nights)

st.markdown("")

if st.button(f"🔍 {tr('Analyze Market')}"):

    with st.spinner(tr("Scanning Airbnb competitor listings...")):

        events = get_miami_events(
            selected_checkin.strftime("%Y-%m-%d"),
            selected_checkout.strftime("%Y-%m-%d")
        )

        listings = get_airbnb_prices(
            selected_checkin.strftime("%Y-%m-%d"),
            selected_checkout.strftime("%Y-%m-%d")
        )

    if len(listings) > 0:

        # ---------------------------------------------------
        # BUILD COMPETITOR DATA
        # ---------------------------------------------------

        clean_listings = []

        for idx, listing in enumerate(listings, start=1):
            price = listing["price"]
            if price is None:
                continue
            clean_listings.append({
                "Listing": clean_airbnb_title(listing["raw_text"], listing["title"]),
                "Competitor Price": price,
                "Price per Night": round(price / nights) if nights > 0 else None,
                "Relevance": listing["relevance"],
                "Relevance Score": listing["relevance_score"],
                "direct_competitor": listing["direct_competitor"],
                "fit_score": listing.get("fit_score", 0),
                "fit_reasons": listing.get("fit_reasons", ""),
                "qualified_competitor": listing.get("qualified_competitor", False),
                "Link": listing["link"],
                "Summary": listing["raw_text"][:180] + "...",
            })

        competitor_df = pd.DataFrame(clean_listings)
        st.write("RAW SCRAPER RESULTS:", len(competitor_df))
        st.dataframe(
            competitor_df[
                [
                    "Listing",
                    "fit_score",
                    "qualified_competitor",
                    "direct_competitor"
                ]
            ]
        )
        competitor_df = competitor_df.dropna(subset=["Competitor Price"])
        competitor_df = competitor_df.drop_duplicates(subset=["Listing", "Competitor Price"])
    
        direct_df = competitor_df[competitor_df["direct_competitor"] == True]
        market_df = competitor_df[competitor_df["Relevance"].isin(["High", "Medium"])]
        qualified_df = competitor_df[competitor_df["qualified_competitor"] == True]
        
        if len(qualified_df) >= 2:
            pricing_df = qualified_df
            pricing_source = "Qualified Marenas-like competitors"
        elif len(direct_df) >= 3:
            pricing_df = direct_df
            pricing_source = tr("Direct beachfront competitors")
        else:
            pricing_df = market_df
            pricing_source = tr("General market competitors")

        if len(pricing_df) == 0:
            pricing_df = competitor_df

        avg_competitor_price = pricing_df["Competitor Price"].mean()
        min_competitor_price = pricing_df["Competitor Price"].min()
        max_competitor_price = pricing_df["Competitor Price"].max()

        avg_competitor_nightly = pricing_df["Price per Night"].mean()
        min_competitor_nightly = pricing_df["Price per Night"].min()
        max_competitor_nightly = pricing_df["Price per Night"].max()

        # ---------------------------------------------------
        # HOLIDAYS, WEATHER, EVENTS
        # ---------------------------------------------------

        holiday_events = get_us_holidays_in_range(selected_checkin, selected_checkout)
        holiday_boost = sum(h["impact"] for h in holiday_events)

        try:
            weather_df = get_weather_forecast()
            weather_signal = get_weather_signal(weather_df, selected_checkin, selected_checkout)
        except Exception:
            weather_df = pd.DataFrame()
            weather_signal = {
                "label": "Neutral",
                "score": 0,
                "reason": "weather data unavailable"
            }

        # ---------------------------------------------------
        # DEMAND SCORE ENGINE
        # ---------------------------------------------------

        demand_score = 50
        demand_score += weather_signal["score"]
        demand_score += holiday_boost

        if selected_checkin.weekday() in [4, 5]:
            demand_score += 15

        events_in_window = []
        seen_events = set()

        for event in events:
            try:
                event_name = event.get("name", "Event")
                event_date = pd.to_datetime(event["dates"]["start"]["localDate"]).date()
                event_key = (event_name.lower().strip(), event_date)

                if selected_checkin <= event_date <= selected_checkout and event_key not in seen_events:
                    events_in_window.append(event)
                    seen_events.add(event_key)
            except:
                pass

        event_score = 0
        high_impact_events = []
        medium_impact_events = []

        event_weights = {
            "world cup": 10, "fifa": 10, "formula 1": 10, "f1": 10,
            "art basel": 9, "ultra": 9, "miami open": 8, "super bowl": 10,
            "playoffs": 8, "finals": 8, "bad bunny": 7, "taylor swift": 7,
            "drake": 6, "concert": 3, "festival": 5, "expo": 4, "conference": 4
        }

        for event in events_in_window:
            event_name_original = event.get("name", "Event")
            event_name = event_name_original.lower()
            matched_weight = 1
            for keyword, weight in event_weights.items():
                if keyword in event_name:
                    matched_weight = max(matched_weight, weight)
            event_score += matched_weight
            if matched_weight >= 8:
                high_impact_events.append(event_name_original)
            elif matched_weight >= 4:
                medium_impact_events.append(event_name_original)

        event_score = min(event_score, 30)
        demand_score += event_score

        if len(competitor_df) <= 3:
            demand_score += 20
        elif len(competitor_df) <= 6:
            demand_score += 10

        if avg_competitor_price >= 1800:
            demand_score += 15
        elif avg_competitor_price >= 1400:
            demand_score += 8

        demand_score = min(demand_score, 100)

        real_competitor_avg = avg_competitor_price

        # ---------------------------------------------------
        # SMART PRICE ENGINE
        # ---------------------------------------------------

        available_listings = len(competitor_df)

        if available_listings <= 3:
            occupancy = 90
        elif available_listings <= 6:
            occupancy = 82
        elif available_listings <= 10:
            occupancy = 75
        else:
            occupancy = 65

        avg_market_price = competitor_df["Price per Night"].mean()
        event_impact = 1 + (len(events_in_window) * 0.01)

        suggested_price = round(
            avg_market_price * (
                0.97
                + ((occupancy - 70) / 1000)
                + ((event_impact - 1) / 20)
            )
        )

        suggested_total_price = suggested_price * nights if nights > 0 else suggested_price
        real_competitor_avg = avg_competitor_nightly
        real_competitor_total_avg = avg_competitor_price
        strong_competitors = len(pricing_df)

        decision_threshold = max(15, real_competitor_avg * 0.05)

        if suggested_price > real_competitor_avg + decision_threshold:
            decision = tr("Increase price")
            decision_badge_class = "badge-green"
            decision_message = tr(
                f"The market average is about USD {real_competitor_avg:,.0f} per night. "
                f"Your recommended nightly price is USD {suggested_price:,.0f}. "
                f"Demand signals suggest there may be room to charge a little more."
            )
        elif suggested_price < real_competitor_avg - decision_threshold:
            decision = tr("Lower price")
            decision_badge_class = "badge-red"
            decision_message = tr(
                f"The market average is about USD {real_competitor_avg:,.0f} per night. "
                f"Your recommended nightly price is USD {suggested_price:,.0f}. "
                f"A more competitive price may help avoid losing bookings."
            )
        else:
            decision = tr("Keep price stable")
            decision_badge_class = "badge-yellow"
            decision_message = tr(
                f"Your recommended nightly price is close to the current Airbnb competitor average of USD {real_competitor_avg:,.0f} per night."
            )

        # Build context line for the decision card
        context_parts = []
        if len(events_in_window) > 0:
            context_parts.append(
                tr(f"{len(events_in_window)} events detected for the selected dates")
            )
        if holiday_boost > 0:
            context_parts.append(tr("holiday demand boost active"))
        if weather_signal["label"] not in ["", "N/A"]:
            context_parts.append(tr(f"weather: {weather_signal['reason']}"))

        context_line = " · ".join(context_parts) if context_parts else tr("Normal demand conditions")

        # ---------------------------------------------------
        # ZONE 1 — DECISION CARD (the hero answer)
        # ---------------------------------------------------

        difference = suggested_price - real_competitor_avg
        difference_pct = safe_pct(difference, real_competitor_avg)
        direction = tr("below") if difference < 0 else tr("above")
        price_display = f"${suggested_price:,.0f}"
        
        st.markdown(
            f"""
            <div class="decision-card">
                <div class="decision-label">{tr("Recommended price per night")}</div>
                <div class="decision-price">{price_display}</div>
                <div class="decision-badge {decision_badge_class}">{decision}</div>
                <div class="context-line">
                    {decision_message}<br>
                    <span style="opacity:0.65;font-size:14px;">{context_line}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        with st.popover("ⓘ " + tr("What does this number mean?")):
            st.write(
                tr("This is the recommended nightly price. It is calculated from similar Airbnb competitor nightly prices, then adjusted for events, holidays, weather, and available competitor inventory.")
            )

        # ---------------------------------------------------
        # ZONE 2 — KEY NUMBERS (3 metrics only, clean)
        # ---------------------------------------------------

        kc1, kc2, kc3 = st.columns(3)

        kc1.metric(
            metric_label("Airbnb Avg (competitors)"),
            money(real_competitor_avg),
            help=tr("This is the average nightly price of the competitors selected for pricing. Think of it as: what similar places are charging per night.")
        )

        kc2.metric(
            metric_label("Your price vs market"),
            f"{abs(difference_pct):.1f}% {direction}",
            help=tr("This compares the recommended nightly price with the competitor average. If it is above, the recommendation is higher than the market average. If it is below, it is more competitive.")
        )

        kc3.metric(
            metric_label("Demand score"),
            f"{demand_score}/100",
            help=tr("This is a simple demand score from 0 to 100. Higher means the selected dates look stronger because of demand signals like events, holidays, weather, and limited competitor inventory.")
        )

        st.divider()

        # ---------------------------------------------------
        # ZONE 3 — EXPANDABLE DETAILS
        # ---------------------------------------------------

        # --- Expander: Why this recommendation ---
        with st.expander(f"💡 {tr('Why this recommendation?')}"):

            st.write(

                f"{tr('The recommended nightly price is')} "
                f"{money(suggested_price)}. "
                f"{tr('The comparable Airbnb average is')} "
                f"{money(real_competitor_avg)} "
                f"{tr('per night')}."
            )

            st.write(
            f"{tr('This means the recommendation is')} "
            f"{abs(difference_pct):.1f}% {direction} "
            f"{tr('the comparable market average')}."
            )

            if strong_competitors <= 5:
                market_comment = tr(
                    "Very few strong competitors remain available for these dates. This can mean demand is strong and there is less inventory."
                )
            elif strong_competitors <= 10:
                market_comment = tr(
                    "A moderate number of comparable competitors remain available. This suggests healthy demand."
                )
            else:
                market_comment = tr(
                    "Many comparable competitors are still available. This suggests softer demand and stronger competition."
                )

            st.write(
                tr("The system found")
                + f" **{strong_competitors}** "
                + tr("strong comparable competitors for the selected dates")
                + f". {market_comment}"
            )

            st.write(
                tr("It also found")
                + f" **{len(events_in_window)}** "
                + tr("unique events during the selected dates")
                + "."
            )

            st.write(
                tr("The recommendation stays close to the market average so the unit is not too expensive, but it still adjusts upward when demand signals are strong.")
            )

            st.caption(
                tr(f"Competitor scan from {selected_checkin.strftime('%b %d, %Y')} to {selected_checkout.strftime('%b %d, %Y')}")
            )

        # --- Expander: Demand details ---
        with st.expander(f"🧠 {tr('Demand intelligence')}"):

            holiday_pressure = classify_holiday_pressure(holiday_boost)

            d1, d2, d3, d4 = st.columns(4)

            d1.metric(
                metric_label("Events detected"),
                len(events_in_window),
                help=tr("This is the number of unique events found during the selected dates. Events can bring more travelers to Miami, so they may increase demand.")
            )

            d2.metric(
                metric_label("Available competitors"),
                len(competitor_df),
                help=tr("This is how many Airbnb competitors were found for the same dates. Fewer competitors usually means guests have fewer options.")
            )

            d3.metric(
                metric_label("Holiday impact"),
                holiday_pressure,
                help=tr("This shows if the selected dates include U.S. holidays. Low means no important holiday pressure. Medium means some holiday demand. High means the dates include stronger holiday travel demand.")
            )

            d4.metric(
                metric_label("Weather signal"),
                tr(weather_signal["label"]),
                help=tr("This summarizes how the forecast may affect beach demand. Strong means beach weather looks good. Moderate means weather is okay. Weak means rain, wind, or poor beach conditions could hurt demand. Neutral means weather is not pushing demand up or down.")
            )

            if len(events_in_window) > 0:
                with st.expander(f"📍 {tr('View event details')}"):
                    for event in events_in_window:
                        event_name = event.get("name", "Event")
                        event_date_str = event["dates"]["start"]["localDate"]
                        st.write(f"• {event_name} — {event_date_str}")

            if len(high_impact_events) > 0:
                with st.expander(f"🔥 {tr('High-impact demand drivers')}"):
                    for event_name in high_impact_events[:5]:
                        st.write(f"• {event_name}")

            if len(medium_impact_events) > 0:
                with st.expander(f"📌 {tr('Medium-impact demand drivers')}"):
                    for event_name in medium_impact_events[:5]:
                        st.write(f"• {event_name}")

            if len(holiday_events) > 0:
                with st.expander(f"🎁 {tr('View holiday details')}"):
                    for holiday in holiday_events:
                        st.write(f"• {holiday['name']} — {holiday['date']}")

            if len(events_in_window) == 0 and len(holiday_events) == 0:
                st.caption(tr("No major events or holidays detected for the selected dates."))

        # --- Expander: Booking urgency ---
        with st.expander(f"⚡ {tr('Booking urgency signal')}"):

            if strong_competitors <= 3 and demand_score >= 80:
                urgency_label = tr("Urgent: Raise prices now")
                urgency_message = tr(
                    "Very few strong competitors remain available and demand is high. This means similar places may be filling up, so there may be room to raise the price."
                )
            elif strong_competitors <= 6 and demand_score >= 70:
                urgency_label = tr("Monitor closely")
                urgency_message = tr(
                    "Demand looks healthy and comparable inventory is limited. Watch the market and consider a moderate increase if competitors stay high."
                )
            elif strong_competitors > 10:
                urgency_label = tr("Competitive pressure")
                urgency_message = tr(
                    "Many comparable competitors are still available. Be careful with overpricing because guests have many options."
                )
            else:
                urgency_label = tr("Stable market")
                urgency_message = tr(
                    "Market conditions look balanced. Keeping the price close to the competitor average is reasonable."
                )

            u1, u2 = st.columns(2)

            u1.metric(
                metric_label("Urgency"),
                urgency_label,
                help=tr("This tells you what action may make sense. Stable market means keep close to the market average. Monitor closely means watch competitors before changing. Competitive pressure means many options are available, so avoid overpricing. Urgent means demand looks strong and inventory is limited, so raising price may be reasonable.")
            )

            u2.metric(
                metric_label("Strong competitors"),
                strong_competitors,
                help=tr("These are the most relevant competitors used for pricing, such as Marenas, beachfront resorts, or similar Sunny Isles listings.")
            )

            st.caption(urgency_message)

        # --- Expander: Competitor overview ---
        with st.expander(f"🏠 {tr('Competitor overview')}"):

            m1, m2, m3, m4 = st.columns(4)

            m1.metric(
                metric_label("Avg competitor price"),
                money(avg_competitor_price),
                help=tr("This is the average total stay price among the competitors used for comparison. It covers all selected nights, not just one night.")
            )

            m2.metric(
                metric_label("Lowest price offered"),
                money(min_competitor_price),
                help=tr("This is the lowest total stay price found among the competitors for the selected dates.")
            )

            m3.metric(
                metric_label("Highest price offered"),
                money(max_competitor_price),
                help=tr("This is the highest total stay price found among the competitors for the selected dates.")
            )

            m4.metric(
                metric_label("Listings found"),
                len(competitor_df),
                help=tr("This is the number of Airbnb listings found by the scan for the selected dates.")
            )

            m5, _ = st.columns([1, 3])
            m5.metric(
                metric_label("Direct competitors"),
                len(direct_df),
                help=tr("These are listings that appear to be Marenas or very similar beachfront resort competitors.")
            )

            st.markdown(f"#### {tr('Competitor listings')}")
            with st.popover("ⓘ " + tr("What does relevance mean?")):
                st.write(tr("High relevance means the listing looks very similar or very close to Marenas. Medium relevance means it is useful for comparison but may not be exactly the same. Low relevance means it is less comparable. The score is a simple point system based on words like Marenas, resort, beachfront, ocean, condo, and Sunny Isles."))

            for idx, row in competitor_df.iterrows():

                # Save to Supabase
                try:
                    supabase.from_("competitor_snapshots").insert({
                        "competitor_name": row["Listing"],
                        "competitor_price": float(row["Competitor Price"]),
                        "source": "Airbnb"
                    }).execute()
                except:
                    pass

                with st.container(border=True):
                    col_a, col_b, col_c = st.columns([3, 1, 1])

                    with col_a:
                        st.markdown(f"### {row['Listing']}")
                        st.caption(tr("Sunny Isles Beach / Airbnb"))
                        direct_tag = tr("Direct competitor") if row["direct_competitor"] else tr("General market competitor")
                        fit_tag = "Qualified match" if row["qualified_competitor"] else "Partial match"
                        st.caption(
                            f"{tr('Relevance')}: {tr(row['Relevance'])} | "
                            f"{tr('Score')}: {row['Relevance Score']} | "
                            f"{direct_tag} | "
                            f"{fit_tag} | "
                            f"Fit score: {row['fit_score']} | "
                            f"{row['fit_reasons']}"
                        )
                        st.write(row["Summary"])

                        if isinstance(row["Link"], str) and row["Link"].startswith("http"):
                            st.link_button(tr("View on Airbnb"), row["Link"])

                    with col_b:
                        st.metric(
                            metric_label("Competitor price"),
                            money(row["Competitor Price"]),
                            help=tr("This is the total price shown by Airbnb for the full selected stay.")
                        )

                    with col_c:
                        st.metric(
                            metric_label("Price / night"),
                            money(row["Price per Night"]),
                            help=tr("This is the competitor total price divided by the number of selected nights.")
                        )

        # --- Expander: Daily pricing calendar ---
        with st.expander(f"📅 {tr('Daily pricing calendar')}"):

            suggested_nightly_price = suggested_price
            calendar_rows = []
            calendar_dates = pd.date_range(selected_checkin, selected_checkout - timedelta(days=1))

            for day in calendar_dates:
                day_date = day.date()
                day_name = day.strftime("%A")
                daily_price = suggested_nightly_price
                daily_reasons = []

                if day_date.weekday() in [4, 5]:
                    daily_price *= 1.12
                    daily_reasons.append(tr("Weekend premium"))

                holidays_today = [h["name"] for h in holiday_events if h["date"] == day_date]
                if len(holidays_today) > 0:
                    daily_price *= 1.15
                    daily_reasons.append(tr("Holiday demand"))

                events_today = []
                for event in events_in_window:
                    try:
                        ev_date = pd.to_datetime(event["dates"]["start"]["localDate"]).date()
                        if ev_date == day_date:
                            events_today.append(event.get("name", "Event"))
                    except:
                        pass

                if len(events_today) > 0:
                    daily_price *= 1.10
                    daily_reasons.append(tr("Event demand"))

                weather_note = tr("Not available")
                if not weather_df.empty:
                    weather_day = weather_df[weather_df["time"] == day_date]
                    if len(weather_day) > 0:
                        rain_prob = weather_day.iloc[0]["precipitation_probability_max"]
                        temp_max = weather_day.iloc[0]["temperature_2m_max"]
                        weather_note = f"{temp_max:.0f}°F / {tr('Rain')} {rain_prob:.0f}%"
                        if rain_prob >= 65:
                            daily_price *= 0.92
                            daily_reasons.append(tr("Rain risk"))
                        elif rain_prob <= 30 and temp_max >= 78:
                            daily_price *= 1.05
                            daily_reasons.append(tr("Good beach weather"))

                calendar_rows.append({
                    tr("Date"): day_date,
                    tr("Day"): tr(day_name),
                    tr("Recommended Nightly Price"): round(daily_price),
                    tr("Holiday"): ", ".join(holidays_today) if holidays_today else "",
                    tr("Events"): ", ".join(events_today[:2]) if events_today else "",
                    tr("Weather"): weather_note,
                    tr("Reason"): ", ".join(daily_reasons) if daily_reasons else tr("Normal demand"),
                })

            daily_calendar_df = pd.DataFrame(calendar_rows)
            st.dataframe(daily_calendar_df, use_container_width=True, hide_index=True)

    else:
        st.warning(tr("No competitor listings detected. Try adjusting the dates."))

# ---------------------------------------------------
# HISTORICAL MARKET ANALYTICS — always visible below
# ---------------------------------------------------

with st.expander(f"📈 {tr('Market trend analytics')}"):

    with st.popover("ⓘ " + tr("How to read this chart")):
        st.write(tr("This chart shows the average competitor price saved each time you scanned the market. It helps you see if the market is getting more expensive or cheaper over time."))

    try:
        historical = supabase.from_("competitor_snapshots").select("*").execute()
        historical_data = historical.data

        if len(historical_data) > 0:
            historical_df = pd.DataFrame(historical_data)
            historical_df["created_at"] = pd.to_datetime(historical_df["created_at"])
            historical_df["Date"] = historical_df["created_at"].dt.date

            trend_df = historical_df.groupby("Date")["competitor_price"].mean().reset_index()

            trend_fig = px.line(
                trend_df,
                x="Date",
                y="competitor_price",
                markers=True,
                title=tr("Average Competitor Pricing Trend")
            )

            trend_fig.update_layout(
                xaxis_title=tr("Date"),
                yaxis_title=tr("Average competitor price")
            )

            st.plotly_chart(trend_fig, use_container_width=True)

            if len(trend_df) >= 2:
                latest_price = trend_df.iloc[-1]["competitor_price"]
                previous_price = trend_df.iloc[-2]["competitor_price"]
                price_change = latest_price - previous_price
                price_change_pct = (price_change / previous_price) * 100

                st.markdown(f"#### {tr('Market signals engine')}")

                s1, s2, s3 = st.columns(3)

                s1.metric(
                    metric_label("Latest saved market average"),
                    money(latest_price),
                    help=tr("This is the newest average competitor price saved after the most recent scan.")
                )

                s2.metric(
                    metric_label("Previous saved market average"),
                    money(previous_price),
                    help=tr("This is the average competitor price from the scan before the latest one.")
                )

                s3.metric(
                    metric_label("Market momentum"),
                    f"{price_change_pct:.1f}%",
                    help=tr("This shows how much the market average changed between the last two scans. A positive number means competitors became more expensive. A negative number means competitors became cheaper.")
                )

                st.caption(
                    tr("Use this only as a trend signal. If the last scan was for different dates, the comparison may not be perfect.")
                )

            else:
                st.caption(tr("More historical scans are needed to calculate market momentum."))

        else:
            st.caption(tr("No historical competitor data yet."))

    except Exception as e:
        st.warning(tr(f"Trend analytics unavailable: {e}"))

# ---------------------------------------------------
# SIDEBAR
# ---------------------------------------------------

with st.sidebar:

    st.markdown(
        """<div class="sidebar-logo"><span>Marritta AI</span></div>""",
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <div class="sidebar-card">
            <div style="font-size:18px;font-weight:800;margin-bottom:8px;">Revenue Intelligence</div>
            <div style="font-size:13px;line-height:1.5;">
                {tr("Daily pricing support using Airbnb competitors, Miami events, weather, holidays, and market demand signals.")}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(f"### {tr('Navigation')}")
    st.markdown(f"• {tr('Select dates & analyze')}")
    st.markdown(f"• {tr('Recommended price')}")
    st.markdown(f"• {tr('Demand intelligence')}")
    st.markdown(f"• {tr('Booking urgency')}")
    st.markdown(f"• {tr('Competitor overview')}")
    st.markdown(f"• {tr('Daily pricing calendar')}")
    st.markdown(f"• {tr('Market trends')}")

    st.divider()

    st.markdown(f"### {tr('Data sources')}")
    st.markdown(f'<div class="sidebar-status">✅ {tr("Airbnb competitor scan active")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-status">✅ {tr("Miami events API active")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-status">✅ {tr("Weather forecast active")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-status">✅ {tr("Supabase database active")}</div>', unsafe_allow_html=True)

    st.divider()

    st.caption(tr("The system uses live market data for all recommendations."))

    if st.button(tr("Sign out")):
        st.session_state.logged_in = False
        st.rerun()

    st.divider()
