"""
Victorian Crime Correlations Dashboard
=======================================
Fetches Victorian crime data and overlays with public datasets:
  - Weather (Open-Meteo ERA5)
  - Unemployment (ABS Data API)
  - CPI / Inflation (ABS Data API)
  - Moon phases (ephem library)
  - Population (ABS / hardcoded interpolation)
  - Victoria liquor licences (Data Vic)
  - School holidays (calculated)

Run:
    pip install dash plotly pandas requests numpy scipy ephem
    python RandomCorrelations.py

IMPORTANT — Crime data must be downloaded manually:
  1. Go to: https://www.crimestatistics.vic.gov.au/crime-statistics/latest-victorian-crime-data/download-data
  2. Download: "Data Tables Criminal Incidents Visualisation Year Ending September 2024"
  3. Save as: crime_data.xlsx  in the same folder as this script
"""

import os
import time
import warnings
import requests
import pandas as pd
import numpy as np
import dash
from dash import dcc, html, Input, Output, dash_table
import plotly.graph_objects as go
from scipy import stats
import json

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(SCRIPT_DIR, "crime_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CRIME_FILE = os.path.join(SCRIPT_DIR, "crime_data.xlsx")

# ─────────────────────────────────────────────────────────────────────────────
# COLOURS  (same palette as weather dashboard)
# ─────────────────────────────────────────────────────────────────────────────
BG        = "#1A1A1A"
CARD      = "#242424"
ACCENT    = "#D4A853"
ACCENT2   = "#7EB8C9"
ACCENT3   = "#C4956A"
ACCENT4   = "#6B8F71"
TEXT_MAIN = "#F0EAD6"
TEXT_DIM  = "#8A8070"
RED       = "#C0392B"
PURPLE    = "#8E6BB5"

PALETTE = [ACCENT, ACCENT2, ACCENT3, ACCENT4, RED, PURPLE,
           "#E8A598", "#7FB3D3", "#A9C4A0", "#D4B896"]

PLOT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Georgia, serif", color=TEXT_MAIN, size=13),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_DIM)),
    hovermode="x unified",
    hoverlabel=dict(namelength=-1, font=dict(family="Georgia, serif", size=12)),
)

def axis(title="", **kwargs):
    return dict(title=title, gridcolor="#3A3530", zerolinecolor="#3A3530",
                tickfont=dict(color=TEXT_DIM), **kwargs)

LABEL_STYLE = {"fontSize": "0.7rem", "color": TEXT_DIM, "textTransform": "uppercase",
               "letterSpacing": "0.1em", "marginBottom": "6px", "display": "block"}

def card(children, border_color=ACCENT):
    return html.Div(children, style={
        "background": CARD, "borderRadius": "10px", "padding": "16px 20px",
        "borderLeft": f"4px solid {border_color}", "marginBottom": "14px"
    })

def kpi(title, value, subtitle="", color=ACCENT):
    return html.Div([
        html.P(title, style={"margin": 0, "fontSize": "0.68rem", "color": TEXT_DIM,
                             "textTransform": "uppercase", "letterSpacing": "0.08em"}),
        html.H2(value, style={"margin": "4px 0", "fontSize": "1.7rem",
                              "color": color, "fontFamily": "Georgia, serif"}),
        html.P(subtitle, style={"margin": 0, "fontSize": "0.65rem", "color": TEXT_DIM}),
    ], style={"background": CARD, "borderRadius": "10px", "padding": "14px 18px",
              "borderLeft": f"4px solid {color}", "flex": "1", "minWidth": "140px"})

# ─────────────────────────────────────────────────────────────────────────────
# ① CRIME DATA LOADER
# ─────────────────────────────────────────────────────────────────────────────
def load_crime_data():
    cache = os.path.join(CACHE_DIR, "crime_annual.csv")
    if os.path.exists(cache):
        print("  Loading crime data from cache...")
        return pd.read_csv(cache)

    if not os.path.exists(CRIME_FILE):
        print("  ⚠️  Crime data file not found — using synthetic data.")
        return make_synthetic_crime()

    print("  Parsing real crime data from Excel...")
    try:
        df = pd.read_excel(CRIME_FILE, sheet_name="Table 01", header=0)

        # Summarise by year and offence division
        annual = df.groupby(["Year", "Offence Division"])["Incidents Recorded"].sum().reset_index()
        pivot = annual.pivot(index="Year", columns="Offence Division",
                             values="Incidents Recorded").reset_index()
        pivot.columns.name = None

        col_map = {
            "Year": "year",
            "A Crimes against the person": "crimes_against_person",
            "B Property and deception offences": "property_crime",
            "C Drug offences": "drug_offences",
            "D Public order and security offences": "public_order",
            "E Justice procedures offences": "justice_offences",
            "F Other offences": "other_offences",
        }
        pivot = pivot.rename(columns=col_map)
        pivot["total_incidents"] = pivot[[c for c in pivot.columns if c != "year"]].sum(axis=1)
        pivot = pivot.sort_values("year").reset_index(drop=True)
        pivot.to_csv(cache, index=False)
        print(f"    ✓ Parsed {len(pivot)} years of real crime data ({int(pivot['year'].min())}–{int(pivot['year'].max())})")
        return pivot
    except Exception as e:
        print(f"  Error parsing crime file: {e}\n  Using synthetic data.")
        return make_synthetic_crime()

    print("  Parsing real crime data from Excel...")
    try:
        df = pd.read_excel(CRIME_FILE, sheet_name="Table 01", header=0)
        df.columns = ["year", "year_ending", "offence_division",
                      "offence_subdivision", "offence_subgroup",
                      "incidents", "rate_per_100k"]

        # Summarise by year and offence division
        annual = df.groupby(["year", "offence_division"])["incidents"].sum().reset_index()
        pivot = annual.pivot(index="year", columns="offence_division",
                             values="incidents").reset_index()

        # Rename columns cleanly
        pivot.columns.name = None
        col_map = {
            "year": "year",
            "A Crimes against the person": "crimes_against_person",
            "B Property and deception offences": "property_crime",
            "C Drug offences": "drug_offences",
            "D Public order and security offences": "public_order",
            "E Justice procedures offences": "justice_offences",
            "F Other offences": "other_offences",
        }
        pivot = pivot.rename(columns=col_map)
        pivot["total_incidents"] = pivot[[c for c in pivot.columns if c != "year"]].sum(axis=1)
        pivot = pivot.sort_values("year").reset_index(drop=True)
        pivot.to_csv(cache, index=False)
        print(f"    ✓ Parsed {len(pivot)} years of real crime data ({int(pivot['year'].min())}–{int(pivot['year'].max())})")
        return pivot
    except Exception as e:
        print(f"  Error parsing crime file: {e}\n  Using synthetic data.")
        return make_synthetic_crime()

    if not os.path.exists(CRIME_FILE):
        print(f"\n  ⚠️  Crime data file not found at: {CRIME_FILE}")
        print("  Using SYNTHETIC demo data so the dashboard still runs.")
        print("  Download the real file from crimestatistics.vic.gov.au\n")
        return make_synthetic_crime()

    print("  Parsing crime data from Excel...")
    try:
        xl = pd.ExcelFile(CRIME_FILE)
        # Try to find the right sheet — usually 'Table 01' or similar
        sheet = None
        for s in xl.sheet_names:
            if any(x in s.lower() for x in ["table 01", "table01", "criminal incident", "year"]):
                sheet = s
                break
        if sheet is None:
            sheet = xl.sheet_names[0]

        raw = pd.read_excel(CRIME_FILE, sheet_name=sheet, header=None)

        # Find rows that look like year data (contain a 4-digit year)
        records = []
        for i, row in raw.iterrows():
            for j, val in enumerate(row):
                if isinstance(val, (int, float)) and 2000 <= val <= 2030:
                    year = int(val)
                    # Try to grab numeric values from remaining cols
                    nums = [x for x in row[j+1:] if isinstance(x, (int, float)) and x > 100]
                    if nums:
                        records.append({"year": year, "total_incidents": nums[0]})
                    break

        if records:
            df = pd.DataFrame(records).drop_duplicates("year").sort_values("year")
            df.to_csv(cache, index=False)
            return df
        else:
            print("  Could not auto-parse Excel — using synthetic data.")
            return make_synthetic_crime()
    except Exception as e:
        print(f"  Error reading crime file: {e}\n  Using synthetic data.")
        return make_synthetic_crime()


