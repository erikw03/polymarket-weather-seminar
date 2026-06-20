"""
Single entry point for the ingestion layer. Safe to schedule via cron.

Runs both sources. A failure in one source is logged and does NOT prevent the
other from running (each `run()` already isolates per-city errors internally;
here we additionally isolate the two sources from each other).

Usage:
    python run_ingestion.py

Cron example (every hour, on the hour) — note the path has a space, so quote it:
    0 * * * * cd "/path/to/p_2" && /path/to/venv/bin/python run_ingestion.py >> cron.log 2>&1
"""

from __future__ import annotations

import logging
import sys

from src import http_client, ingest_polymarket, ingest_weather

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("run_ingestion")


def main() -> int:
    logger.info("=== Ingestion run starting ===")
    weather_files: list = []
    market_files: list = []

    try:
        weather_files = ingest_weather.run()
    except Exception:
        logger.exception("Weather source crashed (continuing with Polymarket).")

    try:
        market_files = ingest_polymarket.run()
    except Exception:
        logger.exception("Polymarket source crashed (weather already done).")

    http_client.close()

    total = len(weather_files) + len(market_files)
    logger.info("=== Ingestion run finished: %d weather + %d polymarket file(s) ===",
                len(weather_files), len(market_files))

    # Non-zero exit only if BOTH sources produced nothing, so cron surfaces a
    # genuine total failure but tolerates one source being temporarily down.
    return 0 if total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
