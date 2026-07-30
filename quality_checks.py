"""
AP 2.1 — Datenqualitaets-Modul ueber Raw- und Silver-Zone (5 Saeulen, K8).

Saeulen -> Checks:
  Freshness    F1-F3  Alter des juengsten Snapshots je Quelle (weather/polymarket/resolutions)
  Volume       V1-V2  Zeilenzahl je abgeschlossenem Tag gegen gemessene Erwartungsbaender
  Schema       X1-X2  Pflichtfelder/Parsebarkeit im juengsten Tag; Silver-Spalten == Schema
  Nulls/Vert.  N1-N4  Null-Raten, Label-Abdeckung, Overround-Ausreisser, Leakage-Audit
  Lineage      L1-L2  DuckDB==Parquet, Versionierung, Silver-Staleness

Verhalten:
  - Nur lesend (Raw ist WORM; das Modul beobachtet, es repariert nicht).
  - Severity OK/WARN/FAIL; Exit-Code 1 bei >=1 FAIL (cron-/CI-tauglich).
  - Schwellwerte sind DATENGETRIEBEN hergeleitet (Messung 20.06.-12.07., siehe
    docs/DECISIONS_AP2.1.md U3) und stehen hier als benannte Konstanten.

Aufruf:  python quality_checks.py [--json PFAD]
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sys

import duckdb

import config

# ---------------------------------------------------------------- Schwellwerte (U3)
FRESH_SNAPSHOT_WARN_H, FRESH_SNAPSHOT_FAIL_H = 2.5, 6.0     # Soll-Kadenz 1h + Jitter
FRESH_RESOLUTION_WARN_H, FRESH_RESOLUTION_FAIL_H = 36.0, 72.0  # Soll ~taeglich
VOL_WEATHER_BAND, VOL_WEATHER_FAIL = (180, 400), 96          # gemessen 224-328
VOL_MARKET_BAND, VOL_MARKET_FAIL = (90, 200), 48             # gemessen 112-164
LABEL_COVERAGE_WARN, LABEL_COVERAGE_FAIL = 0.99, 0.95        # Tage <= heute-3; gemessen 1.00
NULL_FORECAST_WARN = 0.02
NULL_CLOB_LIVE_WARN = 0.10
NULL_OBSERVED_WARN = 0.05                                    # Tage <= heute-2
OVERROUND_OUTLIER_RATE_WARN = 0.05                           # gemessen ~0.018
LEAKAGE_MIN_HOURS_FAIL = 7.9                                 # NYC-Konstruktionsminimum = 8.0
# X2 trennt harte (strukturelle) von weichen Verstoessen. Weich = einzelne Maerkte
# ohne outcomePrices/clobTokenIds: bekannter transienter Zustand FRISCH GELISTETER
# Maerkte (Gamma listet ~D+2 vor, Preise folgen binnen ~1h; gemessen 1 von ~1800
# Zeilen in 14 Tagen) - build_silver ueberspringt solche Buckets sauber. Erst wenn
# es viele sind, ist es ein echter API-Ausfall -> dann FAIL. Analog zu
# CORRUPT_MAX_RATE in build_silver.py (AP 2.3/U3).
SOFT_VIOLATION_MAX_RATE = 0.05

# Freigegebene Silver-Spalten (docs/cleaned_schema_AP1.1.md, inkl. D3-Revision)
EXPECTED_SILVER_COLUMNS = {
    "city", "target_date", "bucket_label", "bucket_kind", "bucket_unit",
    "bucket_low_native", "bucket_high_native", "bucket_mid_c",
    "yes_price_raw", "yes_price_norm", "overround_sum", "clob_mid",
    "bucket_volume", "bucket_liquidity", "event_volume", "event_liquidity",
    "n_snapshots_pre_asof", "hours_to_event_end",
    "forecast_max_native", "forecast_min_native", "forecast_max_c", "forecast_min_c",
    "label_is_winner_official", "label_in_bucket", "label_source",
    "observed_max_native", "observed_max_c", "observed_max_int_native",
    "observed_lag_days", "market_resolved_bucket", "labels_agree",
    "source", "asof_policy", "market_asof_ts", "forecast_asof_ts",
    "event_id", "event_slug", "market_id", "clob_token_yes",
    "station", "resolution_source_url", "temperature_unit",
    "flag_overround_outlier", "flag_partial_day", "transform_version", "created_at",
}

RESULTS: list[dict] = []


def report(check: str, saeule: str, status: str, wert, schwelle: str, hinweis: str = "") -> None:
    RESULTS.append(dict(check=check, saeule=saeule, status=status,
                        wert=str(wert), schwelle=schwelle, hinweis=hinweis))


def newest(pattern: str) -> str | None:
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def max_fetched_at(path: str) -> dt.datetime | None:
    """Juengster fetched_at im File (voll geparst; nur fuer die juengste Datei benutzt)."""
    best = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                ts = json.loads(line)["_meta"]["fetched_at_utc"]
            except (json.JSONDecodeError, KeyError):
                continue
            t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            best = t if best is None or t > best else best
    return best


# ---------------------------------------------------------------- Freshness (F)
def check_freshness(now: dt.datetime) -> None:
    for name, pattern, warn_h, fail_h in (
        ("F1 weather-Snapshot", str(config.RAW_WEATHER_DIR / "weather_*.ndjson"),
         FRESH_SNAPSHOT_WARN_H, FRESH_SNAPSHOT_FAIL_H),
        ("F2 polymarket-Snapshot", str(config.RAW_POLYMARKET_DIR / "polymarket_*.ndjson"),
         FRESH_SNAPSHOT_WARN_H, FRESH_SNAPSHOT_FAIL_H),
        ("F3 resolutions", str(config.RAW_POLYMARKET_DIR / "resolutions_*.ndjson"),
         FRESH_RESOLUTION_WARN_H, FRESH_RESOLUTION_FAIL_H),
    ):
        f = newest(pattern)
        if not f:
            report(name, "Freshness", "FAIL", "keine Datei", f"<= {fail_h}h")
            continue
        ts = max_fetched_at(f)
        age_h = (now - ts).total_seconds() / 3600 if ts else float("inf")
        status = "OK" if age_h <= warn_h else ("WARN" if age_h <= fail_h else "FAIL")
        report(name, "Freshness", status, f"{age_h:.1f}h", f"WARN>{warn_h}h FAIL>{fail_h}h",
               os.path.basename(f))


# ---------------------------------------------------------------- Volume (V)
def check_volume(now: dt.datetime) -> None:
    """Zeilenzahl je ABGESCHLOSSENEM Tag (U5) gegen gemessene Baender (U3/U4)."""
    today = now.date().isoformat()
    for name, pattern, band, fail_min in (
        ("V1 weather Zeilen/Tag", str(config.RAW_WEATHER_DIR / "weather_*.ndjson"),
         VOL_WEATHER_BAND, VOL_WEATHER_FAIL),
        ("V2 polymarket Zeilen/Tag", str(config.RAW_POLYMARKET_DIR / "polymarket_*.ndjson"),
         VOL_MARKET_BAND, VOL_MARKET_FAIL),
    ):
        bad, checked = [], 0
        for f in sorted(glob.glob(pattern)):
            day = os.path.basename(f).rsplit("_", 1)[1].removesuffix(".ndjson")
            # Randtage vor Dauerbetrieb (21.06.) und der heutige Teiltag sind ausgenommen
            if day >= today or day < "2026-06-21":
                continue
            checked += 1
            n = sum(1 for _ in open(f, encoding="utf-8"))
            if n < fail_min:
                bad.append((day, n, "FAIL"))
            elif not band[0] <= n <= band[1]:
                bad.append((day, n, "WARN"))
        if any(b[2] == "FAIL" for b in bad):
            status = "FAIL"
        elif bad:
            status = "WARN"
        else:
            status = "OK"
        report(name, "Volume", status, f"{checked} Tage, {len(bad)} auffaellig",
               f"Band {band}, FAIL<{fail_min}", "; ".join(f"{d}:{n}" for d, n, _ in bad[:4]))


# ---------------------------------------------------------------- Schema (X)
def check_schema_raw() -> None:
    """Pflichtfelder + Parsebarkeit im juengsten Tag je Quelle (U4)."""
    problems = 0
    f = newest(str(config.RAW_WEATHER_DIR / "weather_*.ndjson"))
    n = 0
    if f:
        for line in open(f, encoding="utf-8"):
            n += 1
            try:
                rec = json.loads(line)
                m = rec["_meta"]
                assert {"source", "kind", "city", "fetched_at_utc"} <= set(m)
                d = rec["response"]["daily"]
                assert len(d["time"]) == len(d["temperature_2m_max"]) == len(d["temperature_2m_min"])
                if m["kind"] in ("weather-forecast", "weather-archive"):
                    assert m.get("station") and m.get("temperature_unit")
            except (AssertionError, KeyError, json.JSONDecodeError):
                problems += 1
    report("X1 Raw-Schema weather", "Schema", "OK" if problems == 0 else "FAIL",
           f"{problems}/{n} Verstoesse", "0 erlaubt", os.path.basename(f or ""))

    # X2 trennt nach Schweregrad (Fix 2026-07-30, siehe docs/incident_2026-07-30_gate-fail.md):
    #   hart  = strukturelle Defekte (kaputtes JSON, fehlende Top-Level-Keys, Event ohne
    #           Datum) -> deuten auf Pipeline-/Merge-Probleme, bleiben FAIL
    #   weich = einzelne Maerkte ohne/mit unparsebarem outcomePrices bzw. clobTokenIds
    #           oder leerem groupItemTitle -> bekannter transienter API-Zustand frisch
    #           gelisteter Maerkte, vom Transform sauber uebersprungen -> WARN
    hard, soft = 0, 0
    f = newest(str(config.RAW_POLYMARKET_DIR / "polymarket_*.ndjson"))
    n = 0
    cities = set()
    if f:
        for line in open(f, encoding="utf-8"):
            n += 1
            try:
                rec = json.loads(line)
                assert {"_meta", "gamma_events", "clob_quotes"} <= set(rec)
                cities.add(rec["_meta"]["city"])
            except (AssertionError, KeyError, json.JSONDecodeError):
                hard += 1
                continue
            line_soft = False
            for ev in rec["gamma_events"]:
                if not (ev.get("eventDate") or ev.get("endDate")):
                    hard += 1
                    continue
                for mk in ev.get("markets", []):
                    try:
                        json.loads(mk["outcomePrices"])   # Doppel-Dekodier-Probe
                        json.loads(mk["clobTokenIds"])
                        assert mk.get("groupItemTitle")
                    except (AssertionError, KeyError, json.JSONDecodeError):
                        line_soft = True
            soft += int(line_soft)
    soft_rate = soft / n if n else 0.0
    if hard or soft_rate > SOFT_VIOLATION_MAX_RATE:
        status = "FAIL"           # struktureller Defekt oder systematischer API-Ausfall
    elif soft or cities != {c.name for c in config.CITIES}:
        status = "WARN"
    else:
        status = "OK"
    report("X2 Raw-Schema polymarket", "Schema", status,
           f"{hard} hart / {soft} weich von {n}, Staedte={sorted(cities)}",
           f"0 hart, weich<={SOFT_VIOLATION_MAX_RATE:.0%}, 4 Staedte",
           os.path.basename(f or ""))


# ---------------------------------------------------------------- Silver (N/L)
def check_silver(now: dt.datetime) -> None:
    db = config.PROJECT_ROOT / "data" / "processed" / "silver.duckdb"
    if not db.exists():
        report("N* Silver", "Nulls/Verteilung", "FAIL", "silver.duckdb fehlt",
               "python build_silver.py ausfuehren")
        return
    con = duckdb.connect(str(db), read_only=True)
    q = lambda sql: con.execute(sql).fetchone()[0]

    # X3: Spaltenmenge == freigegebenes Schema
    cols = {r[0] for r in con.execute("DESCRIBE market_bucket_daily").fetchall()}
    diff = cols ^ EXPECTED_SILVER_COLUMNS
    report("X3 Silver-Spalten == Schema", "Schema", "OK" if not diff else "FAIL",
           f"{len(cols)} Spalten", "exakte Menge", f"Diff: {sorted(diff)}" if diff else "")

    # N1: offizielle Label-Abdeckung fuer reife Tage (<= heute-3)
    cov = q(f"""
        SELECT AVG(CASE WHEN market_resolved_bucket IS NOT NULL THEN 1.0 ELSE 0 END)
        FROM (SELECT DISTINCT city, target_date, market_resolved_bucket
              FROM market_bucket_daily
              WHERE target_date <= DATE '{(now.date() - dt.timedelta(days=3)).isoformat()}')""")
    status = "OK" if cov >= LABEL_COVERAGE_WARN else ("WARN" if cov >= LABEL_COVERAGE_FAIL else "FAIL")
    report("N1 offizielle Label-Abdeckung", "Nulls/Verteilung", status, f"{cov:.1%}",
           f"WARN<{LABEL_COVERAGE_WARN:.0%} FAIL<{LABEL_COVERAGE_FAIL:.0%}", "Tage <= heute-3")

    # N2: Null-Raten
    r = q("SELECT AVG(CASE WHEN forecast_max_native IS NULL THEN 1.0 ELSE 0 END) FROM market_bucket_daily")
    report("N2a forecast_max NULL-Rate", "Nulls/Verteilung",
           "OK" if r <= NULL_FORECAST_WARN else "WARN", f"{r:.1%}", f"WARN>{NULL_FORECAST_WARN:.0%}")
    r = q("SELECT AVG(CASE WHEN clob_mid IS NULL THEN 1.0 ELSE 0 END) FROM market_bucket_daily WHERE source='live'")
    report("N2b clob_mid NULL-Rate (live)", "Nulls/Verteilung",
           "OK" if r <= NULL_CLOB_LIVE_WARN else "WARN", f"{r:.1%}", f"WARN>{NULL_CLOB_LIVE_WARN:.0%}")
    r = q(f"""SELECT AVG(CASE WHEN observed_max_native IS NULL THEN 1.0 ELSE 0 END)
              FROM market_bucket_daily
              WHERE target_date <= DATE '{(now.date() - dt.timedelta(days=2)).isoformat()}'""")
    report("N2c observed NULL-Rate (reife Tage)", "Nulls/Verteilung",
           "OK" if r <= NULL_OBSERVED_WARN else "WARN", f"{r:.1%}", f"WARN>{NULL_OBSERVED_WARN:.0%}")

    # N3: Verteilungs-Checks
    r = q("SELECT AVG(flag_overround_outlier::INT) FROM market_bucket_daily")
    report("N3a Overround-Ausreisser-Rate", "Nulls/Verteilung",
           "OK" if r <= OVERROUND_OUTLIER_RATE_WARN else "WARN", f"{r:.1%}",
           f"WARN>{OVERROUND_OUTLIER_RATE_WARN:.0%}")
    r = q("""SELECT MAX(ABS(s-1)) FROM (SELECT SUM(yes_price_norm) s FROM market_bucket_daily
             GROUP BY city, target_date)""")
    report("N3b Normierung sum=1", "Nulls/Verteilung", "OK" if r < 1e-6 else "FAIL",
           f"{r:.1e}", "FAIL>=1e-6")
    dupes = q("""SELECT COUNT(*) FROM (SELECT city, target_date, bucket_label
                 FROM market_bucket_daily GROUP BY 1,2,3 HAVING COUNT(*)>1)""")
    report("N3c PK-Eindeutigkeit", "Nulls/Verteilung", "OK" if dupes == 0 else "FAIL",
           f"{dupes} Duplikate", "0 erlaubt")

    # N4: Leakage-Audit
    r = q("SELECT MIN(hours_to_event_end) FROM market_bucket_daily")
    report("N4 Leakage-Audit min lead", "Nulls/Verteilung",
           "OK" if r >= LEAKAGE_MIN_HOURS_FAIL else "FAIL", f"{r:.1f}h",
           f"FAIL<{LEAKAGE_MIN_HOURS_FAIL}h", "Konstruktionsminimum NYC=8h")

    # L1: DuckDB == Parquet (Lineage/Konsistenz der Storage-Schichten)
    n_db = q("SELECT COUNT(*) FROM market_bucket_daily")
    pq = str(config.PROJECT_ROOT / "data" / "processed" / "silver" / "market_bucket_daily" / "*" / "*.parquet")
    try:
        n_pq = q(f"SELECT COUNT(*) FROM read_parquet('{pq}')")
    except duckdb.Error:
        n_pq = -1
    report("L1 DuckDB == Parquet", "Lineage", "OK" if n_db == n_pq else "FAIL",
           f"{n_db} vs {n_pq}", "gleich")

    # L2: Versionierung + Staleness von Silver gegenueber Raw
    ver = q("SELECT COUNT(DISTINCT transform_version) FROM market_bucket_daily")
    created = q("SELECT MAX(created_at) FROM market_bucket_daily")
    newest_raw_day = os.path.basename(
        newest(str(config.RAW_POLYMARKET_DIR / "polymarket_*.ndjson")) or "").rsplit("_", 1)[-1][:10]
    stale = str(created.date()) < newest_raw_day
    report("L2 Version/Staleness", "Lineage", "WARN" if stale or ver != 1 else "OK",
           f"build={created:%Y-%m-%d %H:%M}, versions={ver}",
           "1 Version; build >= juengster Raw-Tag",
           f"juengster Raw-Tag {newest_raw_day}" + ("; Silver aelter -> build_silver.py" if stale else ""))
    con.close()


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", metavar="PFAD", help="Report zusaetzlich als JSON schreiben")
    args = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    check_freshness(now)
    check_volume(now)
    check_schema_raw()
    check_silver(now)

    w = max(len(r["check"]) for r in RESULTS)
    print(f"\nDatenqualitaets-Report  {now:%Y-%m-%d %H:%M} UTC")
    print("=" * (w + 60))
    for r in RESULTS:
        mark = {"OK": "  OK ", "WARN": " WARN", "FAIL": " FAIL"}[r["status"]]
        print(f"[{mark}] {r['check']:<{w}}  {r['saeule']:<16} {r['wert']:<28} ({r['schwelle']})"
              + (f"  {r['hinweis']}" if r["hinweis"] else ""))
    n_fail = sum(r["status"] == "FAIL" for r in RESULTS)
    n_warn = sum(r["status"] == "WARN" for r in RESULTS)
    print("-" * (w + 60))
    print(f"Ergebnis: {len(RESULTS)} Checks | {n_fail} FAIL | {n_warn} WARN")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"run_at_utc": now.isoformat(), "results": RESULTS,
                       "n_fail": n_fail, "n_warn": n_warn}, fh, ensure_ascii=False, indent=2)
        print(f"JSON-Report: {args.json}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
