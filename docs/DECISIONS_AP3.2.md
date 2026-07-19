# Entscheidungs- & Änderungslog — AP 3.2 (Modell-Framework)

> Plan: Framework mit TimeSeriesSplit, sauberer Train/Test-Trennung, Metriken
> (Brier, Log Loss, Accuracy); Baselines: Marktpreis-als-Prädiktor + naive
> Forecast-Regel. Meilenstein: Framework trainiert Platzhalter-Modell fehlerfrei.

## Design-Entscheidungen

- **U1 Abhängigkeit scikit-learn:** vom Projektplan vorgegeben (LogReg-Baseline,
  Metriken, später Kalibrierung). In `requirements.txt` mit Begründung; kein
  XGBoost/LightGBM in diesem AP (Entscheidung fällt in AP 4.1 — sklearn's
  HistGradientBoosting ist der dependency-arme Kandidat).
- **U2 Evaluationseinheit = Tag, nicht Zeile:** Modelle scoren Buckets einzeln
  (binär), aber bewertet wird die **normierte Tagesverteilung** je (city, target_date)
  — Multiclass-Brier = Σ_b (q_b − 1{b=Gewinner})², Log Loss = −ln(q_Gewinner),
  Accuracy = argmax(q) == Gewinner. Das entspricht exakt dem Use-Case
  (Verteilungsvergleich Modell vs. Markt) und macht Modell und Markt direkt
  vergleichbar (Markt liefert dieselbe Struktur via `market_p`).
- **U3 Zeitliche Validierung mit Embargo:** sortierte Kalendertage in 5 gleiche
  Blöcke; Folds 2–5 sind Test-Blöcke, Training = alle früheren Tage (expanding
  window), dazwischen **2 Tage Embargo**. Begründung: Resolutions treffen mit
  1–2 Tagen Latenz ein — ein Modell, das im Betrieb heute trainiert würde, hätte
  die Labels von gestern noch nicht. Ohne Embargo wäre die CV leicht optimistisch.
- **U4 Baselines:**
  (a) **Markt**: `market_p` je Tag renormiert (Overround-bereinigt) als Verteilung.
  (b) **Naive Forecast-Regel**: das Bucket mit minimalem |Forecast − Bucket-Mitte|
      erhält Masse 1 (ε-geglättet auf 0,98/Rest, damit Log Loss endlich bleibt).
  Beide brauchen kein Training → identisch über alle Folds evaluierbar.
- **U5 Platzhalter-Modell:** `LogisticRegression` (mit StandardScaler + City-One-Hot,
  `class_weight=None`) auf den 11 Features + 4 City-Dummies. In AP 3.2 geht es um
  das fehlerfreie Durchlaufen des Frameworks; Interpretation/Koeffizienten = AP 3.3.
- **U6 Marktpreise bleiben aus den Modell-Features draußen** (AP 3.1/U3);
  das Framework erzwingt das über eine explizite FEATURES-Konstante.
- **U7 Ergebnisse als Artefakt:** `data/processed/analysis/model_results.json`
  (fold-weise + aggregiert; git-ignoriert, reproduzierbar via Skript).

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Log angelegt, sklearn installiert (U1) | scikit-learn 1.9.0 |
| 2 | `model_framework.py` gebaut | Laden → Folds (expanding, Embargo 2 d) → Scoren → Tages-Normierung → Metriken → JSON-Artefakt |
| 3 | End-to-End-Lauf | **fehlerfrei über 4 Folds, 420 Test-Tage** — Meilenstein erfüllt |

## Erste Zahlen (Platzhalter-Stand — Interpretation gehört zu AP 3.3/4.1)

| Prädiktor | Brier ↓ | Log Loss ↓ | Accuracy ↑ |
|---|---|---|---|
| **Markt** (Baseline) | **0,653** | **1,295** | **48,6 %** |
| LogReg (Platzhalter, untuned) | 0,778 | 1,723 | 33,4 % |
| naive Forecast-Regel | 1,289 | 4,118 | 31,9 % |

Ehrliche Lesart: Der Markt ist (erwartbar) der stärkste Prädiktor — er aggregiert
mehr Information als unser Feature-Satz. Das Platzhalter-Modell schlägt die naive
Regel deutlich bei Brier/Log Loss (bessere Unsicherheits-Quantifizierung), erreicht
aber (noch) nicht die Markt-Kalibrierung. Interessant fürs spätere Kapitel: alle
drei degradieren in Fold 4 (Sommer-Hitzeperiode = schwierigeres Regime).
Die Lücke LogReg↔Markt ist genau der Untersuchungsgegenstand von AP 3.3/4.1
(Koeffizienten-Interpretation, Kalibrierung, Gradient Boosting).

## Meilenstein

✅ **Framework trainiert Platzhalter-Modell fehlerfrei** — Registry-Design: neue
Modelle = 1 Zeile in `MODELS`; Baselines trainingsfrei; Ergebnisse reproduzierbar
als JSON-Artefakt.

## Übergabe an AP 3.3 (LogReg sauber)

- Koeffizienten interpretieren (StandardScaler-skaliert → direkt vergleichbar),
  Klassen-Gewichtung prüfen (Basisrate 9,2 %), ggf. Regularisierung tunen.
- Kalibrierungskurve Modell vs. Markt (Reliability-Diagramm) als Kern-Abbildung.
- Sensitivität: `source`-Subsets (live vs. backfill), Ausschluss geflaggter Tage.
