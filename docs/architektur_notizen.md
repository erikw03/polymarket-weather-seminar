# Architektur-Notizen (AP 1.4) — Material für die Seminararbeit

> Zweck: beim Schreiben (Wochen 4–5) nicht suchen müssen. Jede Behauptung hier ist im
> Repo belegt (Skript/Doc in Klammern). Struktur folgt dem Kapitel-Mapping des Projektplans.
> Stand: Woche-1-Abschluss, 2026-07-13.

## 0. Systemsteckbrief (Zahlen zum Zitieren)

- **Quellen (3):** Open-Meteo (Forecast + ERA5-Archiv, keyless, CC BY 4.0) · Polymarket
  Gamma/CLOB (öffentliche Read-only-APIs) · Polymarket-Resolutions (eigener Fetcher, AP 1.2).
- **Ingestion:** stündlich, cloud-basiert (GitHub Actions), **zwei redundante Trigger**
  (GitHub `schedule` + externer Cron via `workflow_dispatch`-API) → 28–35 Abrufe/Stadt/Tag.
- **Raw (Bronze):** tagesrotierende NDJSON, append-only/WORM, ~350 MB Markt + ~4 MB Wetter
  für 24 Sammeltage; Git-Repo = versioniertes, reproduzierbares Datenarchiv.
- **Cleaned (Silver):** DuckDB + Parquet (Partition: city), **5 457 Zeilen, 505 City-Days
  (01.03.–13.07.2026)**, 4 Städte, Grain = Stadt × Zieltag × Temperatur-Bucket.
- **Deterministischer Full-Rebuild** aus Raw in ~2 s; QS-Checks im Transform (PK-Eindeutigkeit,
  Label-Eindeutigkeit, Leakage-Audit, Normierungsfehler ≤ 3e-16).

## 1. CRISP-DM / MLOps (K1)

- Business Understanding = Forschungsfrage: Wie gut trackt die markt-implizite Verteilung
  (11 Buckets je Stadt-Tag) Forecast und Ist? Metriken: Brier/Log Loss/Accuracy (AP 3).
- Data Understanding = **AP 1.1 Phase A als eigenständiges Artefakt**
  (`docs/raw_inspection_report_AP1.1.md`): 4 read-only Inspektionsskripte, Vorbefund-
  Falsifikation (Archive-Stabilität ❌, Roll-off ⚠️), Leakage-Beleg. → CRISP-DM-Iteration
  konkret zeigbar: Data Understanding erzwang Schema-Änderungen (D2-Cut) und später die
  D3-Revision (Label-Quelle) — zwei dokumentierte Rückkopplungsschleifen.
- Deployment/Operations: Pipeline lief ab Tag 1 produktiv weiter, während Silver entworfen
  wurde (Parallelität von Betrieb und Entwicklung = MLOps-Kernidee).

## 2. Die 4 V's (K1) — am Projekt konkret

- **Volume:** bewusst klein (~400 MB Raw, <10⁴ Silver-Zeilen) → rechtfertigt Architektur-
  Vereinfachungen (kein Spark/Kafka, s. §6), aber Struktur skaliert (NDJSON-Partitionen,
  Parquet, Städte als Config-Liste).
- **Velocity:** stündliche Snapshots; Märkte täglich rollierend; Resolution-Latenz 1–2 Tage
  (gemessen; Freshness-Check-Kandidat AP 2).
- **Variety:** 2 externe API-Familien, 3 Record-Typen Wetter, JSON-in-JSON-Felder
  (`outcomePrices` doppelt dekodieren), gemischte Einheiten (°C / **NYC °F, 2-Grad-Bänder**),
  String-kodierte Zahlen → alles im Silver-Schema normalisiert (nativ + °C geführt).
- **Veracity:** der Kern des Projekts — Quellen-Mismatch Open-Meteo↔Wunderground
  (**23 % exakte Bucket-Übereinstimmung; München-Bias +2 °C**), ERA5-Revisionen (32/112
  Zieltage ändern sich zwischen Abrufen), Overround ~1,023 mit 1,8 % Platzhalter-Ausreißern
  frischer Listings, Post-12Z-Leakage (Preis 0,40→1,00 am Zieltag). Jede dieser Aussagen
  ist mit eigenen Daten quantifiziert (`DECISIONS_AP1.2/1.3.md`).

## 3. Medallion, Rohformat, Parquet (K3+K4)

- **Bronze = WORM:** append-only NDJSON, nie mutiert; Fehlentscheidungen downstream sind
  folgenlos (Beleg: D3-Revision und Backfill erforderten NUR Transform-Neulauf, kein Re-Fetch).
- **Silver = destilliert:** 70 213 Bucket-Snapshots → 5 457 leakage-freie Zeilen; jede Spalte
  mit dokumentierter Lineage (Tabelle in `cleaned_schema_AP1.1.md`: Spalte → Raw-Feld → Regel).
- **Format-Begründung:** NDJSON für append-only Ingestion (zeilenweise, git-diff-freundlich);
  DuckDB für Query-Komfort; Parquet als spaltenorientiertes Austauschformat, Partition nach
  `city` (bewusst flach — Datums-Partitionierung wäre bei dieser Größe Over-Engineering;
  Skalierungspfad im Text erwähnen).
- **Gold (AP 3):** Feature-Tabelle aus Silver; Architektur dafür vorbereitet (Grain trägt
  Bucket-Ebene, `source`-Spalte als Kontrollvariable).

## 4. Observability — 5 Säulen (K8), Ist-Stand & AP-2-Plan

