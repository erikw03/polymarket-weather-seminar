"""AP1.1 Phase A — Inspektionsskript 1: Ablage & Umfang (READ-ONLY).

Zählt Dateien/Zeilen je Quelle, ermittelt Zeitspanne, Städte, `kind`s,
Abrufe pro Stadt/Tag sowie den Backfill-Bestand. Nur Standardbibliothek,
deterministisch (sortierte Dateilisten), verändert nichts.

Aufruf:  python scripts/inspect/01_corpus_overview.py
"""
from __future__ import annotations

import glob
import json
import os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
W_DIR = os.path.join(ROOT, "data", "raw", "weather")
P_DIR = os.path.join(ROOT, "data", "raw", "polymarket")
B_DIR = os.path.join(ROOT, "data", "backfill")


def scan_ndjson(pattern: str):
    files = sorted(glob.glob(pattern))
    total_lines = 0
    bad_lines = 0
    per_file = []
    for f in files:
        n = 0
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                n += 1
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    bad_lines += 1
        per_file.append((os.path.basename(f), n, os.path.getsize(f)))
        total_lines += n
    return files, per_file, total_lines, bad_lines


def main() -> None:
    print("=" * 72)
    print("QUELLE 1: WETTER  (data/raw/weather/weather_*.ndjson)")
    files, per_file, total, bad = scan_ndjson(os.path.join(W_DIR, "weather_*.ndjson"))
    dates = [pf[0].split("_")[1].removesuffix(".ndjson") for pf in per_file]
    print(f"Dateien: {len(files)} | Zeitspanne: {min(dates)} .. {max(dates)} | Zeilen gesamt: {total} | kaputte Zeilen: {bad}")
    print(f"{'Datei':34}{'Zeilen':>8}{'Bytes':>10}")
    for name, n, sz in per_file:
        print(f"{name:34}{n:>8}{sz:>10}")

    # Kalenderlücken
    import datetime as dt
    ds = sorted(dt.date.fromisoformat(d) for d in dates)
    gaps = [str(ds[i - 1] + dt.timedelta(days=1)) + ".." + str(ds[i] - dt.timedelta(days=1))
            for i in range(1, len(ds)) if (ds[i] - ds[i - 1]).days > 1]
    print("Kalenderlücken (Dateiebene):", gaps or "keine")

    # kinds / Städte / Abrufe je Stadt/Tag
    kinds = Counter()
    cities = Counter()
    fetches = defaultdict(set)  # (date, city) -> set of fetched_at (nur forecast als Proxy je Lauf)
    meta_key_variants = Counter()
    for f in files:
        day = os.path.basename(f).split("_")[1].removesuffix(".ndjson")
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                m = rec["_meta"]
                kinds[m.get("kind")] += 1
                cities[m.get("city")] += 1
                meta_key_variants[tuple(sorted(m.keys()))] += 1
                if m.get("kind") == "weather-forecast":
                    fetches[(day, m.get("city"))].add(m.get("fetched_at_utc"))
    print("kinds:", dict(kinds))
    print("Städte:", dict(cities))
    print("_meta-Schlüsselvarianten (Anzahl Records je Variante):")
    for keys, n in meta_key_variants.items():
        print(f"  n={n}: {list(keys)}")
    per_day_counts = Counter(len(v) for v in fetches.values())
    print("Forecast-Abrufe je Stadt/Tag (Verteilung {Abrufe: wie oft}):",
          dict(sorted(per_day_counts.items())))

    print()
    print("=" * 72)
    print("QUELLE 2: POLYMARKET  (data/raw/polymarket/polymarket_*.ndjson)")
    files, per_file, total, bad = scan_ndjson(os.path.join(P_DIR, "polymarket_*.ndjson"))
    dates = [pf[0].split("_")[1].removesuffix(".ndjson") for pf in per_file]
    print(f"Dateien: {len(files)} | Zeitspanne: {min(dates)} .. {max(dates)} | Zeilen gesamt: {total} | kaputte Zeilen: {bad}")
    for name, n, sz in per_file:
        print(f"{name:34}{n:>8}{sz:>10}")

    cities = Counter()
    ev_counts = Counter()
    top_keys = Counter()
    fetches_p = defaultdict(set)
    for f in files:
        day = os.path.basename(f).split("_")[1].removesuffix(".ndjson")
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                top_keys[tuple(sorted(rec.keys()))] += 1
                m = rec["_meta"]
                cities[m.get("city")] += 1
                ev_counts[len(rec.get("gamma_events", []))] += 1
                fetches_p[(day, m.get("city"))].add(m.get("fetched_at_utc"))
    print("Städte:", dict(cities))
    print("Top-Level-Schlüsselvarianten:", {str(list(k)): n for k, n in top_keys.items()})
    print("Events je Abruf (Verteilung {events: wie oft}):", dict(sorted(ev_counts.items())))
    per_day_counts = Counter(len(v) for v in fetches_p.values())
    print("Abrufe je Stadt/Tag (Verteilung):", dict(sorted(per_day_counts.items())))

    print()
    print("=" * 72)
    print("ZUSATZBESTAND: BACKFILL  (data/backfill/*.json, konsolidiert, 21.06.)")
    for f in sorted(glob.glob(os.path.join(B_DIR, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        if "markets" in d:
            dates = [m["date"] for m in d["markets"]]
            n_res = sum(1 for m in d["markets"] if m.get("resolved_bucket"))
            print(f"{os.path.basename(f):44} markets={len(d['markets']):>4} resolved={n_res:>4} "
                  f"span={min(dates)}..{max(dates)}")
        else:
            hf = d.get("historical_forecast", {}).get("daily", {}).get("time", [])
            aa = d.get("archive_actuals", {}).get("daily", {}).get("time", [])
            print(f"{os.path.basename(f):44} forecast_days={len(hf):>4} archive_days={len(aa):>4}")


if __name__ == "__main__":
    main()