def make_synthetic_crime():
    """Realistic-looking synthetic Victorian crime data 2004–2023."""
    np.random.seed(42)
    years = list(range(2004, 2024))
    # Rough shape: rises to ~600k in 2016, dips with COVID, rises again
    base = [440, 455, 470, 488, 500, 510, 525, 540, 558, 570,
            582, 590, 598, 588, 570, 490, 430, 460, 480, 495]
    noise = np.random.normal(0, 5, len(years))
    totals = [int((b + n) * 1000) for b, n in zip(base, noise)]

    # Break into offence categories
    df = pd.DataFrame({
        "year": years,
        "total_incidents": totals,
        "crimes_against_person": [int(t * 0.18) for t in totals],
        "property_crime": [int(t * 0.42) for t in totals],
        "drug_offences": [int(t * 0.09) for t in totals],
        "public_order": [int(t * 0.14) for t in totals],
        "other_offences": [int(t * 0.17) for t in totals],
    })
    cache = os.path.join(CACHE_DIR, "crime_annual.csv")
    df.to_csv(cache, index=False)
    return df

# ─────────────────────────────────────────────────────────────────────────────
# ② WEATHER DATA  (Open-Meteo, annual averages for Melbourne)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_weather_annual():
    cache = os.path.join(CACHE_DIR, "weather_annual.csv")
    if os.path.exists(cache):
        print("  Loading weather from cache...")
        return pd.read_csv(cache)

    print("  Fetching weather data from Open-Meteo...")
    url = "https://archive-api.open-meteo.com/v1/archive"
    all_daily = []

    for yr_start in range(2004, 2024, 5):
        yr_end = min(yr_start + 4, 2023)
        params = {
            "latitude": -37.8136, "longitude": 144.9631,
            "start_date": f"{yr_start}-01-01",
            "end_date": f"{yr_end}-12-31",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
            "timezone": "Australia/Melbourne",
        }
        for attempt in range(4):
            try:
                r = requests.get(url, params=params, timeout=60)
                r.raise_for_status()
                d = r.json()
                df = pd.DataFrame(d["daily"])
                df["time"] = pd.to_datetime(df["time"])
                all_daily.append(df)
                print(f"    ✓ Weather {yr_start}–{yr_end}")
                time.sleep(6)
                break
            except Exception as e:
                print(f"    Retry {attempt+1}: {e}")
                time.sleep(15)

    daily = pd.concat(all_daily, ignore_index=True)
    daily["year"] = daily["time"].dt.year
    annual = daily.groupby("year").agg(
        avg_max_temp=("temperature_2m_max", "mean"),
        avg_min_temp=("temperature_2m_min", "mean"),
        total_rainfall=("precipitation_sum", "sum"),
        avg_max_wind=("windspeed_10m_max", "mean"),
        hot_days=("temperature_2m_max", lambda x: (x >= 35).sum()),
        cold_days=("temperature_2m_min", lambda x: (x <= 5).sum()),
        rain_days=("precipitation_sum", lambda x: (x >= 0.2).sum()),
    ).reset_index()

    annual.to_csv(cache, index=False)
    return annual

# ─────────────────────────────────────────────────────────────────────────────
# ③ ABS DATA  (unemployment + CPI via free ABS Data API)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_abs_unemployment():
    cache = os.path.join(CACHE_DIR, "unemployment_annual.csv")
    if os.path.exists(cache):
        print("  Loading unemployment from cache...")
        return pd.read_csv(cache)

    print("  Fetching Victoria unemployment from ABS Data API...")
    # LF dataflow — Victoria (state code 2), unemployment rate, seasonally adjusted
    # ABS Data API — no API key needed
    url = ("https://data.api.abs.gov.au/rest/data/LF/M2.2.1599.20.Q"
           "?startPeriod=2004-Q1&endPeriod=2023-Q4&format=jsondata")
    try:
        r = requests.get(url, timeout=30,
                         headers={"Accept": "application/vnd.sdmx.data+json"})
        r.raise_for_status()
        data = r.json()
        series = data["data"]["dataSets"][0]["series"]
        obs_list = []
        for key, val in series.items():
            for period_idx, obs in val["observations"].items():
                obs_list.append({"period_idx": int(period_idx), "value": obs[0]})

        # Build time index from structure
        time_periods = data["data"]["structure"]["dimensions"]["observation"][0]["values"]
        period_map = {i: v["id"] for i, v in enumerate(time_periods)}
        df = pd.DataFrame(obs_list)
        df["period"] = df["period_idx"].map(period_map)
        df["year"] = df["period"].str[:4].astype(int)
        annual = df.groupby("year")["value"].mean().reset_index()
        annual.columns = ["year", "vic_unemployment_rate"]
        annual.to_csv(cache, index=False)
        print("    ✓ Unemployment data fetched")
        return annual
    except Exception as e:
        print(f"    ABS unemployment API failed: {e}\n    Using synthetic data.")
        return make_synthetic_unemployment()


def make_synthetic_unemployment():
    years = list(range(2004, 2024))
    # Realistic Vic unemployment rates
    rates = [5.4, 5.2, 4.8, 4.5, 4.4, 5.6, 5.1, 5.0, 5.5, 6.0,
             6.1, 5.9, 5.8, 5.5, 5.3, 7.1, 6.5, 4.8, 3.8, 3.6]
    df = pd.DataFrame({"year": years, "vic_unemployment_rate": rates})
    df.to_csv(os.path.join(CACHE_DIR, "unemployment_annual.csv"), index=False)
    return df


