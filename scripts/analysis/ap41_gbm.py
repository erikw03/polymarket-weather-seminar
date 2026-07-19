"""
AP 4.1 — Modell 2 (Gradient Boosting) sauber: Auswahl, Kalibrierung, Importance,
Vergleichstabelle beider Modelle + Baselines.

Nutzt dasselbe Framework wie AP 3.2/3.3 (Folds, Embargo, Tages-Metriken).
Artefakt: data/processed/analysis/ap41_gbm.json

Aufruf:  python scripts/analysis/ap41_gbm.py
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import model_framework as mf  # noqa: E402
from scripts.analysis.ap33_logreg import calibration, normalize_per_day  # noqa: E402

OUT = os.path.join(ROOT, "data/processed/analysis/ap41_gbm.json")
GRID = list(itertools.product((0.05, 0.1), (15, 31), (150, 400)))  # lr, leaves, iters


def gbm(lr: float, leaves: int, iters: int):
    return HistGradientBoostingClassifier(
        learning_rate=lr, max_leaf_nodes=leaves, max_iter=iters,
        early_stopping=False, random_state=42)


def run_estimator(df, fc, factory) -> tuple[dict, list[dict], pd.DataFrame]:
    """Fold-Schleife fuer einen Estimator; liefert Aggregat, per-Fold, gepoolte Tests."""
    per_fold, pooled = [], []
    for k, train, test in mf.folds(df):
        test = mf.add_baselines(test).copy()
        test["fold"] = k
        m = factory()
        m.fit(train[fc], train["y"].astype(int))
        test["score_model"] = m.predict_proba(test[fc])[:, 1]
        per_fold.append({"fold": k, **mf.day_metrics(test, "score_model")})
        pooled.append(test)
    agg = {k: float(np.mean([f[k] for f in per_fold])) for k in ("brier", "logloss", "accuracy")}
    return agg, per_fold, pd.concat(pooled, ignore_index=True)


def main():
    df = mf.load()
    fc = mf.feature_cols(df)
    print(f"Korpus: {len(df)} Zeilen, {df['target_date'].nunique()} Tage, {len(fc)} Features")

    # ---- U2: Gitter ----
    print("\n=== Modellauswahl GBM (aggregierter Brier ueber 4 Folds) ===")
    grid_results = []
    for lr, leaves, iters in GRID:
        agg, _, _ = run_estimator(df, fc, lambda: gbm(lr, leaves, iters))
        grid_results.append({"lr": lr, "leaves": leaves, "iters": iters, **agg})
        print(f"  lr={lr:<5} leaves={leaves:<3} iters={iters:<4} "
              f"brier={agg['brier']:.4f} logloss={agg['logloss']:.4f} acc={agg['accuracy']:.3f}")
    best = min(grid_results, key=lambda r: r["brier"])
    print(f"  -> gewaehlt: lr={best['lr']}, leaves={best['leaves']}, iters={best['iters']} "
          f"(Brier {best['brier']:.4f})")
    factory_raw = lambda: gbm(best["lr"], best["leaves"], best["iters"])

    # ---- Finale Zahlen GBM (roh) + Kalibrierungspruefung (U3) ----
    agg_raw, per_fold_raw, pooled_raw = run_estimator(df, fc, factory_raw)
    pooled_raw["q_model"] = normalize_per_day(pooled_raw, "score_model")
    pooled_raw["q_market"] = normalize_per_day(pooled_raw, "score_market")
    cal_raw, ece_raw = calibration(pooled_raw, "q_model")
    print(f"\nGBM roh:  brier={agg_raw['brier']:.4f}  ECE={ece_raw:.4f}")

    # isotonische Variante nur, wenn Kalibrierung schlechter als LogReg-Referenz (0.0147)
    result_cal = None
    if ece_raw > 0.0147:
        factory_cal = lambda: CalibratedClassifierCV(factory_raw(), method="isotonic", cv=3)
        agg_cal, per_fold_cal, pooled_cal = run_estimator(df, fc, factory_cal)
        pooled_cal["q_model"] = normalize_per_day(pooled_cal, "score_model")
        _, ece_cal = calibration(pooled_cal, "q_model")
        print(f"GBM +isotonic: brier={agg_cal['brier']:.4f}  ECE={ece_cal:.4f}")
        result_cal = {"aggregate": agg_cal, "ece": ece_cal}
        if agg_cal["brier"] < agg_raw["brier"]:
            print("  -> kalibrierte Variante ist besser (Brier) und wird als Modell 2 gefuehrt")

    # ---- LogReg-Referenz auf identischen Folds (aus Registry) ----
    agg_lr, per_fold_lr, pooled_lr = run_estimator(df, fc, mf.MODELS["logreg"])
    pooled_lr["q_model"] = normalize_per_day(pooled_lr, "score_model")

    # Baselines aus gepooltem Frame (identisch fuer alle)
    market_agg = {k: float(np.mean([mf.day_metrics(g, "q_market")[k]
                                    for _, g in pooled_raw.groupby("fold")]))
                  for k in ("brier", "logloss", "accuracy")}
    pooled_raw["q_naive"] = normalize_per_day(pooled_raw, "score_naive")
    naive_agg = {k: float(np.mean([mf.day_metrics(g, "q_naive")[k]
                                   for _, g in pooled_raw.groupby("fold")]))
                 for k in ("brier", "logloss", "accuracy")}

    # ---- U6: Vergleichstabelle ----
    print("\n=== VERGLEICHSTABELLE (420 Test-Tage, identische Folds) ===")
    rows = [("Markt", market_agg), ("naive Regel", naive_agg),
            ("LogReg (Modell 1)", agg_lr), ("GBM (Modell 2)", agg_raw)]
    if result_cal:
        rows.append(("GBM +isotonic", result_cal["aggregate"]))
    for name, a in rows:
        print(f"  {name:18} brier={a['brier']:.4f}  logloss={a['logloss']:.4f}  acc={a['accuracy']:.3f}")

    # ---- U5: Hypothese Stadt-Interaktion (Brier je Stadt) ----
    print("\n=== Brier je Stadt: GBM vs. LogReg vs. Markt (Hypothese: Muenchen profitiert) ===")
    per_city = {}
    for city, g in pooled_raw.groupby("city"):
        b_gbm = mf.day_metrics(g, "q_model")["brier"]
        b_lr = mf.day_metrics(pooled_lr[pooled_lr["city"] == city], "q_model")["brier"]
        b_mkt = mf.day_metrics(g, "q_market")["brier"]
        per_city[city] = {"gbm": b_gbm, "logreg": b_lr, "markt": b_mkt}
        print(f"  {city:7} GBM={b_gbm:.4f}  LogReg={b_lr:.4f}  Delta={b_lr - b_gbm:+.4f}  Markt={b_mkt:.4f}")

    # ---- U4: Permutation-Importance (Fold 4 Test, binaerer Log Loss) ----
    print("\n=== Permutation-Importance (Fold-4-Test, neg_log_loss, 10 Wiederholungen) ===")
    *_, (k4, train4, test4) = mf.folds(df)
    m4 = factory_raw()
    m4.fit(train4[fc], train4["y"].astype(int))
    imp = permutation_importance(m4, test4[fc], test4["y"].astype(int),
                                 scoring="neg_log_loss", n_repeats=10, random_state=42)
    order = np.argsort(-imp.importances_mean)
    importances = []
    for i in order[:10]:
        importances.append({"feature": fc[i], "mean": float(imp.importances_mean[i]),
                            "std": float(imp.importances_std[i])})
        print(f"  {fc[i]:20} {imp.importances_mean[i]:+.4f} ± {imp.importances_std[i]:.4f}")

    json.dump({"run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
               "grid": grid_results, "chosen": best,
               "gbm_aggregate": agg_raw, "gbm_per_fold": per_fold_raw,
               "gbm_ece": ece_raw, "gbm_calibrated": result_cal,
               "logreg_aggregate": agg_lr, "market_aggregate": market_agg,
               "naive_aggregate": naive_agg, "per_city_brier": per_city,
               "permutation_importance_top10": importances},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print(f"\nArtefakt: {OUT}")


if __name__ == "__main__":
    main()
