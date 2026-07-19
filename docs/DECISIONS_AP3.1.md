# Entscheidungs- & Änderungslog — AP 3.1 (Analysis-Zone & Feature-Engineering)

> Plan: Features bauen (Forecast-Werte, Differenzen, Vortageswerte, Saisonalität),
> ML-ready Tabelle. Meilenstein: Feature-Tabelle existiert.

## Design-Entscheidungen

- **U1 Grain bleibt Bucket-Ebene:** 1 Zeile = (city, target_date, bucket) = eine binäre
  Klassifikationsinstanz („landet das Tagesmax in diesem Bucket?"), Label =
  `label_is_winner_official`. Das trägt Brier/Log Loss direkt; die Tages-Verteilung
  entsteht in AP 3.2 durch Normierung der Bucket-Scores je Tag.
- **U2 Leakage-Regel für Features:** zulässig ist nur, was zum D2-As-of-Zeitpunkt
  (D-1 23:59 lokal) wissbar war. Insbesondere: das **Vortages-Ist (D-1)** ist zulässig —
  der Tag ist zum Cut lokal abgeschlossen, die Station publiziert das Max am selben Abend.
  Ehrliche Fußnote: unsere eigene Pipeline *erfasst* den Wert erst D+1 (Archiv-Lag);
  wir nutzen ihn als „operativ wissbar" (Standard bei Day-ahead-Settings), dokumentiert.
- **U3 Markt-Preise sind KEINE Modell-Features:** `market_p` (= `yes_price_norm`) und
  `clob_mid` werden als eigene Spaltengruppe mitgeführt, aber ausschließlich für die
  Baseline „Markt als Prädiktor" und den Modell-vs-Markt-Vergleich. Ein Modell, das den
  Marktpreis frisst, könnte nichts Eigenständiges mehr zeigen (Zirkularität).
- **U4 Nur gelabelte Tage in der Feature-Tabelle** (527 von 531): ungelabelte jüngste Tage
  sind für Training/Evaluation nutzlos; sie bleiben im Silver und rutschen nach, sobald
  die Resolution eintrifft (Full-Rebuild).
- **U5 Zeilen mit fehlenden Kern-Features werden verworfen statt imputiert** (13 Tage ohne
  Vortages-Ist an Serien-/Lückenrändern): sauberer für LogReg-Interpretierbarkeit als
  Imputations-Magie; Anzahl wird geloggt und als QS-Zahl ausgewiesen.
- **U6 Randbuckets:** `f_bucket_width_c` = reale Intervallbreite in °C (1,0 °C-Städte,
  ~1,11 °C NYC-2°F-Bänder); offene Ränder erhalten die Breite der inneren Buckets ihrer
  Stadt + Flag `f_bucket_is_edge` (das Modell lernt den Rand-Effekt über das Flag,
  nicht über eine erfundene Breite).
- **U7 Storage:** eigenes Artefakt `data/processed/analysis.duckdb`, Tabelle
  `feature_table` + Parquet-Export (Partition city) — Medallion-Trennung Silver/Gold
  sichtbar im Dateisystem; idempotenter Full-Rebuild aus Silver (`build_features.py`).
- **U8 Saisonalität** als `f_doy_sin/cos` (Jahreszyklus, stetig); `city` bleibt
  kategorial (Encoding ist Sache des Modell-Frameworks in AP 3.2).

## Feature-Katalog (v1)

| Gruppe | Spalten |
|---|---|
| Schlüssel | `city`, `target_date`, `bucket_label` |
| Label | `y` (= label_is_winner_official) |
| Markt (nur Baseline/Vergleich, U3) | `market_p`, `clob_mid` |
| Bucket-Geometrie | `f_bucket_mid_c`, `f_bucket_width_c`, `f_bucket_is_edge` |
| Forecast | `f_fc_max_c`, `f_dist_fc` (fc−mid, signiert), `f_absdist_fc`, `f_fc_span` (max−min) |
| Persistenz | `f_prevday_obs_c`, `f_dist_prevday`, `f_trend` (fc − Vortages-Ist) |
| Saisonalität | `f_doy_sin`, `f_doy_cos` |
| Kontrolle/QS (nicht fürs Modell) | `source`, `flag_partial_day`, `flag_overround_outlier`, `n_snapshots_pre_asof`, `hours_to_event_end` |

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Voraussetzungen geprüft | 527 gelabelte Tage, alle mit Forecast, 514 mit Vortages-Ist |
| 2 | Log angelegt | diese Datei |
| 3 | `build_features.py` gebaut + Lauf | **5 564 Zeilen, 514 City-Days (02.03.–18.07.)**; 13 Tage ohne Vortages-Ist verworfen (U5); QS: 0 Duplikate, genau 1 Label je Tag, 0 Kern-Feature-Nulls |
| 4 | Signal-Check | siehe unten — Features tragen |

## Signal-Check (Beleg, dass die Feature-Tabelle „lebt")

P(Bucket gewinnt) nach Forecast-Distanz `f_dist_fc` (gerundet):
unimodaler Peak bei 0 °C (31,2 %), sauber symmetrisch abfallend auf ~0 % bei ±5 °C —
das Kern-Feature trägt. Auffällig & erklärbar: leichte Asymmetrie zugunsten dist = −1
(27,4 % vs. 16,8 % bei +1) = der bekannte Station-über-Forecast-Bias (Gewinner liegt
tendenziell 1 Grad ÜBER dem Forecast; vgl. München +2 °C). Der Markt-Mittelpreis folgt
derselben Kurve (28,1 % am Peak) → Markt und Forecast sehen dieselbe Physik.
Persistenz-Feature (`f_dist_prevday`) deutlich schwächer (Plateau ~14 %) — erwartbar,
bleibt als Sekundärsignal. Basisrate 9,2 % (≈ 1/11 Buckets, konsistent).

## Meilenstein

✅ **Feature-Tabelle existiert:** `data/processed/analysis.duckdb` → `feature_table`
(+ Parquet je Stadt). 11 Modell-Features (Geometrie/Forecast/Persistenz/Saison),
Label `y`, Markt-Spalten strikt getrennt (U3), Kontroll-Spalten für Sensitivität.

## Übergabe an AP 3.2 (Modell-Framework)

- Zeitliche Splits auf `target_date` (TimeSeriesSplit; Basis 02.03.–18.07., 514 Tage).
- Tages-Normierung der Bucket-Scores (Verteilung je city×target_date) vor Brier/Log Loss.
- Baselines: (1) `market_p` direkt als Prädiktor, (2) naive Regel „Bucket, in das
  `f_fc_max_c` fällt, bekommt p=1" (bzw. verschmiert ±1 °C).
- `city` kategorial encoden; `source`/Flags als Ausschluss-Sensitivität, nicht als Feature.
