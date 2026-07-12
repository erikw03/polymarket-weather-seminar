"""
AP 1.3 — One-off backfill of LEAD-CONSISTENT historical forecasts.

Why: the live pipeline's D2 policy freezes the forecast at the last fetch before
00:00 local of the target day (lead ~1 day). The `historical_forecast` stored on
2026-06-21 represents same-day (lead ~0) values and would make backfill rows
better-informed than live rows. The Open-Meteo *Previous Runs* API exposes the
forecast as issued ~24 h earlier (`temperature_2m_previous_day1`, hourly), which
matched our live day-ahead forecasts best (MAE 0.3-0.6 C, see DECISIONS_AP1.3).

Raw-zone principles: writes NEW files `data/backfill/weather_<city>_prevday1.json`
(hourly API response verbatim + _meta envelope); never touches existing files;
idempotent (skips a city whose file already exists).

Usage:  python backfill_prevday_forecast.py [START END]   (default 2026-03-01 2026-06-20)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys

import config
from src import http_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("backfill_prevday")

PREVRUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
BACKFILL_DIR = config.PROJECT_ROOT / "data" / "backfill"


def run(start: dt.date, end: dt.date) -> None:
    BACKFILL_DIR.mkdir(parents=True, exist_ok=True)
    for city in config.CITIES:
        out = BACKFILL_DIR / f"weather_{city.name.lower().replace(' ', '-')}_prevday1.json"
        if out.exists():
            logger.info("%s: %s existiert bereits - uebersprungen (idempotent)", city.name, out.name)
            continue
        payload = http_client.get_json(PREVRUNS_URL, params={
            "latitude": city.latitude, "longitude": city.longitude,
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "hourly": "temperature_2m_previous_day1",
            "timezone": city.timezone,
            "temperature_unit": city.temperature_unit,
        })
        envelope = {
            "_meta": {
                "source": "open-meteo-previous-runs",
                "kind": "weather-prevday1-hourly",
                "city": city.name,
                "latitude": city.latitude, "longitude": city.longitude,
                "temperature_unit": city.temperature_unit, "station": city.station,
                "lead": "previous_day1 (~24h, lead-konsistent zu D2)",
                "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
            "response": payload,  # hourly arrays verbatim; daily aggregation im Transform
        }
        out.write_text(json.dumps(envelope, ensure_ascii=False))
        n = len(payload.get("hourly", {}).get("time", []))
        logger.info("%s: %d Stundenwerte [%s..%s] -> %s", city.name, n, start, end, out.name)
    http_client.close()


if __name__ == "__main__":
    s = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 2 else dt.date(2026, 3, 1)
    e = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else dt.date(2026, 6, 20)
    run(s, e)
