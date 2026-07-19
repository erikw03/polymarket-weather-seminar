# Modell 2 — Gradient Boosting: Ergebnisse (AP 4.1)

> Reproduzierbar via `python scripts/analysis/ap41_gbm.py`
> (Artefakt: `data/processed/analysis/ap41_gbm.json`, Stand 2026-07-19; identische
> Folds/Embargo/Metriken wie Modell 1). Implementierung: sklearn
> `HistGradientBoostingClassifier` (LightGBM-Familie; bewusste Plan-Abweichung
> ohne neues Dependency, DECISIONS_AP4.1/U1).

## 1. Modellauswahl

Gitter lr × Blätter × Iterationen (8 Konfigurationen): **die kleinste Konfiguration
gewinnt** (lr=0,05, 15 Blätter, 150 Iterationen, Brier 0,7949); jede Kapazitäts-
Erhöhung verschlechtert monoton (bis 1,074 bei der größten). Klassisches
Overfitting-Muster bei ~4–5 k Trainingszeilen und einem dominanten Feature.

## 2. Kalibrierung

GBM roh ist überkonfident (ECE 0,0181 > LogReg 0,0147) → isotonische Kalibrierung
(3-fach-CV **im Trainingsfenster**): **ECE 0,0119 (bester Wert aller Prädiktoren)**,
Brier 0,7949 → 0,7817. Die kalibrierte Variante ist Modell 2. (Nebenwirkung:
Accuracy sinkt auf 29,3 % — Isotonic glättet die argmax-Spitzen; für den
Wahrscheinlichkeits-Vergleich ist Brier/ECE das relevante Kriterium.)

## 3. Vergleichstabelle (Meilenstein; 420 Test-Tage, identische Folds)

| Prädiktor | Brier ↓ | Log Loss ↓ | Accuracy ↑ | ECE ↓ |
|---|---|---|---|---|
| **Markt** | **0,653** | **1,295** | **48,6 %** | 0,0124 |
| LogReg (Modell 1) | **0,777** | 1,721 | 33,4 % | 0,0147 |
| GBM +isotonic (Modell 2) | 0,782 | 1,734 | 29,3 % | **0,0119** |
| GBM roh | 0,795 | 1,763 | 32,8 % | 0,0181 |
| naive Regel | 1,289 | 4,118 | 31,9 % | — |

## 4. Hypothesen-Test (aus AP 3.3): ❌ widerlegt

Erwartung war: GBM-Interaktionen (Stadt × Distanz) bilden den städtespezifischen
Bias ab → Brier-Gewinn, v. a. München. Befund je Stadt (Brier, GBM − LogReg):
London −0,054, **München −0,033**, NYC −0,055 (LogReg jeweils besser!), nur
Tokio +0,078 für GBM. **Die Zusatzkapazität zahlt sich nicht aus** — der lineare
Bias-Term der LogReg genügt; was fehlt, ist Information, nicht Modellklasse.
Das deckt sich mit dem AP-3.3-Befund (Markt-Vorsprung = Schärfe/Information).

## 5. Feature-Importance (Permutation, Fold-4-Test, Log Loss)

`f_absdist_fc` dominiert mit Abstand (+0,170), `f_dist_fc` (+0,038) trägt den
Bias, alles Weitere ≤ +0,008 (inkl. Stadt-Dummies) — konsistent mit dem
LogReg-Koeffizientenbild. Beide Modelle „sehen" dieselbe simple Struktur.

## Fazit für die Arbeit

1. **Beide Modelle liegen praktisch gleichauf** (ΔBrier 0,005) — ein sauberes
   Occam-Ergebnis: bei diesem Feature-Satz ist die interpretierbare Baseline
   nicht zu schlagen.
2. **Kalibrieren lohnt:** Modell 2 ist nach isotonischer Kalibrierung der am
   besten kalibrierte Prädiktor überhaupt (ECE 0,0119 < Markt 0,0124) — schlägt
   den Markt aber trotzdem nicht bei Brier → erneut: der Markt gewinnt über
   **Schärfe**, nicht Kalibrierung.
3. Der Engpass ist Information (Feature-Satz), nicht Modellkapazität —
   direkte Überleitung zur Diskussion/Ausblick (mehr Leads, Ensemble-Spreads,
   stündliche Forecast-Profile als Erweiterungen).

## Limitationen

- Wie AP 3.3: Auswahl auf Berichts-Folds (Effekt hier größer sichtbar: Gitter-
  Spannweite 0,28 Brier — die Wahl „kleinste Konfiguration" ist aber strukturell
  begründet, nicht Zufallstreffer).
- Isotonic mit cv=3 im Trainingsfenster mischt Tage nicht-chronologisch
  (innerhalb Train akzeptiert; dokumentierte Vereinfachung).
