"""
AP 3.2 — Modell-Framework: zeitliche CV, Tages-Verteilungs-Metriken, Baselines.

Bewertungslogik (U2): Modelle scoren jedes Bucket binaer; je (city, target_date)
werden die Scores zu einer Verteilung q normiert und gegen den offiziellen
Gewinner bewertet:
    Brier    = Sum_b (q_b - 1{b=Gewinner})^2      (Multiclass, pro Tag)
    LogLoss  = -ln(q_Gewinner)                     (geclippt)
    Accuracy = argmax(q) == Gewinner
Der Markt liefert via `market_p` dieselbe Struktur -> direkte Vergleichbarkeit.

Validierung (U3): expanding window ueber Kalendertage, 4 Test-Bloecke,
2 Tage Embargo (Resolution-Latenz; ohne Embargo waere die CV optimistisch).

Baselines (U4, trainingsfrei):
    market : market_p je Tag renormiert
    naive  : Masse ~1 auf Bucket mit min |Forecast - Bucket-Mitte| (eps-geglaettet)

Modelle (U5): Registry MODELS; v1 nur Platzhalter-LogReg. AP 3.3/4.1 ergaenzen.

Aufruf:  python model_framework.py            # alle Modelle + Baselines
         python model_framework.py --json PFAD
"""

from __future__ import annotations

import argparse
import datetime as dt
import json

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import config

DB = config.PROJECT_ROOT / "data" / "processed" / "analysis.duckdb"
RESULTS_DEFAULT = config.PROJECT_ROOT / "data" / "processed" / "analysis" / "model_results.json"

# U6: Marktpreise sind bewusst NICHT enthalten (Zirkularitaet).
FEATURES = [
    "f_bucket_mid_c", "f_bucket_width_c", "f_bucket_is_edge",
    "f_fc_max_c", "f_dist_fc", "f_absdist_fc", "f_fc_span",
    "f_prevday_obs_c", "f_dist_prevday", "f_trend",
    "f_doy_sin", "f_doy_cos",
]
N_FOLDS = 4          # Test-Bloecke (nach initialem Trainingsblock)
EMBARGO_DAYS = 2     # Resolution-Latenz (U3)
EPS = 1e-6

MODELS = {
    # Platzhalter (U5); AP 3.3 interpretiert, AP 4.1 ergaenzt Gradient Boosting.
    "logreg": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
}


# ---------------------------------------------------------------- Daten
def load() -> pd.DataFrame:
    con = duckdb.connect(str(DB), read_only=True)
    df = con.execute("SELECT * FROM feature_table").df()
    con.close()
    df["target_date"] = pd.to_datetime(df["target_date"]).dt.date
    df = pd.get_dummies(df, columns=[], dtype=float)  # placeholder, city below
    for c in sorted(df["city"].unique()):              # City-One-Hot als Feature
        df[f"f_city_{c}"] = (df["city"] == c).astype(float)
    return df.sort_values(["target_date", "city", "f_bucket_mid_c"]).reset_index(drop=True)


def feature_cols(df: pd.DataFrame) -> list[str]:
    return FEATURES + [c for c in df.columns if c.startswith("f_city_")]


def folds(df: pd.DataFrame):
    """Expanding-Window-Folds ueber Kalendertage mit Embargo (U3)."""
    days = sorted(df["target_date"].unique())
    blocks = np.array_split(np.array(days), N_FOLDS + 1)  # Block 0 = Initial-Training
    for k in range(1, N_FOLDS + 1):
        test_days = set(blocks[k])
        embargo_cut = min(blocks[k]) - dt.timedelta(days=EMBARGO_DAYS)
        train_days = {d for b in blocks[:k] for d in b if d <= embargo_cut}
        yield k, df[df["target_date"].isin(train_days)], df[df["target_date"].isin(test_days)]


