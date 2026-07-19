# Entscheidungs- & Änderungslog — AP 3.3 (Modell 1: Logistic Regression sauber)

> Plan: LogReg trainieren, Koeffizienten interpretieren, gegen Baselines vergleichen.
> Meilenstein: Modell 1 mit Ergebnissen.

## Design-Entscheidungen

- **U1 Modellauswahl transparent auf der CV:** kleines Gitter (C ∈ {0,1, 1, 10} ×
  class_weight ∈ {None, balanced}), bewertet über die 4 bestehenden Zeit-Folds,
  Auswahlkriterium = **Brier** (Proper Scoring Rule; Accuracy wäre für
  Wahrscheinlichkeits-Vergleich das falsche Kriterium). Ehrliche Fußnote: Auswahl
  auf denselben Folds wie die Berichtsmetrik ist bei 4 Folds pragmatisch
  (nested CV wäre Overkill); wird als Limitation erwähnt.
- **U2 Koeffizienten-Interpretation auf standardisierten Features** (StandardScaler
  in der Pipeline): Koeffizienten sind dann direkt als „Log-Odds-Änderung je
  Standardabweichung" vergleichbar. Fit fürs Koeffizienten-Bild auf dem gesamten
  gelabelten Korpus (Interpretation, nicht Evaluation — Evaluation bleibt CV).
- **U3 Kalibrierung numerisch statt als Plot:** Reliability-Tabelle (gepoolte
  Test-Vorhersagen aller Folds; Bins schief gewählt, weil ~90 % der Bucket-Probs
  < 0,15 liegen) + ECE für Modell UND Markt. Abbildungen entstehen in der
  Schreibphase (AP 5.x) aus denselben Daten — keine neue Plot-Abhängigkeit jetzt.
- **U4 Sensitivität:** Metriken getrennt nach `source` (backfill/live) und ohne
  Overround-geflaggte Tage — Modell und Markt identisch behandelt.
- **U5 Reproduzierbarkeit:** `scripts/analysis/ap33_logreg.py` erzeugt alle Zahlen
  (JSON-Artefakt); das Ergebnis-Doc zitiert daraus. Das Registry-Modell `logreg`
  im Framework wird auf die gewählte Konfiguration aktualisiert (AP 4.1 vergleicht
  dagegen).

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Log angelegt | diese Datei |
| 2 | `scripts/analysis/ap33_logreg.py` gebaut + Lauf | Gitter → C=10/none (Brier 0,7774); Koeffizienten, Kalibrierung, Sensitivität; JSON-Artefakt |
| 3 | Registry aktualisiert | `model_framework.MODELS['logreg']` = gewählte Konfiguration |
| 4 | Ergebnis-Doc | `docs/modell1_logreg_ergebnisse.md` (Zahlen + Interpretation + Limitationen) |

## Meilenstein

✅ **Modell 1 mit Ergebnissen.** Kernbefunde:
1. LogReg schlägt die naive Regel klar (Brier 0,777 vs. 1,289), bleibt aber hinter
   dem Markt (0,653) zurück.
2. **Der Markt-Vorsprung ist Schärfe, nicht Kalibrierung** (ECE 0,0124 vs. 0,0147 —
   fast gleichauf; Accuracy 48,6 % vs. 33,4 %). Zentrale These fürs Ergebnis-Kapitel.
3. Das Modell lernt den Station-über-Forecast-Bias selbstständig (signierter
   Distanz-Koeffizient −0,26) — konsistent mit den Datenqualitäts-Befunden aus AP 1.2.
4. Koeffizienten-Bild extrem klar: |Forecast-Distanz| dominiert (−2,16), alles andere
   ist Beiwerk — gut erzählbar als „interpretierbare Baseline".

## Übergabe an AP 4.1 (Modell 2: Gradient Boosting)

- Kandidat: sklearn `HistGradientBoostingClassifier` (kein neues Dependency;
  XGBoost/LightGBM nur falls nötig — Entscheidung dort dokumentieren).
- Hypothese aus 3.3: Interaktionen (Stadt × Distanz) sollten den städtespezifischen
  Bias abbilden können → erwartbarer Brier-Gewinn ggü. LogReg.
- Kalibrierung prüfen (Boosting oft überkonfident → ggf. Platt/Isotonic).
- Gleiches Framework, gleiche Folds, gleiche Baselines (Vergleichbarkeit).