def fetch_abs_cpi():
    cache = os.path.join(CACHE_DIR, "cpi_annual.csv")
    if os.path.exists(cache):
        print("  Loading CPI from cache...")
        return pd.read_csv(cache)

    print("  Fetching CPI from ABS Data API...")
    url = ("https://data.api.abs.gov.au/rest/data/CPI/1.10001.10.50.Q"
           "?startPeriod=2004-Q1&endPeriod=2023-Q4&format=jsondata")
    try:
        r = requests.get(url, timeout=30,
                         headers={"Accept": "application/vnd.sdmx.data+json"})
        r.raise_for_status()
        data = r.json()
        series = data["data"]["dataSets"][0]["series"]
        obs_list = []
        for key, val in series.items():
            for period_idx, obs in val["observations"].items():
                obs_list.append({"period_idx": int(period_idx), "value": obs[0]})

        time_periods = data["data"]["structure"]["dimensions"]["observation"][0]["values"]
        period_map = {i: v["id"] for i, v in enumerate(time_periods)}
        df = pd.DataFrame(obs_list)
        df["period"] = df["period_idx"].map(period_map)
        df["year"] = df["period"].str[:4].astype(int)
        annual = df.groupby("year")["value"].mean().reset_index()
        annual.columns = ["year", "cpi_index"]
        # Calculate annual % change
        annual["cpi_pct_change"] = annual["cpi_index"].pct_change() * 100
        annual.to_csv(cache, index=False)
        print("    ✓ CPI data fetched")
        return annual
    except Exception as e:
        print(f"    ABS CPI API failed: {e}\n    Using synthetic data.")
        return make_synthetic_cpi()

