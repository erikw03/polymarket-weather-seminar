# Polymarket × Weather — Ingestion Layer

A data-engineering seminar project (university, **non-commercial**). This repo
currently contains **only the ingestion layer**: it collects two public data
sources into an append-only raw zone for later ML analysis.

**Research question (analytical, not a trading tool):** How well do Polymarket's
implied probabilities for daily-temperature markets track weather forecasts and
the actual outcome?

Everything here is **read-only**. We only fetch public data — no wallet, no
authentication, no trading. (Trading on Polymarket is geoblocked in Germany; we
keep the framing strictly analytical.)

## Data sources

1. **Open-Meteo** — daily temperature forecasts + observed actuals (ERA5 archive).
2. **Polymarket** — public "Highest temperature in `<city>` on `<date>`" markets
   via the Gamma API (metadata + prices) and the CLOB API (live order-book quotes).

Both APIs are public and require **no API key**.

## Attribution & licensing

> Weather data by [Open-Meteo.com](https://open-meteo.com/), licensed under
> **CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/).

Open-Meteo's free non-commercial tier allows up to 10,000 calls/day, which is far
more than this pipeline uses. Polymarket data is accessed via its **public,
read-only** Gamma and CLOB endpoints.

## Project layout

```
p_2/
├── config.py             # target cities (lat/lon/tz) + endpoints + tunables
├── run_ingestion.py      # single entry point (cron-safe); runs both sources
├── requirements.txt
├── .env.example          # tunables (no secrets needed)
├── src/
│   ├── http_client.py    # shared httpx client + tenacity retry policy
│   ├── ingest_weather.py # Open-Meteo forecast + ERA5 archive
│   └── ingest_polymarket.py  # Gamma discovery + CLOB quotes
└── data/
    ├── raw/weather/      # append-only raw snapshots (timestamped JSON)
    ├── raw/polymarket/   # append-only raw snapshots (timestamped JSON)
    └── processed/        # empty for now (cleaning is a later step)
```

## Setup

```bash
cd "/path/to/p_2"          # NB: the path may contain a space — quote it
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # optional; defaults work as-is
```

## Run

```bash
python run_ingestion.py            # both sources
python -m src.ingest_weather       # weather only
python -m src.ingest_polymarket    # polymarket only
```

Each run writes new **timestamped** files to `data/raw/...`; nothing is ever
overwritten.

## Schedule (cron)

Snapshot prices regularly — hourly here. **Start scheduling the day it works:**
historical Polymarket price snapshots cannot be backfilled in bulk, so every day
of delay is lost training data. (Past *forecasts* can be backfilled via
Open-Meteo's historical-forecast API; past *market prices* mostly cannot.)

This project runs **hourly on macOS via launchd** (preferred over cron on a
laptop: cron silently skips runs while the machine sleeps, whereas launchd runs
at load and coalesces one run on wake). The agent lives at
`~/Library/LaunchAgents/com.erikwegner.weather-polymarket-ingest.plist` and uses
`StartInterval=3600` + `RunAtLoad`, logging to `cron.log`.

```bash
# (re)load the hourly agent
launchctl unload ~/Library/LaunchAgents/com.erikwegner.weather-polymarket-ingest.plist 2>/dev/null
launchctl load   ~/Library/LaunchAgents/com.erikwegner.weather-polymarket-ingest.plist
launchctl list | grep weather-polymarket-ingest    # PID + last exit code (0 = ok)
```

Laptop caveat: data has gaps while the machine is asleep (nights/weekends). For
gap-free collection, deploy on an always-on machine and use plain cron instead:

```cron
0 * * * * cd "/path/to/p_2" && /path/to/p_2/.venv/bin/python run_ingestion.py >> cron.log 2>&1
```

### Backfilling missed forecasts

Only *forecasts* can be recovered (market prices cannot). Backfill a date range:

```bash
python backfill_forecast.py 2026-06-16 2026-06-19   # inclusive, YYYY-MM-DD
```

This writes `weather-historical-forecast_*.json` snapshots into the raw zone.

## Design decisions (Betriebskonzept)

- **Batch, not streaming.** Daily-temperature markets move slowly and resolve
  once per day; periodic polling (e.g. hourly via cron) captures the price path
  with negligible load. No streaming infrastructure is justified.
- **Append-only immutable raw zone.** Every run writes a new timestamped file and
  never mutates old ones. This makes the pipeline idempotent and safe to re-run,
  and gives a full audit trail of exactly what each API returned and when.
- **Store raw, clean later.** Responses are stored verbatim (wrapped in a tiny
  `_meta` envelope recording what/when). Cleaning, joining and quality checks are
  deliberately deferred to a separate later stage.
- **Resilience.** Transient HTTP failures (network errors, 429, 5xx) are retried
  with exponential backoff (`tenacity`); 4xx are not retried. A failure in one
  source never crashes the other, and per-city errors are isolated.
- **Externalised config.** Cities and tunables live in `config.py` / `.env`, so
  scaling from "Munich only" to many cities needs no code change.

## Data-quality caveats (to address in the report)

- **Two different "actuals".** Polymarket settles on the official station reading
  (Wunderground/NWS); Open-Meteo's archive is **ERA5 reanalysis** on a grid.
  These can differ slightly — reconcile and document when building the corpus.
- **ERA5 lag.** The archive lags real time by ~5 days, so the most recent days in
  the look-back window may come back null.
- **JSON-in-JSON.** Several Gamma fields (`outcomes`, `outcomePrices`,
  `clobTokenIds`) are JSON-encoded strings and must be parsed twice.

## Out of scope (later steps)

Corpus join/cleaning, DuckDB storage, data-quality checks, and the ML model are
intentionally **not** built yet.
