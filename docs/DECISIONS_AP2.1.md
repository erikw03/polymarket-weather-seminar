# Entscheidungs- & Änderungslog — AP 2.1 (Datenqualitäts-Modul, 5 Säulen)

> Ziel laut Plan: Checks für Freshness, Volume, Schema, Null-Rate; Meilenstein
> `quality_checks.py` läuft über den Korpus. Vorgaben unverändert (Raw read-only).

## Design-Entscheidungen

- **U1 Ein Modul, drei Ebenen:** `quality_checks.py` (Repo-Root, wie vom Plan benannt) prüft
  (a) Raw-Zone, (b) Silver-Artefakt, (c) Konsistenz zwischen beiden (Lineage-Säule).
  Kein Rebuild im Check — das Modul beobachtet nur (Observability ≠ Reparatur);
  Staleness von Silver ist selbst ein Check-Ergebnis.
- **U2 Severity-Modell OK / WARN / FAIL** mit Exit-Code 1 bei ≥1 FAIL → cron-/CI-tauglich
  (AP 2.2 baut Alerting-Konzept darauf auf). WARN bricht nicht ab (Betrieb läuft weiter),
  FAIL bedeutet „Datenprodukt nicht vertrauenswürdig".
- **U3 Schwellwerte datengetrieben, nicht geraten** (gemessen am Korpus 20.06.–12.07., im
  Modul als Konstanten mit Herkunftskommentar):
  - Freshness Snapshots: WARN > 2,5 h, FAIL > 6 h (Soll-Kadenz 1 h + Scheduler-Jitter).
  - Freshness Resolutions: WARN > 36 h, FAIL > 72 h seit jüngster Resolutions-Datei
    (Soll ~täglich; gemessene Label-Latenz 1–2 Tage).
  - Volume je Volltag: Wetter [180, 400] WARN-Band, FAIL < 96 (=<12 Abrufe); Markt [90, 200],
    FAIL < 48. (Gemessen: 224–328 bzw. 112–164; Doppel-Trigger macht die Spanne breit.)
  - Offizielle Label-Abdeckung für Tage ≤ heute−3: FAIL < 95 %, WARN < 99 % (gemessen: 100 %).
  - Null-Raten Silver: forecast_max WARN > 2 %; clob_mid nur auf source='live' WARN > 10 %
    (Backfill hat konstruktionsbedingt NULL); observed_max für Tage ≤ heute−2 WARN > 5 %.
  - Leakage-Audit: FAIL wenn min(hours_to_event_end) < 7,9 h (NYC-Konstruktionsminimum 8 h).
- **U4 Volume auf Dateiebene (Zeilenzahl), Detail nur für den jüngsten Tag:** volle Parse
  aller 400 MB je Lauf wäre unnötig teuer; Zeilenzahlen erkennen Ausfälle genauso. Nur die
  jüngste Datei je Quelle wird voll geparst (Freshness + Schema + Städte-Vollständigkeit).
- **U5 Randtage ausgenommen:** Volume-Checks laufen nur über abgeschlossene Kalendertage
  (UTC-gestern und älter); der heutige Teiltag würde sonst dauernd falsch alarmieren.
- **U6 Säule „Lineage" als Konsistenz-Checks:** Parquet-Zeilenzahl == DuckDB-Zeilenzahl,
  `transform_version`/`created_at` gesetzt, Silver-Spaltenmenge == freigegebene Schemaliste,
  Silver-Stand nicht älter als jüngster abgeschlossener Raw-Tag (WARN).

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Volumes gemessen (Schwellen-Herleitung) | Wetter 224–328, Markt 112–164 Zeilen/Volltag |
| 2 | Log angelegt | diese Datei |
| 3 | `quality_checks.py` gebaut | 18 Checks über 5 Säulen, Severity OK/WARN/FAIL, Exit-Code, `--json` |
| 4 | Lauf über den Korpus | **18/18 OK, 0 WARN, 0 FAIL** (Report im Chat; Overround-Rate 4,7 % knapp unter WARN-Schwelle 5 % — beobachten) |
| 5 | Negativtests | Freshness mit now+8h → F1/F2 FAIL ✓; Volume mit absurden Bändern → FAIL ✓ (Modul ist kein Schönwetter-Check) |

## Meilenstein

✅ **`quality_checks.py` läuft über den Korpus** (Plan AP 2.1). 18 Checks / 5 Säulen:
Freshness (3), Volume (2), Schema (3, inkl. Silver-Spaltenabgleich gegen freigegebenes
Schema), Nulls/Verteilung (8, inkl. Label-Abdeckung, Normierung, PK, Leakage-Audit),
Lineage (2, DuckDB==Parquet, Version/Staleness).

## Nachtrag 2026-07-30 — U3 erweitert: X2-Check trennt nach Schweregrad

Betriebserfahrung (Vorfall `docs/incident_2026-07-30_gate-fail.md`) zeigte, dass die
ursprüngliche „0 Verstöße erlaubt"-Regel für X2 **zu streng** war: ein frisch
gelisteter Markt ohne `outcomePrices` (legitimer, ~1 h kurzer Gamma-Zustand) ließ
7 Läufe in Folge rot werden — obwohl `build_silver` solche Buckets sauber überspringt
und die Daten einwandfrei waren.

Neue Regel im X2-Check: **hart** (kaputtes JSON, fehlende Top-Level-Keys, Event ohne
Datum) → FAIL; **weich** (einzelner Markt ohne/mit unparsebarem `outcomePrices`/
`clobTokenIds`, leeres `groupItemTitle`) → WARN; weich über
`SOFT_VIOLATION_MAX_RATE = 5 %` der Zeilen → doch FAIL (systematischer API-Ausfall).

Begründung/Prinzip: **Ein Check darf nicht strenger sein als die Verarbeitung, die er
absichert.** FAIL heißt „Datenprodukt nicht vertrauenswürdig", nicht „irgendetwas
weicht ab". Damit ist die Raten-Schwellen-Logik (analog `CORRUPT_MAX_RATE` in
`build_silver.py`, AP 2.3/U3) durchgängiges Entwurfsmuster im Projekt.

## Offene Punkte / Übergabe

- 📌 AP 2.2: Schwellwert-Alarme auf dem `--json`-Output + Alerting-Konzept (nur konzeptionell).
- 📌 AP 2.2/2.3-Kandidat: Quality-Gate in den Actions-Workflow (Lauf nach jeder Ingestion,
  FAIL macht den Run rot = kostenloses Alerting via GitHub-Mail). Bewusst noch NICHT eingebaut
  — gehört zu „Pipeline härten" (AP 2.3), erst dort mit Fehlersimulation testen.
- 🔍 N3a (Overround-Ausreißer 4,7 %) liegt knapp unter der WARN-Schwelle; steigt die Rate,
  zuerst prüfen, ob mehr „frische Listings" as-of gewählt werden (D+2-Events nachts gelistet).
