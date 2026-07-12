# Entscheidungs- & Änderungslog — AP 1.3 (Backfill historische Daten)

> Fortsetzung von `DECISIONS_AP1.2.md`. Ziel laut Projektplan: historische Daten
> rückwirkend einspeisen, Cleaned-Transform darauf laufen lassen → Korpus wächst
> rückwirkend. Meilenstein: Korpus deckt auch Zeit vor Sammelstart (20.06.) ab.

## Ausgangslage (aus AP 1.1 Phase A bekannt)

- `data/backfill/` (erhoben 21.06., Raw-Zone-Prinzip: API-Antworten verbatim):
  - `polymarket_<city>_history.json`: **423 aufgelöste Events** (2026-03-01…06-20) mit
    `resolved_bucket` + stündlicher Yes-Preis-Trajektorie je Bucket (CLOB `/prices-history`).
  - `weather_<city>_history.json`: `historical_forecast` + `archive_actuals` (daily, 112 Tage).
- Silver-Schema sieht `source='backfill'` vor (F2/AP 1.1); Lineage-Quelle [B] dokumentiert.
- Offener Punkt aus AP 1.1: Forecast-Lücke 17.–19.06. (live nicht gesammelt).

## Zentrale Konsistenzfrage dieses AP (vorab identifiziert)

Die D2-As-of-Politik verlangt den Forecast-Stand **vor 00:00 Lokalzeit des Zieltags**
(= Day-ahead, Lead ~1 Tag). Zu prüfen: Welchen Lead repräsentieren die am 21.06.
gespeicherten `historical_forecast`-Tageswerte? Falls Lead 0 (Same-day-Lauf), wären
Backfill-Zeilen systematisch besser informiert als Live-Zeilen → unfairer Vergleich.
Dann: Lead-1-konsistente Quelle beschaffen (Open-Meteo „Previous Runs"-API) oder
Forecast-Spalten im Backfill mit Flag versehen. → Wird per Live-Probe verifiziert.

## Entscheidungen AP 1.3

- ✅ **U1 Lead-konsistenter Backfill-Forecast = Previous-Runs-API (`temperature_2m_previous_day1`).**
  Live-Probe gegen die eigenen Day-ahead-Forecasts (je 20 Tage): previous_day1 MAE 0,30 (London) /
  0,61 (München) vs. historical-forecast-daily 0,73/0,74 → previous_day1 ist empirisch näher UND
  per Konstruktion lead-konsistent (~24 h). Der am 21.06. gespeicherte `historical_forecast`
  (Lead ~0, besser informiert) wird für Features NICHT verwendet (bleibt als Raw liegen).
  Restinkonsistenz (~0,3–0,6 °C MAE) dokumentierte Limitation.
- ✅ **U2 Live gewinnt bei Überlappung:** (city, target_date) mit Live-Zeilen wird im Backfill
  übersprungen (Live hat Volumen/CLOB/exakte as-of-Timestamps; Backfill nicht).
- ✅ **U3 Ausschlussregel dünner Tage:** Bucket ohne Pre-Cut-Preis → Zeile entfällt; Tag entfällt
  ganz, wenn <50 % der Buckets Pre-Cut-Preise haben ODER das offizielle Gewinner-Bucket keinen
  hat (nicht labelbar). Ergebnis: 7 von 423 Tagen übersprungen (1,7 %).
- ✅ **U4 QS-Regel präzisiert:** Open-Meteo-Sekundärlabel darf im Backfill Summe 0 haben, wenn
  dessen Gewinner-Bucket vor dem Cut nie gehandelt wurde (wahrheitsgemäß alle false; Beleg:
  München 30.03., obs 6 °C, 6°C-Bucket ungehandelt). Summe >1 bleibt überall fatal, Summe 0 bei live fatal.
- ✅ **U5 Overround-Approximation im Backfill:** `overround_sum` = Summe der je Bucket letzten
  Pre-Cut-Preise (Timestamps differieren um Minuten zwischen Buckets — dokumentierte Näherung).
- ✅ **U6 Historisch nicht verfügbar → NULL:** `clob_mid`, Volumen/Liquidität, `forecast_asof_ts`,
  `event_id`, `market_id`, `resolution_source_url`, `observed_lag_days` (Schema-Doc angepasst).
- ✅ **U7 Resolutions-Nachfang 16.–19.06.:** Init-Backfill (AP 1.2) begann am 20.06.; Fetcher-Lauf
  mit `since=2026-06-16` fing 16 weitere Events (u. a. München 17./18.06., die als Live-Zeilen aus
  dem 16.06.-Snapshot existieren, sowie 12.07.).

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Log angelegt | diese Datei |
| 2 | Backfill-Bestand gesichtet (read-only) | Struktur ok; Wetter-Backfill nutzt Flughafen-Koordinaten ✓ |
| 3 | Lead-Probe beider APIs | → U1 (previous_day1 gewinnt) |
| 4 | `backfill_prevday_forecast.py` + Lauf | 4 neue Raw-Dateien `weather_<city>_prevday1.json` (je 2 688 Stundenwerte, 01.03.–20.06.); idempotent ✓ |
| 5 | `build_silver.py` um `load_backfill_rows()` erweitert | U2–U6 implementiert |
| 6 | QS-Fehlalarm analysiert | München 30.03. → U4, Check präzisiert |
| 7 | Resolutions-Nachfang | 16 Events (U7) |
| 8 | Finaler Lauf | **5 457 Zeilen, 505 city-days (01.03.–13.07.), 500 mit offiziellem Label, 505 mit Forecast; QS grün** |

## Verifikation

- Lücke 17.–19.06. geschlossen (Backfill bzw. Live-Zeilen aus 16.06.-Snapshot; NYC 18.06. = 1 der
  7 U3-Ausschlüsse).
- Kein (city, target_date) doppelt (Live-wins-Dedup: 0 Konflikte).
- `labels_agree` Backfill 0,19–0,47 je Stadt — gleiches Muster wie live (München am schlechtesten),
  d. h. der Quellen-Mismatch ist zeitstabil und kein Artefakt des Sammelzeitraums.

## Offene Punkte

- 📌 AP 2.x: `official_known`-Freshness-Check; Volume-Check mit erwarteter Spanne 28–35 Abrufe/Tag.
- 🔍 Anmerkung fürs Arbeit-Kapitel: Backfill-Zeilen haben KEINE `flag_partial_day`-Semantik und
  approximierte Overrounds (U5) — bei Sensitivitätsanalysen `source` als Kontrollvariable nutzen.