# ---------------------------------------------------------------- Bewertung
def day_metrics(test: pd.DataFrame, score_col: str) -> dict:
    """Scores je Tag normieren und gegen den Gewinner bewerten (U2)."""
    briers, lls, accs = [], [], []
    for (_, _), g in test.groupby(["city", "target_date"]):
        q = g[score_col].to_numpy(dtype=float)
        q = np.clip(q, 0, None)
        q = q / q.sum() if q.sum() > 0 else np.full(len(q), 1 / len(q))
        yv = g["y"].to_numpy(dtype=float)
        briers.append(float(np.sum((q - yv) ** 2)))
        lls.append(float(-np.log(max(q[yv == 1][0], EPS))) if yv.sum() == 1 else np.nan)
        accs.append(float(np.argmax(q) == np.argmax(yv)))
    return {"brier": np.nanmean(briers), "logloss": np.nanmean(lls),
            "accuracy": np.nanmean(accs), "n_days": len(briers)}


def add_baselines(test: pd.DataFrame) -> pd.DataFrame:
    test = test.copy()
    test["score_market"] = test["market_p"]
    # naive Forecast-Regel: min |dist| je Tag bekommt 0.98, Rest teilt sich 0.02
    idx = test.groupby(["city", "target_date"])["f_absdist_fc"].transform("min")
    is_best = (test["f_absdist_fc"] == idx).astype(float)
    n_best = test.groupby(["city", "target_date"])["f_absdist_fc"] \
                 .transform(lambda s: (s == s.min()).sum())
    n_all = test.groupby(["city", "target_date"])["f_absdist_fc"].transform("size")
    test["score_naive"] = np.where(is_best > 0, 0.98 / n_best, 0.02 / (n_all - n_best))
    return test


# ---------------------------------------------------------------- Lauf
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(RESULTS_DEFAULT))
    args = ap.parse_args()

    df = load()
    fc = feature_cols(df)
    print(f"feature_table: {len(df)} Zeilen, {df['target_date'].nunique()} Tage, "
          f"{len(fc)} Features | Folds={N_FOLDS}, Embargo={EMBARGO_DAYS}d")

    results: dict[str, list[dict]] = {}
    for k, train, test in folds(df):
        test = add_baselines(test)
        row_info = (f"Fold {k}: train {train['target_date'].min()}..{train['target_date'].max()} "
                    f"({train['target_date'].nunique()}d) -> test {test['target_date'].min()}.."
                    f"{test['target_date'].max()} ({test['target_date'].nunique()}d)")
        print("\n" + row_info)
        scored = {"market": "score_market", "naive": "score_naive"}
        for name, factory in MODELS.items():
            model = factory()
            model.fit(train[fc], train["y"].astype(int))
            test[f"score_{name}"] = model.predict_proba(test[fc])[:, 1]
            scored[name] = f"score_{name}"
        for name, col in scored.items():
            m = day_metrics(test, col)
            m["fold"] = k
            results.setdefault(name, []).append(m)
            print(f"  {name:8} brier={m['brier']:.4f}  logloss={m['logloss']:.4f}  "
                  f"acc={m['accuracy']:.3f}  (n={m['n_days']} Tage)")

    print("\n=== AGGREGAT (Mittel ueber Folds) ===")
    agg = {}
    for name, ms in results.items():
        agg[name] = {k: float(np.mean([m[k] for m in ms])) for k in ("brier", "logloss", "accuracy")}
        agg[name]["n_days_total"] = int(sum(m["n_days"] for m in ms))
        a = agg[name]
        print(f"  {name:8} brier={a['brier']:.4f}  logloss={a['logloss']:.4f}  "
              f"acc={a['accuracy']:.3f}  ({a['n_days_total']} Test-Tage)")

    out = {"run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
           "config": {"features": fc, "n_folds": N_FOLDS, "embargo_days": EMBARGO_DAYS},
           "per_fold": results, "aggregate": agg}
    RESULTS_DEFAULT.parent.mkdir(parents=True, exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    print(f"\nErgebnisse: {args.json}")


if __name__ == "__main__":
    main()
