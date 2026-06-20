"""
One-off backfill of *issued weather forecasts* for past dates the live scheduler
missed (e.g. the gap before automation was switched on).

This recovers forecasts ONLY. Polymarket price snapshots cannot be backfilled —
those days are lost.

Usage:
    python backfill_forecast.py START END     # dates as YYYY-MM-DD, inclusive
    python backfill_forecast.py 2026-06-16 2026-06-19
"""

from __future__ import annotations

import datetime as dt
import logging
import sys

from src import http_client, ingest_weather

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    start = dt.date.fromisoformat(argv[1])
    end = dt.date.fromisoformat(argv[2])
    if end < start:
        print("END must be on or after START")
        return 2
    written = ingest_weather.backfill(start, end)
    http_client.close()
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
