# Modell 1 — Logistische Regression: Ergebnisse (AP 3.3)

> Reproduzierbar via `python scripts/analysis/ap33_logreg.py`
> (Artefakt: `data/processed/analysis/ap33_logreg.json`, Stand 2026-07-19,
> Korpus 5 564 Zeilen / 514 gelabelte City-Days, 4 Zeit-Folds mit 2 d Embargo).

## 1. Modellauswahl

Gitter C ∈ {0,1, 1, 10} × class_weight ∈ {none, balanced}, Kriterium Brier (CV):
C nahezu unsensitiv (0,7774–0,7835), `balanced` verschlechtert durchgängig
(+0,015 Brier) — bei gut kalibrierten Wahrscheinlichkeiten ist Umgewichtung der
Basisrate (9,2 %) kontraproduktiv. **Gewählt: C=10, ohne Klassengewichtung.**

## 2. Endergebnis vs. Baselines (420 Test-Tage)

| Prädiktor | Brier ↓ | Log Loss ↓ | Accuracy ↑ |
|---|---|---|---|
| Markt | **0,653** | **1,295** | **48,6 %** |
| **LogReg (Modell 1)** | 0,777 | 1,721 | 33,4 % |
| naive Forecast-Regel | 1,289 | 4,118 | 31,9 % |

## 3. Koeffizienten (log-odds je Standardabweichung)

| Feature | Koef. | Lesart |
|---|---|---|
| `f_absdist_fc` | **−2,16** | dominiert: je weiter das Bucket vom Forecast, desto unwahrscheinlicher — die Physik des Problems |
| `f_dist_fc` | −0,26 | signiert: Buckets **über** dem Forecast sind ceteris paribus wahrscheinlicher — der bekannte Station-über-Forecast-Bias, vom Modell selbst gelernt |
| `f_bucket_is_edge` | +0,24 | offene Randbuckets sammeln Restmasse |
| `f_dist_prevday` / `f_trend` | −0,15 / −0,09 | Persistenz: schwach, aber vorhanden |
| Saison / Stadt-Dummies / Rest | ≤ ±0,09 | nahezu irrelevant — der Forecast trägt fast alles |

## 4. Kalibrierung (gepoolt, 4 614 Bucket-Vorhersagen)

**ECE: Modell 0,0147 vs. Markt 0,0124** — beide gut kalibriert, Markt minimal besser.
Reliability-Tabelle (pred/emp je Bin) im JSON-Artefakt; auffällig: der Markt
überschätzt den Bin [0,05–0,10) (0,072 → emp. 0,042), das Modell ist in den
mittleren Bins leicht unterkonfident.

**Kernbefund fürs Ergebnis-Kapitel:** Der Markt-Vorsprung (ΔBrier ≈ 0,12) kommt
**nicht** aus besserer Kalibrierung, sondern aus **Schärfe**: der Markt
konzentriert mehr Masse auf das richtige Bucket (Accuracy 48,6 % vs. 33,4 %) —
plausibel, weil er Informationen aggregiert, die unser Feature-Satz nicht hat
(Intraday-Modellläufe, stationsspezifisches Wissen, Order-Flow).

## 5. Sensitivität (Modell | Markt, Brier)

| Subset | Modell | Markt | n Tage |
|---|---|---|---|
| source=backfill (Mär–Jun) | 0,759 | 0,633 | 308 |
| source=live (Jun–Jul) | 0,829 | 0,709 | 112 |
| ohne Overround-Tage | 0,776 | 0,651 | 404 |

Ordnung überall stabil (Markt < Modell < naiv); beide degradieren im
Sommer-Regime (live) gleichgerichtet — kein Hinweis auf Daten-Artefakte;
Overround-Tage verzerren nichts Nennenswertes.

## Limitationen (ehrlich)

- Modellauswahl auf denselben Folds wie die Berichtsmetrik (4 Folds; nested CV
  bewusst verzichtet — als Limitation ausweisen). Effektgröße der Auswahl war
  ohnehin minimal (ΔBrier < 0,007).
- LogReg ohne Interaktionen: der städtespezifische Bias (München +2 °C) kann nur
  global über `f_dist_fc` gelernt werden — Kandidat für Gradient Boosting (AP 4.1).
