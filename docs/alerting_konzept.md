# Alerting-Konzept (AP 2.2) — konzeptionell

> Scope laut Projektplan: Alerting wird **beschrieben, nicht gebaut** (bewusste
> Seminar-Vereinfachung). Grundlage sind die zwei real existierenden Signalgeber:
> `quality_checks.py` (AP 2.1, Pipeline-Gesundheit, 18 Checks, Exit-Code) und
> `anomaly_checks.py` (AP 2.2, Inhalts-Anomalien, Findings mit Severity).

## 1. Signal-Taxonomie

| Signalquelle | Ebene | Beispiel | Bedeutung |
|---|---|---|---|
| Ingestion-Lauf (GitHub Actions) | Prozess | Run schlägt fehl | Sammlung unterbrochen |
| `quality_checks.py` FAIL | Pipeline | Freshness > 6 h, PK-Duplikate, DuckDB≠Parquet | Datenprodukt nicht vertrauenswürdig |
| `quality_checks.py` WARN | Pipeline | Volume außerhalb Band, Label-Abdeckung < 99 % | Beobachten, kein Notfall |
| `anomaly_checks.py` WARN | Inhalt | Überraschungssieger p<0,02; Forecast-Miss > Fence | Manuell prüfen: Datenfehler vs. echtes Ereignis |
| `anomaly_checks.py` INFO | Inhalt | Overround-Tag, Ist-Sprung > p95 | Nur Protokoll/Analyse-Kontext |

Kernunterscheidung: **Pipeline-Signale sind actionable** (etwas reparieren),
**Inhalts-Signale sind investigierbar** (etwas verstehen). Nur erstere dürfen wecken.

## 2. Routing & Kanäle (Soll-Konzept)

- **P1 (sofort):** Ingestion-Fehlschlag ≥ 2 aufeinanderfolgende Läufe ODER Quality-FAIL.
  Kanal produktiv: PagerDuty/Slack-Webhook. **Im Projekt real vorhanden:** GitHub macht den
  Run rot und mailt den Repo-Owner — für ein Ein-Personen-Seminarprojekt der komplette
  P1-Pfad zum Preis von 0 €.
- **P2 (täglicher Digest):** alle WARN beider Module, aggregiert (eine Mail/Slack-Post pro
  Tag, nicht pro Finding). Konzept: `--json`-Reports beider Module werden von einem
  Digest-Job eingesammelt.
- **P3 (kein Versand):** INFO-Findings landen nur im JSON-Report/Log — abrufbar, nie störend.

## 3. Betriebsregeln (gegen Alarm-Müdigkeit)

1. **Dedup/Fingerprint:** `check + city + target_date` — dasselbe Finding wird nie zweimal
   gemeldet (JSON-Reports sind append-only vergleichbar).
2. **Entprellung:** Freshness-WARN erst nach 2 aufeinanderfolgenden Überschreitungen melden
   (Scheduler-Jitter ist normal, belegt: GitHub „best effort", Verspätungen bis ~15 min).
3. **Eskalation:** 3 × FAIL in Folge → P1 unabhängig vom Check-Typ.
4. **Auto-Resolve:** Finding verschwindet aus dem nächsten Report → als erledigt markieren,
   keine „Recovery"-Mail (Rauschen).
5. **Stumm-Liste:** erklärte Findings (z. B. A8-Overround-Tage im März-Backfill) werden mit
   Begründung gepinnt statt gelöscht — Alarmlage bleibt ehrlich, Historie bleibt erhalten.

## 4. Runbooks (Kurzform; aus real erlebten Vorfällen)

| Alarm | Erste Prüfung | Bekannte Ursache aus dem Projekt |
|---|---|---|
| Freshness FAIL | Actions-Tab: laufen Runs? beide Trigger? | GitHub-Scheduler lieferte nicht (21.06.) → externer Cron als Redundanz |
| Volume FAIL | Zeilenzahl der Tagesdatei; API-Status | Teiltage am Sammelbeginn; Doppel-Trigger verbreitert Band |
| Label-Abdeckung WARN | `resolutions_*`-Dateien; Latenz 1–2 d normal | Wunderground finalisiert spät (23:41Z beobachtet) |
| A1/A2 WARN | Wetterlage prüfen (echt?) vs. Koordinaten/Unit | Koordinatenwechsel München (1,5 °C Sprung) |
| A3 WARN | Label gegen `resolutions_*` gegenprüfen | echte Marktüberraschungen (6 Fälle, analytisch wertvoll) |
| A4 WARN | Bucket-Kind prüfen | Randbucket-False-Positive → Regel U6 (nur innere Buckets) |

## 5. Prepare–Detect–Resolve–Prevent-Einordnung

- **Prepare:** Schwellen datengetrieben kalibriert; Severity-Modell; Redundanz-Trigger.
- **Detect:** 18 Pipeline-Checks + 8 Anomalie-Checks, beide cron-fähig mit Exit-Codes/JSON.
- **Resolve:** Runbooks oben; Backfill-Pfade existieren nachweislich (Resolutions-Nachfang,
  Previous-Runs-Forecasts).
- **Prevent:** jeder untersuchte Alarm wird zur Regel (A4-Verfeinerung ist das gelebte
  Beispiel dieses AP; davor: D2-Cut aus Leakage-Befund, `:17`-Cron aus Scheduler-Ausfall).

## 6. Bewusste Vereinfachungen (für die Arbeit auszuweisen)

- Kein On-Call, keine SLO-Formalitäten, kein Incident-Tool — bei einem stündlichen
  Batch-Projekt mit 1 Betreiber wäre das Zeremonie ohne Erkenntnisgewinn.
- Digest-Job (P2) ist beschrieben, nicht gebaut; das CI-Quality-Gate (Checks als
  Workflow-Step, FAIL = roter Run = Mail) ist der konkrete nächste Schritt in **AP 2.3**,
  dort inklusive Fehlersimulation getestet.