| Säule | schon vorhanden (Woche 1) | AP 2 baut aus |
|---|---|---|
| Freshness | Actions-Historie; Resolution-Latenz bekannt (1–2 d) | Check „Zeit seit letztem Snapshot/Label" |
| Volume | erwartete Spanne 28–35 Abrufe/Tag gemessen | Schwellwert-Check gegen Spanne (nicht Fixwert!) |
| Schema | Feldinventar-Skript (`02_schema_inventory.py`); `_meta`-Varianten bekannt (11 Alt-Records) | Drift-Check auf neue/fehlende Felder |
| Nulls/Verteilung | QS-Flags im Transform (Overround, Teiltage) | Null-Raten + Ausreißer-Report |
| Lineage | Lineage-Tabelle je Spalte; `transform_version` (Git-Hash) + `created_at` je Zeile | — (dokumentieren) |

- **Gelebtes Beispiel für Lineage-Wert:** München-Koordinatenwechsel (Stadtzentrum→Flughafen,
  20.06.) erzeugte 1,5 °C-Sprung im Archiv → nur auffindbar, weil `_meta` Koordinaten je
  Record speichert; Fix = „jüngster Abruf + nur Stations-Records" (D3).

## 5. Fehlertoleranz & Prepare-Detect-Resolve-Prevent (K8+K10)

- **Prepare:** Retry/Backoff (tenacity, nur transiente Fehler), Quellen-Isolation (Ausfall
  einer Quelle crasht die andere nie — try/except je Quelle in `run_ingestion.py`),
  Doppel-Trigger als Redundanz, append-only (kein korrumpierbarer Zustand), Idempotenz
  überall (Fetcher: Bestandscheck; Transform: Full-Rebuild).
- **Detect:** QS-Checks brechen den Transform hart ab (Beleg: München 30.03. wurde vom
  Check gefangen, nicht von mir) — plus AP-2-Checks (oben).
- **Resolve:** Backfill-Pfade existieren und wurden real genutzt: Forecast-Lücke 17.–19.06.
  via Previous-Runs-API geschlossen; Resolutions rückwirkend ab 16.06. nachgefangen;
  GitHub-Scheduler-Ausfall (21.06.) durch externen Trigger gelöst.
- **Prevent:** Erkenntnisse wurden zu Regeln: Leakage → D2-Cut vor lokalem Tagesbeginn;
  Platzhalter-Preise → Overround-Flag; Scheduler-Unzuverlässigkeit → Redundanz + Off-Peak-Cron
  (`17 * * * *` statt `:00`); Alt-Meta-Records → `station`-Pflichtkriterium im Label-Join.
- **Ehrliche Grenzen** (in der Arbeit ausweisen): Cloud-Scheduler „best effort" (Minuten-Jitter);
  Backfill ohne Volumen/CLOB und mit approximiertem Overround (U5/AP 1.3); Forecast-Lead-
  Restdifferenz Live vs. Backfill ~0,3–0,6 °C MAE (U1/AP 1.3); NYC 18.06. dünn gehandelt
  → ausgeschlossen (1 von 505 Tagen fehlt deswegen... genauer: 7/423 Backfill-Tage per U3-Regel).

## 6. Nur-konzeptionell-Kapitel (mit Begründung der Vereinfachung)

- **Kafka/CDC (K3):** Stündliches Batch-Polling genügt, weil Märkte träge sind und täglich
  resolven; Event-Streaming brächte Sub-Minuten-Latenz, die die Forschungsfrage nicht braucht.
  Konzeptioneller Anschluss: jede NDJSON-Zeile IST ein Event → Kafka-Topic-Analogie sauber erklärbar.
- **Hadoop/Spark (K4):** 400 MB / 5,5 k Zeilen — Single-Node DuckDB verarbeitet das in Sekunden;
  verteiltes Rechnen ab ~ >RAM-Datenmengen bzw. vielen hundert Städten argumentieren.
- **Cloud/S3+Lambda (K6):** GitHub Actions + Git-Repo übernimmt die Rollen (Scheduler=EventBridge,
  Runner=Lambda, Repo=S3+Versionierung) zum Preis von 0 € — Mapping-Tabelle in der Arbeit möglich.

## 7. Roter Faden fürs Ergebnis-Kapitel (AP 3 vorbereitet)

- Baselines stehen konzeptionell fest: (1) Markt-Preis als Prädiktor (`yes_price_norm`),
  (2) naive Forecast-Regel (Bucket, in den `forecast_max_native` fällt). Beide direkt aus
  Silver ableitbar — keine weitere Datenarbeit nötig.
- Zeitreihen-Validierung: `target_date`-sortierte Splits; `source` (live/backfill) als
  Kontrollvariable; `flag_*`-Spalten als Ausschluss-Sensitivität.
- Erwartbare Story: Markt vs. Forecast sind nahe beieinander (Juni-Prototyp zeigte
  MAE-Größenordnung 0,4–1,3 °C fürs Markt-Modus vs. Ist); der interessante Teil ist
  Kalibrierung der Verteilung, nicht Punktprognose.

## Woche-1-Abschluss (Status)

**Meilenstein „Cleaned-Pipeline steht" erreicht (13.07.):** 3 Quellen laufen autonom;
Schema dokumentiert & freigegeben (D1–D6 + D3-Revision); Transform idempotent mit QS;
Backfill integriert (505 City-Days). Übergabe an Woche 2 (Observability): offene Punkte
in `DECISIONS_AP1.3.md` §Offene Punkte (Freshness-/Volume-Checks, Null-Raten, Drift).
