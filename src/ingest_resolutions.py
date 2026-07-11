"""
Resolution fetcher (AP 1.2, from AP 1.1 decision D4).

Problem it solves: resolved events roll off Polymarket's live feed (the hourly
collector filters to open markets), so the corpus never captures the official
market outcome. This module fetches the *resolved* event object once per market
via `GET /events?slug=<event_slug>` (event slugs are deterministic:
`highest-temperature-in-<city>-on-<month>-<d>-<year>`) and appends it verbatim
to a NEW append-only raw source:

    data/raw/polymarket/resolutions_YYYY-MM-DD.ndjson   (1 line = 1 resolved event)

Raw-zone principles kept:
- Existing raw files are never touched (WORM); this only appends new files.
- The Gamma event is stored exactly as received; deriving the winning bucket is
  the transform's job, not ingestion's.
- Idempotent: before fetching, existing resolutions files are scanned; an event
  is fetched only if no resolved record exists yet. Unresolved events are NOT
  written (they are retried on the next run).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib

import config
from src import http_client, raw_store

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 4  # markets resolve within ~1-2 days; 4 gives slack


def _city_slug(city: config.City) -> str:
    return city.name.lower().replace(" ", "-")


def event_slug(city: config.City, d: dt.date) -> str:
    """Deterministic Polymarket event slug (validated against live data in June)."""
    return (f"highest-temperature-in-{_city_slug(city)}-on-"
            f"{d.strftime('%B').lower()}-{d.day}-{d.year}")


def _already_captured() -> set[str]:
    """Slugs of events already stored as resolved in any resolutions_*.ndjson."""
    seen: set[str] = set()
    for f in sorted(config.RAW_POLYMARKET_DIR.glob("resolutions_*.ndjson")):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("event", {}).get("closed"):
                    seen.add(rec.get("_meta", {}).get("event_slug", ""))
    return seen


def fetch_resolution(slug: str) -> dict | None:
    """Fetch one event by slug; return the raw event dict or None."""
    try:
        data = http_client.get_json(f"{config.GAMMA_BASE_URL}/events", params={"slug": slug})
    except Exception:
        logger.warning("resolution fetch failed for slug=%s", slug)
        return None
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict) and data.get("markets"):
        return data
    return None


def run(lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        since: dt.date | None = None) -> int:
    """Capture resolutions for past target days that are not yet on file.

    `since` overrides the lookback window (used for the one-off init backfill).
    Returns the number of newly captured resolved events.
    """
    today = dt.date.today()
    start = since or (today - dt.timedelta(days=lookback_days))
    captured = _already_captured()
    new = 0
    for city in config.CITIES:
        d = start
        while d < today:  # only past target days can be resolved
            slug = event_slug(city, d)
            d += dt.timedelta(days=1)
            if slug in captured:
                continue
            ev = fetch_resolution(slug)
            if not ev:
                continue  # market may not exist for this day/city
            if not ev.get("closed"):
                logger.info("  %s not resolved yet - will retry next run", slug)
                continue
            record = {
                "_meta": {
                    "source": "polymarket",
                    "kind": "resolution",
                    "city": city.name,
                    "target_date": ev.get("eventDate") or slug[-10:],
                    "event_slug": slug,
                    "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                },
                "event": ev,  # raw Gamma event, verbatim (incl. final outcomePrices)
            }
            raw_store.append_record(config.RAW_POLYMARKET_DIR, "resolutions", record)
            new += 1
            logger.info("  captured resolution: %s", slug)
    logger.info("Resolutions: %d newly captured (window %s..%s).", new, start, today)
    return new


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    since = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    run(since=since)
