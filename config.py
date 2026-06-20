"""
Central configuration for the ingestion layer.

Design decision (for the Betriebskonzept / report):
- Target cities are *config*, not hard-coded in the scripts, so the pipeline can
  scale from "Munich only" to many cities without touching ingestion logic.
- We externalise tunables (forecast horizon, archive look-back, CLOB enrichment)
  via environment variables (.env), with sensible defaults so the pipeline runs
  out of the box with zero secrets. No API keys are needed for either source.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env if present. Nothing secret lives here today, but keeping config
# externalised is good hygiene and required by the project brief.
load_dotenv()


@dataclass(frozen=True)
class City:
    """A target city.

    - `name` MUST match how Polymarket spells it in the market question (e.g.
      'NYC', not 'New York'), because we filter markets by that string.
    - `latitude`/`longitude` point at the *resolution weather station* (usually
      an airport), NOT the city centre, so the Open-Meteo forecast/actuals align
      with what the market actually settles on.
    - `temperature_unit` matches the market's unit so the forecast and the market
      buckets are directly comparable (Polymarket quotes NYC in °F, others in °C).
    - `station` is documentation only (the official settlement station).
    """

    name: str
    latitude: float
    longitude: float
    timezone: str  # IANA tz, used by Open-Meteo so 'daily' aligns to local days
    temperature_unit: str = "celsius"  # "celsius" or "fahrenheit"
    station: str = ""


# --- Target cities -----------------------------------------------------------
# Coordinates are the official Polymarket settlement stations (verified June 2026
# from each market's resolution description). Adding a city is one line; ~20+
# cities have live daily markets (Paris, Madrid, Seoul, Singapore, Beijing, ...).
CITIES: list[City] = [
    City(name="Munich", latitude=48.3538, longitude=11.7861, timezone="Europe/Berlin",
         temperature_unit="celsius", station="Munich Airport"),
    City(name="London", latitude=51.5048, longitude=0.0495, timezone="Europe/London",
         temperature_unit="celsius", station="London City Airport"),
    City(name="NYC", latitude=40.7769, longitude=-73.8740, timezone="America/New_York",
         temperature_unit="fahrenheit", station="LaGuardia Airport"),
    City(name="Tokyo", latitude=35.5494, longitude=139.7798, timezone="Asia/Tokyo",
         temperature_unit="celsius", station="Tokyo Haneda Airport"),
]


# --- API endpoints (verified live, June 2026) --------------------------------
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
# Historical-forecast API: returns the forecast that *was* issued for a past date.
# Used to backfill forecasts for days the live scheduler missed (market prices,
# unlike forecasts, cannot be backfilled).
OPEN_METEO_HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
CLOB_BASE_URL = "https://clob.polymarket.com"


# --- Tunables (override via .env) --------------------------------------------
# How many days of forecast to pull (today + N-1 following days).
FORECAST_DAYS = int(os.getenv("FORECAST_DAYS", "3"))

# How many days back to request observed actuals from the ERA5 archive.
# NOTE: ERA5 reanalysis lags real time by ~5 days, so the most recent days in
# this window may come back null. We store whatever the API returns (raw zone).
ARCHIVE_LOOKBACK_DAYS = int(os.getenv("ARCHIVE_LOOKBACK_DAYS", "7"))

# Whether to enrich each Polymarket bucket with a live CLOB midpoint quote.
# Gamma's `outcomePrices` is already a fine price snapshot; CLOB midpoint is a
# second, order-book-derived price. Toggle off to cut request volume.
CLOB_ENRICH = os.getenv("CLOB_ENRICH", "true").lower() in ("1", "true", "yes")

# Only ingest markets that are still open (closed == false). Past markets can't
# gain new price information, so for live snapshotting we skip them.
ONLY_OPEN_MARKETS = os.getenv("ONLY_OPEN_MARKETS", "true").lower() in ("1", "true", "yes")


# --- Storage layout ----------------------------------------------------------
# Append-only "raw zone": every run writes a new timestamped file, nothing is
# ever overwritten. This makes the pipeline idempotent/safe to re-run and gives
# us an immutable audit trail of exactly what each source returned and when.
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
RAW_WEATHER_DIR = PROJECT_ROOT / "data" / "raw" / "weather"
RAW_POLYMARKET_DIR = PROJECT_ROOT / "data" / "raw" / "polymarket"

# Network behaviour
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "30"))
