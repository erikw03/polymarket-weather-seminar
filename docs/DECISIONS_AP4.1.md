# Entscheidungs- & Änderungslog — AP 4.1 (Modell 2: Gradient Boosting)

> Plan: XGBoost/LightGBM, Kalibrierung, Feature-Importance, Vergleich mit Modell 1
> + Baselines. Meilenstein: beide Modelle + Vergleichstabelle.

## Design-Entscheidungen

- **U1 Bibliothekswahl — bewusste Plan-Abweichung:** statt XGBoost/LightGBM nutze ich
  sklearns `HistGradientBoostingClassifier`. Begründung: identische Algorithmus-Familie
  (histogram-basiertes GBDT, LightGBM-Bauart), **null zusätzliche Abhängigkeiten**
  (Projektprinzip seit AP 1.1), für 5,5 k Zeilen × 16 Features jenseits jeder
  Performance-Relevanz. In der Arbeit als „Gradient Boosting (sklearn-Implementierung
  der LightGBM-Familie)" ausweisen. XGBoost bliebe Option, falls HGB versagt (tat es nicht).
- **U2 Gitter klein & transparent** (wie AP 3.3, Kriterium Brier auf denselben Folds):
  learning_rate ∈ {0,05, 0,1} × max_leaf_nodes ∈ {15, 31} × max_iter ∈ {150, 400};
  kein Early Stopping (interner Random-Validation-Split wäre bei Zeitreihen unsauber).
- **U3 Kalibrierung explizit prüfen** (Boosting neigt zu Überkonfidenz): ECE/Reliability
  wie in AP 3.3; falls deutlich schlechter als LogReg (0,0147), zusätzlich isotonische
  Kalibrierung (`CalibratedClassifierCV`, cv=3 **innerhalb** des Train-Fensters) als
  Variante bewerten. Entscheidung nach Zahlen.
- **U4 Feature-Importance via Permutation** (HGB hat keine native Importance): auf dem
  Test-Fenster von Fold 4 (jüngstes Regime), Metrik = binärer Log Loss, n_repeats=10.
- **U5 Hypothesen-Test aus AP 3.3:** Interaktionen (Stadt × Distanz) sollten den
  städtespezifischen Bias abbilden → Vergleich Brier je Stadt GBM vs. LogReg
  (Erwartung: München profitiert am stärksten).
- **U6 Vergleichstabelle** = Meilenstein-Artefakt: Markt / naiv / LogReg / GBM (ggf.
  +kalibriert), fold-weise + aggregiert, identische Folds/Embargo/Metriken für alle.

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Log angelegt | diese Datei |
| 2 | `scripts/analysis/ap41_gbm.py` + Lauf | Gitter (8 Konfig.) → kleinste gewinnt (lr 0,05/15 Blätter/150 Iter.); roh überkonfident → isotonisch kalibriert (U3 griff) |
| 3 | Vergleichstabelle erstellt (U6) | Markt 0,653 · LogReg 0,777 · **GBM+iso 0,782** · naiv 1,289 (Brier) |
| 4 | Hypothese U5 getestet | ❌ widerlegt: LogReg in 3 von 4 Städten besser; Zusatzkapazität zahlt nicht |
| 5 | Registry + Ergebnis-Doc | `MODELS['gbm']` ergänzt; `docs/modell2_gbm_ergebnisse.md` |

## Meilenstein

✅ **Beide Modelle + Vergleichstabelle.** Kernbefunde: (1) Modelle praktisch gleichauf
(Occam: interpretierbare Baseline reicht); (2) GBM+isotonic = bester ECE aller
Prädiktoren (0,0119, sogar < Markt 0,0124), verliert trotzdem bei Brier → Markt-
Vorsprung ist definitiv Schärfe/Information, nicht Kalibrierung; (3) Engpass ist der
Feature-Satz, nicht die Modellklasse — saubere Überleitung zu Diskussion/Ausblick.

## Übergabe (Rest von Woche 4 laut Plan)

- **AP 4.2/4.3 (Schreiben Gliederung/Methodik + Ingestion/Storage):** Material liegt
  vollständig in `architektur_notizen.md`, `betriebskonzept_notizen.md`, den
  Ergebnis-Docs und den DECISIONS-Logs.
- **AP 4.4 DATA FREEZE (So 03.08.):** finaler `git pull` + `build_silver` +
  `build_features` + beide Analyse-Skripte auf dem Freeze-Stand; Ergebnistabellen
  fixieren (JSON-Artefakte einfrieren/committen als Freeze-Referenz — Entscheidung
  dort: Ausnahme vom „processed nicht committen" für die zwei Ergebnis-JSONs).
