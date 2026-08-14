# 🧊 Data Freeze — Kennzahlen (Stand 2026-08-14, 07:16 UTC)

> **Verbindliche Zahlenbasis der Seminararbeit.** Alle `[Z: …]`-Marker in
> `docs/arbeit/` werden gegen diese Tabelle ersetzt. Ab hier ändert sich nichts mehr;
> die Ingestion läuft zwar weiter, ihre Daten fließen aber nicht mehr in die Arbeit ein.
> Reproduzierbar über die mitgesicherten Artefakte in diesem Ordner.

## Korpus & Speicherzonen

| Größe | Wert |
|---|---|
| Sammelzeitraum Live-Ingestion | 20.06.–14.08.2026 (**57 Sammeltage**) |
| Abgedeckter Zeitraum inkl. Backfill | **01.03.–14.08.2026** |
| Bronze (Rohzone) | **1,0 GB**, 149 Tagesdateien |
| Abrufe je Stadt und Tag | **39–45** (Median 41) |
| Silver | **6.887 Zeilen**; 2,0 MB DuckDB + 700 KB Parquet |
| Gold (Feature-Tabelle) | **6.708 Zeilen**, **618 Stadt-Tage**; 780 KB |
| Full-Rebuild Bronze→Silver→Gold | **4,2 s** (ein Rechenkern) |
| Städte | 4 (London, München, NYC, Tokio) |
| Temperatur-Buckets je Markt | ~11 |

## Qualität & Betrieb

| Größe | Wert |
|---|---|
| Qualitäts-Checks | **18/18 OK**, 0 FAIL, 0 WARN |
| Anomalie-Findings | 119 (11 WARN, 108 INFO) — WARNs sind erklärte Extremereignisse |
| Resilienz-Nachweise | **8/8 bestanden** (`scripts/harden/test_resilience.py`) |
| Dokumentierte Betriebsvorfälle | 3 (Scheduler-Ausfall, Merge-Race, Fehlalarm) |
| Leakage-Audit (min. Vorlauf) | 8,0 h (Konstruktionsminimum NYC) |

## Datenqualität: Label-Quellen-Mismatch

| Größe | Wert |
|---|---|
| Exakte Bucket-Übereinstimmung Open-Meteo ↔ offizielle Auflösung | **32,7 %** (n = 630 Tage) |
| Mittlerer Versatz München | **+1,35 °C** |
| Mittlerer Versatz NYC / London / Tokio | −0,94 °F / −0,19 °C / +0,42 °C |

## Modellergebnisse (420 Test-Tage, identische Zeit-Folds mit 2 Tagen Embargo)

| Prädiktor | Brier ↓ | Log Loss ↓ | Accuracy ↑ | ECE ↓ |
|---|---|---|---|---|
| **Markt** | **0,659** | **1,308** | **47,5 %** | **0,0110** |
| LogReg (Modell 1) | 0,787 | 1,749 | 33,3 % | 0,0117 |
| GBM + isotonic (Modell 2) | 0,784 | 1,751 | 32,2 % | – |
| GBM roh | 0,793 | 1,780 | 31,8 % | – |
| naive Forecast-Regel | 1,292 | 4,125 | 31,7 % | – |

**Gewählte Konfigurationen:** LogReg C=1,0 ohne Klassengewichtung; GBM lr=0,05,
15 Blätter, 150 Iterationen + isotonische Kalibrierung.

## ⚠️ Abweichungen gegenüber den Zwischenständen (AP 3.3 / 4.1, 19.07.)

Ehrlich auszuweisen, da die Ergebnis-Docs ältere Zahlen nennen:

| Aussage | Zwischenstand | **Freeze** | Gilt weiter? |
|---|---|---|---|
| Label-Übereinstimmung | 23 % | **32,7 %** | Ja — Mismatch bleibt gravierend, Schätzung ist mit n=630 stabiler |
| München-Versatz | +2,0 °C | **+1,35 °C** | Ja — systematischer Bias, Betrag geringer |
| LogReg vs. GBM | LogReg besser (0,777 vs. 0,782) | **GBM minimal besser (0,784 vs. 0,787)** | **Angepasst:** beide sind praktisch gleichauf (Δ 0,003); die Aussage lautet daher „Modellklasse ist nicht der Engpass", nicht „LogReg schlägt GBM" |
| Kalibrierung | GBM+iso besser als Markt (0,0119 vs. 0,0124) | **Markt minimal besser (0,0110 vs. 0,0117)** | **Angepasst:** Kernaussage bleibt — Kalibrierung praktisch gleichauf, der Markt gewinnt über **Schärfe** (Accuracy 47,5 % vs. 33 %) |
| Stadt-Interaktions-Hypothese | widerlegt | **weiterhin widerlegt** (LogReg in 3 von 4 Städten besser) | Ja |

**Fazit der Abweichungen:** Alle tragenden Aussagen bleiben gültig; zwei Detail-
Vergleiche kippen knapp und werden im Text entsprechend vorsichtiger formuliert.

## Gesicherte Freeze-Artefakte (in diesem Ordner)

`ap33_logreg.json` · `ap41_gbm.json` · `model_results.json` · `quality_report.json` ·
`anomaly_report.json` — Kopien aus `data/processed/analysis/` (dort git-ignoriert, da
abgeleitet; hier bewusst versioniert als Beleg der Abgabefassung).
