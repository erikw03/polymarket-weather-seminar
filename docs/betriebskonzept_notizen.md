# Betriebskonzept — Notizen & Bausteine (AP 2.4)

> Vorsortiertes Material für das ~1.200-Wörter-Kapitel (AP 5.1). Struktur = spätere
> Kapitel-Gliederung; jeder Punkt hat Beleg im Repo. Ergänzt `architektur_notizen.md`
> (dort: Gesamtsystem/4V/Medallion; hier: der laufende BETRIEB).

## K1 — Betriebsmodell (Wer/Was/Wann)

- **Vollautomatischer Batch-Betrieb, 0 manuelle Handgriffe:** stündlich GitHub-Actions-Lauf:
  Ingestion (3 Quellen) → Daten-Commit → Silver-Build → Quality-Gate (18 Checks).
- **Doppelte Trigger-Redundanz** (GitHub `schedule` + externer Cron via REST) — Konsequenz
  aus real erlebtem Scheduler-Ausfall am 21.06.; Cron off-peak `:17` statt `:00`.
- Betreiber-Aufwand im Normalbetrieb: `git pull` (Daten holen) — sonst nichts.
- Kosten: 0 € (öffentliches Repo, öffentliche APIs, Free-Tier-Cron).

## K2 — Observability (5 Säulen, Ist-Implementierung)

| Säule | Implementierung | Beleg |
|---|---|---|
| Freshness | F1–F3 in `quality_checks.py` (Snapshot-Alter je Quelle; Schwellen 2,5 h/6 h bzw. 36 h/72 h) | Lauf 13.07.: 0,3 h/0,3 h/0,5 h |
| Volume | V1–V2 gegen gemessene Bänder (nicht Fixwerte — Doppel-Trigger!) | 21 Volltage, 0 auffällig |
| Schema | X1–X3 inkl. Doppel-Dekodier-Probe + Silver-Spaltenabgleich | 46 Spalten exakt |
| Nulls/Verteilung | N1–N4: Label-Abdeckung, Null-Raten, Overround, Normierung, PK, Leakage-Audit | 100 % Abdeckung reifer Tage |
| Lineage | L1–L2 (DuckDB==Parquet, Versionierung) + `lineage.md` + Tracer-Skript | Kette bis Datei+Zeile belegt |

- Dazu Inhalts-Ebene: `anomaly_checks.py` (8 Checks, selbstkalibrierende Fences je Stadt,
  Severity INFO/WARN) — Trennung „actionable (Pipeline)" vs. „investigierbar (Inhalt)".

## K3 — Alerting (Konzept + realer Minimalpfad)

- Konzept vollständig in `alerting_konzept.md` (Routing P1–P3, Dedup/Entprellung/Eskalation,
  Stumm-Liste, Runbooks).
- **Real in Betrieb:** P1-Pfad = Quality-Gate im CI → FAIL = roter Run = GitHub-Mail.
  Bewusste Reihenfolge: Gate NACH Daten-Commit (Qualitätsalarm blockiert nie Persistenz).
- Bewusste Vereinfachung (begründen): kein On-Call/PagerDuty bei 1-Personen-Betrieb.

## K4 — Fehlertoleranz (Prepare–Detect–Resolve–Prevent, mit Nachweisen)

- **Prepare:** Retry/Backoff nur für transiente Fehler (T1–T4 ✓), Quellen-Isolation (T5 ✓),
  append-only Raw (kein korrumpierbarer Zustand), Idempotenz überall (Fetcher-Bestandscheck,
  Transform-Full-Rebuild T8 ✓), Trigger-Redundanz.
- **Detect:** 18 + 8 Checks, stündlich; harter Exit-Code (T6 ✓); toleranter NDJSON-Reader
  mit Korruptions-Schwelle 0,5 % (T7 ✓).
- **Resolve:** dokumentierte Runbooks; real durchgeführte Backfills (Resolutions-Nachfang
  16.–19.06., Previous-Runs-Forecasts, Lücke 17.–19.06. geschlossen).
- **Prevent:** Vorfall → Regel: Leakage→D2-Cut · Scheduler→Redundanz+`:17` · Koordinaten→
  Stations-Kriterium · Randbucket-Fehlalarm→A4-Verfeinerung · Platzhalter-Preise→Overround-Flag.
- Beleg-Suite: `scripts/harden/test_resilience.py` — **8/8 reproduzierbar** (MockTransport,
  Raw unberührt).

## K5 — Grenzen & Restrisiken (ehrlich ausweisen)

1. GitHub-Scheduler „best effort" (Minuten-Jitter; historisch 1 kompletter Ausfall) —
   mitigiert durch Redundanz, nicht eliminiert.
2. Cloud-Abhängigkeit: fällt GitHub aus, sammelt niemand (bewusst akzeptiert; lokaler
   launchd-Agent existiert als reaktivierbarer Fallback).
3. Resolution-Latenz 1–2 Tage (Wunderground finalisiert spät) — by design, kein Fehler.
4. Backfill-Zeilen: kein Volumen/CLOB, approximierter Overround, Forecast-Lead-Rest-
   differenz ~0,3–0,6 °C — `source`-Spalte macht es kontrollierbar.
5. Token-Hygiene: cron-job.org-PAT (repo-scoped, Actions r/w) nach Abgabe widerrufen.

## Kennzahlen für den Text (Stand 13.07.)

Sammelbetrieb seit 20.06. · 28–35 Abrufe/Stadt/Tag · ~350 MB Raw · 5 468 Silver-Zeilen ·
506 City-Days (01.03.–13.07.) · 500 mit offiziellem Label · QS 18/18 OK · Härtung 8/8 ·
Anomalien: 99 Findings (7 WARN, alle erklärt) · 0 € Betriebskosten.
