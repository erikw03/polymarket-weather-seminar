"""
Polymarket ingestion (read-only, public, no auth).

Captures, for each configured city, a snapshot of the live daily-temperature
prediction market(s) and their current prices. This is purely analytical: we
only READ public data. No wallet, no trading (trading is geoblocked in Germany
anyway). Research question: how well do the implied probabilities track the
weather forecast and the eventual actual temperature?

How a temperature market is structured (verified live, June 2026):
- Discovery: GET /public-search?q=... returns `events[]`, each with a `markets[]`
  array. A temperature event (e.g. "Highest temperature in Munich on June 16?")
  is a negRisk group of ~11 Yes/No buckets, one per °C range. The YES prices of
  the buckets form an implied probability distribution over tomorrow's high.
- Several Gamma fields are JSON-encoded *strings* inside the JSON and must be
  parsed twice: `outcomes`, `outcomePrices`, `clobTokenIds`.
- Live order-book prices come from the CLOB API keyed by a `token_id` taken from
  `clobTokenIds` (index 0 = the "Yes" outcome).

We store the raw Gamma event objects verbatim plus, optionally, the raw CLOB
quote responses, wrapped in a small envelope. Nothing is reshaped/cleaned here.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib

import config
from src import http_client, raw_store

logger = logging.getLogger(__name__)


def discover_events(city: config.City) -> list[dict]:
    """Find temperature events for `city` via the public-search endpoint.

    Returns the de-duplicated list of event objects whose title looks like
    "Highest temperature in <city> ...". Honours ONLY_OPEN_MARKETS so we skip
    already-resolved markets (which can't gain new price information).
    """
    data = http_client.get_json(
        f"{config.GAMMA_BASE_URL}/public-search",
        params={"q": f"highest temperature {city.name}", "limit_per_type": 60},
    )
    events = data.get("events", []) if isinstance(data, dict) else []

    seen: set[str] = set()
    out: list[dict] = []
    needle = f"temperature in {city.name.lower()}"
    for ev in events:
        title = (ev.get("title") or "").lower()
        if needle not in title:
            continue  # filters out other cities the search may have returned
        if config.ONLY_OPEN_MARKETS and ev.get("closed"):
            continue
        slug = ev.get("slug")
        if slug in seen:
            continue
        seen.add(slug)
        out.append(ev)
    return out


def fetch_event_detail(slug: str) -> dict | None:
    """Re-fetch a full event by slug to get the freshest sub-market prices.

    /events?slug= returns a list; we take the first element. Returns None on
    failure so one bad event doesn't abort the whole city.
    """
    try:
        data = http_client.get_json(
            f"{config.GAMMA_BASE_URL}/events", params={"slug": slug}
        )
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
    except Exception:
        logger.exception("Failed to fetch event detail for slug=%s", slug)
    return None


def _yes_token_ids(event: dict) -> list[str]:
    """Extract the YES-outcome CLOB token_id from every sub-market of an event.

    Demonstrates the double-JSON-decode: `clobTokenIds` is a JSON string holding
    a 2-element array [yes_token, no_token]; index 0 is YES.
    """
    tokens: list[str] = []
    for m in event.get("markets", []):
        raw = m.get("clobTokenIds")
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            if parsed:
                tokens.append(parsed[0])
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse clobTokenIds on market %s", m.get("id"))
    return tokens


def fetch_clob_quote(token_id: str) -> dict:
    """Live order-book quote for one token: midpoint + best buy/sell price.

    Each sub-call is isolated; a missing field just stays absent. Returned dict
    holds the raw CLOB responses, unmodified.
    """
    quote: dict = {}
    for key, path, params in (
        ("midpoint", "/midpoint", {"token_id": token_id}),
        ("price_buy", "/price", {"token_id": token_id, "side": "buy"}),
        ("price_sell", "/price", {"token_id": token_id, "side": "sell"}),
    ):
        try:
            quote[key] = http_client.get_json(f"{config.CLOB_BASE_URL}{path}", params=params)
        except Exception:
            logger.warning("CLOB %s failed for token %s", key, token_id[:12])
    return quote


def _write_raw(city: config.City, events: list[dict], clob_quotes: dict) -> pathlib.Path:
    """Append one city snapshot as a line to today's NDJSON partition.

    One line per city per run; all cities share the day's `polymarket_<date>.ndjson`.
    The raw Gamma/CLOB bodies are stored verbatim inside the envelope.
    """
    envelope = {
        "_meta": {
            "source": "polymarket",
            "access": "read-only public (Gamma + CLOB), no auth",
            "city": city.name,
            "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "gamma_base": config.GAMMA_BASE_URL,
            "clob_base": config.CLOB_BASE_URL,
            "event_count": len(events),
        },
        "gamma_events": events,        # raw event objects, verbatim
        "clob_quotes": clob_quotes,    # keyed by token_id, raw CLOB bodies
    }
    return raw_store.append_record(config.RAW_POLYMARKET_DIR, "polymarket", envelope)


def ingest_city(city: config.City) -> pathlib.Path | None:
    """Snapshot all live temperature markets for one city."""
    try:
        discovered = discover_events(city)
    except Exception:
        logger.exception("Market discovery FAILED for %s", city.name)
        return None

    if not discovered:
        logger.warning("No %s temperature markets matched (open=%s).", city.name,
                       config.ONLY_OPEN_MARKETS)
        return None

    events: list[dict] = []
    clob_quotes: dict = {}
    for ev in discovered:
        detail = fetch_event_detail(ev["slug"]) or ev  # fall back to search result
        events.append(detail)
        logger.info("  %s | open=%s | %d buckets", detail.get("title"),
                    not detail.get("closed"), len(detail.get("markets", [])))

        if config.CLOB_ENRICH:
            for token_id in _yes_token_ids(detail):
                if token_id not in clob_quotes:  # de-dupe across events
                    clob_quotes[token_id] = fetch_clob_quote(token_id)

    path = _write_raw(city, events, clob_quotes)
    logger.info("Polymarket %s: %d event(s), %d CLOB quote(s) -> %s",
                city.name, len(events), len(clob_quotes), path.name)
    return path


def run() -> list[pathlib.Path]:
    """Ingest Polymarket for every configured city. Isolated per city."""
    written: list[pathlib.Path] = []
    for city in config.CITIES:
        path = ingest_city(city)
        if path:
            written.append(path)
    logger.info("Polymarket ingestion done: %d file(s) written.", len(written))
    return written


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    run()
