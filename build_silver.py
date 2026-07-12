"""
AP 1.2 — Transform Raw(Bronze) -> Cleaned(Silver).

Implements the approved schema `docs/cleaned_schema_AP1.1.md` exactly:
  grain   : 1 row = city x target_date x bucket (each bucket is its own binary market)
  as-of   : last snapshot BEFORE 00:00 *local time* of the target day (D2, leakage-safe)
  label   : Open-Meteo archive max, latest fetch wins, station coords only,
            rounded half-up to whole degrees in the market's native unit (D3)
  output  : DuckDB `data/processed/silver.duckdb` table `market_bucket_daily`
            + Parquet export partitioned by city (idempotent full rebuild)

Raw zone is read-only for this script. Re-running always reproduces the same
table from the same raw corpus (deterministic full rebuild = idempotency).

Usage:  python build_silver.py
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import logging
import re
import subprocess
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("build_silver")

DB_PATH = config.PROJECT_ROOT / "data" / "processed" / "silver.duckdb"
PARQUET_DIR = config.PROJECT_ROOT / "data" / "processed" / "silver" / "market_bucket_daily"
OVERROUND_OUTLIER_THRESHOLD = 0.10  # |sum-1| above this -> flag (approved schema)
ASOF_POLICY = "D-1_2359_local"

CITY = {c.name: c for c in config.CITIES}
TZ = {c.name: ZoneInfo(c.timezone) for c in config.CITIES}


# ---------------------------------------------------------------- helpers
def parse_ts(iso: str) -> dt.datetime:
    """ISO string -> aware UTC datetime."""
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def cutoff(city: str, target_date: dt.date) -> dt.datetime:
    """D2 as-of cut: 00:00 local time of the target day, as UTC instant."""
    return dt.datetime.combine(target_date, dt.time(0, 0), tzinfo=TZ[city]).astimezone(dt.timezone.utc)


def f_to_c(v: float | None) -> float | None:
    return None if v is None else round((v - 32.0) * 5.0 / 9.0, 2)


def to_c(v: float | None, unit: str) -> float | None:
    return f_to_c(v) if unit == "fahrenheit" else v


def half_up(v: float) -> int:
    """Round to whole degrees, ties away from zero (D3; NOT Python's banker's round)."""
    return int(Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


BUCKET_RE_RANGE = re.compile(r"^(-?\d+)\s*-\s*(-?\d+)°([CF])$")
BUCKET_RE_EXACT = re.compile(r"^(-?\d+)°([CF])$")
BUCKET_RE_BELOW = re.compile(r"^(-?\d+)°([CF]) or below$")
BUCKET_RE_ABOVE = re.compile(r"^(-?\d+)°([CF]) or (?:higher|above)$")


def parse_bucket(label: str) -> dict | None:
    """Parse the 4 label patterns into kind/unit/bounds (native)."""
    if (m := BUCKET_RE_EXACT.match(label)):
        n, u = int(m.group(1)), m.group(2)
        return {"bucket_kind": "exact", "bucket_unit": u, "low": n, "high": n}
    if (m := BUCKET_RE_RANGE.match(label)):
        return {"bucket_kind": "range", "bucket_unit": m.group(3),
                "low": int(m.group(1)), "high": int(m.group(2))}
    if (m := BUCKET_RE_BELOW.match(label)):
        return {"bucket_kind": "below", "bucket_unit": m.group(2), "low": None, "high": int(m.group(1))}
    if (m := BUCKET_RE_ABOVE.match(label)):
        return {"bucket_kind": "above", "bucket_unit": m.group(2), "low": int(m.group(1)), "high": None}
    return None


def in_bucket(value_int: int, b: dict) -> bool:
    lo, hi = b["low"], b["high"]
    return (lo is None or value_int >= lo) and (hi is None or value_int <= hi)


# ---------------------------------------------------------------- pass 1: market snapshots
def load_market_asof() -> tuple[dict, dict, set]:
    """One streaming pass over polymarket_*.ndjson.

    Returns:
      best[(city, target_date)]  = (asof_ts, event_dict, clob_quotes_dict_of_line)
      n_pre[(city, target_date)] = count of snapshots before the cut
      partial_days               = set of file dates considered partial (U5)
    """
    best: dict = {}
    n_pre: dict = defaultdict(int)
    line_counts: dict[str, int] = {}
    files = sorted(glob.glob(str(config.RAW_POLYMARKET_DIR / "polymarket_*.ndjson")))
    now = dt.datetime.now(dt.timezone.utc)
    for f in files:
        fday = f.rsplit("_", 1)[1].removesuffix(".ndjson")
        n_lines = 0
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                n_lines += 1
                rec = json.loads(line)
                city = rec["_meta"]["city"]
                ts = parse_ts(rec["_meta"]["fetched_at_utc"])
                for ev in rec.get("gamma_events", []):
                    td_s = ev.get("eventDate") or ev.get("endDate", "")[:10]
                    try:
                        td = dt.date.fromisoformat(td_s)
                    except ValueError:
                        continue
                    cut = cutoff(city, td)
                    if ts >= cut:
                        continue  # post-cut snapshot: never a feature (leakage rule)
                    if cut > now:
                        continue  # target day not started yet: as-of not final (U8) -> skip
                    key = (city, td)
                    n_pre[key] += 1
                    if key not in best or ts > best[key][0]:
                        best[key] = (ts, ev, rec.get("clob_quotes", {}))
        line_counts[fday] = n_lines
    med = sorted(line_counts.values())[len(line_counts) // 2]
    partial = {d for d, n in line_counts.items() if n < 0.5 * med}
    partial.add(max(line_counts))  # last collection day is still filling
    logger.info("market pass: %d target-day events selected, partial days=%s",
                len(best), sorted(partial))
    return best, n_pre, partial


# ---------------------------------------------------------------- pass 2: weather
def load_weather() -> tuple[dict, dict]:
    """One pass over weather_*.ndjson.

    forecasts[(city, target_date)] = (asof_ts, max_native, min_native)   [pre-cut latest]
    observed[(city, target_date)]  = (latest_fetch_ts, max_native, first_seen_lag_days)
    Label rule (D3/U6): archive records must carry `_meta.station` (excludes the
    11 legacy records incl. Munich city-centre coordinates).
    """
    forecasts: dict = {}
    obs_latest: dict = {}
    obs_first_seen: dict = {}
    files = sorted(glob.glob(str(config.RAW_WEATHER_DIR / "weather_*.ndjson")))
    now = dt.datetime.now(dt.timezone.utc)
    for f in files:
        fday = dt.date.fromisoformat(f.rsplit("_", 1)[1].removesuffix(".ndjson"))
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                meta = rec["_meta"]
                city, kind = meta["city"], meta["kind"]
                if kind not in ("weather-forecast", "weather-archive"):
                    continue  # F3: ignore the single historical-forecast record
                ts = parse_ts(meta["fetched_at_utc"])
                daily = rec["response"]["daily"]
                for i, t in enumerate(daily["time"]):
                    td = dt.date.fromisoformat(t)
                    vmax = daily["temperature_2m_max"][i]
                    key = (city, td)
                    if kind == "weather-forecast":
                        cut = cutoff(city, td)
                        if ts >= cut or cut > now:
                            continue
                        if key not in forecasts or ts > forecasts[key][0]:
                            forecasts[key] = (ts, vmax, daily["temperature_2m_min"][i])
                    else:  # weather-archive -> label source
                        if not meta.get("station") or vmax is None:
                            continue  # U6 legacy exclusion / missing value
                        if key not in obs_latest or ts > obs_latest[key][0]:
                            obs_latest[key] = (ts, vmax)
                        lag = (fday - td).days
                        if key not in obs_first_seen or lag < obs_first_seen[key]:
                            obs_first_seen[key] = lag
    observed = {k: (ts, v, obs_first_seen.get(k)) for k, (ts, v) in obs_latest.items()}
    logger.info("weather pass: %d forecast keys, %d observed keys", len(forecasts), len(observed))
    return forecasts, observed


# ---------------------------------------------------------------- pass 3: resolutions
def load_resolutions() -> dict:
    """resolutions_*.ndjson -> winner bucket label per (city, target_date)."""
    winners: dict = {}
    for f in sorted(glob.glob(str(config.RAW_POLYMARKET_DIR / "resolutions_*.ndjson"))):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                ev = rec.get("event", {})
                if not ev.get("closed"):
                    continue
                city = rec["_meta"]["city"]
                td = dt.date.fromisoformat(rec["_meta"]["target_date"])
                for mk in ev.get("markets", []):
                    try:
                        if float(json.loads(mk["outcomePrices"])[0]) >= 0.99:
                            winners[(city, td)] = mk["groupItemTitle"]
                            break
                    except (KeyError, ValueError, json.JSONDecodeError):
                        continue
    logger.info("resolutions pass: %d official winners", len(winners))
    return winners


# ---------------------------------------------------------------- backfill (AP 1.3)
def load_backfill_rows(live_keys: set, version: str, created: dt.datetime) -> list[dict]:
    """Rows with source='backfill' from data/backfill/ (Mar 1 - Jun 20 2026).

    Sources per city:
      polymarket_<c>_history.json  -> hourly yes-price trajectories + resolved_bucket
      weather_<c>_prevday1.json    -> lead-consistent forecast (previous_day1 hourly -> daily max/min)
      weather_<c>_history.json     -> archive_actuals (secondary Open-Meteo label)

    Rules (DECISIONS_AP1.3):
      - live wins: (city, target_date) already in live silver -> skipped here
      - per-bucket as-of: last trajectory point before the D2 cut; buckets without a
        pre-cut point are dropped; if <50% of buckets or the WINNER bucket lack a
        pre-cut price, the whole day is skipped (incomplete distribution/unlabelable)
      - overround_sum approximated from per-bucket as-of prices (timestamps differ
        by minutes across buckets; documented approximation)
      - not available historically -> NULL: clob_mid, volumes, forecast_asof_ts,
        event_id, market_id, resolution_source_url, observed_lag_days
    """
    bdir = config.PROJECT_ROOT / "data" / "backfill"
    rows: list[dict] = []
    skipped_days = 0
    for c in config.CITIES:
        cs = c.name.lower().replace(" ", "-")
        try:
            hist = json.loads((bdir / f"polymarket_{cs}_history.json").read_text())
            wx = json.loads((bdir / f"weather_{cs}_history.json").read_text())
            prev = json.loads((bdir / f"weather_{cs}_prevday1.json").read_text())
        except FileNotFoundError as e:
            logger.warning("backfill files missing for %s (%s) - skipped", c.name, e)
            continue
        # previous_day1 hourly -> per-date native max/min
        fc_by_date: dict[str, list[float]] = defaultdict(list)
        h = prev["response"]["hourly"]
        for t, v in zip(h["time"], h["temperature_2m_previous_day1"]):
            if v is not None:
                fc_by_date[t[:10]].append(v)
        # archive actuals -> per-date native max
        aa = wx["archive_actuals"]["daily"]
        obs_by_date = {t: v for t, v in zip(aa["time"], aa["temperature_2m_max"]) if v is not None}

        for m in hist["markets"]:
            td = dt.date.fromisoformat(m["date"])
            if (c.name, td) in live_keys:
                continue  # live wins on overlap
            winner = m.get("resolved_bucket")
            cut = cutoff(c.name, td)
            end_ts = parse_ts(m["endDate"])
            # per-bucket as-of selection
            sel = []  # (bucket_label, parsed, yes, asof_ts, n_pre)
            for b in m["buckets"]:
                pb = parse_bucket(b["bucket"])
                if pb is None:
                    continue
                pre = [(t, p) for t, p in ((pt["t"], pt["p"]) for pt in b["history"])
                       if dt.datetime.fromtimestamp(t, dt.timezone.utc) < cut]
                if not pre:
                    continue
                t_last, p_last = pre[-1]
                sel.append((b["bucket"], pb, float(p_last),
                            dt.datetime.fromtimestamp(t_last, dt.timezone.utc), len(pre),
                            b.get("yes_token")))
            if not winner or len(sel) < 0.5 * len(m["buckets"]) or winner not in {s[0] for s in sel}:
                skipped_days += 1
                continue
            osum = sum(s[2] for s in sel)
            if osum == 0:
                skipped_days += 1
                continue
            fcv = fc_by_date.get(m["date"]) or None
            obs = obs_by_date.get(m["date"])
            obs_int = half_up(obs) if obs is not None else None
            om_label = next((lbl for lbl, pb, *_ in sel
                             if obs_int is not None and in_bucket(obs_int, pb)), None)
            for lbl, pb, yes, asof_ts, n_pre, token in sel:
                low, high = pb["low"], pb["high"]
                mid_native = low if high is None else high if low is None else (low + high) / 2
                rows.append({
                    "city": c.name, "target_date": td, "bucket_label": lbl,
                    "bucket_kind": pb["bucket_kind"], "bucket_unit": pb["bucket_unit"],
                    "bucket_low_native": low, "bucket_high_native": high,
                    "bucket_mid_c": to_c(float(mid_native), c.temperature_unit),
                    "yes_price_raw": yes, "yes_price_norm": yes / osum, "overround_sum": osum,
                    "clob_mid": None, "bucket_volume": None, "bucket_liquidity": None,
                    "event_volume": None, "event_liquidity": None,
                    "n_snapshots_pre_asof": n_pre,
                    "hours_to_event_end": round((end_ts - asof_ts).total_seconds() / 3600, 2),
                    "forecast_max_native": max(fcv) if fcv else None,
                    "forecast_min_native": min(fcv) if fcv else None,
                    "forecast_max_c": to_c(max(fcv), c.temperature_unit) if fcv else None,
                    "forecast_min_c": to_c(min(fcv), c.temperature_unit) if fcv else None,
                    "label_is_winner_official": lbl == winner,
                    "label_in_bucket": in_bucket(obs_int, pb) if obs_int is not None else None,
                    "label_source": "market_resolution_official; aux=open_meteo_archive_latest",
                    "observed_max_native": obs, "observed_max_c": to_c(obs, c.temperature_unit),
                    "observed_max_int_native": obs_int,
                    "observed_lag_days": None,
                    "market_resolved_bucket": winner,
                    "labels_agree": (winner == om_label) if winner and om_label else None,
                    "source": "backfill", "asof_policy": ASOF_POLICY,
                    "market_asof_ts": asof_ts.replace(tzinfo=None), "forecast_asof_ts": None,
                    "event_id": None, "event_slug": m.get("slug"), "market_id": None,
                    "clob_token_yes": token,
                    "station": c.station, "resolution_source_url": None,
                    "temperature_unit": c.temperature_unit,
                    "flag_overround_outlier": abs(osum - 1) > OVERROUND_OUTLIER_THRESHOLD,
                    "flag_partial_day": False,
                    "transform_version": version, "created_at": created.replace(tzinfo=None),
                })
    logger.info("backfill pass: %d rows, %d days skipped (sparse/unlabelable)",
                len(rows), skipped_days)
    return rows


# ---------------------------------------------------------------- assemble
def build_rows() -> pd.DataFrame:
    best, n_pre, partial_days = load_market_asof()
    forecasts, observed = load_weather()
    winners = load_resolutions()
    try:
        version = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                                 text=True, cwd=config.PROJECT_ROOT).stdout.strip() or "unknown"
    except OSError:
        version = "unknown"
    created = dt.datetime.now(dt.timezone.utc)

    rows = []
    for (city, td), (asof_ts, ev, clob) in sorted(best.items()):
        c = CITY[city]
        unit = c.temperature_unit
        end_ts = parse_ts(ev["endDate"])
        fc = forecasts.get((city, td))
        ob = observed.get((city, td))
        obs_int = half_up(ob[1]) if ob else None
        winner = winners.get((city, td))

        # per-event: prices of all buckets at this snapshot (for overround/norm)
        buckets = []
        for mk in ev.get("markets", []):
            b = parse_bucket(mk.get("groupItemTitle", ""))
            if b is None:
                logger.warning("unparseable bucket label %r (%s %s) - row skipped",
                               mk.get("groupItemTitle"), city, td)
                continue
            try:
                yes = float(json.loads(mk["outcomePrices"])[0])
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
            buckets.append((mk, b, yes))
        osum = sum(y for _, _, y in buckets)
        if not buckets or osum == 0:
            continue

        # open-meteo label bucket for labels_agree
        om_label = next((mk.get("groupItemTitle") for mk, b, _ in buckets
                         if obs_int is not None and in_bucket(obs_int, b)), None)

        for mk, b, yes in buckets:
            token = None
            try:
                token = json.loads(mk["clobTokenIds"])[0]
            except (KeyError, ValueError, json.JSONDecodeError):
                pass
            mid = None
            if token and token in clob:
                try:
                    mid = float(clob[token]["midpoint"]["mid"])
                except (KeyError, ValueError, TypeError):
                    pass
            low, high = b["low"], b["high"]
            mid_native = low if high is None else high if low is None else (low + high) / 2
            rows.append({
                # keys
                "city": city, "target_date": td, "bucket_label": mk["groupItemTitle"],
                # bucket geometry
                "bucket_kind": b["bucket_kind"], "bucket_unit": b["bucket_unit"],
                "bucket_low_native": low, "bucket_high_native": high,
                "bucket_mid_c": to_c(float(mid_native), unit),
                # market features (as-of)
                "yes_price_raw": yes, "yes_price_norm": yes / osum, "overround_sum": osum,
                "clob_mid": mid,
                "bucket_volume": mk.get("volumeNum"), "bucket_liquidity": mk.get("liquidityNum"),
                "event_volume": ev.get("volume"), "event_liquidity": ev.get("liquidity"),
                "n_snapshots_pre_asof": n_pre[(city, td)],
                "hours_to_event_end": round((end_ts - asof_ts).total_seconds() / 3600, 2),
                # weather features (as-of)
                "forecast_max_native": fc[1] if fc else None,
                "forecast_min_native": fc[2] if fc else None,
                "forecast_max_c": to_c(fc[1], unit) if fc else None,
                "forecast_min_c": to_c(fc[2], unit) if fc else None,
                # label
                "observed_max_native": ob[1] if ob else None,
                "observed_max_c": to_c(ob[1], unit) if ob else None,
                "observed_max_int_native": obs_int,
                # D3-Revision (freigegeben 2026-07-11): PRIMARY label = official market
                # resolution (Wunderground outcome via resolutions_*.ndjson). The
                # Open-Meteo label stays as documented secondary (label_in_bucket).
                "label_is_winner_official": (mk["groupItemTitle"] == winner) if winner else None,
                "label_in_bucket": in_bucket(obs_int, b) if obs_int is not None else None,
                "label_source": "market_resolution_official; aux=open_meteo_archive_latest",
                "observed_lag_days": ob[2] if ob else None,
                "market_resolved_bucket": winner,
                "labels_agree": (winner == om_label) if winner and om_label else None,
                # metadata / lineage / QS
                "source": "live",
                "asof_policy": ASOF_POLICY,
                "market_asof_ts": asof_ts.replace(tzinfo=None),
                "forecast_asof_ts": fc[0].replace(tzinfo=None) if fc else None,
                "event_id": ev.get("id"), "event_slug": ev.get("slug"), "market_id": mk.get("id"),
                "clob_token_yes": token,
                "station": c.station, "resolution_source_url": ev.get("resolutionSource"),
                "temperature_unit": unit,
                "flag_overround_outlier": abs(osum - 1) > OVERROUND_OUTLIER_THRESHOLD,
                "flag_partial_day": asof_ts.strftime("%Y-%m-%d") in partial_days,
                "transform_version": version,
                "created_at": created.replace(tzinfo=None),
            })

    # AP 1.3: extend with historical rows (live wins on overlapping days)
    live_keys = set(best.keys())
    rows.extend(load_backfill_rows(live_keys, version, created))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- write + verify
def main() -> None:
    df = build_rows()
    logger.info("assembled %d silver rows", len(df))

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.register("df", df)
    con.execute("CREATE OR REPLACE TABLE market_bucket_daily AS SELECT * FROM df")

    # primary-key uniqueness (grain check)
    dupes = con.execute("""
        SELECT COUNT(*) FROM (SELECT city, target_date, bucket_label
                              FROM market_bucket_daily
                              GROUP BY 1,2,3 HAVING COUNT(*) > 1)""").fetchone()[0]
    # Open-Meteo label: at most one winning bucket per day; zero is only legal for
    # backfill days whose Open-Meteo-winning bucket was never traded pre-cut (U4).
    bad_label = con.execute("""
        SELECT COUNT(*) FROM (SELECT city, target_date
                              FROM market_bucket_daily
                              WHERE observed_max_int_native IS NOT NULL
                              GROUP BY 1,2
                              HAVING SUM(CASE WHEN label_in_bucket THEN 1 ELSE 0 END) > 1
                                  OR (SUM(CASE WHEN label_in_bucket THEN 1 ELSE 0 END) = 0
                                      AND ANY_VALUE(source) = 'live'))""").fetchone()[0]
    bad_official = con.execute("""
        SELECT COUNT(*) FROM (SELECT city, target_date
                              FROM market_bucket_daily
                              WHERE market_resolved_bucket IS NOT NULL
                              GROUP BY 1,2
                              HAVING SUM(CASE WHEN label_is_winner_official THEN 1 ELSE 0 END) <> 1)""").fetchone()[0]
    # leakage audit: as-of must be well before event end (>= ~12h)
    min_lead = con.execute("SELECT MIN(hours_to_event_end) FROM market_bucket_daily").fetchone()[0]
    # normalized probabilities sum to 1 per event
    norm_err = con.execute("""
        SELECT MAX(ABS(s - 1)) FROM (SELECT SUM(yes_price_norm) s FROM market_bucket_daily
                                     GROUP BY city, target_date)""").fetchone()[0]

    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY market_bucket_daily TO '{PARQUET_DIR}'
        (FORMAT PARQUET, PARTITION_BY (city), OVERWRITE_OR_IGNORE)""")
    con.close()

    logger.info("QS: pk_duplicates=%d | bad_label_days=%d | bad_official_days=%d | "
                "min_hours_to_end=%.1f | max_norm_error=%.2e",
                dupes, bad_label, bad_official, min_lead, norm_err)
    if dupes or bad_label or bad_official:
        raise SystemExit("QS check failed - see log")
    logger.info("wrote %s (table market_bucket_daily) + parquet under %s", DB_PATH, PARQUET_DIR)


if __name__ == "__main__":
    main()
