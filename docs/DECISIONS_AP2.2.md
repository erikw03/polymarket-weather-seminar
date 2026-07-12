# Entscheidungs- & Änderungslog — AP 2.2 (Anomalie-Erkennung & Alerting-Konzept)

> Plan: einfache Schwellwert-Checks + Log-Ausgabe; Alerting NUR konzeptionell.
> Meilenstein: Checks melden Auffälligkeiten. Abgrenzung: AP 2.1 prüft Pipeline-Gesundheit
> (läuft alles?), AP 2.2 prüft Inhalte (sind die Werte plausibel?).

## Design-Entscheidungen

- **U1 Selbstkalibrierende Schwellen je Stadt:** Kalibrierungsmessung zeigt starke
  Stadt-Unterschiede (Forecast-Fehler p95: London 2,3 vs. NYC 6,0 nativ; Tag-zu-Tag-Sprung
  p95: Tokio 5,1 vs. NYC 19,6 °F). Fixe globale Schwellen wären für NYC Daueralarm oder für
  London blind. Daher berechnet das Modul robuste Quantil-Fences je Stadt zur Laufzeit aus
  dem Korpus (INFO > p95-Fence, WARN > p99×1,25), ergänzt um **absolute Sanity-Grenzen**
  (Temperatur −25…+50 °C, Preis ∈ [0,1]) gegen echte Datenkorruption.
  Ehrliche Grenze: bei ~125 Tagen je Stadt sind p99-Quantile grob; dokumentiert.
- **U2 Anomalie ≠ Pipeline-Fehler:** Exit-Code bleibt 0 (Findings sind Beobachtungen,
  z. T. echtes Wetter/echte Marktbewegung — kein Grund, einen Cron rot zu machen);
  `--strict` erzwingt Exit 1 bei ≥1 WARN (für ein späteres CI-Gate). Das harte Gate bleibt
  `quality_checks.py` (AP 2.1).
- **U3 Findings-Format vereinheitlicht:** (severity, check, city, target_date, wert, fence,
  hinweis) — als Tabelle geloggt und per `--json` maschinenlesbar (Grundlage des
  Alerting-Konzepts: Fingerprint = check+city+date für Dedup).
- **U4 Acht Checks (A1–A8),** alle auf Silver (read-only), Herleitung je Check im Modul-Docstring:
  A1 Forecast-Miss · A2 Tag-zu-Tag-Sprung im Ist · A3 Überraschungs-Gewinner (as-of-Prob des
  späteren Gewinners < 5 % INFO / < 2 % WARN; Kalibrierung: p05 = 0,066) · A4 degenerierte
  Verteilung (max p > 0,95 bei Lead > 20 h) · A5 Bucket-Anzahl < 9 INFO / < 7 WARN ·
  A6 dünner Markt (event_volume < 20 % des Stadt-Medians, nur live) · A7 absolute
  Sanity-Grenzen · A8 Overround-Ausreißer-Tage (Flag aus Silver, als Findings gelistet).
- **U5 Alerting nur als Konzept-Doc** (`docs/alerting_konzept.md`), wie der Plan es verlangt —
  die real existierende Minimal-Implementierung (rote GitHub-Actions-Läufe + Mail bei
  Ingestion-Crash) wird als „Ist-Zustand" beschrieben, das Quality-Gate als AP-2.3-Schritt.

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Schwellen-Kalibrierung am Korpus | 4 Messungen (Forecast-Miss, Sprünge, Gewinner-Prob, Buckets/Volumen) |
| 2 | Log angelegt | diese Datei |
| 3 | `anomaly_checks.py` gebaut (A1–A8) | erster Lauf: 103 Findings, 11 WARN |
| 4 | Kreuztreffer München 13.04. untersucht | **False-Positive-Mechanismus gefunden:** A4 flaggte offene Randbuckets („11°C or higher" bei Forecast 18 °C → p=0,991 ist rational) |
| 5 | **U6: A4 nur für innere Buckets** (exact/range) | Re-Lauf: **99 Findings, 7 WARN, 92 INFO** — alle 4 A4-WARNs waren Randbucket-Artefakte |
| 6 | `docs/alerting_konzept.md` geschrieben | Signal-Taxonomie, Routing P1–P3, Betriebsregeln, Runbooks aus echten Vorfällen, PDRP-Mapping |

## Ergebnis-Interpretation (ehrlich)

- Die **7 verbleibenden WARNs sind keine Datenfehler**, sondern echte Extremereignisse:
  1× Forecast-Miss 5,5 °C (München 13.04.) und 6× Überraschungssieger (Markt gab dem
  späteren Gewinner < 2 %; z. B. London 04.05. p=0,001). Für die Analyse (AP 3/Arbeit)
  sind genau diese Tage Gold — Kalibrierungs-Diskussion.
- Die A4-Iteration (Finding → Drill-down → Regel verfeinert) ist das gelebte
  Prevent-Beispiel fürs Betriebskonzept-Kapitel.
- INFO-Gros: 41 Quantil-Übertreter (per Konstruktion ~5 % der Tage), 26 Overround-Tage
  (März/April-Backfill, frische Listings), 1 dünner Markt (München 18.06., vol=3 336).

## Meilenstein

✅ **„Checks melden Auffälligkeiten"** — 8 Anomalie-Checks laufen über den Korpus,
Findings mit Severity/Fence/Hinweis als Tabelle + `--json`; Alerting-Konzept dokumentiert.

## Übergabe an AP 2.3 (Pipeline härten)

- Quality-Gate in Actions einbauen (`quality_checks.py` als Workflow-Step, FAIL = rot = Mail)
  und mit simulierten Fehlern testen (API down, kaputte Datei, stale Silver).
- Retry/Backoff-Verhalten unter echtem Fehler verifizieren; Idempotenz-Nachweis wiederholen.
