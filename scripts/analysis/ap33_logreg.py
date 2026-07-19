"""
AP 3.3 — Modell 1 (LogReg) sauber: Auswahl, Koeffizienten, Kalibrierung, Sensitivitaet.

Wiederverwendet das Framework aus AP 3.2 (Folds, Tages-Metriken, Baselines).
Erzeugt alle Zahlen reproduzierbar und schreibt sie als JSON-Artefakt:
    data/processed/analysis/ap33_logreg.json

Aufruf:  python scripts/analysis/ap33_logreg.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import model_framework as mf  # noqa: E402

OUT = os.path.join(ROOT, "data/processed/analysis/ap33_logreg.json")
GRID = [(c, w) for c in (0.1, 1.0, 10.0) for w in (None, "balanced")]
CAL_BINS = [0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.70, 1.01]


def pipeline(C: float, weight):
    return make_pipeline(StandardScaler(),
                         LogisticRegression(C=C, class_weight=weight, max_iter=4000))


def run_config(df, fc, C, weight):
    """Aggregierte + fold-weise Metriken fuer eine LogReg-Konfiguration."""
    per_fold, pooled = [], []
    for k, train, test in mf.folds(df):
        test = mf.add_baselines(test)
        m = pipeline(C, weight)
        m.fit(train[fc], train["y"].astype(int))
        test = test.copy()
        test["fold"] = k
        test["score_model"] = m.predict_proba(test[fc])[:, 1]
        per_fold.append({"fold": k, **mf.day_metrics(test, "score_model")})
        pooled.append(test)
    agg = {k: float(np.mean([f[k] for f in per_fold])) for k in ("brier", "logloss", "accuracy")}
    return agg, per_fold, pd.concat(pooled, ignore_index=True)


def normalize_per_day(df, col):
    """Score-Spalte je (city, target_date) zu Wahrscheinlichkeiten normieren."""
    s = df.groupby(["city", "target_date"])[col].transform("sum")
    return (df[col].clip(lower=0) / s.replace(0, np.nan)).fillna(0)


def calibration(df, prob_col):
    """Reliability-Tabelle + ECE ueber gepoolte Bucket-Wahrscheinlichkeiten."""
    p = df[prob_col].to_numpy()
    y = df["y"].astype(int).to_numpy()
    rows, ece = [], 0.0
    for lo, hi in zip(CAL_BINS[:-1], CAL_BINS[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum() == 0:
            continue
        rows.append({"bin": f"[{lo:.2f},{hi:.2f})", "n": int(m.sum()),
                     "mean_pred": float(p[m].mean()), "emp_freq": float(y[m].mean())})
        ece += m.sum() / len(p) * abs(p[m].mean() - y[m].mean())
    return rows, float(ece)


def subset_metrics(pooled, mask, cols=("q_model", "q_market")):
    out = {}
    sub = pooled[mask]
    for name, col in zip(("model", "market"), cols):
        out[name] = mf.day_metrics(sub, col)
    return out


def main():
    df = mf.load()
    fc = mf.feature_cols(df)
    print(f"Korpus: {len(df)} Zeilen, {df['target_date'].nunique()} Tage, {len(fc)} Features")

    # ---- U1: Gitter transparent auf der CV, Kriterium Brier ----
    print("\n=== Modellauswahl (aggregierter Brier ueber 4 Folds) ===")
    grid_results = []
    for C, w in GRID:
        agg, _, _ = run_config(df, fc, C, w)
        grid_results.append({"C": C, "class_weight": w or "none", **agg})
        print(f"  C={C:<5} weight={str(w or 'none'):<9} brier={agg['brier']:.4f} "
              f"logloss={agg['logloss']:.4f} acc={agg['accuracy']:.3f}")
    best = min(grid_results, key=lambda r: r["brier"])
    C_best, w_best = best["C"], None if best["class_weight"] == "none" else best["class_weight"]
    print(f"  -> gewaehlt: C={C_best}, class_weight={best['class_weight']} (Brier {best['brier']:.4f})")

    # ---- Finale fold-weise Zahlen + gepoolte Predictions ----
    agg, per_fold, pooled = run_config(df, fc, C_best, w_best)
    pooled["q_model"] = normalize_per_day(pooled, "score_model")
    pooled["q_market"] = normalize_per_day(pooled, "score_market")
    # Markt fold-weise aus pooled (score_market ist schon drin)
    market_folds = [mf.day_metrics(g, "q_market") for _, g in pooled.groupby("fold")]
    market_aggregate = {k: float(np.mean([m[k] for m in market_folds]))
                        for k in ("brier", "logloss", "accuracy")}

    # ---- U2: Koeffizienten (standardisiert, Fit auf gesamtem Korpus) ----
    m_full = pipeline(C_best, w_best)
    m_full.fit(df[fc], df["y"].astype(int))
    coefs = sorted(zip(fc, m_full.named_steps["logisticregression"].coef_[0]),
                   key=lambda x: -abs(x[1]))
    print("\n=== Koeffizienten (log-odds je Standardabweichung, sortiert) ===")
    for name, c in coefs:
        print(f"  {name:20} {c:+.3f}")

    # ---- U3: Kalibrierung Modell vs. Markt (gepoolte Test-Vorhersagen) ----
    cal_model, ece_model = calibration(pooled, "q_model")
    cal_market, ece_market = calibration(pooled, "q_market")
    print(f"\n=== Kalibrierung (gepoolt, {len(pooled)} Bucket-Vorhersagen) ===")
    print(f"  ECE Modell={ece_model:.4f}  |  ECE Markt={ece_market:.4f}")
    print(f"  {'Bin':14}{'n':>6}  {'Modell pred/emp':>18}  {'Markt pred/emp':>18}")
    cm = {r["bin"]: r for r in cal_market}
    for r in cal_model:
        mk = cm.get(r["bin"], {})
        print(f"  {r['bin']:14}{r['n']:>6}  {r['mean_pred']:.3f} / {r['emp_freq']:.3f}      "
              f"{mk.get('mean_pred', float('nan')):.3f} / {mk.get('emp_freq', float('nan')):.3f}")

    # ---- U4: Sensitivitaet ----
    print("\n=== Sensitivitaet (Tages-Metriken je Subset) ===")
    sens = {}
    for label, mask in (("source=backfill", pooled["source"] == "backfill"),
                        ("source=live", pooled["source"] == "live"),
                        ("ohne_overround_tage", ~pooled["flag_overround_outlier"])):
        r = subset_metrics(pooled, mask)
        sens[label] = r
        print(f"  {label:22} Modell brier={r['model']['brier']:.4f} acc={r['model']['accuracy']:.3f}"
              f"  | Markt brier={r['market']['brier']:.4f} acc={r['market']['accuracy']:.3f}"
              f"  (n={r['model']['n_days']})")

    json.dump({"run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
               "grid": grid_results, "chosen": best,
               "model_per_fold": per_fold, "model_aggregate": agg,
               "market_aggregate": market_aggregate,
               "coefficients": [{"feature": n, "coef": float(c)} for n, c in coefs],
               "calibration": {"model": cal_model, "market": cal_market,
                               "ece_model": ece_model, "ece_market": ece_market},
               "sensitivity": {k: {n: {kk: float(vv) for kk, vv in d.items()}
                                   for n, d in v.items()} for k, v in sens.items()}},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print(f"\nArtefakt: {OUT}")


if __name__ == "__main__":
    main()
