# Entscheidungs- & Änderungslog — AP 1.1 (Raw sichten & Cleaned-Schema entwerfen)

> Laufendes Log. Jede Annahme, offene Frage und Entscheidung mit Begründung.
> Status-Kürzel: ✅ entschieden · 🔶 vorgeschlagen (wartet auf Freigabe) · ❓ offen

## Rahmen

- **Datum:** 2026-07-10 (AP 1.1 laut `projektplan_data_engineering.md`)
- **Scope:** Analyse & Schema-Design für Raw(Bronze) → Cleaned(Silver). KEIN Transform-Bau (das ist AP 1.2).
- **Raw ist WORM:** alle Skripte unter `scripts/inspect/` öffnen Rohdaten ausschließlich lesend.

## Transparenz / Vorgeschichte

- Die Ingestion-Skripte (`src/ingest_*.py`, `src/raw_store.py`) und ein **früher Prototyp
  `build_processed.py`** (21.06., DuckDB-Tabellen) sind in früheren Claude-Sessions entstanden.
  Der Prototyp ist **nicht** der AP-1.2-Transform und wird in AP 1.1 weder ausgeführt noch
  weiterentwickelt; er dient höchstens als Ideenquelle. Alle „Vorbefunde" aus dem Auftrag
  werden unabhängig am vollen Korpus verifiziert.
- Zusätzlich zum täglichen NDJSON-Raw existiert ein **historischer Backfill-Bestand**
  (`data/backfill/`, konsolidierte JSONs vom 21.06. mit aufgelösten Märkten März–Juni).
  Er ist Teil der Bestandsaufnahme in Phase A, da er die Label-Frage (D3/D4) direkt betrifft.

## Arbeitsschritte-Protokoll (Phase A)

| # | Schritt | Werkzeug/Befehl | Ergebnis |
|---|---|---|---|
| 1 | Korpus aktualisiert | `git pull --rebase --autostash origin main` | Stand 2026-07-10T08:02Z, je 22 Tagesdateien |
| 2 | Projektplan gelesen | `projektplan_data_engineering.md` | AP-1.1-Ziel bestätigt |
| 3 | Log angelegt | diese Datei | — |
| 4 | Umfang/Ablage erhoben | `scripts/inspect/01_corpus_overview.py` | 22+22 Dateien, Lücke 17.–19.06., 3. kind, clob_quotes, Backfill-Bestand |
| 5 | Schema inventarisiert | `scripts/inspect/02_schema_inventory.py` | Feldlisten je Ebene; 11 Alt-Records; String-Zahlen; Resolution-Felder |
| 6 | As-of/Qualität gemessen | `scripts/inspect/03_asof_quality.py` | Archive nicht strikt stabil; Spannweiten; 100 % Ground-Truth-Abdeckung |
| 7 | Drill-down | `scripts/inspect/04_drilldown_leakage_overround.py` | Overround-Ausreißer = frische Listings; Post-12Z-Leakage belegt |
| 8 | Report geschrieben | `docs/raw_inspection_report_AP1.1.md` | Phase A abgeschlossen → STOPP 1 |

## Annahmen — Prüfergebnis Phase A

- A1: Vorbefunde ~80 % bestätigt; **widerlegt:** Archive-Stabilität (32/112 Paare variieren);
  **wesentlich erweitert:** `clob_quotes`, Post-12Z-Sichtbarkeit + Leakage, Bucket-Level-Resolution-Spuren,
  Overround-Ausreißer bei frischen Listings, 11 Alt-Meta-Records, NYC-2°F-Bänder. Details im Report.
- A2: bestätigt — Backfill nutzt dieselben Städte/Stationen/Einheiten; enthält 423 aufgelöste Zieltage
  (2026-03-01…06-20) inkl. `resolved_bucket` → primäre Label-Quelle für die Vergangenheit.

## Fragen F1–F4 — an STOPP 1 vom Auftraggeber an mich delegiert („entscheide du")

- ✅ F1 **Grain:** Bucket-Ebene. Begründung: Auf Polymarket ist jeder Temperatur-Bucket technisch ein
  eigener binärer (Sub-)Markt (eigene `id`, `conditionId`, eigenes Orderbuch). „1 Zeile = 1 Markt × 1 Tag"
  aus dem Projektplan ist damit wörtlich erfüllt: 1 Zeile = 1 Sub-Markt (Bucket) × 1 Zieltag. Details/Alternative → D1.
- ✅ F2 **Backfill im Schema vorsehen:** ja, per Spalte `source ∈ {live, backfill}`. Das Schema wird so
  entworfen, dass AP 1.3 den Backfill ohne Schemaänderung einspielen kann; die tatsächliche Integration
  bleibt AP 1.3 (so sieht es der Projektplan vor).
