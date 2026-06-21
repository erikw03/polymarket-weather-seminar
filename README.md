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

### Historical backfill (the ML dataset)

`backfill_history.py` reconstructs *months* of already-resolved markets — the
biggest lever for dataset size. For every past day it fetches the resolved market
(winning temperature bucket), the full **hourly YES-price trajectory** of every
bucket (CLOB `/prices-history` with explicit `startTs`/`endTs` — `interval=max`
returns nothing for older markets), plus the issued forecast and observed actuals.

```bash
python backfill_history.py 2026-03-01 2026-06-20    # all configured cities
```

Output is a handful of **consolidated** files under `data/backfill/` (one pair
per city), not thousands of tiny snapshots:
`polymarket_<city>_history.json` (markets → buckets → trajectories → outcome) and
`weather_<city>_history.json`. A March–June run yields ~420 resolved city-days and
~240k price points in ~8 MB.

## Design decisions (Betriebskonzept)

- **Batch, not streaming.** Daily-temperature markets move slowly and resolve
  once per day; periodic polling (e.g. hourly via cron) captures the price path
  with negligible load. No streaming infrastructure is justified.
- **Append-only raw zone, partitioned by day (NDJSON).** Each run appends one
  JSON line per snapshot to a per-day file (`weather_<date>.ndjson`,
  `polymarket_<date>.ndjson`) instead of writing hundreds of tiny files. Still
  append-only (we only add lines), so the audit trail and idempotency hold, but
  the repo stays tidy and git stores appended lines efficiently. See
  `src/raw_store.py`.
- **Store raw, clean later.** Responses are stored verbatim (wrapped in a tiny
  `_meta` envelope recording what/when). Cleaning, joining and quality checks are
  deliberately deferred to a separate later stage.
- **Resilience.** Transient HTTP failures (network errors, 429, 5xx) are retried
  with exponential backoff (`tenacity`); 4xx are not retried. A failure in one
  source never crashes the other, and per-city errors are isolated.
- **Externalised config.** Cities and tunables live in `config.py` / `.env`, so
  scaling from "Munich only" to many cities needs no code change.

## Transformation layer (raw → DuckDB)

`build_processed.py` turns the raw zone (live NDJSON + historical backfill) into
clean, typed, analysis-ready tables in `data/processed/temperature_markets.duckdb`.
It is **idempotent** — it drops and rebuilds everything from the raw zone on each
run, so re-run it any time after pulling fresh data:

```bash
python build_processed.py
```

Design choices: main fact grain = (city, target_date, snapshot_time, bucket);
all temperatures normalized to **°C** (native value kept too); ground truth =
the market's **resolved bucket** (official station reading), with ERA5 archive as
an auxiliary actual. The DuckDB file is a *derived artifact* — git-ignored and
regenerated, never hand-edited (raw zone stays the single source of truth).

Tables:
- **`fact_price`** — one row per bucket per snapshot: `yes_price` (implied prob),
  `bucket_low_c/high_c/mid_c`, `hours_to_close`, `source` (live/backfill).
- **`fact_forecast`** — issued forecast max/min (°C) per city/target_date/fetch.
- **`dim_outcome`** — resolved bucket (station truth, °C) + ERA5 actual per market.
- **`mart_market_vs_forecast_vs_actual`** (view) — one row per resolved market
  comparing the market's near-close mode, the forecast, and the actual.

Example query:

```sql
SELECT city, ROUND(AVG(ABS(market_mode_c - actual_station_c)),2) AS market_mae_c,
             ROUND(AVG(ABS(forecast_max_c - actual_station_c)),2) AS forecast_mae_c
FROM mart_market_vs_forecast_vs_actual
WHERE market_mode_c IS NOT NULL GROUP BY city;
```

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
