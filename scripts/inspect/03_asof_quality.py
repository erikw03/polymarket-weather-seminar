"""AP1.1 Phase A — Inspektionsskript 3: As-of, Ground Truth, Roll-off, Qualität (READ-ONLY).

Beantwortet die Phase-A-Fragen 3–8:
  (3) Duplikate/Stabilität: sind Archive-Werte je Tag stabil, Forecast/Preise variabel?
  (4) As-of-Variabilität: Spannweite Forecast-Max & Bucket-Yes-Preis je Zieltag
  (5) Ground-Truth-Verfügbarkeit über den datei-übergreifenden Archive-Join
  (6) Roll-off & Resolution: closed/umaResolutionStatus/closedTime im Korpus? Letzte Sichtung je Event
  (7) Einheiten & Stationen je Stadt (Markt vs. Wetter), Koordinaten-Varianten
  (8) Anomalien: leere gamma_events, outcomePrices-Parsing, Nulls, Preissummen (Overround), UTC-Effekte

Nur Standardbibliothek, deterministisch, verändert nichts.
Aufruf:  python scripts/inspect/03_asof_quality.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import statistics as st
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
W_FILES = sorted(glob.glob(os.path.join(ROOT, "data/raw/weather/weather_*.ndjson")))
P_FILES = sorted(glob.glob(os.path.join(ROOT, "data/raw/polymarket/polymarket_*.ndjson")))


def main() -> None:
    # ---------------------------------------------------------------- Wetter
    # (3)+(5): Archive-Stabilität und Ground-Truth-Verfügbarkeit
    archive_vals = defaultdict(set)        # (city, target_date) -> {max-Werte}
    archive_first_seen = {}                # (city, target_date) -> frühester Dateitag mit Wert
    forecast_series = defaultdict(list)    # (city, target_date) -> [(fetched_at, max)]
    units = defaultdict(Counter)
    coords = defaultdict(Counter)
    null_maxima = 0
    for f in W_FILES:
        fday = os.path.basename(f).split("_")[1].removesuffix(".ndjson")
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                m, d = rec["_meta"], rec["response"]["daily"]
                city = m["city"]
                units[city][m.get("temperature_unit", "?")] += 1
                coords[city][(m["latitude"], m["longitude"])] += 1
                for i, t in enumerate(d["time"]):
                    v = d["temperature_2m_max"][i]
                    if m["kind"] == "weather-archive":
                        if v is None:
                            null_maxima += 1
                            continue
                        archive_vals[(city, t)].add(v)
                        archive_first_seen.setdefault((city, t), fday)
                    elif m["kind"] == "weather-forecast":
                        forecast_series[(city, t)].append((m["fetched_at_utc"], v))

    print("=" * 72)
    print("(3) ARCHIVE-STABILITAET (Dedup-Hypothese)")
    unstable = {k: sorted(v) for k, v in archive_vals.items() if len(v) > 1}
    print(f"(city,target_date)-Paare mit Archive-Wert: {len(archive_vals)}")
    print(f"davon mit >1 unterschiedlichen Max-Werten über alle Abrufe: {len(unstable)}")
    for k, v in list(sorted(unstable.items()))[:8]:
        print(f"  {k}: {v}")
    print(f"Archive-Zellen mit null: {null_maxima}")

    print()
    print("(4a) AS-OF-VARIABILITAET FORECAST (je city×target_date über alle Snapshots)")
    spreads = []
    for (city, t), pts in forecast_series.items():
        vals = [v for _, v in pts if v is not None]
        if len(vals) >= 2:
            spreads.append((max(vals) - min(vals), city, t, len(vals)))
    spreads.sort(reverse=True)
    sp = [s[0] for s in spreads]
    print(f"Zieltage mit >=2 Forecast-Snapshots: {len(sp)}")
    print(f"Spannweite Forecast-Max  mean={st.mean(sp):.2f}  median={st.median(sp):.2f}  "
          f"p90={sorted(sp)[int(0.9 * len(sp))]:.2f}  max={max(sp):.2f} (Einheit nativ)")
    print("Top-3-Beispiele (Spannweite, Stadt, Zieltag, #Snapshots):")
    for s in spreads[:3]:
        print(f"  {s[0]:.1f}  {s[1]}  {s[2]}  n={s[3]}")
    # Beispiel-Zeitreihe für den Report
    ex_key = spreads[0][1], spreads[0][2]
    pts = sorted(forecast_series[ex_key])
    print(f"Beispiel-Zeitreihe {ex_key}: erste/letzte 3 Snapshots:")
    for p in pts[:3] + pts[-3:]:
        print(f"    {p[0][:16]}  max={p[1]}")

    print()
    print("(5) GROUND-TRUTH-VERFUEGBARKEIT (datei-übergreifender Archive-Join)")
    # Lag: erster Dateitag mit beobachtetem Wert minus Zieltag
    import datetime as dt
    lags = Counter()
    for (city, t), fday in archive_first_seen.items():
        try:
            lag = (dt.date.fromisoformat(fday) - dt.date.fromisoformat(t)).days
            lags[lag] += 1
        except ValueError:
            pass
    print("Verteilung 'Lag erster Ist-Wert nach Zieltag' (Tage: Anzahl):",
          dict(sorted(lags.items())))

    # ---------------------------------------------------------------- Markt
    price_series = defaultdict(list)   # (city, eventDate, bucket) -> [(fetched_at, yes)]
    event_last_seen = {}               # (city, eventDate) -> letzter fetched_at
    event_first_seen = {}
    closed_events = Counter()
    closed_markets = Counter()
    uma_status = Counter()
    closed_time_examples = []
    parse_errors = 0
    empty_events = 0
    sum_yes = []                       # Overround: Summe der Yes-Preise je Event-Snapshot
    market_units = defaultdict(Counter)
    stations = defaultdict(set)
    ev_city_mismatch = 0

    for f in P_FILES:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                meta = rec["_meta"]
                city = meta["city"]
                ts = meta["fetched_at_utc"]
                evs = rec.get("gamma_events", [])
                if not evs:
                    empty_events += 1
                for ev in evs:
                    ed = ev.get("eventDate") or (ev.get("endDate", "")[:10])
                    if city.lower() not in ev.get("title", "").lower():
                        ev_city_mismatch += 1
                    key = (city, ed)
                    event_first_seen.setdefault(key, ts)
                    event_last_seen[key] = max(event_last_seen.get(key, ""), ts)
                    if ev.get("closed"):
                        closed_events[key] += 1
                    stations[city].add(ev.get("resolutionSource", ""))
                    s = 0.0
                    for mk in ev.get("markets", []):
                        label = mk.get("groupItemTitle", "")
                        u = "°F" if "°F" in label else ("°C" if "°C" in label else "?")
                        market_units[city][u] += 1
                        if mk.get("closed"):
                            closed_markets[key] += 1
                        st_raw = mk.get("umaResolutionStatus")
                        if st_raw:
                            uma_status[st_raw] += 1
                        if mk.get("closedTime") and len(closed_time_examples) < 5:
                            closed_time_examples.append(
                                (city, ed, label, mk.get("closedTime"), "closed=" + str(mk.get("closed"))))
                        try:
                            yes = float(json.loads(mk["outcomePrices"])[0])
                        except (KeyError, ValueError, IndexError, json.JSONDecodeError):
                            parse_errors += 1
                            continue
                        s += yes
                        price_series[(city, ed, label)].append((ts, yes))
                    if s:
                        sum_yes.append(s)

    print()
    print("(4b) AS-OF-VARIABILITAET BUCKET-YES-PREIS")
    pspreads = []
    for (city, ed, label), pts in price_series.items():
        vals = [v for _, v in pts]
        if len(vals) >= 2:
            pspreads.append((max(vals) - min(vals), city, ed, label, len(vals)))
    ps = sorted(p[0] for p in pspreads)
    print(f"Bucket-Zeitreihen mit >=2 Snapshots: {len(ps)}")
    print(f"Spannweite Yes-Preis  mean={st.mean(ps):.3f}  median={st.median(ps):.3f}  "
          f"p90={ps[int(0.9 * len(ps))]:.3f}  max={max(ps):.3f}")
    pspreads.sort(reverse=True)
    print("Top-3-Beispiele:", [(round(p[0], 3), p[1], p[2], p[3], f"n={p[4]}") for p in pspreads[:3]])

    print()
    print("(6) ROLL-OFF & RESOLUTION")
    print(f"Event-Snapshots mit closed=true: {sum(closed_events.values())} "
          f"(Events betroffen: {len(closed_events)})")
    print(f"Bucket-Snapshots mit closed=true: {sum(closed_markets.values())} "
          f"(Events betroffen: {len(closed_markets)})")
    print("umaResolutionStatus-Werte (Bucket-Ebene):", dict(uma_status))
    print("closedTime-Beispiele:", closed_time_examples)
    # letzte Sichtung relativ zur 12:00Z-Auflösung
    last_seen_hour = Counter()
    for (city, ed), ts in event_last_seen.items():
        try:
            t = dt.datetime.fromisoformat(ts)
            target = dt.date.fromisoformat(ed)
            if t.date() == target:
                last_seen_hour[t.hour] += 1
            elif t.date() > target:
                last_seen_hour[f"D+{(t.date()-target).days}"] += 1
        except ValueError:
            pass
    print("Letzte Sichtung eines Events (UTC-Stunde am Zieltag bzw. D+n):",
          dict(sorted(last_seen_hour.items(), key=str)))

    print()
    print("(7) EINHEITEN & STATIONEN")
    for city in sorted(units):
        print(f"  {city}: Wetter-Einheit={dict(units[city])} | Markt-Bucket-Einheit={dict(market_units[city])}")
        print(f"          Koordinaten-Varianten={dict(coords[city])}")
        print(f"          resolutionSource={sorted(stations[city])}")

    print()
    print("(8) ANOMALIEN")
    print(f"leere gamma_events-Abrufe: {empty_events}")
    print(f"outcomePrices-Parse-Fehler: {parse_errors}")
    print(f"Event-Titel passt nicht zur _meta.city: {ev_city_mismatch}")
    print(f"Summe Yes-Preise je Event-Snapshot (Overround): mean={st.mean(sum_yes):.4f} "
          f"median={st.median(sum_yes):.4f} min={min(sum_yes):.4f} max={max(sum_yes):.4f} (n={len(sum_yes)})")


if __name__ == "__main__":
    main()