- ✅ F3 **`weather-historical-forecast` (n=1) ignorieren:** ein einzelner, manueller Abruf (nur München,
  16.–19.06.) ist keine systematische Quelle; der Transform filtert explizit auf die zwei regulären kinds.
  AP 1.3 backfillt Forecasts ohnehin systematisch. (Raw bleibt natürlich unangetastet.)
- ✅ F4 **Randtage behalten & flaggen:** Silver löscht keine Information (WORM-Geist); Zeilen aus
  Teiltagen bekommen ein Qualitäts-Flag (`flag_partial_day`), das Analyse/Modell filtern kann.
  Ausschluss ist eine Analyse-, keine Speicher-Entscheidung.

## Entscheidungen D1–D6 — ✅ freigegeben an STOPP 2 (2026-07-10, „wie empfohlen")

Vollform mit Spalten/Lineage in `docs/cleaned_schema_AP1.1.md`; hier die Essenz + verworfene Alternativen:

- ✅ **D1 Grain = Stadt × Zieltag × Bucket.** Bucket ist auf Polymarket ein eigener binärer Markt
  → Plan-Formulierung „1 Markt × 1 Tag" wörtlich erfüllt; Brier/Log Loss brauchen Bucket-Zeilen.
  *Verworfen:* Event-Zeile mit Preis-Spalten (instabil: 9–11 Buckets, °C- vs. 2-°F-Bänder).
- ✅ **D2 As-of = letzter Snapshot vor 00:00 Lokalzeit des Zieltags** (einziger v1-Cut; Spalte
  `asof_policy` hält erweiterbar). Begründung: belegtes Leakage ab Zieltag-Vormittag; gleicher
  Informationsstand für Modell & Markt. *Verworfen:* Cut relativ zu `endDate` 12:00Z (je Stadt
  andere Lokalzeit → ungleiche Information; endDate ≠ realer Handelsschluss).
- ✅ **D3 Label = Open-Meteo-Archive, jüngster Abruf, nur Stations-Koordinaten, half-up auf ganze
  Grad nativ** → `label_in_bucket`. Markt-Resolution als Zusatzspalten (`market_resolved_bucket`,
  `labels_agree`) zur Mismatch-Quantifizierung (~0,5–1 °C, Limitation in der Arbeit).
  *Verworfen als Primärquelle:* markt-implizites Ergebnis (zirkulär, Live-Deckungslücken).
- ✅ **D4 Roll-off:** Wetter-Archive als Wahrheit + letzter Pre-Cut-Preis als „market final
  estimate". **To-do AP 1.2:** Resolution-Fetcher (`/events?slug=` am Folgetag →
  `resolutions_<D>.ndjson`, append-only).
- ✅ **D5 Spaltenliste:** voller Umfang inkl. `clob_mid`, `event_volume/liquidity`, QS-Flags,
  beide as-of-Timestamps, Lineage-IDs. Details + Lineage-Tabelle im Schema-Doc.
- ✅ **D6 Join & Einheiten:** Join `(city, target_date)`; Label-Join datei-übergreifend;
  Bucket-Zuordnung ganzzahlig **nativ** (rundungsartefaktfrei). Einheiten nativ führen +
  °C-Zusatzspalten (Modell-Einheit). *Verworfen:* alles auf °F bzw. nur eine Einheit ohne Original.
- ✅ **Zusatz:** DuckDB `data/processed/silver.duckdb` + Parquet partitioniert nach `city`;
  Idempotenz = deterministischer Full-Rebuild; Overround: raw + norm + Flag (>0,10 Ausreißer).

## Offene To-dos (über dieses AP hinaus)

- 📌 **AP 1.2:** Resolution-Fetcher in Ingestion (siehe D4) — einzige Ingestion-Änderung.
- 📌 **AP 1.2:** Transform gemäß Übergabe-Absatz im Schema-Doc (Dedup → Parsing → Ground-Truth-Join
  → QS-Flags → DuckDB/Parquet).
- 📌 **AP 1.3:** Backfill-Bestand (`data/backfill/`, 423 Zieltage) über `source='backfill'` einspielen;
  Forecast-Backfill für Lücke 17.–19.06. prüfen (Open-Meteo Historical-Forecast-API).
- 🔍 Beobachten: Doppel-Trigger (28–35 Abrufe/Tag) ist für Silver egal (D2 nimmt 1 Snapshot),
  könnte aber in AP 2.x (Volume-Checks) als „erwartete Spanne" statt Fixwert modelliert werden.

## Phase-C-Abschluss

- `docs/cleaned_schema_AP1.1.md` finalisiert (Status ✅, Lineage-Tabelle, Übergabe „Bereit für AP 1.2").
- Dieses Log abgeschlossen. AP-1.1-Meilenstein („dokumentiertes Cleaned-Schema") erreicht,
  vorbehaltlich Abnahme an STOPP 3.
