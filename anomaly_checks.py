"""
AP 2.2 — Anomalie-Erkennung auf dem Silver-Korpus (Inhalts-Ebene).

Abgrenzung: `quality_checks.py` (AP 2.1) prueft, ob die PIPELINE gesund ist;
dieses Modul prueft, ob die WERTE plausibel sind. Findings sind Beobachtungen
(z. T. echtes Extremwetter / echte Marktbewegung), KEINE Pipeline-Fehler ->
Exit-Code 0 (mit --strict: 1 bei >=1 WARN, fuer ein spaeteres CI-Gate).

Methode (DECISIONS_AP2.2 U1): Schwellen werden je Stadt SELBSTKALIBRIEREND aus
robusten Quantilen des Korpus berechnet (INFO > p95-Fence, WARN > 1.25*p99),
weil sich die Staedte stark unterscheiden (NYC-Tagessprung p95 = 19.6 F vs.
Tokio 5.1 C). Absolute Sanity-Grenzen fangen echte Korruption unabhaengig davon.
Ehrliche Grenze: ~125 Tage je Stadt machen p99 grob; Quantile werden mit jedem
Sammeltag stabiler.

Checks:
  A1 Forecast-Miss        |forecast_max_c - observed_max_c| > Fence(Stadt)
  A2 Ist-Sprung           |obs(D) - obs(D-1)| in C > Fence(Stadt)
  A3 Ueberraschungssieger as-of-Prob des spaeteren Gewinners < 5% INFO / < 2% WARN
  A4 Degenerierte Vert.   max(yes_price_norm) > 0.95 bei Lead > 20h
  A5 Bucket-Anzahl        < 9 INFO / < 7 WARN
  A6 Duenner Markt        event_volume < 20% des Stadt-Medians (nur live)
  A7 Sanity-Grenzen       Temperatur ausserhalb [-25, 50] C oder Preis nicht in [0,1]
  A8 Overround-Tage       flag_overround_outlier des as-of-Snapshots (aus Silver)

Aufruf:  python anomaly_checks.py [--json PFAD] [--strict]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

import duckdb

import config

DB = config.PROJECT_ROOT / "data" / "processed" / "silver.duckdb"

SURPRISE_INFO, SURPRISE_WARN = 0.05, 0.02       # Kalibrierung: p05 der Gewinner-Prob = 0.066
DEGENERATE_P, DEGENERATE_LEAD_H = 0.95, 20.0
BUCKETS_INFO, BUCKETS_WARN = 9, 7               # Kalibrierung: min=7, p05=9
THIN_MARKET_FRACTION = 0.20
SANITY_TEMP_C = (-25.0, 50.0)

FINDINGS: list[dict] = []


def finding(sev: str, check: str, city: str, date, wert: str, fence: str, hinweis: str = "") -> None:
    FINDINGS.append(dict(severity=sev, check=check, city=city, target_date=str(date),
                         wert=wert, fence=fence, hinweis=hinweis))


def fences(con, sql_value_per_day: str) -> dict[str, tuple[float, float]]:
    """Robuste (INFO, WARN)-Fences je Stadt: (p95, 1.25*p99) der Tageswerte."""
    rows = con.execute(f"""
        SELECT city, QUANTILE_CONT(v, 0.95), QUANTILE_CONT(v, 0.99)
        FROM ({sql_value_per_day}) GROUP BY city""").fetchall()
    return {c: (p95, 1.25 * p99) for c, p95, p99 in rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", metavar="PFAD")
    ap.add_argument("--strict", action="store_true", help="Exit 1 bei >=1 WARN")
    args = ap.parse_args()
    con = duckdb.connect(str(DB), read_only=True)

    # ---- A1 Forecast-Miss (in C, cross-city vergleichbar; Fences je Stadt) ----
    day_miss = """SELECT DISTINCT city, target_date,
                         ABS(forecast_max_c - observed_max_c) v
                  FROM market_bucket_daily
                  WHERE forecast_max_c IS NOT NULL AND observed_max_c IS NOT NULL"""
    f = fences(con, day_miss)
    for city, date, v in con.execute(f"SELECT * FROM ({day_miss}) ORDER BY city, target_date").fetchall():
        if v is None:
            continue
        info_f, warn_f = f[city]
        if v > warn_f:
            finding("WARN", "A1 Forecast-Miss", city, date, f"{v:.1f}C", f">{warn_f:.1f}C")
        elif v > info_f:
            finding("INFO", "A1 Forecast-Miss", city, date, f"{v:.1f}C", f">{info_f:.1f}C")

    # ---- A2 Tag-zu-Tag-Sprung im Ist (C) ----
    day_jump = """WITH o AS (SELECT DISTINCT city, target_date, observed_max_c v
                             FROM market_bucket_daily WHERE observed_max_c IS NOT NULL)
                  SELECT city, target_date,
                         ABS(v - LAG(v) OVER (PARTITION BY city ORDER BY target_date)) v
                  FROM o QUALIFY v IS NOT NULL"""
    f = fences(con, day_jump)
    for city, date, v in con.execute(f"SELECT * FROM ({day_jump}) ORDER BY 1,2").fetchall():
        if v is None:
            continue
        info_f, warn_f = f[city]
        if v > warn_f:
            finding("WARN", "A2 Ist-Sprung", city, date, f"{v:.1f}C", f">{warn_f:.1f}C",
                    "Datenfehler ODER echter Wetterumschwung - manuell pruefen")
        elif v > info_f:
            finding("INFO", "A2 Ist-Sprung", city, date, f"{v:.1f}C", f">{info_f:.1f}C")

    # ---- A3 Ueberraschungssieger ----
    for city, date, p in con.execute(f"""
            SELECT city, target_date, yes_price_norm FROM market_bucket_daily
            WHERE label_is_winner_official AND yes_price_norm < {SURPRISE_INFO}
            ORDER BY yes_price_norm""").fetchall():
        sev = "WARN" if p < SURPRISE_WARN else "INFO"
        finding(sev, "A3 Ueberraschungssieger", city, date, f"p={p:.3f}",
                f"<{SURPRISE_WARN if sev == 'WARN' else SURPRISE_INFO}",
                "Markt lag weit daneben (oder Label pruefen)")

    # ---- A4 Degenerierte Verteilung frueh vor Schluss ----
    # U6: NUR innere Buckets (exact/range) flaggen. Offene Randbuckets ("11C or
    # higher") sind bei Wetter weit im Bucket-Inneren zu Recht ~1.0 (verifizierter
    # False-Positive Muenchen 2026-04-13: Forecast 18C, Top-Bucket ">=11C", p=0.991).
    for city, date, lbl, p, lead in con.execute(f"""
            WITH mx AS (SELECT city, target_date, bucket_label, bucket_kind,
                               yes_price_norm p, hours_to_event_end h,
                               ROW_NUMBER() OVER (PARTITION BY city, target_date
                                                  ORDER BY yes_price_norm DESC) rn
                        FROM market_bucket_daily)
            SELECT city, target_date, bucket_label, p, h FROM mx
            WHERE rn = 1 AND p > {DEGENERATE_P} AND h > {DEGENERATE_LEAD_H}
              AND bucket_kind IN ('exact', 'range')""").fetchall():
        finding("WARN", "A4 Degenerierte Verteilung", city, date,
                f"{lbl}: p={p:.3f} bei {lead:.0f}h Lead", f">{DEGENERATE_P} & >{DEGENERATE_LEAD_H}h",
                "inneres Bucket 'sicher' lange vor Aufloesung - Platzhalter/stale?")

    # ---- A5 Bucket-Anzahl ----
    for city, date, nb in con.execute(f"""
            SELECT city, target_date, COUNT(*) FROM market_bucket_daily
            GROUP BY 1,2 HAVING COUNT(*) < {BUCKETS_INFO}""").fetchall():
        finding("WARN" if nb < BUCKETS_WARN else "INFO", "A5 Bucket-Anzahl",
                city, date, str(nb), f"<{BUCKETS_WARN if nb < BUCKETS_WARN else BUCKETS_INFO}",
                "duenn gehandelter Tag (U3-Ausschluesse moeglich)")

    # ---- A6 Duenner Markt (nur live, Volumen vorhanden) ----
    for city, date, v, med in con.execute(f"""
            WITH ev AS (SELECT DISTINCT city, target_date, event_volume v
                        FROM market_bucket_daily WHERE source='live' AND event_volume IS NOT NULL),
                 m AS (SELECT city, MEDIAN(v) med FROM ev GROUP BY 1)
            SELECT ev.city, ev.target_date, ev.v, m.med FROM ev JOIN m USING (city)
            WHERE ev.v < {THIN_MARKET_FRACTION} * m.med""").fetchall():
        finding("INFO", "A6 Duenner Markt", city, date,
                f"vol={v:,.0f}", f"<{THIN_MARKET_FRACTION:.0%} von median {med:,.0f}")

    # ---- A7 Sanity-Grenzen (Korruptions-Fang, unabhaengig von Quantilen) ----
    for city, date, col, v in con.execute(f"""
            SELECT city, target_date, 'observed_max_c', observed_max_c FROM market_bucket_daily
            WHERE observed_max_c IS NOT NULL AND (observed_max_c < {SANITY_TEMP_C[0]} OR observed_max_c > {SANITY_TEMP_C[1]})
            UNION ALL
            SELECT city, target_date, 'forecast_max_c', forecast_max_c FROM market_bucket_daily
            WHERE forecast_max_c IS NOT NULL AND (forecast_max_c < {SANITY_TEMP_C[0]} OR forecast_max_c > {SANITY_TEMP_C[1]})
            UNION ALL
            SELECT city, target_date, 'yes_price_norm', yes_price_norm FROM market_bucket_daily
            WHERE yes_price_norm < 0 OR yes_price_norm > 1""").fetchall():
        finding("WARN", "A7 Sanity", city, date, f"{col}={v}", "physikalische Grenzen",
                "moegliche Datenkorruption")

    # ---- A8 Overround-Ausreisser-Tage (Flag aus Silver) ----
    for city, date, s in con.execute("""
            SELECT DISTINCT city, target_date, overround_sum FROM market_bucket_daily
            WHERE flag_overround_outlier ORDER BY 1, 2""").fetchall():
        finding("INFO", "A8 Overround-Tag", city, date, f"sum={s:.2f}", "|sum-1|>0.10",
                "as-of fiel auf frisches Listing (Platzhalter-Quotes)")

    con.close()

    # ---- Report ----
    order = {"WARN": 0, "INFO": 1}
    FINDINGS.sort(key=lambda x: (order[x["severity"]], x["check"], x["city"], x["target_date"]))
    now = dt.datetime.now(dt.timezone.utc)
    print(f"\nAnomalie-Report  {now:%Y-%m-%d %H:%M} UTC   (Korpus: Silver)")
    print("=" * 100)
    for x in FINDINGS:
        print(f"[{x['severity']:>4}] {x['check']:<26} {x['city']:<7} {x['target_date']}  "
              f"{x['wert']:<22} (Fence {x['fence']})" + (f"  {x['hinweis']}" if x['hinweis'] else ""))
    n_warn = sum(x["severity"] == "WARN" for x in FINDINGS)
    n_info = len(FINDINGS) - n_warn
    print("-" * 100)
    print(f"Ergebnis: {len(FINDINGS)} Findings | {n_warn} WARN | {n_info} INFO")
    if args.json:
        json.dump({"run_at_utc": now.isoformat(), "findings": FINDINGS},
                  open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"JSON-Report: {args.json}")
    return 1 if (args.strict and n_warn) else 0


if __name__ == "__main__":
    sys.exit(main())