def fetch_vic_retail_trade():
    cache = os.path.join(CACHE_DIR, "retail_trade_annual.csv")
    if os.path.exists(cache):
        print("  Loading retail trade from cache...")
        return pd.read_csv(cache)

    print("  Fetching Victorian retail trade from ABS Data API...")
    # ABS Retail Trade dataflow - Victoria (state=2), total retail, seasonally adjusted
    url = ("https://data.api.abs.gov.au/rest/data/RT/M2..TOT.20"
           "?startPeriod=2016-01&endPeriod=2025-12&format=jsondata")
    try:
        r = requests.get(url, timeout=30,
                         headers={"Accept": "application/vnd.sdmx.data+json",
                                  "User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        series = data["data"]["dataSets"][0]["series"]
        obs_list = []
        for key, val in series.items():
            for period_idx, obs in val["observations"].items():
                obs_list.append({"period_idx": int(period_idx), "value": obs[0]})

        time_periods = data["data"]["structure"]["dimensions"]["observation"][0]["values"]
        period_map = {i: v["id"] for i, v in enumerate(time_periods)}
        df = pd.DataFrame(obs_list)
        df["period"] = df["period_idx"].map(period_map)
        df["year"] = df["period"].str[:4].astype(int)
        annual = df.groupby("year")["value"].sum().reset_index()
        annual.columns = ["year", "vic_retail_turnover_m"]
        annual = annual[annual["year"].between(2016, 2025)]
        annual.to_csv(cache, index=False)
        print("    ✓ Victorian retail trade fetched")
        return annual
    except Exception as e:
        print(f"    ABS retail trade API failed: {e}\n    Using synthetic data.")
        years = list(range(2016, 2024))
        # Realistic Vic monthly retail turnover summed annually ($M)
        turnover = [74200, 76800, 79100, 81500, 71200, 83400, 91600, 95800]
        df = pd.DataFrame({"year": years, "vic_retail_turnover_m": turnover})
        df.to_csv(cache, index=False)
        return df

def make_synthetic_cpi():
    years = list(range(2004, 2024))
    changes = [2.4, 3.0, 3.5, 2.3, 4.4, 1.8, 2.8, 3.4, 2.2, 2.5,
               2.9, 2.5, 1.5, 1.8, 1.9, 0.9, 3.5, 3.5, 7.8, 5.4]
    df = pd.DataFrame({"year": years, "cpi_pct_change": changes})
    df.to_csv(os.path.join(CACHE_DIR, "cpi_annual.csv"), index=False)
    return df

# ─────────────────────────────────────────────────────────────────────────────
# ④ MOON PHASES  (calculated via ephem or fallback formula)
# ─────────────────────────────────────────────────────────────────────────────
def calc_moon_phases():
    cache = os.path.join(CACHE_DIR, "moon_annual.csv")
    if os.path.exists(cache):
        print("  Loading moon data from cache...")
        return pd.read_csv(cache)

    print("  Calculating moon phases...")
    try:
        import ephem
        records = []
        for year in range(2004, 2024):
            full_moons = 0
            d = ephem.Date(f"{year}/1/1")
            end = ephem.Date(f"{year+1}/1/1")
            while d < end:
                d = ephem.next_full_moon(d)
                if ephem.Date(f"{year}/1/1") <= d < ephem.Date(f"{year+1}/1/1"):
                    full_moons += 1
                d = ephem.Date(d + 1)
            records.append({"year": year, "full_moons_count": full_moons,
                            "has_blue_moon": 1 if full_moons == 13 else 0})
        df = pd.DataFrame(records)
    except ImportError:
        print("    ephem not installed — using standard lunar calendar.")
        # Standard: most years have 12 full moons, ~every 2.7 years have 13
        years = list(range(2004, 2024))
        blue_moon_years = {2004, 2007, 2010, 2012, 2015, 2018, 2020, 2023}
        df = pd.DataFrame({
            "year": years,
            "full_moons_count": [13 if y in blue_moon_years else 12 for y in years],
            "has_blue_moon": [1 if y in blue_moon_years else 0 for y in years],
        })

    df.to_csv(cache, index=False)
    return df

# ─────────────────────────────────────────────────────────────────────────────
# ⑤ VICTORIAN POPULATION  (ABS Census interpolated)
# ─────────────────────────────────────────────────────────────────────────────
def get_vic_population():
    cache = os.path.join(CACHE_DIR, "population_annual.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache)

    print("  Building Victoria population estimates...")
    # ABS ERP Victoria — census anchor points with linear interpolation
    anchors = {
        2004: 4_934_000, 2006: 5_126_000, 2011: 5_574_000,
        2016: 6_039_000, 2021: 6_504_000, 2023: 6_830_000,
    }
    years = list(range(2004, 2024))
    pops = []
    anchor_years = sorted(anchors.keys())
    for y in years:
        # Find surrounding anchors
        lo = max([a for a in anchor_years if a <= y], default=anchor_years[0])
        hi = min([a for a in anchor_years if a >= y], default=anchor_years[-1])
        if lo == hi:
            pops.append(anchors[lo])
        else:
            frac = (y - lo) / (hi - lo)
            pops.append(int(anchors[lo] + frac * (anchors[hi] - anchors[lo])))

    df = pd.DataFrame({"year": years, "vic_population": pops})
    df.to_csv(cache, index=False)
    return df

# ─────────────────────────────────────────────────────────────────────────────
# ⑥ SCHOOL HOLIDAYS  (approximate — Victorian school terms)
# ─────────────────────────────────────────────────────────────────────────────
def get_school_holidays():
    # Victoria has ~4 terms per year, with holidays between
    # We count approximate holiday weeks per year (~14 weeks typical)
    years = list(range(2004, 2024))
    # COVID years had unusual arrangements
    holiday_weeks = [14] * len(years)
    for i, y in enumerate(years):
        if y == 2020: holiday_weeks[i] = 20  # extended due to COVID
        if y == 2021: holiday_weeks[i] = 18
    return pd.DataFrame({"year": years, "school_holiday_weeks": holiday_weeks})

# ─────────────────────────────────────────────────────────────────────────────
# ⑦ LIQUOR LICENCES  (Data Vic — approximate annual counts)
# ─────────────────────────────────────────────────────────────────────────────
def get_liquor_licences():
    cache = os.path.join(CACHE_DIR, "liquor_annual.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache)

    print("  Fetching liquor licence data from Data Vic...")
    try:
        # Current snapshot from Data Vic — approximate historical counts
        url = "https://discover.data.vic.gov.au/api/3/action/datastore_search?resource_id=d44d0e20-e5df-4af5-ae0b-9f6048e3e6e6&limit=100000"
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        if data.get("success"):
            records = data["result"]["records"]
            df = pd.DataFrame(records)
            # Try to extract year from date column
            for col in df.columns:
                if "date" in col.lower() or "year" in col.lower():
                    try:
                        df["year"] = pd.to_datetime(df[col], errors="coerce").dt.year
                        annual = df.groupby("year").size().reset_index(name="liquor_licences")
                        annual = annual[annual["year"].between(2004, 2023)]
                        annual.to_csv(cache, index=False)
                        return annual
                    except Exception:
                        pass
    except Exception as e:
        print(f"    Liquor licence API failed: {e}")

    # Fallback: estimated annual counts based on known trends
    years = list(range(2004, 2024))
    licences = [17000, 17400, 17800, 18100, 18500, 18800, 19100, 19500, 19900, 20200,
                20500, 20900, 21200, 21500, 21700, 20800, 20500, 21000, 21400, 21800]
    df = pd.DataFrame({"year": years, "liquor_licences": licences})
    df.to_csv(cache, index=False)
    return df

# ─────────────────────────────────────────────────────────────────────────────
# ⑧ MERGE ALL DATA
# ─────────────────────────────────────────────────────────────────────────────
def build_master_df(crime, weather, unemployment, cpi, retail, moon, population,
                    school_holidays, liquor):
    df = crime.copy()
    for other in [weather, unemployment, cpi, retail, moon, population,
                  school_holidays, liquor]:
        if "year" in other.columns:
            df = df.merge(other, on="year", how="left")

    # Derived columns
    if "vic_population" in df.columns and "total_incidents" in df.columns:
        df["crime_rate_per_100k"] = df["total_incidents"] / df["vic_population"] * 100_000

    # Year-on-year change columns
    for col in ["total_incidents", "crimes_against_person", "property_crime",
                "drug_offences", "public_order"]:
        if col in df.columns:
            df[col + "_yoy"] = df[col].pct_change() * 100

    return df.sort_values("year").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# ⑨ CORRELATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────
CRIME_VARS = {
    "total_incidents": "Total Criminal Incidents",
    "crimes_against_person": "Crimes Against Person",
    "property_crime": "Property Crime",
    "drug_offences": "Drug Offences",
    "public_order": "Public Order Offences",
    "crime_rate_per_100k": "Crime Rate per 100k Population",
    "total_incidents_yoy": "Total Incidents — YoY Change (%)",
    "crimes_against_person_yoy": "Crimes Against Person — YoY Change (%)",
    "property_crime_yoy": "Property Crime — YoY Change (%)",
    "drug_offences_yoy": "Drug Offences — YoY Change (%)",
    "public_order_yoy": "Public Order — YoY Change (%)",
}

PREDICTOR_VARS = {
    "avg_max_temp": "Avg Max Temperature (°C)",
    "avg_min_temp": "Avg Min Temperature (°C)",
    "total_rainfall": "Total Annual Rainfall (mm)",
    "hot_days": "Hot Days (≥35°C)",
    "cold_days": "Cold Days (≤5°C)",
    "rain_days": "Rain Days (≥0.2mm)",
    "avg_max_wind": "Avg Max Wind Speed (km/h)",
    "vic_unemployment_rate": "Victoria Unemployment Rate (%)",
    "cpi_pct_change": "CPI Annual Change (%)",
    "full_moons_count": "Full Moons Per Year",
    "has_blue_moon": "Blue Moon Year (0/1)",
    "vic_population": "Victoria Population",
    "school_holiday_weeks": "School Holiday Weeks",
    "liquor_licences": "Liquor Licences (est.)",
    "vic_retail_turnover_m": "Vic Retail Turnover ($M annual)",
}

def compute_correlations(df, crime_var):
    df = df.copy()
    # Also compute year-on-year change version
    if crime_var in df.columns:
        df[crime_var + "_yoy"] = df[crime_var].pct_change() * 100

    results = []
    for var, label in PREDICTOR_VARS.items():
        if var not in df.columns:
            continue
        sub = df[[crime_var, var]].dropna()
        if len(sub) < 5:
            continue
        try:
            r, p = stats.pearsonr(sub[crime_var], sub[var])
            rs, ps = stats.spearmanr(sub[crime_var], sub[var])
            results.append({
                "variable": label,
                "col": var,
                "pearson_r": round(r, 3),
                "pearson_p": round(p, 4),
                "spearman_r": round(rs, 3),
                "spearman_p": round(ps, 4),
                "abs_r": abs(r),
                "n": len(sub),
            })
        except Exception:
            pass
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results).sort_values("abs_r", ascending=False)

# ─────────────────────────────────────────────────────────────────────────────
# LOAD ALL DATA
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "═"*60)
print("  Victorian Crime Correlations Dashboard")
print("  Loading and fetching data...")
print("═"*60)

crime_df      = load_crime_data()
weather_df    = fetch_weather_annual()
unemp_df      = fetch_abs_unemployment()
cpi_df        = fetch_abs_cpi()
retail_df     = fetch_vic_retail_trade()
moon_df       = calc_moon_phases()
pop_df        = get_vic_population()
school_df     = get_school_holidays()
liquor_df     = get_liquor_licences()

master = build_master_df(crime_df, weather_df, unemp_df, cpi_df,
                          retail_df, moon_df, pop_df, school_df, liquor_df) 

print(f"\n  ✓ Master dataset: {len(master)} years × {len(master.columns)} variables")
print("  Starting dashboard...\n")

# Available crime columns (only those present)
available_crime_vars = {k: v for k, v in CRIME_VARS.items() if k in master.columns}
available_pred_vars  = {k: v for k, v in PREDICTOR_VARS.items() if k in master.columns}

YEAR_MIN = int(master["year"].min())
YEAR_MAX = int(master["year"].max())

# ─────────────────────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────────────────────
app = dash.Dash(__name__, title="Victorian Crime Correlations")

app.index_string = """<!DOCTYPE html>
<html>
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<style>
  body { margin: 0; }
  .Select-control, .Select--single > .Select-control {
    background-color: #1A1A1A !important;
    border: 1px solid #555 !important;
  }
  .Select-value-label, .Select-single-value {
    color: #B0B0B0 !important;
    background-color: #1A1A1A !important;
  }
  .Select-placeholder { color: #777 !important; }
  .Select-input > input { color: #B0B0B0 !important; background: #1A1A1A !important; }
  .Select-arrow { border-top-color: #B0B0B0 !important; }
  .Select-menu-outer { background: #1A1A1A !important; border: 1px solid #555 !important; z-index:9999!important; }
  .Select-option { background: #1A1A1A !important; color: #B0B0B0 !important; }
  .Select-option.is-focused { background: #333 !important; color: #D4A853 !important; }
  .Select-option.is-selected { background: #2A2A2A !important; color: #D4A853 !important; font-weight:bold!important; }
</style>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""

server = app.server
app.config.suppress_callback_exceptions = True

crime_options = [{"label": v, "value": k} for k, v in available_crime_vars.items()]
pred_options  = [{"label": v, "value": k} for k, v in available_pred_vars.items()]

app.layout = html.Div([

    # ── Header ──────────────────────────────────────────────────────────────
    html.Div([
        html.Div([
            html.Span("🔍", style={"fontSize": "1.4rem", "marginRight": "10px"}),
            html.Span("Victorian Crime — Correlation Explorer",
                      style={"fontSize": "1.2rem", "fontWeight": "700",
                             "fontFamily": "Georgia, serif", "color": TEXT_MAIN}),
        ], style={"display": "flex", "alignItems": "center"}),
        html.P("Crime Statistics Agency Victoria · ABS · Open-Meteo · 2004–2023",
               style={"margin": 0, "fontSize": "0.72rem", "color": TEXT_DIM}),
    ], style={
        "background": CARD, "padding": "14px 32px",
        "display": "flex", "justifyContent": "space-between", "alignItems": "center",
        "borderBottom": f"2px solid {ACCENT}", "position": "sticky", "top": 0, "zIndex": 999,
    }),

    html.Div([

        # ── Sidebar ─────────────────────────────────────────────────────────
        html.Div([
            html.Span("Controls", style={"fontSize": "0.65rem", "color": ACCENT,
                "textTransform": "uppercase", "letterSpacing": "0.15em", "fontWeight": "700"}),
            html.Hr(style={"borderColor": "#3A3530", "margin": "8px 0"}),

            html.Label("Crime Measure", style=LABEL_STYLE),
            dcc.Dropdown(id="crime-var", options=crime_options,
                         value=crime_options[0]["value"], clearable=False,
                         style={"color": "#B0B0B0"}),

            html.Br(),
            html.Label("Compare With", style=LABEL_STYLE),
            dcc.Dropdown(id="pred-var", options=pred_options,
                         value=pred_options[0]["value"], clearable=False,
                         style={"color": "#B0B0B0"}),

            html.Br(),
            html.Label("Year Range", style=LABEL_STYLE),
            html.Div([
                html.Div([
                    html.Span("From", style={"fontSize": "0.62rem", "color": TEXT_DIM,
                              "marginBottom": "4px", "display": "block"}),
                    dcc.Dropdown(
                        id="year-from",
                        options=[{"label": str(y), "value": y} for y in range(YEAR_MIN, YEAR_MAX+1)],
                        value=YEAR_MIN, clearable=False,
                        style={"color": "#B0B0B0"},
                    ),
                ], style={"flex": 1}),
                html.Div([
                    html.Span("To", style={"fontSize": "0.62rem", "color": TEXT_DIM,
                              "marginBottom": "4px", "display": "block"}),
                    dcc.Dropdown(
                        id="year-to",
                        options=[{"label": str(y), "value": y} for y in range(YEAR_MIN, YEAR_MAX+1)],
                        value=YEAR_MAX, clearable=False,
                        style={"color": "#B0B0B0"},
                    ),
                ], style={"flex": 1}),
            ], style={"display": "flex", "gap": "8px"}),

            html.Hr(style={"borderColor": "#3A3530", "margin": "16px 0 8px 0"}),
            html.P([
                html.Strong("Note on data:", style={"color": TEXT_DIM}), html.Br(),
                "Crime data from Crime Statistics Agency Victoria (annual, year ending Sept). ",
                "Weather from Open-Meteo ERA5. Economic data from ABS Data API. ",
                "All correlations are Pearson r with Spearman cross-check. ",
                html.Br(), html.Br(),
                html.Strong("⚠️ n≈20 years.", style={"color": ACCENT}),
                " Correlations are exploratory — not causal.",
            ], style={"fontSize": "0.6rem", "color": "#6A6055", "lineHeight": "1.6"}),

        ], style={
            "width": "260px", "minWidth": "260px", "background": CARD,
            "padding": "24px 18px", "display": "flex", "flexDirection": "column",
            "gap": "4px", "borderRight": "1px solid #3A3530", "overflowY": "auto",
        }),

        # ── Main ────────────────────────────────────────────────────────────
        html.Div([
            html.Div(id="kpi-row", style={"display": "flex", "gap": "12px",
                                          "flexWrap": "wrap", "marginBottom": "16px"}),

            dcc.Tabs(id="tabs", value="overview", children=[
                dcc.Tab(label="📈 Crime Trends",       value="overview"),
                dcc.Tab(label="🔗 Scatter Explorer",   value="scatter"),
                dcc.Tab(label="🏆 Auto-Correlations",  value="autocorr"),
                dcc.Tab(label="🔥 Correlation Matrix", value="heatmap"),
                dcc.Tab(label="📊 All Variables",      value="allvars"),
                dcc.Tab(label="ℹ️  About",              value="about"),
            ], colors={"border": "#3A3530", "primary": ACCENT, "background": CARD},
            style={"fontFamily": "Georgia, serif", "fontSize": "0.83rem"}),

            html.Div(id="tab-content", style={"marginTop": "12px"}),
        ], style={"flex": 1, "padding": "22px 28px", "overflow": "auto"}),

    ], style={"display": "flex", "flex": 1, "overflow": "hidden",
              "height": "calc(100vh - 57px)"}),

    html.Div([
        html.Span("Victorian Crime Correlation Explorer  ·  Data: CSA Vic, ABS, Open-Meteo",
                  style={"color": "#5A5045", "fontSize": "0.62rem"}),
    ], style={"background": BG, "padding": "5px 32px",
              "borderTop": "1px solid #3A3530"}),

], style={"fontFamily": "Georgia, serif", "backgroundColor": BG, "color": TEXT_MAIN,
          "height": "100vh", "display": "flex", "flexDirection": "column",
          "overflow": "hidden"})


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACKS
# ─────────────────────────────────────────────────────────────────────────────
def filter_master(yr_range):
    yf = int(yr_range[0]) if yr_range[0] is not None else YEAR_MIN
    yt = int(yr_range[1]) if yr_range[1] is not None else YEAR_MAX
    if yf > yt: yf, yt = yt, yf
    return master[(master["year"] >= yf) & (master["year"] <= yt)].copy()


@app.callback(
    Output("kpi-row", "children"),
    Input("crime-var", "value"),
    Input("pred-var", "value"),
    Input("year-from", "value"),
    Input("year-to", "value"),
)
def update_kpis(crime_var, pred_var, yf, yt):
    df = df = filter_master([yf, yt])
    if df.empty or crime_var not in df.columns:
        return []

    crime_label = available_crime_vars.get(crime_var, crime_var)
    pred_label  = available_pred_vars.get(pred_var, pred_var)

    latest = df.iloc[-1]
    first  = df.iloc[0]

    crime_latest = latest.get(crime_var, None)
    crime_first  = first.get(crime_var, None)
    change_pct   = ((crime_latest - crime_first) / crime_first * 100) if crime_first else 0

    # Correlation
    sub = df[[crime_var, pred_var]].dropna()
    if len(sub) >= 4:
        r, p = stats.pearsonr(sub[crime_var], sub[pred_var])
        r_str = f"r = {r:+.3f}"
        p_str = f"p = {p:.3f}" + (" ✓" if p < 0.05 else "")
        corr_color = ACCENT2 if abs(r) > 0.6 else (ACCENT if abs(r) > 0.3 else TEXT_DIM)
    else:
        r_str, p_str, corr_color = "—", "insufficient data", TEXT_DIM

    return [
        kpi(f"Latest — {crime_label[:25]}", f"{int(crime_latest):,}" if crime_latest else "—",
            f"Year {int(latest['year'])}", ACCENT),
        kpi("Change Over Period", f"{change_pct:+.1f}%",
            f"{int(first['year'])}–{int(latest['year'])}", ACCENT3),
        kpi(f"Correlation with {pred_label[:20]}", r_str, p_str, corr_color),
        kpi("Years of Data", str(len(df)), f"{int(df['year'].min())}–{int(df['year'].max())}",
            ACCENT4),
    ]


@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "value"),
    Input("crime-var", "value"),
    Input("pred-var", "value"),
    Input("year-from", "value"),
    Input("year-to", "value"),
)
def render_tab(tab, crime_var, pred_var, yf, yt):
    df = df = filter_master([yf, yt])
    if df.empty:
        return html.P("No data for selected range.", style={"color": TEXT_DIM})

    crime_label = available_crime_vars.get(crime_var, crime_var)
    pred_label  = available_pred_vars.get(pred_var, pred_var)

    # ── CRIME TRENDS ─────────────────────────────────────────────────────────
    if tab == "overview":
        fig = go.Figure()
        for i, (col, label) in enumerate(available_crime_vars.items()):
            if col not in df.columns or col == "crime_rate_per_100k":
                continue
            fig.add_trace(go.Scatter(
                x=df["year"], y=df[col],
                name=label, line=dict(color=PALETTE[i % len(PALETTE)], width=2),
                mode="lines+markers", marker=dict(size=6),
            ))
        fig.update_layout(
            **PLOT_BASE,
            title=dict(text="Victorian Criminal Incidents by Category",
                       font=dict(size=14, color=TEXT_MAIN)),
            xaxis=axis("Year"), yaxis=axis("Incidents"),
            height=420, margin=dict(l=60, r=40, t=60, b=50),
        )
        fig.update_layout(legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_DIM)))

        # Rate per 100k
        fig2 = go.Figure()
        if "crime_rate_per_100k" in df.columns:
            fig2.add_trace(go.Bar(
                x=df["year"], y=df["crime_rate_per_100k"],
                marker_color=ACCENT, name="Rate per 100k",
            ))
        fig2.update_layout(
            **PLOT_BASE,
            title=dict(text="Crime Rate per 100,000 Population",
                       font=dict(size=14, color=TEXT_MAIN)),
            xaxis=axis("Year"), yaxis=axis("Rate per 100k"),
            height=320, margin=dict(l=60, r=40, t=60, b=50),
        )
        fig2.update_layout(legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_DIM)))

        note = card([
            html.P("⚠️  COVID-19 Note", style={"color": ACCENT, "fontWeight": "700",
                   "margin": "0 0 6px 0", "fontSize": "0.82rem"}),
            html.P("2020–2021 figures were significantly impacted by COVID-19 lockdowns and the "
                   "introduction of CHO Direction breach offence codes. Treat these years with "
                   "caution when interpreting correlations.",
                   style={"color": TEXT_DIM, "fontSize": "0.78rem", "margin": 0}),
        ], ACCENT3)

        return html.Div([
            dcc.Graph(figure=fig,  config={"displayModeBar": False}),
            dcc.Graph(figure=fig2, config={"displayModeBar": False}),
            note,
        ])

    # ── SCATTER EXPLORER ─────────────────────────────────────────────────────
    elif tab == "scatter":
        sub = df[[crime_var, pred_var, "year"]].dropna()
        if len(sub) < 4:
            return html.P("Not enough data for scatter plot.", style={"color": TEXT_DIM})

        r, p = stats.pearsonr(sub[crime_var], sub[pred_var])
        rs, ps = stats.spearmanr(sub[crime_var], sub[pred_var])

        # Regression line
        z = np.polyfit(sub[pred_var], sub[crime_var], 1)
        poly = np.poly1d(z)
        x_line = np.linspace(sub[pred_var].min(), sub[pred_var].max(), 100)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=sub[pred_var], y=sub[crime_var],
            mode="markers+text",
            text=sub["year"].astype(str),
            textposition="top center",
            textfont=dict(size=9, color=TEXT_DIM),
            marker=dict(color=ACCENT, size=10, line=dict(color=ACCENT2, width=1)),
            name="Data points",
            hovertemplate="%{text}<br>" + pred_label + ": %{x}<br>" + crime_label + ": %{y}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=x_line, y=poly(x_line),
            mode="lines",
            line=dict(color=ACCENT2, width=2, dash="dot"),
            name="Trend line",
        ))
        fig.update_layout(
            **PLOT_BASE,
            title=dict(text=f"{crime_label}  vs  {pred_label}",
                       font=dict(size=14, color=TEXT_MAIN)),
            xaxis=axis(pred_label),
            yaxis=axis(crime_label),
            height=500, margin=dict(l=70, r=40, t=60, b=60),
        )
        fig.update_layout(legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_DIM)))

        sig = p < 0.05
        interp = "strong" if abs(r) > 0.7 else ("moderate" if abs(r) > 0.4 else "weak")
        direction = "positive" if r > 0 else "negative"

        result_card = card([
            html.P("📐  Correlation Results", style={"color": ACCENT, "fontWeight": "700",
                   "margin": "0 0 10px 0", "fontSize": "0.85rem"}),
            html.Div([
                html.Div([
                    html.P("Pearson r", style={"color": TEXT_DIM, "fontSize": "0.7rem", "margin": "0 0 2px 0"}),
                    html.P(f"{r:+.3f}", style={"color": ACCENT2 if abs(r) > 0.5 else ACCENT,
                           "fontSize": "1.4rem", "fontFamily": "Georgia, serif", "margin": 0}),
                ], style={"flex": 1, "textAlign": "center"}),
                html.Div([
                    html.P("p-value", style={"color": TEXT_DIM, "fontSize": "0.7rem", "margin": "0 0 2px 0"}),
                    html.P(f"{p:.4f} {'✓ sig.' if sig else '✗ not sig.'}", style={
                           "color": ACCENT4 if sig else TEXT_DIM,
                           "fontSize": "1.1rem", "fontFamily": "Georgia, serif", "margin": 0}),
                ], style={"flex": 1, "textAlign": "center"}),
                html.Div([
                    html.P("Spearman r", style={"color": TEXT_DIM, "fontSize": "0.7rem", "margin": "0 0 2px 0"}),
                    html.P(f"{rs:+.3f}", style={"color": ACCENT2 if abs(rs) > 0.5 else ACCENT,
                           "fontSize": "1.4rem", "fontFamily": "Georgia, serif", "margin": 0}),
                ], style={"flex": 1, "textAlign": "center"}),
                html.Div([
                    html.P("n (years)", style={"color": TEXT_DIM, "fontSize": "0.7rem", "margin": "0 0 2px 0"}),
                    html.P(str(len(sub)), style={"color": TEXT_MAIN,
                           "fontSize": "1.4rem", "fontFamily": "Georgia, serif", "margin": 0}),
                ], style={"flex": 1, "textAlign": "center"}),
            ], style={"display": "flex", "gap": "12px", "marginBottom": "10px"}),
            html.P(
                f"There is a {interp} {direction} correlation (r = {r:+.3f}) between {crime_label} "
                f"and {pred_label}. "
                f"{'This is statistically significant (p < 0.05).' if sig else 'This is NOT statistically significant (p ≥ 0.05).'} "
                f"Note: with only ~{len(sub)} data points, interpret with caution.",
                style={"color": TEXT_DIM, "fontSize": "0.78rem", "margin": 0}
            ),
        ])

        return html.Div([dcc.Graph(figure=fig, config={"displayModeBar": False}), result_card])

    # ── AUTO-CORRELATIONS ────────────────────────────────────────────────────
    elif tab == "autocorr":
        corr_df = compute_correlations(df, crime_var)
        if corr_df.empty:
            return html.P("No correlation data available.", style={"color": TEXT_DIM})

        colors = [ACCENT2 if abs(r) > 0.6 else (ACCENT if abs(r) > 0.3 else TEXT_DIM)
                  for r in corr_df["pearson_r"]]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=corr_df["pearson_r"],
            y=corr_df["variable"],
            orientation="h",
            marker_color=colors,
            text=[f"r={r:+.3f}  p={p:.3f}" for r, p in
                  zip(corr_df["pearson_r"], corr_df["pearson_p"])],
            textposition="outside",
            textfont=dict(color=TEXT_DIM, size=10),
            hovertemplate="%{y}<br>Pearson r: %{x}<extra></extra>",
        ))
        fig.add_vline(x=0, line_color=TEXT_DIM, line_width=1, opacity=0.5)
        fig.add_vline(x=0.5,  line_dash="dot", line_color=ACCENT2, opacity=0.4)
        fig.add_vline(x=-0.5, line_dash="dot", line_color=ACCENT2, opacity=0.4)
        fig.update_layout(
            **PLOT_BASE,
            title=dict(text=f"All Correlations with {crime_label} — Ranked by Strength",
                       font=dict(size=14, color=TEXT_MAIN)),
            xaxis=axis("Pearson r", range=[-1.1, 1.3]),
            yaxis=dict(tickfont=dict(color=TEXT_DIM, size=11), automargin=True),
            height=max(400, len(corr_df) * 32 + 80),
            margin=dict(l=240, r=120, t=60, b=50),
            showlegend=False,
        )

        tbl = dash_table.DataTable(
            data=corr_df[["variable","pearson_r","pearson_p","spearman_r","spearman_p","n"]
                         ].to_dict("records"),
            columns=[
                {"name": "Variable",       "id": "variable"},
                {"name": "Pearson r",      "id": "pearson_r"},
                {"name": "Pearson p",      "id": "pearson_p"},
                {"name": "Spearman r",     "id": "spearman_r"},
                {"name": "Spearman p",     "id": "spearman_p"},
                {"name": "n",              "id": "n"},
            ],
            style_table={"overflowX": "auto", "marginTop": "16px"},
            style_header={"backgroundColor": CARD, "color": ACCENT, "fontWeight": "700",
                          "border": "1px solid #3A3530", "fontFamily": "Georgia, serif",
                          "fontSize": "0.75rem"},
            style_cell={"backgroundColor": BG, "color": TEXT_MAIN,
                        "border": "1px solid #3A3530", "fontFamily": "Georgia, serif",
                        "fontSize": "0.82rem", "padding": "7px 12px", "textAlign": "center"},
            style_data_conditional=[
                {"if": {"row_index": "odd"}, "backgroundColor": "#1E1E1E"},
                {"if": {"filter_query": "{pearson_p} < 0.05", "column_id": "pearson_p"},
                 "color": ACCENT4, "fontWeight": "700"},
                {"if": {"filter_query": "{pearson_r} > 0.5", "column_id": "pearson_r"},
                 "color": ACCENT2},
                {"if": {"filter_query": "{pearson_r} < -0.5", "column_id": "pearson_r"},
                 "color": RED},
            ],
            sort_action="native",
        )

        return html.Div([dcc.Graph(figure=fig, config={"displayModeBar": False}), tbl])

    # ── HEATMAP ──────────────────────────────────────────────────────────────
    elif tab == "heatmap":
        all_vars = list(available_crime_vars.keys()) + list(available_pred_vars.keys())
        cols = [c for c in all_vars if c in df.columns]
        labels = [available_crime_vars.get(c, available_pred_vars.get(c, c)) for c in cols]

        sub = df[cols].dropna()
        if len(sub) < 4:
            return html.P("Not enough data for heatmap.", style={"color": TEXT_DIM})

        corr_matrix = sub.corr()

        fig = go.Figure(go.Heatmap(
            z=corr_matrix.values,
            x=labels, y=labels,
            colorscale=[
                [0.0, "#C0392B"], [0.35, "#5A4030"], [0.5, "#242424"],
                [0.65, "#2C4A5A"], [1.0, "#7EB8C9"]
            ],
            zmid=0, zmin=-1, zmax=1,
            text=[[f"{v:.2f}" for v in row] for row in corr_matrix.values],
            texttemplate="%{text}",
            textfont=dict(size=9, color=TEXT_MAIN),
            hovertemplate="%{y} × %{x}<br>r = %{z:.3f}<extra></extra>",
            colorbar=dict(tickfont=dict(color=TEXT_DIM), title=dict(text="r", font=dict(color=TEXT_DIM))),
        ))
        fig.update_layout(
            **PLOT_BASE,
            title=dict(text="Full Correlation Matrix — All Variables",
                       font=dict(size=14, color=TEXT_MAIN)),
            xaxis=dict(tickfont=dict(color=TEXT_DIM, size=9), tickangle=-45, automargin=True),
            yaxis=dict(tickfont=dict(color=TEXT_DIM, size=9), automargin=True),
            height=650, margin=dict(l=200, r=80, t=60, b=200),
        )

        return dcc.Graph(figure=fig, config={"displayModeBar": False})

    # ── ALL VARIABLES ─────────────────────────────────────────────────────────
    elif tab == "allvars":
        figs = []
        for col, label in available_pred_vars.items():
            if col not in df.columns:
                continue
            sub = df[["year", col]].dropna()
            if sub.empty:
                continue
            f = go.Figure()
            f.add_trace(go.Scatter(
                x=sub["year"], y=sub[col],
                name=label, line=dict(color=ACCENT2, width=2),
                mode="lines+markers", marker=dict(size=5),
            ))
            f.update_layout(
                **PLOT_BASE,
                title=dict(text=label, font=dict(size=12, color=TEXT_MAIN)),
                xaxis=axis("Year"), yaxis=axis(""),
                height=250, margin=dict(l=60, r=20, t=40, b=40),
                showlegend=False,
            )
            f.update_layout(hovermode="closest")
            figs.append(html.Div(dcc.Graph(figure=f, config={"displayModeBar": False}),
                                 style={"flex": "0 0 48%"}))

        return html.Div(figs, style={"display": "flex", "flexWrap": "wrap", "gap": "12px"})

    # ── ABOUT ────────────────────────────────────────────────────────────────
    elif tab == "about":
        def src_block(title, items, color=ACCENT):
            rows = []
            for name, desc in items:
                rows.append(html.Tr([
                    html.Td(name, style={"color": color, "fontWeight": "700",
                        "padding": "8px 14px", "fontSize": "0.8rem",
                        "whiteSpace": "nowrap", "borderBottom": "1px solid #3A3530",
                        "width": "200px", "verticalAlign": "top"}),
                    html.Td(desc, style={"color": TEXT_DIM, "padding": "8px 14px",
                        "fontSize": "0.78rem", "lineHeight": "1.6",
                        "borderBottom": "1px solid #3A3530"}),
                ]))
            return html.Div([
                html.H4(title, style={"color": color, "margin": 0, "fontSize": "0.9rem",
                    "fontWeight": "700", "padding": "12px 14px", "background": "#1E1E1E",
                    "borderLeft": f"4px solid {color}", "borderRadius": "8px 8px 0 0"}),
                html.Table(html.Tbody(rows),
                    style={"width": "100%", "borderCollapse": "collapse",
                           "background": CARD, "borderRadius": "0 0 8px 8px"}),
            ], style={"marginBottom": "16px", "borderRadius": "8px",
                      "overflow": "hidden", "border": "1px solid #3A3530"})

        return html.Div([
            src_block("📁  Data Sources", [
                ("Crime Statistics Agency",
                 "Annual criminal incident data from the Crime Statistics Agency Victoria. "
                 "Years ending September 2004–2023. Includes total incidents and breakdowns "
                 "by offence division. Download from crimestatistics.vic.gov.au."),
                ("Open-Meteo ERA5",
                 "Daily weather reanalysis data for Melbourne CBD (lat -37.81, lon 144.96). "
                 "Aggregated to annual averages. Free API, no key required."),
                ("ABS Data API",
                 "Victoria unemployment rate (Labour Force Survey, series LF) and CPI annual "
                 "change (Consumer Price Index). Free REST API from data.api.abs.gov.au."),
                ("Moon Phases",
                 "Full moon counts calculated using the ephem astronomical library. "
                 "Falls back to a standard lunar calendar if ephem is not installed."),
                ("Population",
                 "ABS Estimated Resident Population for Victoria. Census anchor points "
                 "(2006, 2011, 2016, 2021) with linear interpolation for intermediate years."),
                ("Liquor Licences",
                 "Estimated annual Victorian liquor licence counts based on published "
                 "VCGLR annual reports and Data Vic datasets. Approximate only."),
                ("School Holidays",
                 "Approximate Victorian school holiday weeks per year based on the "
                 "standard 4-term academic calendar. COVID years (2020–21) adjusted."),
            ]),
            src_block("📐  Methodology", [
                ("Pearson r",
                 "Measures the linear correlation between two variables. Ranges from -1 "
                 "(perfect negative) to +1 (perfect positive). Assumes normality."),
                ("Spearman r",
                 "Rank-based correlation — more robust to outliers and non-normal "
                 "distributions. Used as a cross-check against Pearson."),
                ("p-value",
                 "Probability of observing this correlation by chance if the null hypothesis "
                 "(no correlation) is true. p < 0.05 is the conventional significance threshold. "
                 "With only ~20 data points, power is low — treat non-significant results with care."),
                ("Sample size caveat",
                 "Annual data gives approximately 18–20 data points. This is sufficient for "
                 "exploratory analysis but borderline for reliable statistical inference. "
                 "All results should be treated as hypothesis-generating, not conclusive."),
                ("COVID caveat",
                 "2020–2021 are outliers due to lockdowns and the introduction of CHO Direction "
                 "breach offences. Excluding these years may reveal cleaner underlying correlations."),
            ], color=ACCENT2),
        ], style={"maxWidth": "860px", "paddingBottom": "20px"})

    return html.Div("Select a tab.")


# ─────────────────────────────────────────────────────────────────────────────
server = app.server
if __name__ == "__main__":
    print("\n" + "═"*60)
    print("  Open: http://127.0.0.1:8051")
    print("═"*60 + "\n")
    app.run(debug=True, port=8051)
