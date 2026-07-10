"""AP1.1 Phase A — Inspektionsskript 4: Drill-down Overround-Ausreißer & Post-12Z-Leakage (READ-ONLY).

(a) Findet Event-Snapshots mit extremer Yes-Preissumme (<0.9 oder >1.1) und zeigt Kontext.
(b) Zeigt für ein Beispiel-Event die Preisentwicklung des Gewinner-Buckets über den Zieltag
    (vor/nach 12:00Z endDate), um Leakage-Fenster zu belegen.
(c) Zählt Zieltage je Stadt im Marktkorpus und deren Ground-Truth-Abdeckung (Wetter-Archive).

Nur Standardbibliothek, deterministisch. Aufruf: python scripts/inspect/04_drilldown_leakage_overround.py
"""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P_FILES = sorted(glob.glob(os.path.join(ROOT, "data/raw/polymarket/polymarket_*.ndjson")))
W_FILES = sorted(glob.glob(os.path.join(ROOT, "data/raw/weather/weather_*.ndjson")))


def main() -> None:
    outliers = []
    series = defaultdict(list)   # (city,eventDate) -> [(ts, {label: yes}, event_closed)]
    market_days = defaultdict(set)
    for f in P_FILES:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                city = rec["_meta"]["city"]
                ts = rec["_meta"]["fetched_at_utc"]
                for ev in rec.get("gamma_events", []):
                    ed = ev.get("eventDate") or ev.get("endDate", "")[:10]
                    market_days[city].add(ed)
                    prices = {}
                    for mk in ev.get("markets", []):
                        try:
                            prices[mk["groupItemTitle"]] = float(json.loads(mk["outcomePrices"])[0])
                        except Exception:
                            pass
                    s = sum(prices.values())
                    if s and (s < 0.9 or s > 1.1):
                        outliers.append((round(s, 3), city, ed, ts[:16],
                                         sorted(prices.items(), key=lambda x: -x[1])[:3]))
                    series[(city, ed)].append((ts, prices))

    print("(a) OVERROUND-AUSREISSER  (Summe Yes < 0.9 oder > 1.1):", len(outliers))
    for o in sorted(outliers, reverse=True)[:6]:
        print("  sum=%s %s %s %s top3=%s" % o)
    print("  ... betroffene (Stadt,Zieltag):", sorted({(o[1], o[2]) for o in outliers}))

    print()
    print("(b) POST-12Z-VERHALTEN — Beispiel London 2026-06-22 (endDate=12:00Z)")
    pts = sorted(series[("London", "2026-06-22")])
    # zeige stündlich: Zeit, Top-Bucket und dessen Preis
    for ts, prices in pts[::4]:
        if not prices:
            continue
        top = max(prices.items(), key=lambda x: x[1])
        print(f"  {ts[:16]}  top={top[0]:>15}  yes={top[1]:.3f}  sum={sum(prices.values()):.3f}")

    print()
    print("(c) ZIELTAGE JE STADT IM MARKTKORPUS + GROUND-TRUTH-ABDECKUNG")
    observed = defaultdict(set)
    for f in W_FILES:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                if rec["_meta"]["kind"] != "weather-archive":
                    continue
                d = rec["response"]["daily"]
                for i, t in enumerate(d["time"]):
                    if d["temperature_2m_max"][i] is not None:
                        observed[rec["_meta"]["city"]].add(t)
    import datetime as dt
    today = dt.date(2026, 7, 10)
    for city in sorted(market_days):
        days = market_days[city]
        past = {d for d in days if dt.date.fromisoformat(d) < today}
        cov = past & observed[city]
        print(f"  {city}: Zieltage im Markt={len(days)} (davon vergangen={len(past)}), "
              f"mit Open-Meteo-Ist={len(cov)}, fehlend={sorted(past - cov)}")


if __name__ == "__main__":
    main()
