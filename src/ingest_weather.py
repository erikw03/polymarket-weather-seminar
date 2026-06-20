"""
Weather ingestion from Open-Meteo (no API key required).

Pulls two things per city:
  1. Daily *forecast* (temperature_2m_max / _min) from the forecast endpoint.
  2. Recent observed *actuals* from the ERA5 archive endpoint.

Each is written verbatim to the append-only raw zone as a timestamped JSON file.
We do NOT clean or reshape here — that's a separate, later step. The raw zone
must stay immutable so we can always reproduce/audit what the API returned.

Data source: Open-Meteo (https://open-meteo.com/), licensed CC BY 4.0.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib

import config
from src import http_client

logger = logging.getLogger(__name__)


def _utc_stamp() -> str:
    """Filesystem-safe UTC timestamp, e.g. 2026-06-16T08-45-09Z."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _write_raw(directory: pathlib.Path, prefix: str, city: config.City, payload: dict) -> pathlib.Path:
    """Write `payload` to a new timestamped file. Never overwrites (append-only).

    We wrap the raw API response in a tiny envelope recording *what* we fetched
    and *when*, but the API body itself (`response`) is stored exactly as
    received.
    """
    directory.mkdir(parents=True, exist_ok=True)
    safe_city = city.name.lower().replace(" ", "-")
    path = directory / f"{prefix}_{safe_city}_{_utc_stamp()}.json"
    envelope = {
        "_meta": {
            "source": "open-meteo",
            "kind": prefix,  # "weather-forecast" or "weather-archive"
            "city": city.name,
            "latitude": city.latitude,
            "longitude": city.longitude,
            "temperature_unit": city.temperature_unit,
            "station": city.station,
            "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        "response": payload,  # raw, unmodified API body
    }
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2))
    return path


def fetch_forecast(city: config.City) -> dict:
    """Daily max/min temperature forecast for the next `FORECAST_DAYS` days."""
    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": city.timezone,
        "temperature_unit": city.temperature_unit,  # match the market's unit
        "forecast_days": config.FORECAST_DAYS,
    }
    return http_client.get_json(config.OPEN_METEO_FORECAST_URL, params=params)


def fetch_archive(city: config.City) -> dict:
    """Observed actual daily max/min from ERA5 for the recent look-back window.

    NOTE (data-quality caveat for the report): ERA5 reanalysis lags ~5 days, so
    the most recent dates may be null. Also, ERA5 is a gridded reanalysis while
    Polymarket settles on the official station (Wunderground/NWS) reading, so the
    two 'actuals' can differ slightly. We store both and reconcile later.
    """
    today = dt.date.today()
    end = today - dt.timedelta(days=1)  # yesterday
    start = today - dt.timedelta(days=config.ARCHIVE_LOOKBACK_DAYS)
    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": city.timezone,
        "temperature_unit": city.temperature_unit,
    }
    return http_client.get_json(config.OPEN_METEO_ARCHIVE_URL, params=params)


def fetch_historical_forecast(city: config.City, start: dt.date, end: dt.date) -> dict:
    """The forecast that *was issued* for a past date range (historical-forecast
    API). Lets us recover forecasts for days the live scheduler missed. Market
    prices cannot be recovered this way — only forecasts."""
    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": city.timezone,
        "temperature_unit": city.temperature_unit,
    }
    return http_client.get_json(config.OPEN_METEO_HISTORICAL_FORECAST_URL, params=params)


def backfill(start: dt.date, end: dt.date) -> list[pathlib.Path]:
    """One-off: backfill issued forecasts for [start, end] for every city.

    Writes into the same raw zone with the same envelope as live runs, tagged
    `kind: weather-historical-forecast` so it is distinguishable from the live
    forecast snapshots.
    """
    written: list[pathlib.Path] = []
    for city in config.CITIES:
        try:
            payload = fetch_historical_forecast(city, start, end)
            path = _write_raw(config.RAW_WEATHER_DIR, "weather-historical-forecast", city, payload)
            n = len(payload.get("daily", {}).get("time", []))
            logger.info("Backfill %s: %d day(s) [%s..%s] -> %s",
                        city.name, n, start, end, path.name)
            written.append(path)
        except Exception:
            logger.exception("Backfill FAILED for %s", city.name)
    logger.info("Backfill done: %d file(s) written.", len(written))
    return written


def ingest_city(city: config.City) -> list[pathlib.Path]:
    """Fetch forecast + archive for one city and write raw snapshots.

    A failure in one of the two fetches is logged but does not prevent the other
    from being written.
    """
    written: list[pathlib.Path] = []

    try:
        forecast = fetch_forecast(city)
        path = _write_raw(config.RAW_WEATHER_DIR, "weather-forecast", city, forecast)
        n = len(forecast.get("daily", {}).get("time", []))
        logger.info("Forecast %s: %d day(s) -> %s", city.name, n, path.name)
        written.append(path)
    except Exception:
        logger.exception("Forecast fetch FAILED for %s", city.name)

    try:
        archive = fetch_archive(city)
        path = _write_raw(config.RAW_WEATHER_DIR, "weather-archive", city, archive)
        n = len(archive.get("daily", {}).get("time", []))
        logger.info("Archive  %s: %d day(s) -> %s", city.name, n, path.name)
        written.append(path)
    except Exception:
        logger.exception("Archive fetch FAILED for %s", city.name)

    return written


def run() -> list[pathlib.Path]:
    """Ingest weather for every configured city. Isolated per city."""
    all_written: list[pathlib.Path] = []
    for city in config.CITIES:
        all_written.extend(ingest_city(city))
    logger.info("Weather ingestion done: %d file(s) written.", len(all_written))
    return all_written


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    run()
