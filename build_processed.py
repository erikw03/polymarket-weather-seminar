"""
Transformation layer: raw zone  ->  clean, typed DuckDB tables (the "silver/gold"
stage of the pipeline).

Design decisions (Betriebskonzept) — chosen with the seminar in mind:
- GRAIN of the main fact table = (city, target_date, snapshot_time, bucket).
  One row per temperature bucket per snapshot. This is the most detailed grain;
  every coarser view (per-snapshot distribution, per-market summary) can be
  aggregated up from it, so we never lose information.
- UNITS are normalized to °C for uniform analysis (NYC trades in °F), but the
  original native value/unit is kept in every row, so nothing is thrown away.
- GROUND TRUTH for the actual outcome is the market's resolved bucket (the
  official station reading Polymarket settles on). The Open-Meteo ERA5 archive is
  kept alongside as an *auxiliary* actual — it is a gridded reanalysis and runs
  ~1–2 °C below the station, which we surface rather than hide.
- IDEMPOTENT: tables are dropped and rebuilt from the raw zone on every run, so
  re-running after more data is collected simply refreshes everything. The raw
  zone stays the single source of truth; this DuckDB file is a derived artifact
  (hence git-ignored and regenerated, never hand-edited).

Sources combined:
- Live raw zone: data/raw/{polymarket,weather}/*.ndjson (hourly snapshots).
- Historical backfill: data/backfill/{polymarket,weather}_<city>_history.json.

Output: data/processed/temperature_markets.duckdb with tables
    fact_price, fact_forecast, dim_outcome
and a convenience mart view  mart_market_vs_forecast_vs_actual.

Usage:  python build_processed.py
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import logging
import re

import duckdb
import pandas as pd

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("build_processed")

DB_PATH = config.PROJECT_ROOT / "data" / "processed" / "temperature_markets.duckdb"
CLOSE_HOUR_UTC = 12  # markets resolve at 12:00 UTC on the target date


# --- parsing helpers ---------------------------------------------------------
def f_to_c(x: float | None) -> float | None:
    return None if x is None else round((x - 32) * 5.0 / 9.0, 2)


def parse_bucket(label: str, unit: str) -> dict:
    """Parse a bucket label into numeric bounds, in native unit and in °C.

    Handles: "21°C", "32-33°F" (range), "9°C or below", "46°F or higher".
    Returns native low/high/mid plus their °C equivalents and a `kind`.
    """
    low = high = None
    if "or below" in label:
        kind = "below"
        high = int(re.search(r"\d+", label).group())
        mid = high
    elif "or higher" in label or "or above" in label:
        kind = "above"
        low = int(re.search(r"\d+", label).group())
        mid = low
    elif (rng := re.search(r"(\d+)\s*-\s*(\d+)", label)):
        kind = "range"
        low, high = int(rng.group(1)), int(rng.group(2))
        mid = (low + high) / 2
    else:
        kind = "exact"
        low = high = int(re.search(r"\d+", label).group())
        mid = low

    if unit == "fahrenheit":
        to_c = f_to_c
    else:
        to_c = lambda v: None if v is None else float(v)
    return {
        "bucket_kind": kind,
        "bucket_low_c": to_c(low), "bucket_high_c": to_c(high), "bucket_mid_c": to_c(mid),
    }


def iso_to_naive_utc(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)


def target_date_of(end_date_iso: str) -> dt.date:
    return iso_to_naive_utc(end_date_iso).date()


def hours_to_close(snapshot: dt.datetime, target_date: dt.date) -> float:
    close = dt.datetime.combine(target_date, dt.time(CLOSE_HOUR_UTC))
    return round((close - snapshot).total_seconds() / 3600.0, 2)


UNIT_BY_CITY = {c.name: c.temperature_unit for c in config.CITIES}


# --- load PRICES (the fact table) -------------------------------------------
def load_prices() -> pd.DataFrame:
    rows: list[dict] = []

    # 1) live hourly snapshots
    for f in glob.glob(str(config.RAW_POLYMARKET_DIR / "polymarket_*.ndjson")):
        for line in open(f, encoding="utf-8"):
            rec = json.loads(line)
            city = rec["_meta"]["city"]
            unit = UNIT_BY_CITY.get(city, "celsius")
            snap = iso_to_naive_utc(rec["_meta"]["fetched_at_utc"])
            for ev in rec.get("gamma_events", []):
                td = target_date_of(ev["endDate"])
                for m in ev.get("markets", []):
                    op = json.loads(m.get("outcomePrices") or "[]")
                    if not op:
                        continue
                    b = parse_bucket(m["groupItemTitle"], unit)
                    rows.append({
                        "city": city, "target_date": td, "snapshot_ts": snap,
                        "source": "live", "native_unit": unit,
                        "bucket_label": m["groupItemTitle"], **b,
                        "yes_price": float(op[0]),
                        "hours_to_close": hours_to_close(snap, td),
                    })

    # 2) historical backfill (full hourly trajectories of resolved markets)
    for f in glob.glob(str(config.PROJECT_ROOT / "data" / "backfill" / "polymarket_*_history.json")):
        data = json.load(open(f, encoding="utf-8"))
        city = data["city"]
        unit = UNIT_BY_CITY.get(city, "celsius")
        for m in data["markets"]:
            td = dt.date.fromisoformat(m["date"])
            for bk in m["buckets"]:
                b = parse_bucket(bk["bucket"], unit)
                for pt in bk["history"]:
                    snap = dt.datetime.fromtimestamp(pt["t"], dt.timezone.utc).replace(tzinfo=None)
                    rows.append({
                        "city": city, "target_date": td, "snapshot_ts": snap,
                        "source": "backfill", "native_unit": unit,
                        "bucket_label": bk["bucket"], **b,
                        "yes_price": float(pt["p"]),
                        "hours_to_close": hours_to_close(snap, td),
                    })

    df = pd.DataFrame(rows)
    # Data-quality: live and backfill can overlap on recent closed days. Dedup at
    # hourly resolution, preferring backfill (the curated settled trajectory).
    df["snap_hour"] = df["snapshot_ts"].dt.floor("h")
    df["prio"] = (df["source"] == "live").astype(int)  # backfill=0 wins
    df = (df.sort_values("prio")
            .drop_duplicates(["city", "target_date", "bucket_label", "snap_hour"], keep="first")
            .drop(columns=["snap_hour", "prio"])
            .reset_index(drop=True))
    return df


# --- load FORECASTS ----------------------------------------------------------
def _forecast_rows_from_daily(city, unit, daily, ts, source, rows):
    to_c = f_to_c if unit == "fahrenheit" else (lambda v: float(v))
    for i, d in enumerate(daily["time"]):
        rows.append({
            "city": city, "target_date": dt.date.fromisoformat(d),
            "forecast_ts": ts, "source": source, "native_unit": unit,
            "forecast_max_native": daily["temperature_2m_max"][i],
            "forecast_min_native": daily["temperature_2m_min"][i],
            "forecast_max_c": to_c(daily["temperature_2m_max"][i]),
            "forecast_min_c": to_c(daily["temperature_2m_min"][i]),
        })


def load_forecasts() -> pd.DataFrame:
    rows: list[dict] = []
    for f in glob.glob(str(config.RAW_WEATHER_DIR / "weather_*.ndjson")):
        for line in open(f, encoding="utf-8"):
            rec = json.loads(line)
            if rec["_meta"]["kind"] != "weather-forecast":
                continue
            city = rec["_meta"]["city"]
            unit = rec["_meta"].get("temperature_unit") or UNIT_BY_CITY.get(city, "celsius")
            _forecast_rows_from_daily(city, unit, rec["response"]["daily"],
                                      iso_to_naive_utc(rec["_meta"]["fetched_at_utc"]), "live", rows)
    for f in glob.glob(str(config.PROJECT_ROOT / "data" / "backfill" / "weather_*_history.json")):
        data = json.load(open(f, encoding="utf-8"))
        hf = data.get("historical_forecast")
        if hf:
            _forecast_rows_from_daily(data["city"], data["temperature_unit"], hf["daily"],
                                      None, "backfill", rows)
    return pd.DataFrame(rows)


# --- load OUTCOMES (resolved bucket + ERA5 actual) ---------------------------
def load_outcomes() -> pd.DataFrame:
    res_rows, era_rows = [], []

    # resolved winning bucket (= official station reading) from backfill
    for f in glob.glob(str(config.PROJECT_ROOT / "data" / "backfill" / "polymarket_*_history.json")):
        data = json.load(open(f, encoding="utf-8"))
        city = data["city"]; unit = UNIT_BY_CITY.get(city, "celsius")
        for m in data["markets"]:
            if not m.get("resolved_bucket"):
                continue
            b = parse_bucket(m["resolved_bucket"], unit)
            res_rows.append({"city": city, "target_date": dt.date.fromisoformat(m["date"]),
                             "resolved_bucket": m["resolved_bucket"],
                             "resolved_mid_c": b["bucket_mid_c"],
                             "resolved_low_c": b["bucket_low_c"], "resolved_high_c": b["bucket_high_c"]})

    # ERA5 archive actual (auxiliary) from live + backfill
    def add_archive(city, unit, daily):
        to_c = f_to_c if unit == "fahrenheit" else (lambda v: None if v is None else float(v))
        for i, d in enumerate(daily["time"]):
            v = daily["temperature_2m_max"][i]
            era_rows.append({"city": city, "target_date": dt.date.fromisoformat(d),
                             "era5_actual_max_c": to_c(v)})

    for f in glob.glob(str(config.RAW_WEATHER_DIR / "weather_*.ndjson")):
        for line in open(f, encoding="utf-8"):
            rec = json.loads(line)
            if rec["_meta"]["kind"] == "weather-archive":
                city = rec["_meta"]["city"]
                unit = rec["_meta"].get("temperature_unit") or UNIT_BY_CITY.get(city, "celsius")
                add_archive(city, unit, rec["response"]["daily"])
    for f in glob.glob(str(config.PROJECT_ROOT / "data" / "backfill" / "weather_*_history.json")):
        data = json.load(open(f, encoding="utf-8"))
        aa = data.get("archive_actuals")
        if aa:
            add_archive(data["city"], data["temperature_unit"], aa["daily"])

    res = pd.DataFrame(res_rows).drop_duplicates(["city", "target_date"])
    era = (pd.DataFrame(era_rows).dropna(subset=["era5_actual_max_c"])
           .drop_duplicates(["city", "target_date"]))
    return res.merge(era, on=["city", "target_date"], how="outer")


# --- build -------------------------------------------------------------------
def main() -> None:
    logger.info("Loading & transforming raw zone ...")
    prices = load_prices()
    forecasts = load_forecasts()
    outcomes = load_outcomes()
    logger.info("fact_price=%d rows | fact_forecast=%d rows | dim_outcome=%d rows",
                len(prices), len(forecasts), len(outcomes))

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    for name, df in [("fact_price", prices), ("fact_forecast", forecasts), ("dim_outcome", outcomes)]:
        con.register("_df", df)
        con.execute(f"DROP TABLE IF EXISTS {name}")
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM _df")
        con.unregister("_df")

    # Gold mart: one row per resolved market joining the market's closing-ish
    # implied-mode bucket, the latest issued forecast, and the actual outcome.
    con.execute("""
        CREATE OR REPLACE VIEW mart_market_vs_forecast_vs_actual AS
        WITH last_price AS (   -- the most informative snapshot: closest to close
            SELECT city, target_date, bucket_mid_c, yes_price,
                   ROW_NUMBER() OVER (PARTITION BY city, target_date
                                      ORDER BY hours_to_close ASC, yes_price DESC) rn
            FROM fact_price WHERE hours_to_close >= 0
        ),
        market_mode AS (       -- bucket the market judged most likely near close
            SELECT city, target_date, bucket_mid_c AS market_mode_c, yes_price AS market_mode_prob
            FROM last_price WHERE rn = 1
        ),
        fc AS (                -- latest issued forecast per target_date
            SELECT city, target_date, forecast_max_c,
                   ROW_NUMBER() OVER (PARTITION BY city, target_date
                                      ORDER BY forecast_ts DESC NULLS LAST) rn
            FROM fact_forecast
        )
        SELECT o.city, o.target_date,
               mm.market_mode_c, mm.market_mode_prob,
               f.forecast_max_c,
               o.resolved_mid_c AS actual_station_c,
               o.era5_actual_max_c
        FROM dim_outcome o
        LEFT JOIN market_mode mm USING (city, target_date)
        LEFT JOIN (SELECT city, target_date, forecast_max_c FROM fc WHERE rn = 1) f
               USING (city, target_date)
        ORDER BY o.city, o.target_date
    """)
    con.close()
    logger.info("Wrote %s", DB_PATH)


if __name__ == "__main__":
    main()
