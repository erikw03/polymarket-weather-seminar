"""
One-off HISTORICAL backfill of resolved temperature markets + matching weather.

Why: forward hourly collection only yields ~one resolved outcome per city per day.
Polymarket, however, keeps hundreds of past daily markets, and the CLOB exposes
their full hourly price trajectories. Combined with Open-Meteo's historical
forecast + observed actuals, this lets us assemble months of (market trajectory →
forecast → actual outcome) records *today*, which is what makes the dataset large
enough for ML.

What it does, per city, for every past day in the window:
  1. Build the deterministic market slug and fetch the resolved event from Gamma.
  2. Record the metadata, the resolved winning bucket, and for every bucket the
     hourly YES-price trajectory (CLOB /prices-history with explicit startTs/endTs
     — `interval=max` returns nothing for older markets).
  3. Pull the issued forecast (historical-forecast API) and observed actuals
     (archive API) for the whole window.

Output: a FEW consolidated files (not thousands), one pair per city, under
`data/backfill/`:
  - polymarket_<city>_history.json
  - weather_<city>_history.json

Usage:
    python backfill_history.py                      # default window
    python backfill_history.py 2026-03-01 2026-06-20
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import sys

import config
from src import http_client

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("backfill_history")

BACKFILL_DIR = config.PROJECT_ROOT / "data" / "backfill"
DEFAULT_START = dt.date(2026, 3, 1)   # markets generally don't predate this
PRICE_FIDELITY = 60                    # minutes between points (hourly, like live)


# --- helpers -----------------------------------------------------------------
def city_slug(city: config.City) -> str:
    return city.name.lower().replace(" ", "-")


def market_slug(city: config.City, d: dt.date) -> str:
    # e.g. highest-temperature-in-munich-on-may-1-2026
    return f"highest-temperature-in-{city_slug(city)}-on-{d.strftime('%B').lower()}-{d.day}-{d.year}"


def _ts(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def fetch_event(slug: str) -> dict | None:
    """Fetch a market event by slug; None if it doesn't exist."""
    try:
        data = http_client.get_json(f"{config.GAMMA_BASE_URL}/events", params={"slug": slug})
    except Exception:
        return None
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict) and data.get("markets"):
        return data
    return None


def bucket_history(token: str, start_iso: str | None, end_iso: str | None) -> list[dict]:
    """Hourly YES-price trajectory for one bucket token over its trading life."""
    params: dict = {"market": token, "fidelity": PRICE_FIDELITY}
    if start_iso and end_iso:
        params["startTs"] = _ts(start_iso) - 3600
        params["endTs"] = _ts(end_iso) + 3600
    else:
        params["interval"] = "max"
    try:
        return http_client.get_json(f"{config.CLOB_BASE_URL}/prices-history", params=params).get("history", [])
    except Exception:
        logger.warning("prices-history failed for token %s", token[:12])
        return []


# --- per-source backfill -----------------------------------------------------
def backfill_markets(city: config.City, start: dt.date, end: dt.date) -> list[dict]:
    records: list[dict] = []
    d = start
    while d <= end:
        ev = fetch_event(market_slug(city, d))
        # Only resolved (closed) markets carry a real outcome + final trajectory.
        if ev and ev.get("closed"):
            rec = {
                "date": d.isoformat(),
                "slug": ev.get("slug"),
                "title": ev.get("title"),
                "endDate": ev.get("endDate"),
                "conditionId": ev.get("conditionId"),
                "temperature_unit": city.temperature_unit,
                "buckets": [],
            }
            winner = None
            for m in ev.get("markets", []):
                op = json.loads(m.get("outcomePrices") or "[]")
                title = m.get("groupItemTitle")
                resolved_yes = bool(op and float(op[0]) >= 0.99)
                if resolved_yes:
                    winner = title
                try:
                    tok = json.loads(m["clobTokenIds"])[0]
                except (KeyError, json.JSONDecodeError, TypeError):
                    continue
                hist = bucket_history(tok, m.get("startDate") or ev.get("startDate"),
                                      m.get("endDate") or ev.get("endDate"))
                rec["buckets"].append({
                    "bucket": title,
                    "yes_token": tok,
                    "resolved_yes": resolved_yes,
                    "history": hist,  # list of {"t": unix_secs, "p": yes_price}
                })
            rec["resolved_bucket"] = winner
            pts = sum(len(b["history"]) for b in rec["buckets"])
            logger.info("  %s %s -> winner %s | %d buckets, %d price points",
                        city.name, d, winner, len(rec["buckets"]), pts)
            records.append(rec)
        d += dt.timedelta(days=1)
    return records


def backfill_weather(city: config.City, start: dt.date, end: dt.date) -> dict:
    """Issued forecast + observed actuals for the whole window (one call each)."""
    common = {
        "latitude": city.latitude, "longitude": city.longitude,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": city.timezone, "temperature_unit": city.temperature_unit,
    }
    out: dict = {"city": city.name, "station": city.station,
                 "temperature_unit": city.temperature_unit}
    try:
        out["historical_forecast"] = http_client.get_json(
            config.OPEN_METEO_HISTORICAL_FORECAST_URL, params=common)
    except Exception:
        logger.exception("historical-forecast failed for %s", city.name)
    try:
        out["archive_actuals"] = http_client.get_json(
            config.OPEN_METEO_ARCHIVE_URL, params=common)
    except Exception:
        logger.exception("archive failed for %s", city.name)
    return out


def _write(name: str, payload) -> pathlib.Path:
    BACKFILL_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKFILL_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def run(start: dt.date, end: dt.date) -> None:
    logger.info("=== Historical backfill %s .. %s for %d cities ===",
                start, end, len(config.CITIES))
    for city in config.CITIES:
        logger.info("--- %s ---", city.name)
        markets = backfill_markets(city, start, end)
        p1 = _write(f"polymarket_{city_slug(city)}_history.json", {
            "city": city.name, "station": city.station,
            "window": [start.isoformat(), end.isoformat()],
            "market_count": len(markets), "markets": markets,
        })
        weather = backfill_weather(city, start, end)
        p2 = _write(f"weather_{city_slug(city)}_history.json", weather)
        logger.info("%s: %d resolved markets -> %s ; weather -> %s",
                    city.name, len(markets), p1.name, p2.name)
    http_client.close()
    logger.info("=== Backfill complete ===")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        s = dt.date.fromisoformat(sys.argv[1])
        e = dt.date.fromisoformat(sys.argv[2])
    else:
        s = DEFAULT_START
        e = dt.date.today() - dt.timedelta(days=1)
    run(s, e)
