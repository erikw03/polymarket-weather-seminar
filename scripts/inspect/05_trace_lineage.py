"""AP 2.4 — Lineage-Tracer (READ-ONLY): Silver-Zeile -> exakte Raw-Herkunft.

Nimmt (Stadt, Zieltag, Bucket) und druckt die komplette Herkunftskette:
  1. die Silver-Zeile (Werte + as-of-Timestamps + transform_version)
  2. die Raw-Zeile des Markt-Snapshots  (Datei + Zeilennr., via market_asof_ts)
  3. die Raw-Zeile des Forecast-Snapshots (via forecast_asof_ts)
  4. die Raw-Zeile des Labels (Archiv, juengster Abruf)
  5. die Resolutions-Zeile (offizielles Ergebnis)

Demonstriert, dass jede Zahl im Silver bis zur API-Antwort rueckverfolgbar ist.

Aufruf:  python scripts/inspect/05_trace_lineage.py Munich 2026-07-05 "24°C"
"""
from __future__ import annotations

import glob
import json
import os
import sys

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_line(pattern: str, match) -> tuple[str, int, dict] | None:
    """Erste NDJSON-Zeile (Datei, Zeilennr., Record), auf die `match` zutrifft."""
    for f in sorted(glob.glob(pattern)):
        with open(f, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if match(rec):
                    return os.path.relpath(f, ROOT), i, rec
    return None


def show(title: str, hit, extract) -> None:
    print(f"\n--- {title} ---")
    if not hit:
        print("  (nicht gefunden)")
        return
    path, ln, rec = hit
    print(f"  Datei : {path}  (Zeile {ln})")
    for k, v in extract(rec).items():
        print(f"  {k:14}: {v}")


def main(city: str, date: str, bucket: str) -> None:
    con = duckdb.connect(os.path.join(ROOT, "data/processed/silver.duckdb"), read_only=True)
    row = con.execute("""
        SELECT * FROM market_bucket_daily
        WHERE city=? AND target_date=? AND bucket_label=?""", [city, date, bucket]).df()
    con.close()
    if row.empty:
        print(f"Keine Silver-Zeile fuer ({city}, {date}, {bucket})")
        return
    r = row.iloc[0]
    print(f"SILVER-ZEILE  {city} | {date} | {bucket}   (source={r['source']}, "
          f"transform={r['transform_version']}, erstellt {r['created_at']})")
    print(f"  yes_price_raw={r['yes_price_raw']}  yes_price_norm={round(r['yes_price_norm'],4)}  "
          f"clob_mid={r['clob_mid']}")
    print(f"  forecast_max={r['forecast_max_native']}  observed_max={r['observed_max_native']}  "
          f"label_official={r['label_is_winner_official']}  winner={r['market_resolved_bucket']}")

    m_ts = str(r["market_asof_ts"]).replace(" ", "T")[:19]
    f_ts = str(r["forecast_asof_ts"]).replace(" ", "T")[:19] if r["forecast_asof_ts"] is not None else None

    show(f"1) MARKT-SNAPSHOT (as-of {m_ts}Z)",
         find_line(os.path.join(ROOT, "data/raw/polymarket/polymarket_*.ndjson"),
                   lambda rec: rec.get("_meta", {}).get("city") == city
                   and rec["_meta"]["fetched_at_utc"][:19] == m_ts),
         lambda rec: {
             "fetched_at": rec["_meta"]["fetched_at_utc"],
             "event": next((e["slug"] for e in rec["gamma_events"]
                            if (e.get("eventDate") or e.get("endDate", "")[:10]) == date), "?"),
             "outcomePrices": next((mk["outcomePrices"] for e in rec["gamma_events"]
                                    if (e.get("eventDate") or "") == date
                                    for mk in e["markets"] if mk["groupItemTitle"] == bucket), "?"),
         })

    if f_ts:
        show(f"2) FORECAST-SNAPSHOT (as-of {f_ts}Z)",
             find_line(os.path.join(ROOT, "data/raw/weather/weather_*.ndjson"),
                       lambda rec: rec["_meta"].get("city") == city
                       and rec["_meta"].get("kind") == "weather-forecast"
                       and rec["_meta"]["fetched_at_utc"][:19] == f_ts),
             lambda rec: {
                 "fetched_at": rec["_meta"]["fetched_at_utc"],
                 "daily.time": rec["response"]["daily"]["time"],
                 "temp_max": rec["response"]["daily"]["temperature_2m_max"],
             })
    else:
        print("\n--- 2) FORECAST-SNAPSHOT --- (backfill: previous_day1-Datei, kein Einzel-Snapshot)")

    # Label: juengster Archiv-Abruf, der den Zieltag enthaelt (Suche rueckwaerts)
    hits = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/raw/weather/weather_*.ndjson"))):
        with open(f, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                m = rec.get("_meta", {})
                if (m.get("city") == city and m.get("kind") == "weather-archive"
                        and m.get("station") and date in rec["response"]["daily"]["time"]):
                    hits.append((os.path.relpath(f, ROOT), i, rec))
    if hits:
        path, ln, rec = max(hits, key=lambda h: h[2]["_meta"]["fetched_at_utc"])
        idx = rec["response"]["daily"]["time"].index(date)
        print(f"\n--- 3) LABEL-QUELLE (Archiv, juengster von {len(hits)} Abrufen) ---")
        print(f"  Datei : {path}  (Zeile {ln})")
        print(f"  fetched_at    : {rec['_meta']['fetched_at_utc']}")
        print(f"  temp_max[{date}] = {rec['response']['daily']['temperature_2m_max'][idx]}")

    show("4) OFFIZIELLE RESOLUTION",
         find_line(os.path.join(ROOT, "data/raw/polymarket/resolutions_*.ndjson"),
                   lambda rec: rec.get("_meta", {}).get("city") == city
                   and rec["_meta"].get("target_date") == date),
         lambda rec: {
             "fetched_at": rec["_meta"]["fetched_at_utc"],
             "event.closed": rec["event"]["closed"],
             "winner": next((mk["groupItemTitle"] for mk in rec["event"]["markets"]
                             if json.loads(mk["outcomePrices"])[0] == "1"
                             or float(json.loads(mk["outcomePrices"])[0]) >= 0.99), "?"),
         })


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
